from __future__ import annotations

from pathlib import Path
from typing import Sequence

import numpy as np
import pandas as pd


def _basis_matrix(
    height_m: np.ndarray,
    first_floor: np.ndarray,
    top_floor: np.ndarray,
    knots_m: Sequence[float],
) -> np.ndarray:
    columns = [height_m.astype(float)]
    for knot in knots_m:
        columns.append(np.maximum(0.0, height_m - float(knot)))
    columns.append(first_floor.astype(float))
    columns.append(top_floor.astype(float))
    return np.column_stack(columns)


def _basis_vector(
    height_m: float,
    knots_m: Sequence[float],
    first_floor: bool = False,
    top_floor: bool = False,
) -> np.ndarray:
    values = [float(height_m)]
    values.extend(max(0.0, float(height_m) - float(knot)) for knot in knots_m)
    values.extend([float(first_floor), float(top_floor)])
    return np.asarray(values, dtype=float)


def _select_identifiable_columns(
    x_within: np.ndarray,
    column_names: Sequence[str],
    *,
    special_indices: Sequence[int],
    tolerance: float = 1e-10,
) -> tuple[list[int], list[int]]:
    """Keep a full-rank subset while prioritizing special-floor terms.

    Official releases can legitimately contain no comparable 1F transactions or
    insufficient support for one spline hinge. Those cases should not make the
    whole analysis fail.
    """
    nonzero = [
        index
        for index in range(x_within.shape[1])
        if float(np.linalg.norm(x_within[:, index])) > tolerance
    ]

    # Height first, then the policy-relevant first/top-floor dummies, then the
    # increasingly flexible spline hinges.
    hinge_indices = [
        index
        for index in range(1, x_within.shape[1])
        if index not in special_indices
    ]
    priority = [0, *special_indices, *hinge_indices]

    selected: list[int] = []
    current_rank = 0
    for index in priority:
        if index not in nonzero or index in selected:
            continue
        trial = x_within[:, [*selected, index]]
        trial_rank = int(np.linalg.matrix_rank(trial))
        if trial_rank > current_rank:
            selected.append(index)
            current_rank = trial_rank

    dropped = [index for index in range(x_within.shape[1]) if index not in selected]
    return selected, dropped


def fit_within_stack_height_model(
    comparable: pd.DataFrame,
    *,
    knots_m: Sequence[float] = (12.8, 25.6, 38.4),
    reference_height_m: float = 12.8,
    floor_height_m: float = 3.2,
    min_special_n: int = 10,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, object]]:
    """Estimate height and special-floor effects with stack fixed effects.

    Model:
        log(unit_price) = stack_FE + linear_spline(height)
                          + first_floor + top_floor + error

    Stack fixed effects are removed by within-stack demeaning. Standard errors
    use a cluster-robust sandwich estimator clustered by stack_key.

    If a requested term is not identified in a specific release (for example,
    there are no comparable first-floor transactions), it is dropped from the
    fitted design and reported as no_observations or unidentified instead of
    aborting the analysis.
    """
    required = {
        "stack_key",
        "unit_price_ntd_m2",
        "height_agl_m",
        "floor",
        "total_floor",
        "is_first_floor",
        "is_top_floor",
        "is_special_floor",
    }
    missing = sorted(required - set(comparable.columns))
    if missing:
        raise ValueError(f"Missing model columns: {missing}")
    if comparable.empty:
        raise ValueError("No comparable observations available for modeling.")

    knots_m = tuple(float(knot) for knot in knots_m)
    df = comparable.copy()
    df = df[df["unit_price_ntd_m2"].astype(float) > 0].copy()
    if df.empty:
        raise ValueError("No positive unit prices available for modeling.")

    height = df["height_agl_m"].to_numpy(dtype=float)
    first = df["is_first_floor"].to_numpy(dtype=bool)
    top = (
        df["is_top_floor"].to_numpy(dtype=bool)
        & ~df["is_first_floor"].to_numpy(dtype=bool)
    )
    y = np.log(df["unit_price_ntd_m2"].to_numpy(dtype=float))
    x_full = _basis_matrix(height, first, top, knots_m)

    column_names = [
        "height",
        *(f"hinge_{k:g}m" for k in knots_m),
        "first_floor",
        "top_floor",
    ]
    first_index = 1 + len(knots_m)
    top_index = first_index + 1

    keys = df["stack_key"].astype(str).to_numpy()
    x_within_full = x_full.copy()
    y_within = y.copy()
    unique_keys = pd.unique(keys)
    for key in unique_keys:
        mask = keys == key
        x_within_full[mask] -= x_full[mask].mean(axis=0)
        y_within[mask] -= y[mask].mean()

    selected, dropped = _select_identifiable_columns(
        x_within_full,
        column_names,
        special_indices=(first_index, top_index),
    )
    if not selected:
        raise ValueError("No identifiable model columns remain after demeaning.")

    x_within = x_within_full[:, selected]
    n, p = x_within.shape
    rank = int(np.linalg.matrix_rank(x_within))
    if rank < p:
        raise ValueError(
            f"Reduced model remains rank deficient: rank={rank}, parameters={p}."
        )
    if len(unique_keys) <= 1 or n <= p:
        raise ValueError("Not enough observations/clusters for the fixed-effect model.")

    beta, *_ = np.linalg.lstsq(x_within, y_within, rcond=None)
    fitted = x_within @ beta
    residual = y_within - fitted

    xtx_inv = np.linalg.pinv(x_within.T @ x_within)
    meat = np.zeros((p, p), dtype=float)
    for key in unique_keys:
        mask = keys == key
        score = x_within[mask].T @ residual[mask]
        meat += np.outer(score, score)

    clusters = len(unique_keys)
    correction = (clusters / (clusters - 1)) * ((n - 1) / (n - p))
    covariance = correction * (xtx_inv @ meat @ xtx_inv)
    standard_error = np.sqrt(np.clip(np.diag(covariance), 0.0, None))

    selected_position = {full_index: pos for pos, full_index in enumerate(selected)}
    effect_specs = (
        ("first_floor", first_index, int(first.sum())),
        ("top_floor", top_index, int(top.sum())),
    )
    effect_rows: list[dict[str, object]] = []
    for name, full_index, sample_n in effect_specs:
        if sample_n == 0:
            status = "no_observations"
        elif full_index not in selected_position:
            status = "unidentified"
        elif sample_n < min_special_n:
            status = "insufficient_sample"
        else:
            status = "ok"

        if full_index in selected_position:
            index = selected_position[full_index]
            estimate = float(beta[index])
            se = float(standard_error[index])
            estimate_pct = (np.exp(estimate) - 1.0) * 100.0
            ci_low_pct = (np.exp(estimate - 1.96 * se) - 1.0) * 100.0
            ci_high_pct = (np.exp(estimate + 1.96 * se) - 1.0) * 100.0
        else:
            estimate = np.nan
            se = np.nan
            estimate_pct = np.nan
            ci_low_pct = np.nan
            ci_high_pct = np.nan

        effect_rows.append(
            {
                "effect": name,
                "n": sample_n,
                "beta_log": estimate,
                "se_log": se,
                "estimate_pct": estimate_pct,
                "ci_low_pct": ci_low_pct,
                "ci_high_pct": ci_high_pct,
                "reportable": status == "ok",
                "status": status,
            }
        )
    effects = pd.DataFrame(effect_rows)

    regular = df[~df["is_special_floor"].astype(bool)]
    if regular.empty:
        raise ValueError("No regular floors available for model curve.")

    min_floor = int(regular["floor"].min())
    max_floor = int(regular["floor"].max())
    min_height = float(regular["height_agl_m"].min())
    max_height = float(regular["height_agl_m"].max())
    if not min_height <= reference_height_m <= max_height:
        reference_height_m = float(regular["height_agl_m"].median())

    reference_basis = _basis_vector(reference_height_m, knots_m)[selected]
    curve_rows: list[dict[str, float | int]] = []
    for floor in range(min_floor, max_floor + 1):
        height_value = (floor - 1) * floor_height_m
        current_basis = _basis_vector(height_value, knots_m)[selected]
        delta = current_basis - reference_basis
        estimate_log = float(delta @ beta)
        variance = float(delta @ covariance @ delta)
        se_log = float(np.sqrt(max(0.0, variance)))
        curve_rows.append(
            {
                "floor": floor,
                "height_agl_m": height_value,
                "relative_premium_pct": (np.exp(estimate_log) - 1.0) * 100.0,
                "ci_low_pct": (
                    np.exp(estimate_log - 1.96 * se_log) - 1.0
                ) * 100.0,
                "ci_high_pct": (
                    np.exp(estimate_log + 1.96 * se_log) - 1.0
                ) * 100.0,
                "reference_height_m": reference_height_m,
            }
        )
    curve = pd.DataFrame(curve_rows)

    sst = float(np.square(y_within).sum())
    sse = float(np.square(residual).sum())
    diagnostics: dict[str, object] = {
        "model": "within_stack_linear_spline",
        "model_observations": int(n),
        "model_clusters": int(clusters),
        "model_candidate_parameters": int(x_within_full.shape[1]),
        "model_parameters": int(p),
        "model_rank": rank,
        "model_columns": ",".join(column_names[index] for index in selected),
        "model_dropped_columns": ",".join(column_names[index] for index in dropped),
        "model_knots_m": ",".join(str(float(k)) for k in knots_m),
        "model_reference_height_m": float(reference_height_m),
        "model_within_r2": float(1.0 - sse / sst) if sst > 0 else np.nan,
        "model_special_min_n": int(min_special_n),
    }
    return effects, curve, diagnostics


def plot_model_curve(curve: pd.DataFrame, output_path: str | Path) -> None:
    import matplotlib.pyplot as plt

    if curve.empty:
        raise ValueError("No model curve to plot.")

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    x = curve["height_agl_m"].to_numpy(dtype=float)
    y = curve["relative_premium_pct"].to_numpy(dtype=float)
    low = curve["ci_low_pct"].to_numpy(dtype=float)
    high = curve["ci_high_pct"].to_numpy(dtype=float)

    fig, ax = plt.subplots(figsize=(10, 5.5))
    ax.fill_between(x, low, high, alpha=0.2, label="95% cluster-robust CI")
    ax.plot(x, y, marker="o", label="Adjusted height effect")
    ax.axhline(0, linewidth=1, linestyle="--")
    ax.set_xlabel("Estimated AGL (m)")
    ax.set_ylabel("Relative price premium (%)")
    ax.set_title("Within-stack adjusted height model")
    ax.grid(axis="y", alpha=0.2)
    ax.legend()
    fig.tight_layout()
    fig.savefig(output_path)
    plt.close(fig)
