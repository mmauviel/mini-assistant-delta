"""Resolve BTS 'late aircraft' delay minutes into root causes by chaining each
flight to the previous leg flown by the same aircraft (tail number).

Usage:
    python3 -I src/trace_root_cause.py --bts data/bts --out data/out
Outputs:
    flights_root_causes.parquet   one row per Delta-network flight, raw + resolved causes
    monthly_airport_root_causes.csv  month x arrival airport x scope (mainline / network)
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

CAUSES = ["CarrierDelay", "WeatherDelay", "NASDelay", "SecurityDelay"]
LA = "LateAircraftDelay"
RESOLVED = ["Carrier", "Weather", "NAS", "Security", "Unresolved"]
MAX_GAP_MIN = 24 * 60


def hhmm_to_min(s: pd.Series) -> np.ndarray:
    v = s.fillna(-1).astype(int).to_numpy()
    return np.where(v < 0, np.nan, (v // 100) * 60 + v % 100)


READ = ["FlightDate", "Marketing_Airline_Network", "Operating_Airline", "Tail_Number",
        "Flight_Number_Operating_Airline", "Origin", "Dest", "CRSDepTime", "CRSArrTime",
        "ArrDelay", "ArrDel15", "Cancelled", "Diverted"] + CAUSES + [LA]
CATEGORICAL = ["Marketing_Airline_Network", "Operating_Airline", "Tail_Number", "Origin", "Dest"]


def _read(p: Path) -> pd.DataFrame:
    d = pd.read_parquet(p, columns=READ)
    d = d[(d.Cancelled == 0) & (d.Diverted == 0) & d.Tail_Number.notna()]
    return d.astype({c: "category" for c in CATEGORICAL})


def load(folder: Path) -> pd.DataFrame:
    parts = [_read(p) for p in sorted(folder.glob("bts_*.parquet"))]
    d = pd.concat(parts, ignore_index=True)  # categories union -> object; re-categorise
    d = d.astype({c: "category" for c in CATEGORICAL})
    d["date"] = pd.to_datetime(d.FlightDate)
    d["crs_dep"] = (d.date - pd.Timestamp("2000-01-01")).dt.days * 1440 + hhmm_to_min(d.CRSDepTime)
    for c in CAUSES + [LA]:
        d[c] = d[c].fillna(0.0)
    d = d.drop_duplicates(["Operating_Airline", "Tail_Number", "FlightDate", "CRSDepTime", "Origin"])
    return d.sort_values(["Operating_Airline", "Tail_Number", "crs_dep"]).reset_index(drop=True)


def resolve(d: pd.DataFrame) -> pd.DataFrame:
    """Split each flight's late-aircraft minutes across the previous leg's
    already-resolved cause mix (recursive along the chain, proportional split).
    A link counts only if the previous leg is the same aircraft, landed at this
    flight's origin, and departed less than 24 h before."""
    n = len(d)
    out = np.zeros((n, len(RESOLVED)))
    out[:, :4] = d[CAUSES].to_numpy()
    la = d[LA].to_numpy()
    tail = pd.factorize(pd.MultiIndex.from_arrays([d.Operating_Airline, d.Tail_Number]))[0]
    airports = pd.Index(pd.concat([d.Origin.astype(str), d.Dest.astype(str)]).unique())
    org = airports.get_indexer(d.Origin.astype(str))
    dst = airports.get_indexer(d.Dest.astype(str))
    t = d.crs_dep.to_numpy()
    reason = np.full(n, "", dtype=object)
    for i in np.flatnonzero(la > 0):
        j = i - 1
        if j < 0 or tail[j] != tail[i]:
            reason[i] = "no_previous_leg"
        elif dst[j] != org[i]:
            reason[i] = "previous_leg_elsewhere"
        elif t[i] - t[j] >= MAX_GAP_MIN:
            reason[i] = "gap_over_24h"
        elif out[j].sum() <= 0:
            reason[i] = "previous_leg_no_cause"
        else:
            out[i] += la[i] * out[j] / out[j].sum()
            reason[i] = "traced"
            continue
        out[i, -1] += la[i]
    res = pd.DataFrame(out, columns=RESOLVED, index=d.index)
    res["trace_status"] = reason
    return res


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bts", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--first-month", default="2023-01")
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)

    d = load(a.bts)
    d = pd.concat([d, resolve(d)], axis=1)
    # December 2022 is loaded only so January 2023 flights can link to it.
    d = d[(d.Marketing_Airline_Network == "DL") & (d.date >= pd.Timestamp(a.first_month + "-01"))]
    d["scope"] = np.where(d.Operating_Airline == "DL", "mainline", "regional")
    d["year"], d["month"] = d.date.dt.year, d.date.dt.month
    d.drop(columns=["date", "crs_dep"]).to_parquet(a.out / "flights_root_causes.parquet", index=False)

    late = d[d.ArrDel15 == 1].copy()
    raw_cols = CAUSES + [LA]
    late[[c + "_ct" for c in raw_cols]] = late[raw_cols].div(late[raw_cols].sum(axis=1), axis=0)
    late[[c + "_ct" for c in RESOLVED]] = late[RESOLVED].div(late[RESOLVED].sum(axis=1), axis=0)
    agg_cols = raw_cols + RESOLVED + [c + "_ct" for c in raw_cols + RESOLVED]
    frames = []
    for scope, sub in [("mainline", late[late.scope == "mainline"]), ("network", late)]:
        g = sub.groupby(["year", "month", "Dest"])[agg_cols].sum()
        g["late_flights"] = sub.groupby(["year", "month", "Dest"]).size()
        frames.append(g.assign(scope=scope).reset_index())
    pd.concat(frames).round(3).to_csv(a.out / "monthly_airport_root_causes.csv", index=False)


if __name__ == "__main__":
    main()
