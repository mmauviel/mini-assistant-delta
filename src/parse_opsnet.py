"""Parse an FAA OPSNET 'Delay By Cause' export (HTML saved as .xls, grouped by
Date and Facility) into a tidy Parquet table.

Usage:
    python3 -I src/parse_opsnet.py --report <WEB-Report.xls> --out data/opsnet/opsnet_daily.parquet
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

import pandas as pd

CAUSES = ["total", "weather", "volume", "equipment", "runway", "other"]
COLS = [f"{c}_{m}" for c in CAUSES for m in ("delays", "avg_min", "min")]
ROW = re.compile(
    r"<tr>\s*<td nowrap style=text-align:left;>(\d\d/\d\d/\d{4})</td>\s*"
    r"<td nowrap style=text-align:left;>([A-Z0-9]{3,4})\s*</td>"
    r"((?:\s*<td nowrap align=right>[\d,]*</td>){18})")
CELL = re.compile(r"<td nowrap align=right>([\d,]*)</td>")
MAX_BYTES = 1024 * 1024 * 1024


def parse(path: Path) -> pd.DataFrame:
    if path.stat().st_size > MAX_BYTES:
        raise ValueError("report larger than expected")
    text = path.read_text(encoding="latin-1")
    if "Delay By Cause Report" not in text:
        raise ValueError("not an OPSNET Delay By Cause report")
    rows = []
    for date, fac, cells in ROW.findall(text):
        vals = [int(v.replace(",", "") or 0) for v in CELL.findall(cells)]
        rows.append([date, fac, *vals])
    d = pd.DataFrame(rows, columns=["date", "facility", *COLS])
    d["date"] = pd.to_datetime(d.date, format="%m/%d/%Y")
    check = d[[f"{c}_delays" for c in CAUSES[1:]]].sum(axis=1)
    if not (check == d.total_delays).all():
        raise ValueError("cause counts do not add up to the total")
    return d.drop(columns=[c for c in COLS if c.endswith("avg_min")])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    a = ap.parse_args()
    a.out.parent.mkdir(parents=True, exist_ok=True)
    d = parse(a.report)
    d.to_parquet(a.out, index=False)
    print(f"{len(d)} rows, {d.facility.nunique()} facilities, {d.date.min():%Y-%m-%d} to {d.date.max():%Y-%m-%d}")


if __name__ == "__main__":
    main()
