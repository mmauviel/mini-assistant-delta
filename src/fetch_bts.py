"""Download BTS Marketing Carrier On-Time files month by month, keep only the
columns and aircraft the study needs, store as Parquet, discard the raw file.

Usage:
    python3 -I src/fetch_bts.py --start 2022-12 --end 2026-08 --out data/bts
"""
from __future__ import annotations

import argparse
import logging
import tempfile
import time
import urllib.request
import zipfile
from pathlib import Path

import pandas as pd

URL = ("https://transtats.bts.gov/PREZIP/"
       "On_Time_Marketing_Carrier_On_Time_Performance_Beginning_January_2018_{y}_{m}.zip")
MAX_BYTES = 600 * 1024 * 1024  # refuse anything unexpectedly large
NETWORK = "DL"

COLUMNS = [
    "FlightDate", "Marketing_Airline_Network", "Operating_Airline", "Tail_Number",
    "Flight_Number_Operating_Airline", "Origin", "Dest",
    "CRSDepTime", "DepTime", "DepDelay", "TaxiOut", "WheelsOff", "WheelsOn", "TaxiIn",
    "CRSArrTime", "ArrTime", "ArrDelay", "ArrDel15",
    "Cancelled", "CancellationCode", "Diverted",
    "CRSElapsedTime", "ActualElapsedTime", "Distance",
    "CarrierDelay", "WeatherDelay", "NASDelay", "SecurityDelay", "LateAircraftDelay",
]

log = logging.getLogger("fetch_bts")


def months(start: str, end: str):
    y, m = map(int, start.split("-"))
    ye, me = map(int, end.split("-"))
    while (y, m) <= (ye, me):
        yield y, m
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)


def download(url: str, dest: Path, retries: int = 3) -> None:
    if not url.startswith("https://transtats.bts.gov/"):
        raise ValueError(f"unexpected host: {url}")
    for attempt in range(1, retries + 1):
        try:
            with urllib.request.urlopen(url, timeout=300) as r, open(dest, "wb") as f:
                total = 0
                while chunk := r.read(1 << 20):
                    total += len(chunk)
                    if total > MAX_BYTES:
                        raise ValueError("download exceeds size limit")
                    f.write(chunk)
            if not zipfile.is_zipfile(dest):
                raise ValueError("response is not a zip archive")
            return
        except Exception as exc:  # noqa: BLE001 - retried, then re-raised
            log.warning("attempt %d failed for %s: %s", attempt, url, exc)
            if attempt == retries:
                raise
            time.sleep(10 * attempt)


def read_month(zip_path: Path) -> pd.DataFrame:
    """Read the single CSV member by name; never extract to disk (no zip-slip)."""
    with zipfile.ZipFile(zip_path) as z:
        csvs = [n for n in z.namelist() if n.lower().endswith(".csv") and "/" not in n]
        if len(csvs) != 1:
            raise ValueError(f"expected one CSV in archive, found {csvs}")
        wanted = set(COLUMNS)
        with z.open(csvs[0]) as fh:
            # Some BTS headers carry trailing spaces (e.g. "Operating_Airline ").
            d = pd.read_csv(fh, usecols=lambda c: c.strip() in wanted, low_memory=False)
    d.columns = d.columns.str.strip()
    missing = wanted - set(d.columns)
    if missing:
        raise ValueError(f"columns missing from BTS file: {sorted(missing)}")
    return d.astype({"Tail_Number": "string", "CancellationCode": "string"})


def filter_network(d: pd.DataFrame, network: str = NETWORK) -> pd.DataFrame:
    """Keep every flight marketed by `network`, plus every other flight flown that
    month by an aircraft that also flew for `network` (needed to chain legs)."""
    mine = d.Marketing_Airline_Network == network
    tails = set(zip(d.loc[mine, "Operating_Airline"], d.loc[mine, "Tail_Number"].dropna()))
    keys = pd.Series(list(zip(d.Operating_Airline, d.Tail_Number)), index=d.index)
    return d[mine | keys.isin(tails)].reset_index(drop=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", required=True)
    ap.add_argument("--end", required=True)
    ap.add_argument("--out", required=True, type=Path)
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    for y, m in months(a.start, a.end):
        target = a.out / f"bts_{y}_{m:02d}.parquet"
        if target.exists():
            log.info("skip %s (exists)", target.name)
            continue
        with tempfile.TemporaryDirectory() as tmp:
            zp = Path(tmp) / "month.zip"
            download(URL.format(y=y, m=m), zp)
            raw = read_month(zp)
        kept = filter_network(raw)
        part = target.with_suffix(".part")
        kept.to_parquet(part, index=False)
        part.rename(target)  # atomic: a crash never leaves a half-written month
        log.info("%d-%02d raw=%d kept=%d", y, m, len(raw), len(kept))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    main()
