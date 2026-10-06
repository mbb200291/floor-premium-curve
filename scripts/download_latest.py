from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from zipfile import ZipFile

import requests

URLS = {
    "sale": "https://plvr.land.moi.gov.tw/opendata/lvr_landAcsv.zip",
    "presale": "https://plvr.land.moi.gov.tw/opendata/lvr_landBcsv.zip",
}


def download(kind: str, output_root: Path) -> None:
    url = URLS[kind]
    kind_root = output_root / kind
    kind_root.mkdir(parents=True, exist_ok=True)
    zip_path = kind_root / f"{kind}.zip"

    with requests.get(url, stream=True, timeout=120) as response:
        response.raise_for_status()
        digest = hashlib.sha256()
        with zip_path.open("wb") as handle:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if not chunk:
                    continue
                digest.update(chunk)
                handle.write(chunk)

    extract_root = kind_root / "csv"
    extract_root.mkdir(parents=True, exist_ok=True)
    with ZipFile(zip_path) as archive:
        root = extract_root.resolve()
        for member in archive.infolist():
            destination = (extract_root / member.filename).resolve()
            if root not in destination.parents and destination != root:
                raise ValueError(f"Unsafe ZIP path: {member.filename}")
        archive.extractall(extract_root)

    metadata = {
        "kind": kind,
        "url": url,
        "downloaded_at_utc": datetime.now(timezone.utc).isoformat(),
        "sha256": digest.hexdigest(),
        "zip": str(zip_path),
        "extracted_to": str(extract_root),
    }
    (kind_root / "metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(metadata, ensure_ascii=False, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--kind", choices=["presale", "sale", "all"], default="presale")
    parser.add_argument("--output-dir", type=Path, default=Path("data/raw/latest"))
    args = parser.parse_args()

    kinds = ["presale", "sale"] if args.kind == "all" else [args.kind]
    for kind in kinds:
        download(kind, args.output_dir)


if __name__ == "__main__":
    main()
