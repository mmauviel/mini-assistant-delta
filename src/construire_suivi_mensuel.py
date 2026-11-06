# Partie 3, chaîne de données, dernière étape : fabrique delta_monthly_airport_full.csv, le fichier que le manager
# téléverse dans Dify (et que lit etape7_mini_assistant.py).
#
# Usage :
#   python3 -I construire_suivi_mensuel.py --vols data/out/flights_root_causes_weather.parquet \
#       [--opsnet data/opsnet/opsnet_daily.parquet] --out delta_monthly_airport_full.csv
#
# Entrée : un vol par ligne, sortie de weather_join.py (causes remontées de vol en vol + météo à l'origine et à
# destination). Sortie : une ligne par périmètre (mainline, network) × mois × aéroport d'arrivée.
import argparse
from pathlib import Path

import numpy as np
import pandas as pd

BRUTES = ["CarrierDelay", "WeatherDelay", "NASDelay", "SecurityDelay", "LateAircraftDelay"]
RESOLUES = ["Carrier", "Weather", "NAS", "Security", "Unresolved"]
CLES = ["year", "month", "Dest"]
MAUVAIS = ["thunderstorm", "low ceiling/visibility"]
FAA = ["total", "weather", "volume", "equipment", "runway", "other"]


def agreger(f: pd.DataFrame) -> pd.DataFrame:
    """Agrège les vols d'un périmètre par mois et aéroport d'arrivée."""
    vole = f[(f.Cancelled == 0) & (f.Diverted == 0)].copy()
    wx = vole.dest_wx.isin(MAUVAIS) | vole.orig_wx.isin(MAUVAIS)
    ts = (vole.dest_wx == "thunderstorm") | (vole.orig_wx == "thunderstorm")
    vole["nas_min_wx_either"] = vole.NASDelay.where(wx, 0)
    vole["nas_min_ts_either"] = vole.NASDelay.where(ts, 0)
    vole["nas_min_dest_ts"] = vole.NASDelay.where(vole.dest_wx == "thunderstorm", 0)
    vole["nas_min_dest_lowcig"] = vole.NASDelay.where(vole.dest_wx == "low ceiling/visibility", 0)
    vole["flights_wx_either"] = wx.astype(int)
    vole["flights_dest_ts"] = (vole.dest_wx == "thunderstorm").astype(int)

    # Vols en retard répartis entre les causes au prorata de leurs minutes, comme les colonnes _ct de BTS
    late = vole[vole.ArrDel15 == 1].copy()
    for cols in (BRUTES, RESOLUES):
        late[[c + "_ct" for c in cols]] = late[cols].div(late[cols].sum(axis=1), axis=0)

    g = vole.groupby(CLES).agg(flights_flown=("Dest", "size"),
                               **{c: (c, "sum") for c in ["nas_min_wx_either", "nas_min_ts_either", "nas_min_dest_ts",
                                                          "nas_min_dest_lowcig", "flights_wx_either", "flights_dest_ts"]})
    m = late.groupby(CLES)[BRUTES + RESOLUES + [c + "_ct" for c in BRUTES + RESOLUES]].sum()
    m["late15_flights"] = late.groupby(CLES).size()
    return g.join(m, how="left").fillna(0).reset_index()  # aucun vol en retard ce mois-là : 0


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--vols", required=True, type=Path, help="flights_root_causes_weather.parquet (sortie de weather_join.py)")
    ap.add_argument("--opsnet", type=Path, help="opsnet_daily.parquet (sortie de parse_opsnet.py), facultatif")
    ap.add_argument("--out", required=True, type=Path)
    a = ap.parse_args()

    f = pd.read_parquet(a.vols)
    parts = [agreger(f[f.scope == "mainline"]).assign(scope="mainline"),
             agreger(f).assign(scope="network")]
    t = pd.concat(parts, ignore_index=True).rename(columns={"Dest": "airport"})

    if a.opsnet is not None:
        o = pd.read_parquet(a.opsnet)
        o = o.copy()
        o["facility"] = o.facility.replace({"PBI": "DJT"})
        o["year"], o["month"] = pd.to_datetime(o.date).dt.year, pd.to_datetime(o.date).dt.month
        cols = [f"{c}_{k}" for c in FAA for k in ("delays", "min")]
        faa = o.groupby(["year", "month", "facility"])[cols].sum().add_prefix("faa_").reset_index()
        t["_fac"] = t.airport.replace({"PBI": "DJT"})
        t = t.merge(faa.rename(columns={"facility": "_fac"}), on=["year", "month", "_fac"], how="left").drop(columns="_fac")  # vide si la FAA ne suit pas cet aéroport

    ordre = ["scope", "year", "month", "airport", "flights_flown"] + BRUTES + RESOLUES \
        + [c + "_ct" for c in BRUTES + RESOLUES] + ["nas_min_wx_either", "nas_min_ts_either", "nas_min_dest_ts",
                                                    "nas_min_dest_lowcig", "flights_wx_either", "flights_dest_ts", "late15_flights"]
    t = t[ordre + [c for c in t.columns if c.startswith("faa_")]]
    num = t.select_dtypes(include=np.number).columns.difference(["year", "month"])
    t[num] = t[num].round(2)
    t.sort_values(["scope", "year", "month", "airport"]).to_csv(a.out, index=False)
    print(f"{len(t)} lignes écrites dans {a.out}")


if __name__ == "__main__":
    main()
