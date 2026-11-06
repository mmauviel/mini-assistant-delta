"""Flag each Delta flight with the weather at its origin (departure hour) and its
destination (arrival hour), from archived METARs, and measure how NAS delay
changes with it.

Usage:
    python3 -I src/weather_join.py --flights data/out/flights_root_causes.parquet \
        --weather data/weather --out data/out
"""
from __future__ import annotations

import argparse
from pathlib import Path

import airportsdata
import numpy as np
import pandas as pd

ALIASES = {"PBI": "DJT"}  # same airport, re-coded in 2026
CEILING_FT, VIS_MI = 1000, 3  # IFR thresholds


def hourly_flags(path: Path) -> pd.DataFrame:
    w = pd.read_csv(path, usecols=["valid", "vsby", "wxcodes", "skyc1", "skyl1",
                                   "skyc2", "skyl2", "skyc3", "skyl3"])
    w["valid"] = pd.to_datetime(w.valid)  # UTC
    ceil = np.full(len(w), np.inf)
    for k in (1, 2, 3):
        layer = w[f"skyc{k}"].isin(["BKN", "OVC", "VV"]).to_numpy()
        ceil = np.where(layer, np.minimum(ceil, w[f"skyl{k}"].fillna(np.inf).to_numpy()), ceil)
    w["ts"] = w.wxcodes.fillna("").str.contains("TS")
    w["ifr"] = (w.vsby < VIS_MI).fillna(False) | (ceil < CEILING_FT)
    h = w.assign(hour=w.valid.dt.floor("h")).groupby("hour")[["ts", "ifr"]].any()
    h = h.asfreq("h", fill_value=False)
    # condition counts if seen within +/- 1 h of the hour
    return h.rolling(3, center=True, min_periods=1).max().astype(bool)


def to_utc_hour(date: pd.Series, hhmm: pd.Series, tz: str) -> pd.Series:
    v = hhmm.fillna(0).astype(int) % 2400
    local = pd.to_datetime(date) + pd.to_timedelta(v // 100, unit="h")
    return (local.dt.tz_localize(tz, ambiguous="NaT", nonexistent="shift_forward")
                 .dt.tz_convert("UTC").dt.tz_localize(None))


def condition(ts: pd.Series, ifr: pd.Series) -> np.ndarray:
    return np.select([ts.fillna(False).to_numpy(bool), ifr.fillna(False).to_numpy(bool)],
                     ["thunderstorm", "low ceiling/visibility"], "clear")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--flights", required=True, type=Path)
    ap.add_argument("--weather", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    a = ap.parse_args()

    meta = airportsdata.load("IATA")
    f = pd.read_parquet(a.flights)
    f["Origin"], f["Dest"] = f.Origin.astype(str), f.Dest.astype(str)
    overnight = f.CRSArrTime.fillna(0) < f.CRSDepTime.fillna(0)
    f["arr_date"] = pd.to_datetime(f.FlightDate) + pd.to_timedelta(overnight.astype(int), unit="D")

    for side, ap_col, date_col, time_col in [("dest", "Dest", "arr_date", "CRSArrTime"),
                                             ("orig", "Origin", "FlightDate", "CRSDepTime")]:
        f[f"{side}_ts"], f[f"{side}_ifr"] = pd.NA, pd.NA
        for code, idx in f.groupby(ap_col).groups.items():
            wx_file = a.weather / f"wx_{code}.csv"
            rec = meta.get(code) or meta.get(ALIASES.get(code, ""))
            if rec is None or not wx_file.exists():
                continue  # airport outside the 161 studied: left unflagged
            flags = hourly_flags(wx_file)
            hours = to_utc_hour(f.loc[idx, date_col], f.loc[idx, time_col], rec["tz"])
            hit = flags.reindex(hours.to_numpy())
            f.loc[idx, f"{side}_ts"] = hit.ts.to_numpy()
            f.loc[idx, f"{side}_ifr"] = hit.ifr.to_numpy()
        f[f"{side}_wx"] = condition(f[f"{side}_ts"], f[f"{side}_ifr"])
        f.loc[f[f"{side}_ts"].isna(), f"{side}_wx"] = "no data"

    f.drop(columns=["arr_date"]).to_parquet(a.out / "flights_root_causes_weather.parquet", index=False)

    rows = []
    for scope, sub in [("mainline", f[f.scope == "mainline"]), ("network", f)]:
        for side in ("dest", "orig"):
            g = sub.groupby(f"{side}_wx").agg(
                flights=("ArrDel15", "size"),
                late15_pct=("ArrDel15", "mean"),
                nas_coded_pct=("NASDelay", lambda s: (s > 0).mean()),
                weather_coded_pct=("WeatherDelay", lambda s: (s > 0).mean()),
                nas_min_per_flight=("NASDelay", "mean"),
                nas_min_total=("NASDelay", "sum"),
            )
            g[["late15_pct", "nas_coded_pct", "weather_coded_pct"]] *= 100
            g["nas_min_share_pct"] = 100 * g.nas_min_total / g.nas_min_total.sum()
            rows.append(g.round(2).assign(scope=scope, side=side).reset_index()
                        .rename(columns={f"{side}_wx": "condition"}))
    pd.concat(rows).to_csv(a.out / "weather_vs_nas_summary.csv", index=False)


if __name__ == "__main__":
    main()
