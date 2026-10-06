from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from floor_premium.core import (
    build_curve,
    load_source_dir,
    plot_curve,
    prepare_transactions,
    read_real_price_csv,
    summarize_special_floors,
)
from floor_premium.model import fit_within_stack_height_model, plot_model_curve


def write_summary(path: Path, diagnostics: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# Analysis summary", ""]
    for key, value in diagnostics.items():
        lines.append(f"- {key}: {value}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--input-dir", type=Path)
    source.add_argument("--input-file", type=Path)
    parser.add_argument("--kind", choices=["presale", "sale"], default="presale")
    parser.add_argument("--floor-height-m", type=float, default=3.2)
    parser.add_argument("--output", type=Path, default=Path("data/processed/curve.csv"))
    parser.add_argument(
        "--observations",
        type=Path,
        default=Path("data/processed/observations.csv"),
    )
    parser.add_argument(
        "--special-floors",
        type=Path,
        default=Path("data/processed/special_floors.csv"),
    )
    parser.add_argument(
        "--model-effects",
        type=Path,
        default=Path("data/processed/model_special_effects.csv"),
    )
    parser.add_argument(
        "--model-curve",
        type=Path,
        default=Path("data/processed/model_curve.csv"),
    )
    parser.add_argument("--plot", type=Path, default=Path("results/curve.svg"))
    parser.add_argument(
        "--model-plot",
        type=Path,
        default=Path("results/model_curve.svg"),
    )
    parser.add_argument(
        "--summary",
        type=Path,
        default=Path("results/analysis_summary.md"),
    )
    parser.add_argument(
        "--model-knots-m",
        type=float,
        nargs="*",
        default=[12.8, 25.6, 38.4],
    )
    parser.add_argument("--model-reference-height-m", type=float, default=12.8)
    parser.add_argument("--model-special-min-n", type=int, default=10)
    args = parser.parse_args()

    if args.input_file:
        frame = read_real_price_csv(args.input_file)
    else:
        frame = load_source_dir(args.input_dir, kind=args.kind)

    strict, prep_diag = prepare_transactions(frame, floor_height_m=args.floor_height_m)
    comparable, curve, curve_diag = build_curve(strict)
    special = summarize_special_floors(comparable)
    model_effects, model_curve, model_diag = fit_within_stack_height_model(
        comparable,
        knots_m=tuple(args.model_knots_m),
        reference_height_m=args.model_reference_height_m,
        floor_height_m=args.floor_height_m,
        min_special_n=args.model_special_min_n,
    )

    for path in (
        args.output,
        args.observations,
        args.special_floors,
        args.model_effects,
        args.model_curve,
    ):
        path.parent.mkdir(parents=True, exist_ok=True)

    curve.to_csv(args.output, index=False)
    comparable.to_csv(args.observations, index=False)
    special.to_csv(args.special_floors, index=False)
    model_effects.to_csv(args.model_effects, index=False)
    model_curve.to_csv(args.model_curve, index=False)
    plot_curve(curve, comparable, args.plot)
    plot_model_curve(model_curve, args.model_plot)

    diagnostics: dict[str, object] = {
        **prep_diag,
        **curve_diag,
        **model_diag,
        "floor_height_m": args.floor_height_m,
        "plotted_regular_floor_buckets": int(curve["included_in_plot"].sum()),
    }
    write_summary(args.summary, diagnostics)
    print(pd.Series(diagnostics).to_string())


if __name__ == "__main__":
    main()
