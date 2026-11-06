# Partie 3, chaîne de données : refait le fichier « causes de retard » du BTS (Airline_Delay_Cause.csv) à partir des
# fichiers vol par vol que fetch_bts.py télécharge. Ces fichiers ont une adresse fixe sur transtats.bts.gov, alors que
# le fichier des causes se télécharge à la main dans un formulaire : refaire le second à partir des premiers permet de
# tout télécharger automatiquement chaque mois.
#
# Usage :
#   python3 -I construire_fichier_bts.py --bts data/bts --depuis 2023-01 --out Airline_Delay_Cause.csv
# (--depuis : premier mois gardé ; fetch_bts.py télécharge aussi le mois d'avant, utile seulement au suivi des avions)
#
# Même définition que le BTS (vols opérés par Delta, compagnie DL) :
#   arr_flights = vols prévus à l'arrivée (annulés et déroutés compris) ; arr_del15 = vols arrivés avec 15 min ou plus de retard ;
#   *_ct = vols en retard répartis entre les causes au prorata de leurs minutes ; arr_cancelled, arr_diverted.
# Vérifié sur janv. 2023 - août 2026 : mêmes valeurs que le fichier du BTS, à un vol près sur quelques lignes.
import argparse
from pathlib import Path

import pandas as pd

COMPAGNIE = "DL"
MINUTES = {"CarrierDelay": "carrier_ct", "WeatherDelay": "weather_ct", "NASDelay": "nas_ct",
           "SecurityDelay": "security_ct", "LateAircraftDelay": "late_aircraft_ct"}
CLES = ["year", "month", "airport"]
NOMS = Path(__file__).resolve().parent / "noms_aeroports.csv"


def construire(vols: pd.DataFrame, noms: pd.DataFrame | None = None) -> pd.DataFrame:
    v = vols[vols.Operating_Airline == COMPAGNIE].copy()
    d = pd.to_datetime(v.FlightDate)
    v["year"], v["month"], v["airport"] = d.dt.year, d.dt.month, v.Dest
    g = v.groupby(CLES).agg(arr_flights=("Dest", "size"), arr_cancelled=("Cancelled", "sum"), arr_diverted=("Diverted", "sum"))
    late = v[(v.ArrDel15 == 1) & (v.Cancelled == 0) & (v.Diverted == 0)].copy()
    minutes = late[list(MINUTES)].fillna(0)
    parts = minutes.div(minutes.sum(axis=1), axis=0).fillna(0)  # sans minutes renseignées : 0
    late[list(MINUTES.values())] = parts.to_numpy()
    m = late.groupby(CLES).agg(arr_del15=("Dest", "size"), **{c: (c, "sum") for c in MINUTES.values()})
    t = g.join(m, how="left").fillna(0).reset_index()
    t.insert(2, "carrier", COMPAGNIE)
    t.insert(3, "carrier_name", "Delta Air Lines Inc.")
    t["airport_name"] = t.airport.map(dict(zip(noms.airport, noms.airport_name)) if noms is not None else {}).fillna(t.airport)
    cols = ["year", "month", "carrier", "carrier_name", "airport", "airport_name", "arr_flights", "arr_del15",
            "carrier_ct", "weather_ct", "nas_ct", "security_ct", "late_aircraft_ct", "arr_cancelled", "arr_diverted"]
    t = t[cols]
    num = cols[6:]
    t[num] = t[num].astype(float).round(2)
    return t.sort_values(["year", "month", "airport"], ascending=[False, False, True])


def main() -> None:
    ap = argparse.ArgumentParser(description="Refait Airline_Delay_Cause.csv à partir des fichiers vol par vol du BTS")
    ap.add_argument("--bts", required=True, type=Path, help="dossier des fichiers bts_AAAA_MM.parquet (sortie de fetch_bts.py)")
    ap.add_argument("--depuis", help="premier mois gardé, AAAA-MM (par défaut : tous)")
    ap.add_argument("--out", required=True, type=Path)
    a = ap.parse_args()
    fichiers = sorted(a.bts.glob("bts_*.parquet"))
    if not fichiers:
        raise SystemExit(f"aucun fichier bts_*.parquet dans {a.bts}")
    colonnes = ["FlightDate", "Operating_Airline", "Dest", "ArrDel15", "Cancelled", "Diverted", *MINUTES]
    vols = pd.concat([pd.read_parquet(f, columns=colonnes) for f in fichiers], ignore_index=True)
    noms = pd.read_csv(NOMS) if NOMS.exists() else None
    t = construire(vols, noms)
    if a.depuis:
        y, m = map(int, a.depuis.split("-"))
        t = t[(t.year > y) | ((t.year == y) & (t.month >= m))]
    t.to_csv(a.out, index=False)
    print(f"{len(t)} lignes écrites dans {a.out}")


if __name__ == "__main__":
    main()
