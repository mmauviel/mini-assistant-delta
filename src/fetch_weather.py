"""Download hourly airport weather (IEM ASOS archive of NWS/FAA METARs) for every
arrival airport in the BTS delay-cause CSV.

Usage:
    python3 -I src/fetch_weather.py --airports-csv <Airline_Delay_Cause.csv> \
        --start 2022-12-01 --end 2026-09-01 --out data/weather
"""
from __future__ import annotations

import argparse
import logging
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path

import pandas as pd

BASE = "https://mesonet.agron.iastate.edu/cgi-bin/request/asos.py"
FIELDS = ["vsby", "wxcodes", "skyc1", "skyl1", "skyc2", "skyl2", "skyc3", "skyl3", "sknt", "gust"]
STATION_RE = re.compile(r"^[A-Z0-9]{3,4}$")
PAUSE_S = 5  # IEM answers bursts with HTTP 429
log = logging.getLogger("fetch_weather")


def iem_station(iata: str, airports: dict) -> str:
    """IEM ids: contiguous-US airports drop the leading K of the ICAO code
    (KATL -> ATL); Alaska, Hawaii and the territories keep the full ICAO code
    (PANC, PHNL, TJSJ). Renamed codes follow the current ICAO (PBI -> KDJT -> DJT)."""
    rec = airports.get(iata) or airports.get(ALIASES.get(iata, ""))
    if rec is None:
        return iata
    icao = rec["icao"]
    return icao[1:] if icao.startswith("K") else icao


ALIASES = {"PBI": "DJT"}  # Palm Beach International was re-coded in 2026


def build_url(station: str, start: str, end: str) -> str:
    if not STATION_RE.fullmatch(station):
        raise ValueError(f"invalid station id: {station!r}")
    y1, m1, d1 = start.split("-")
    y2, m2, d2 = end.split("-")
    params = [("station", station)] + [("data", f) for f in FIELDS] + [
        ("year1", y1), ("month1", m1), ("day1", d1),
        ("year2", y2), ("month2", m2), ("day2", d2),
        ("tz", "Etc/UTC"), ("format", "onlycomma"), ("missing", "empty"),
        ("trace", "empty"), ("report_type", "3"),  # 3 = routine hourly METAR
    ]
    return f"{BASE}?{urllib.parse.urlencode(params)}"


def fetch(url: str, dest: Path, retries: int = 4) -> int:
    for attempt in range(1, retries + 1):
        try:
            with urllib.request.urlopen(url, timeout=300) as r:
                body = r.read()
            if not body.startswith(b"station,"):
                raise ValueError(f"unexpected response: {body[:80]!r}")
            part = dest.with_suffix(".part")
            part.write_bytes(body)
            part.rename(dest)
            return body.count(b"\n") - 1
        except Exception as exc:  # noqa: BLE001 - retried, then re-raised
            log.warning("attempt %d failed: %s", attempt, exc)
            if attempt == retries:
                raise
            time.sleep(30 * attempt)
    return 0


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--airports-csv", required=True, type=Path)
    ap.add_argument("--start", required=True)
    ap.add_argument("--end", required=True)
    ap.add_argument("--out", required=True, type=Path)
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    import airportsdata  # widely used IATA/ICAO/timezone table

    meta = airportsdata.load("IATA")
    airports = sorted(pd.read_csv(a.airports_csv).airport.dropna().unique())
    failed = []
    for s in airports:
        dest = a.out / f"wx_{s}.csv"
        if dest.exists() and dest.stat().st_size > 200:  # header-only file = retry
            continue
        try:
            n = fetch(build_url(iem_station(s, meta), a.start, a.end), dest)
            if n == 0:
                raise ValueError("no observations returned")
            log.info("%s rows=%d", s, n)
        except Exception as exc:  # noqa: BLE001 - keep going, report at the end
            failed.append(s)
            log.error("%s failed: %s", s, exc)
        time.sleep(PAUSE_S)
    log.info("done, %d airports, failed: %s", len(airports), failed)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    main()
