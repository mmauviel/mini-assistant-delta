"""Tests de construire_fichier_bts.py : le fichier des causes de retard refait à partir des vols (petit jeu inventé)."""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import construire_fichier_bts as cfb  # noqa: E402


def vols():
    base = dict(FlightDate="2026-07-03", Operating_Airline="DL", Dest="MCO", ArrDel15=0.0, Cancelled=0.0, Diverted=0.0,
                CarrierDelay=None, WeatherDelay=None, NASDelay=None, SecurityDelay=None, LateAircraftDelay=None)
    return pd.DataFrame([
        {**base, "ArrDel15": 1.0, "CarrierDelay": 30.0, "WeatherDelay": 0.0, "NASDelay": 10.0, "SecurityDelay": 0.0, "LateAircraftDelay": 0.0},
        {**base, "ArrDel15": 1.0, "CarrierDelay": 0.0, "WeatherDelay": 0.0, "NASDelay": 0.0, "SecurityDelay": 0.0, "LateAircraftDelay": 20.0},
        {**base},                                         # à l'heure
        {**base, "Cancelled": 1.0},                       # annulé : compté dans arr_flights, pas dans arr_del15
        {**base, "Diverted": 1.0, "ArrDel15": None},      # dérouté : idem
        {**base, "Operating_Airline": "9E", "ArrDel15": 1.0, "CarrierDelay": 15.0},  # régional : hors fichier
    ])


def test_meme_definition_que_le_bts():
    t = cfb.construire(vols(), pd.DataFrame({"airport": ["MCO"], "airport_name": ["Orlando, FL: Orlando International"]}))
    r = t.iloc[0]
    assert len(t) == 1 and (r.year, r.month, r.airport, r.carrier) == (2026, 7, "MCO", "DL")
    assert r.arr_flights == 5 and r.arr_del15 == 2 and r.arr_cancelled == 1 and r.arr_diverted == 1
    assert r.carrier_ct == 0.75 and r.nas_ct == 0.25 and r.late_aircraft_ct == 1 and r.weather_ct == 0
    assert r.airport_name == "Orlando, FL: Orlando International"


def test_nom_inconnu_garde_le_code():
    assert cfb.construire(vols()).iloc[0].airport_name == "MCO"
