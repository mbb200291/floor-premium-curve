from __future__ import annotations

import csv
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
    """Parse an MOI floor label such as 二十四層 or 24."""
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


def _read_csv_with_schema_repair(
    path: Path,
    encoding: str,
) -> tuple[pd.DataFrame, int, int]:
    """Read legacy MOI CSVs whose data rows occasionally exceed header width.

    Historical files sometimes contain an unescaped ASCII comma in 備註. When a
    row has extra fields, merge exactly the excess fields back into 備註 so all
    trailing identifier/project/unit columns retain their original positions.
    Rows shorter than the header are padded rather than dropped.

    If excess fields remain after the 備註 repair, preserve them in synthetic
    _extra_N columns. No source row is silently skipped.
    """
    with path.open("r", encoding=encoding, newline="") as handle:
        reader = csv.reader(handle)
        try:
            header = next(reader)
        except StopIteration:
            return pd.DataFrame(), 0, 0

        if header:
            header[0] = header[0].lstrip("\ufeff")
        expected_width = len(header)
        note_index = header.index("備註") if "備註" in header else None

        source_rows: list[list[str]] = []
        repaired_rows = 0
        max_extra_columns = 0

        for row in reader:
            if not row or not any(cell != "" for cell in row):
                continue

            original_width = len(row)
            if len(row) > expected_width and note_index is not None:
                excess = len(row) - expected_width
                note_end = note_index + excess + 1
                row = (
                    row[:note_index]
                    + [",".join(row[note_index:note_end])]
                    + row[note_end:]
                )

            if original_width != expected_width:
                repaired_rows += 1

            max_extra_columns = max(
                max_extra_columns,
                max(0, len(row) - expected_width),
            )
            source_rows.append(row)

    columns = [
        *header,
        *(f"_extra_{index}" for index in range(1, max_extra_columns + 1)),
    ]
    final_width = len(columns)
    normalized_rows = [
        row[:final_width] + [""] * max(0, final_width - len(row))
        for row in source_rows
    ]
    return pd.DataFrame(normalized_rows, columns=columns), repaired_rows, max_extra_columns


def read_real_price_csv(path: str | Path) -> pd.DataFrame:
    """Read an MOI CSV with explicit row-width validation.

    We intentionally use csv.reader for all source files. pandas.read_csv can
    silently reinterpret a malformed row with one extra field as an index,
    which would shift every named column without raising ParserError.
    """
    path = Path(path)
    errors: list[Exception] = []

    required_header_markers = {"移轉層次", "總樓層數", "單價元平方公尺"}
    encodings = (
        "utf-8-sig",
        "utf-8",
        "big5",
        "cp950",
        "utf-16",
        "utf-16-le",
        "utf-16-be",
    )

    for encoding in encodings:
        try:
            frame, repaired_rows, extra_columns = _read_csv_with_schema_repair(
                path,
                encoding,
            )
        except (UnicodeDecodeError, UnicodeError, csv.Error) as exc:
            errors.append(exc)
            continue

        frame = normalize_columns(frame)
        if not required_header_markers.issubset(set(frame.columns)):
            errors.append(
                ValueError(
                    f"decoded with {encoding} but required MOI columns are missing"
                )
            )
            continue

        frame["_source_file"] = str(path)
        frame.attrs["csv_schema_repaired_rows"] = int(repaired_rows)
        frame.attrs["csv_schema_extra_columns"] = int(extra_columns)
        frame.attrs["csv_encoding"] = encoding

        if repaired_rows:
            print(
                "CSV_SCHEMA_REPAIR "
                f"path={path} repaired_rows={repaired_rows} "
                f"extra_columns={extra_columns}"
            )
        if encoding not in {"utf-8-sig", "utf-8"}:
            print(f"CSV_ENCODING path={path} encoding={encoding}")
        return frame

    details = "; ".join(type(error).__name__ for error in errors[-4:])
    raise ValueError(f"Unable to parse {path}; attempts ended with: {details}")

def normalize_columns(frame: pd.DataFrame) -> pd.DataFrame:
    frame = frame.copy()
    for old, new in COLUMN_ALIASES.items():
        if old in frame.columns and new not in frame.columns:
            frame = frame.rename(columns={old: new})
    return frame


def deduplicate_source_rows(frame: pd.DataFrame) -> pd.DataFrame:
    """Deduplicate repeated snapshots by MOI serial number when available."""
    if "編號" not in frame.columns:
        return frame.reset_index(drop=True)

    serial = frame["編號"].astype(str).str.strip()
    valid = ~serial.isin(["", "NA", "nan", "None"])
    duplicate = valid & serial.duplicated(keep="last")
    return frame.loc[~duplicate].reset_index(drop=True)


def find_source_files(root: str | Path, kind: str = "presale") -> list[Path]:
    root = Path(root)
    suffix = "_lvr_land_b.csv" if kind == "presale" else "_lvr_land_a.csv"
    files = [
        path
        for path in root.rglob("*.csv")
        if path.name.lower().endswith(suffix)
    ]
    return sorted(files)


def load_source_dir(root: str | Path, kind: str = "presale") -> pd.DataFrame:
    files = find_source_files(root, kind=kind)
    if not files:
        raise FileNotFoundError(f"No {kind} real-price CSV files found under {root}")

    frames: list[pd.DataFrame] = []
    repaired_files = 0
    repaired_rows = 0
    max_extra_columns = 0
    unreadable_files: list[str] = []

    for path in files:
        try:
            frame = read_real_price_csv(path)
        except ValueError as exc:
            unreadable_files.append(str(path))
            print(f"CSV_SKIPPED path={path} reason={exc}")
            continue

        file_repaired_rows = int(frame.attrs.get("csv_schema_repaired_rows", 0))
        if file_repaired_rows:
            repaired_files += 1
            repaired_rows += file_repaired_rows
        max_extra_columns = max(
            max_extra_columns,
            int(frame.attrs.get("csv_schema_extra_columns", 0)),
        )
        frames.append(frame)

    if not frames:
        raise ValueError(f"No readable {kind} CSV files found under {root}")

    combined = pd.concat(frames, ignore_index=True, sort=False)
    before = len(combined)
    combined = deduplicate_source_rows(combined)
    combined.attrs["source_files"] = len(files)
    combined.attrs["source_rows_before_dedup"] = before
    combined.attrs["deduplicated_rows"] = before - len(combined)
    combined.attrs["schema_repaired_files"] = repaired_files
    combined.attrs["schema_repaired_rows"] = repaired_rows
    combined.attrs["schema_extra_columns_max"] = max_extra_columns
    combined.attrs["unreadable_source_files"] = len(unreadable_files)
    combined.attrs["unreadable_source_paths"] = "|".join(unreadable_files)
    return combined


def prepare_transactions(
    frame: pd.DataFrame,
    floor_height_m: float = 3.2,
) -> tuple[pd.DataFrame, dict[str, int]]:
    source_files = int(frame.attrs.get("source_files", 1))
    source_rows_before_dedup = int(
        frame.attrs.get("source_rows_before_dedup", len(frame))
    )
    deduplicated_rows = int(frame.attrs.get("deduplicated_rows", 0))
    schema_repaired_files = int(frame.attrs.get("schema_repaired_files", 0))
    schema_repaired_rows = int(frame.attrs.get("schema_repaired_rows", 0))
    schema_extra_columns_max = int(frame.attrs.get("schema_extra_columns_max", 0))
    unreadable_source_files = int(frame.attrs.get("unreadable_source_files", 0))
    unreadable_source_paths = str(frame.attrs.get("unreadable_source_paths", ""))

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
        "source_files": source_files,
        "source_rows_before_dedup": source_rows_before_dedup,
        "deduplicated_rows": deduplicated_rows,
        "schema_repaired_files": schema_repaired_files,
        "schema_repaired_rows": schema_repaired_rows,
        "schema_extra_columns_max": schema_extra_columns_max,
        "unreadable_source_files": unreadable_source_files,
        "unreadable_source_paths": unreadable_source_paths,
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
    """Build the ordinary height curve while keeping special floors separate."""
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
    combined = pd.concat(
        (read_real_price_csv(path) for path in paths),
        ignore_index=True,
    )
    return deduplicate_source_rows(combined)
