import math

import numpy as np
import pandas as pd

from floor_premium.core import (
    build_curve,
    deduplicate_source_rows,
    infer_stack_key,
    parse_floor,
    prepare_transactions,
    summarize_special_floors,
)
from floor_premium.model import fit_within_stack_height_model


def test_parse_floor():
    assert parse_floor("二層") == 2
    assert parse_floor("十四層") == 14
    assert parse_floor("二十四層") == 24
    assert parse_floor("105") == 105
    assert math.isnan(parse_floor("地下二層"))
    assert math.isnan(parse_floor("1-3"))


def test_infer_stack_key():
    assert infer_stack_key("青耘上", "C-10F號", 10) == "青耘上::C"
    assert infer_stack_key("鉑金愛悅", "A07-06F號", 6) == "鉑金愛悅::A07"
    assert infer_stack_key("X", "A棟07號", 7) is None


def test_deduplicate_source_rows_keeps_latest_nonblank_serial():
    frame = pd.DataFrame(
        {
            "編號": ["A", "A", "", ""],
            "value": ["old", "new", "blank1", "blank2"],
        }
    )
    result = deduplicate_source_rows(frame)
    assert result["value"].tolist() == ["new", "blank1", "blank2"]


def test_curve_uses_same_stack_median():
    frame = pd.DataFrame(
        {
            "移轉層次": ["二層", "三層", "四層"],
            "總樓層數": ["10", "10", "10"],
            "建物型態": ["華廈(10層含以下有電梯)"] * 3,
            "主要用途": ["住家用"] * 3,
            "單價元平方公尺": ["90", "100", "110"],
            "備註": [""] * 3,
            "建案名稱": ["P"] * 3,
            "棟及號": ["A-2F號", "A-3F號", "A-4F號"],
        }
    )
    strict, prep = prepare_transactions(frame)
    comparable, curve, diag = build_curve(strict)

    assert prep["strict_stack_rows"] == 3
    assert diag["comparable_stacks"] == 1
    assert comparable["premium_pct"].round(6).tolist() == [-10.0, 0.0, 10.0]
    assert curve["floor"].tolist() == [2, 3, 4]


def test_special_floors_are_kept_but_excluded_from_main_curve():
    frame = pd.DataFrame(
        {
            "移轉層次": ["一層", "二層", "三層", "四層"],
            "總樓層數": ["4"] * 4,
            "建物型態": ["華廈(10層含以下有電梯)"] * 4,
            "主要用途": ["住家用"] * 4,
            "單價元平方公尺": ["105", "90", "100", "110"],
            "備註": [""] * 4,
            "建案名稱": ["P"] * 4,
            "棟及號": ["A-1F號", "A-2F號", "A-3F號", "A-4F號"],
        }
    )
    strict, _ = prepare_transactions(frame)
    comparable, curve, diag = build_curve(strict, min_floor_observations=1)
    special = summarize_special_floors(comparable).set_index("category")

    assert comparable["is_first_floor"].sum() == 1
    assert comparable["is_top_floor"].sum() == 1
    assert curve["floor"].tolist() == [2, 3]
    assert diag["regular_floor_observations"] == 2
    assert special.loc["first_floor", "n"] == 1
    assert special.loc["top_floor", "n"] == 1
    assert not bool(special.loc["top_floor", "adjusted_for_height"])


def test_within_stack_model_recovers_special_effects():
    rows = []
    for stack_index, total_floor in enumerate([6, 8, 10, 12, 14, 16]):
        stack_key = f"P::{stack_index}"
        stack_intercept = math.log(100_000 + stack_index * 10_000)
        for floor in [1, 2, 4, total_floor]:
            height = (floor - 1) * 3.2
            is_first = floor == 1
            is_top = floor == total_floor
            log_price = (
                stack_intercept
                + 0.01 * height
                + 0.08 * float(is_first)
                - 0.03 * float(is_top)
            )
            rows.append(
                {
                    "stack_key": stack_key,
                    "floor": floor,
                    "total_floor": total_floor,
                    "height_agl_m": height,
                    "is_first_floor": is_first,
                    "is_top_floor": is_top,
                    "is_special_floor": is_first or is_top,
                    "unit_price_ntd_m2": math.exp(log_price),
                }
            )

    comparable = pd.DataFrame(rows)
    effects, curve, diag = fit_within_stack_height_model(
        comparable,
        knots_m=(),
        reference_height_m=9.6,
        min_special_n=1,
    )
    indexed = effects.set_index("effect")

    assert np.isclose(
        indexed.loc["first_floor", "estimate_pct"],
        (math.exp(0.08) - 1) * 100,
    )
    assert np.isclose(
        indexed.loc["top_floor", "estimate_pct"],
        (math.exp(-0.03) - 1) * 100,
    )
    assert indexed["reportable"].all()
    assert diag["model_rank"] == 3
    assert not curve.empty


def test_model_drops_unidentified_first_floor_term():
    rows = []
    for stack_index, total_floor in enumerate([8, 10, 12, 14]):
        stack_key = f"P::{stack_index}"
        stack_intercept = math.log(100_000 + stack_index * 10_000)
        for floor in [2, 4, total_floor]:
            height = (floor - 1) * 3.2
            is_top = floor == total_floor
            log_price = stack_intercept + 0.01 * height - 0.02 * float(is_top)
            rows.append(
                {
                    "stack_key": stack_key,
                    "floor": floor,
                    "total_floor": total_floor,
                    "height_agl_m": height,
                    "is_first_floor": False,
                    "is_top_floor": is_top,
                    "is_special_floor": is_top,
                    "unit_price_ntd_m2": math.exp(log_price),
                }
            )

    effects, curve, diag = fit_within_stack_height_model(
        pd.DataFrame(rows),
        knots_m=(12.8, 25.6, 38.4),
        min_special_n=1,
    )
    indexed = effects.set_index("effect")

    assert indexed.loc["first_floor", "status"] == "no_observations"
    assert not bool(indexed.loc["first_floor", "reportable"])
    assert "first_floor" in diag["model_dropped_columns"]
    assert not curve.empty
