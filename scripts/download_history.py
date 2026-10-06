from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime
from pathlib import Path
from zipfile import ZipFile, is_zipfile
from zoneinfo import ZoneInfo

import requests

URL_TEMPLATE = (
    "https://plvr.land.moi.gov.tw/DownloadSeason"
    "?season={season}&type=zip&fileName=lvr_landcsv.zip"
)


def parse_season(value: str) -> tuple[int, int]:
    year_text, quarter_text = value.upper().split("S", 1)
    year = int(year_text)
    quarter = int(quarter_text)
    if quarter not in (1, 2, 3, 4):
        raise ValueError(f"Invalid quarter in season: {value}")
    return year, quarter


def format_season(year: int, quarter: int) -> str:
    return f"{year}S{quarter}"


def iter_seasons(start: str, end: str) -> list[str]:
    start_year, start_quarter = parse_season(start)
    end_year, end_quarter = parse_season(end)
    if (start_year, start_quarter) > (end_year, end_quarter):
        raise ValueError("start season must not be after end season")

    seasons: list[str] = []
    year, quarter = start_year, start_quarter
    while (year, quarter) <= (end_year, end_quarter):
        seasons.append(format_season(year, quarter))
        quarter += 1
        if quarter == 5:
            year += 1
            quarter = 1
    return seasons


def current_roc_season() -> str:
    now = datetime.now(ZoneInfo("Asia/Taipei"))
    roc_year = now.year - 1911
    quarter = (now.month - 1) // 3 + 1
    return format_season(roc_year, quarter)


def safe_extract(zip_path: Path, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    root = output_dir.resolve()
    with ZipFile(zip_path) as archive:
        for member in archive.infolist():
            destination = (output_dir / member.filename).resolve()
            if root not in destination.parents and destination != root:
                raise ValueError(f"Unsafe ZIP path: {member.filename}")
        archive.extractall(output_dir)


def download_season(season: str, output_root: Path) -> dict[str, object]:
    season_root = output_root / season
    season_root.mkdir(parents=True, exist_ok=True)
    zip_path = season_root / "season.zip"
    url = URL_TEMPLATE.format(season=season)

    digest = hashlib.sha256()
    with requests.get(url, stream=True, timeout=120) as response:
        status_code = response.status_code
        if status_code != 200:
            return {
                "season": season,
                "available": False,
                "status_code": status_code,
                "url": url,
            }

        with zip_path.open("wb") as handle:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if not chunk:
                    continue
                digest.update(chunk)
                handle.write(chunk)

    if not is_zipfile(zip_path):
        zip_path.unlink(missing_ok=True)
        return {
            "season": season,
            "available": False,
            "status_code": status_code,
            "url": url,
            "reason": "response_is_not_zip",
        }

    extract_root = season_root / "csv"
    safe_extract(zip_path, extract_root)
    return {
        "season": season,
        "available": True,
        "status_code": status_code,
        "url": url,
        "sha256": digest.hexdigest(),
        "zip": str(zip_path),
        "extracted_to": str(extract_root),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start-season", default="110S3")
    parser.add_argument("--end-season", default=current_roc_season())
    parser.add_argument("--output-dir", type=Path, default=Path("data/raw/history"))
    args = parser.parse_args()

    results = []
    for season in iter_seasons(args.start_season, args.end_season):
        result = download_season(season, args.output_dir)
        results.append(result)
        print(json.dumps(result, ensure_ascii=False))

    metadata = {
        "start_season": args.start_season,
        "end_season": args.end_season,
        "generated_at": datetime.now(ZoneInfo("Asia/Taipei")).isoformat(),
        "downloaded_seasons": [
            result["season"] for result in results if result.get("available")
        ],
        "unavailable_seasons": [
            result["season"] for result in results if not result.get("available")
        ],
        "seasons": results,
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
