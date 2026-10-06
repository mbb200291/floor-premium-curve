from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

COLUMN_ALIASES = {
    "單價每平方公尺": "單價元平方公尺",
    "車位移轉總面積(平方公尺)": "車位移轉總面積平方公尺",
}

SPECIAL_TRANSACTION_PATTERN = r"親友|員工|共有人|特殊關係|毛胚屋"
RESIDENTIAL_TYPE_PATTERN = r"住宅大樓|華廈|套房"

ZH_DIGITS = {
    "零": 0,
    "〇": 0,
    "一": 1,
    "二": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
}


def parse_floor(value: object) -> float:
    """Parse an MOI floor label such as 二十四層 or 24.

    Multi-floor transfers, basements, whole-building transfers and other
    non-single-floor labels return NaN because they are not comparable here.
    """
    if value is None or pd.isna(value):
        return np.nan

    text = str(value).strip()
    if not text:
        return np.nan

    if any(token in text for token in ("地下", "夾層", "屋頂", "騎樓", "全")):
        return np.nan
    if any(token in text for token in (",", "，", "-", "~", "至")):
        return np.nan

    text = text.replace("層", "").replace("樓", "").strip()
    if re.fullmatch(r"\d+", text):
        return float(int(text))
    if not re.fullmatch(r"[零〇一二三四五六七八九十百]+", text):
        return np.nan

    total = 0
    current = 0
    for char in text:
        if char in ZH_DIGITS:
            current = ZH_DIGITS[char]
        elif char == "十":
            total += (current or 1) * 10
            current = 0
        elif char == "百":
            total += (current or 1) * 100
            current = 0
    return float(total + current)


def infer_stack_key(project: object, unit: object, floor: int) -> str | None:
    """Infer a vertical unit stack only when the unit field explicitly encodes floor."""
    if project is None or unit is None or pd.isna(project) or pd.isna(unit):
        return None

    project_s = str(project).strip()
    unit_s = str(unit).strip()
    if not project_s or project_s == "NA" or not unit_s or unit_s == "NA":
        return None

    original = re.sub(r"號$", "", unit_s)
    cleaned = original
    floor2 = f"{floor:02d}"
    patterns = (
        rf"[-_]?0?{floor}F$",
        rf"[-_]?{floor2}F$",
        rf"[-_]?0?{floor}樓$",
        rf"[-_]?0?{floor}層$",
    )
    for pattern in patterns:
        cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"[-_]+$", "", cleaned)

    if cleaned == original or not cleaned:
        return None
    return f"{project_s}::{cleaned}"


def read_real_price_csv(path: str | Path) -> pd.DataFrame:
    path = Path(path)
    last_error: Exception | None = None
    for encoding in ("utf-8-sig", "utf-8", "big5"):
        try:
            frame = pd.read_csv(path, dtype=str, encoding=encoding, keep_default_na=False)
            frame["_source_file"] = path.name
            return normalize_columns(frame)
        except UnicodeDecodeError as exc:
            last_error = exc
    raise ValueError(f"Unable to decode {path}") from last_error


def normalize_columns(frame: pd.DataFrame) -> pd.DataFrame:
    frame = frame.copy()
    for old, new in COLUMN_ALIASES.items():
        if old in frame.columns and new not in frame.columns:
            frame = frame.rename(columns={old: new})
    return frame


def find_source_files(root: str | Path, kind: str = "presale") -> list[Path]:
    root = Path(root)
    suffix = "_lvr_land_b.csv" if kind == "presale" else "_lvr_land_a.csv"
    files = [
        path for path in root.rglob("*.csv")
        if path.name.lower().endswith(suffix)
    ]
    return sorted(files)


def load_source_dir(root: str | Path, kind: str = "presale") -> pd.DataFrame:
    files = find_source_files(root, kind=kind)
    if not files:
        raise FileNotFoundError(f"No {kind} real-price CSV files found under {root}")
    return pd.concat((read_real_price_csv(path) for path in files), ignore_index=True)


def prepare_transactions(
    frame: pd.DataFrame,
    floor_height_m: float = 3.2,
) -> tuple[pd.DataFrame, dict[str, int]]:
    df = normalize_columns(frame)

    required = [
        "移轉層次",
        "總樓層數",
        "建物型態",
        "主要用途",
        "單價元平方公尺",
        "備註",
        "建案名稱",
        "棟及號",
    ]
    missing = [column for column in required if column not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    source_rows = len(df)
    df = df.copy()
    df["floor"] = df["移轉層次"].map(parse_floor)
    df["total_floor"] = df["總樓層數"].map(parse_floor)
    df["unit_price_ntd_m2"] = pd.to_numeric(df["單價元平方公尺"], errors="coerce")

    type_mask = df["建物型態"].astype(str).str.contains(
        RESIDENTIAL_TYPE_PATTERN, regex=True, na=False
    )
    use_text = df["主要用途"].astype(str)
    use_mask = use_text.str.contains("住", na=False) | use_text.isin(["", "NA"])
    special_mask = df["備註"].astype(str).str.contains(
        SPECIAL_TRANSACTION_PATTERN, regex=True, na=False
    )
    numeric_mask = (
        df["floor"].notna()
        & df["total_floor"].notna()
        & df["unit_price_ntd_m2"].notna()
        & (df["unit_price_ntd_m2"] > 0)
    )

    eligible = df[type_mask & use_mask & ~special_mask & numeric_mask].copy()
    eligible["floor"] = eligible["floor"].astype(int)
    eligible["total_floor"] = eligible["total_floor"].astype(int)
    eligible = eligible[
        (eligible["floor"] > 0) & (eligible["floor"] <= eligible["total_floor"])
    ]

    eligible["stack_key"] = [
        infer_stack_key(project, unit, floor)
        for project, unit, floor in zip(
            eligible["建案名稱"], eligible["棟及號"], eligible["floor"]
        )
    ]
    strict = eligible[eligible["stack_key"].notna()].copy()
    strict["height_agl_m"] = (strict["floor"] - 1) * floor_height_m
    strict["floor_ratio"] = strict["floor"] / strict["total_floor"]
    strict["is_first_floor"] = strict["floor"].eq(1)
    strict["is_top_floor"] = strict["floor"].eq(strict["total_floor"])
    strict["is_special_floor"] = strict["is_first_floor"] | strict["is_top_floor"]

    diagnostics = {
        "source_rows": int(source_rows),
        "eligible_residential_rows": int(len(eligible)),
        "strict_stack_rows": int(len(strict)),
    }
    return strict, diagnostics


def build_curve(
    strict: pd.DataFrame,
    min_group_transactions: int = 3,
    min_group_floors: int = 3,
    min_floor_observations: int = 3,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, int]]:
    """Build the ordinary height curve while keeping special floors separate.

    First-floor and top-floor units remain in comparable observations, but they
    are excluded from the main height curve. This prevents first-floor amenities
    and top-floor attributes from being forced into the continuous height effect.
    """
    stats = strict.groupby("stack_key").agg(
        transactions=("floor", "size"),
        distinct_floors=("floor", "nunique"),
    )
    keep_keys = stats[
        (stats["transactions"] >= min_group_transactions)
        & (stats["distinct_floors"] >= min_group_floors)
    ].index

    comparable = strict[strict["stack_key"].isin(keep_keys)].copy()
    comparable["group_median_unit_price_ntd_m2"] = comparable.groupby("stack_key")[
        "unit_price_ntd_m2"
    ].transform("median")
    comparable["premium_pct"] = (
        comparable["unit_price_ntd_m2"]
        / comparable["group_median_unit_price_ntd_m2"]
        - 1
    ) * 100

    regular = comparable[~comparable["is_special_floor"]].copy()
    curve = (
        regular.groupby("floor", as_index=False)
        .agg(
            height_agl_m=("height_agl_m", "first"),
            n=("premium_pct", "size"),
            median_premium_pct=("premium_pct", "median"),
            mean_premium_pct=("premium_pct", "mean"),
            q25_premium_pct=("premium_pct", lambda s: s.quantile(0.25)),
            q75_premium_pct=("premium_pct", lambda s: s.quantile(0.75)),
        )
        .sort_values("floor")
    )
    curve["included_in_plot"] = curve["n"] >= min_floor_observations

    diagnostics = {
        "comparable_stacks": int(len(keep_keys)),
        "comparable_observations": int(len(comparable)),
        "regular_floor_observations": int(len(regular)),
        "first_floor_observations": int(comparable["is_first_floor"].sum()),
        "top_floor_observations": int(
            (comparable["is_top_floor"] & ~comparable["is_first_floor"]).sum()
        ),
    }
    return comparable, curve, diagnostics


def summarize_special_floors(comparable: pd.DataFrame) -> pd.DataFrame:
    """Summarize special floors without pretending the values are height-adjusted."""
    masks = {
        "first_floor": comparable["is_first_floor"],
        "top_floor": comparable["is_top_floor"] & ~comparable["is_first_floor"],
    }

    rows: list[dict[str, object]] = []
    for category, mask in masks.items():
        subset = comparable[mask]
        if subset.empty:
            rows.append(
                {
                    "category": category,
                    "n": 0,
                    "median_height_agl_m": np.nan,
                    "median_premium_pct": np.nan,
                    "mean_premium_pct": np.nan,
                    "q25_premium_pct": np.nan,
                    "q75_premium_pct": np.nan,
                    "adjusted_for_height": False,
                }
            )
            continue

        rows.append(
            {
                "category": category,
                "n": int(len(subset)),
                "median_height_agl_m": float(subset["height_agl_m"].median()),
                "median_premium_pct": float(subset["premium_pct"].median()),
                "mean_premium_pct": float(subset["premium_pct"].mean()),
                "q25_premium_pct": float(subset["premium_pct"].quantile(0.25)),
                "q75_premium_pct": float(subset["premium_pct"].quantile(0.75)),
                "adjusted_for_height": False,
            }
        )
    return pd.DataFrame(rows)


def plot_curve(
    curve: pd.DataFrame,
    comparable: pd.DataFrame,
    output_path: str | Path,
) -> None:
    import matplotlib.pyplot as plt

    plot = curve[curve["included_in_plot"]].copy()
    if plot.empty:
        raise ValueError("No regular floor bucket has enough observations to plot.")

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    fig, ax = plt.subplots(figsize=(10, 5.5))
    x = plot["height_agl_m"].to_numpy(dtype=float)
    y = plot["median_premium_pct"].to_numpy(dtype=float)
    q25 = plot["q25_premium_pct"].to_numpy(dtype=float)
    q75 = plot["q75_premium_pct"].to_numpy(dtype=float)

    ax.fill_between(x, q25, q75, alpha=0.2, label="Regular-floor IQR")
    ax.plot(x, y, marker="o", label="Regular-floor median")

    first = comparable[comparable["is_first_floor"]]
    if not first.empty:
        ax.scatter(
            first["height_agl_m"],
            first["premium_pct"],
            marker="D",
            label="First floor",
            zorder=3,
        )

    top = comparable[comparable["is_top_floor"] & ~comparable["is_first_floor"]]
    if not top.empty:
        ax.scatter(
            top["height_agl_m"],
            top["premium_pct"],
            marker="o",
            facecolors="none",
            label="Top floor",
            zorder=3,
        )

    ax.axhline(0, linewidth=1, linestyle="--")
    ax.set_xlabel("Estimated AGL (m)")
    ax.set_ylabel("Within-stack price premium (%)")
    ax.set_title("Height premium curve with special floors separated")
    ax.grid(axis="y", alpha=0.2)
    ax.legend()
    fig.tight_layout()
    fig.savefig(output_path)
    plt.close(fig)


def source_frame(paths: Iterable[str | Path]) -> pd.DataFrame:
    return pd.concat((read_real_price_csv(path) for path in paths), ignore_index=True)
