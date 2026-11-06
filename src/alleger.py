# Garde seulement ce que lit le mini-assistant dans Dify, pour que les fichiers passent la limite de taille des
# requêtes HTTP de Dify (environ 1 Mo) : les colonnes utilisées et, pour le suivi, les vols Delta mainline.
# Le mini-assistant donne exactement la même fiche avec les fichiers complets ou allégés.
#
# Usage : python3 -I alleger.py --bts Airline_Delay_Cause.csv --suivi delta_monthly_airport_full.csv --out donnees
import argparse
from pathlib import Path

import pandas as pd

COLS_BTS = ["year", "month", "airport", "airport_name", "arr_flights", "arr_del15",
            "carrier_ct", "late_aircraft_ct", "nas_ct", "weather_ct"]
COLS_SUIVI = ["year", "month", "airport", "scope", "Carrier_ct", "NAS_ct", "Weather_ct", "Security_ct",
              "Unresolved_ct", "NASDelay", "nas_min_wx_either"]


def alleger_bts(t: pd.DataFrame) -> pd.DataFrame:
    return t[COLS_BTS]


def alleger_suivi(t: pd.DataFrame) -> pd.DataFrame:
    return t.loc[t.scope == "mainline", COLS_SUIVI]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--bts", required=True, type=Path)
    ap.add_argument("--suivi", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    alleger_bts(pd.read_csv(a.bts)).to_csv(a.out / "Airline_Delay_Cause.csv", index=False)
    alleger_suivi(pd.read_csv(a.suivi)).to_csv(a.out / "suivi_mainline.csv", index=False)
    for f in ("Airline_Delay_Cause.csv", "suivi_mainline.csv"):
        print(f, (a.out / f).stat().st_size // 1024, "Ko")


if __name__ == "__main__":
    main()
