import math

import pandas as pd

from floor_premium.core import (
    build_curve,
    infer_stack_key,
    parse_floor,
    prepare_transactions,
    summarize_special_floors,
)


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
