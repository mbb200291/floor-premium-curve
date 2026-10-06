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
)


def write_summary(path: Path, diagnostics: dict[str, int | float]) -> None:
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
    parser.add_argument("--observations", type=Path, default=Path("data/processed/observations.csv"))
    parser.add_argument("--plot", type=Path, default=Path("results/curve.svg"))
    parser.add_argument("--summary", type=Path, default=Path("results/analysis_summary.md"))
    args = parser.parse_args()

    if args.input_file:
        frame = read_real_price_csv(args.input_file)
    else:
        frame = load_source_dir(args.input_dir, kind=args.kind)

    strict, prep_diag = prepare_transactions(frame, floor_height_m=args.floor_height_m)
    comparable, curve, curve_diag = build_curve(strict)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.observations.parent.mkdir(parents=True, exist_ok=True)
    curve.to_csv(args.output, index=False)
    comparable.to_csv(args.observations, index=False)
    plot_curve(curve, args.plot)

    diagnostics = {
        **prep_diag,
        **curve_diag,
        "floor_height_m": args.floor_height_m,
        "plotted_floor_buckets": int(curve["included_in_plot"].sum()),
    }
    write_summary(args.summary, diagnostics)
    print(pd.Series(diagnostics).to_string())


if __name__ == "__main__":
    main()
