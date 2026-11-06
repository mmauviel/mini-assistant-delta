"""Tests de la dernière étape de la chaîne : construire_suivi_mensuel.py (petit jeu de vols inventé)."""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import construire_suivi_mensuel as csm  # noqa: E402


def vols():
    base = dict(year=2026, month=7, Dest="MCO", Cancelled=0.0, Diverted=0.0, scope="mainline",
                dest_wx="clear", orig_wx="clear", ArrDel15=0.0,
                CarrierDelay=0.0, WeatherDelay=0.0, NASDelay=0.0, SecurityDelay=0.0, LateAircraftDelay=0.0,
                Carrier=0.0, Weather=0.0, NAS=0.0, Security=0.0, Unresolved=0.0)
    return pd.DataFrame([
        # en retard : 30 min compagnie + 10 min NAS par orage à destination
        {**base, "ArrDel15": 1.0, "CarrierDelay": 30.0, "NASDelay": 10.0, "Carrier": 30.0, "NAS": 10.0, "dest_wx": "thunderstorm"},
        # en retard : 20 min avion en retard, remontées à 20 min NAS ; plafond bas à l'origine
        {**base, "ArrDel15": 1.0, "LateAircraftDelay": 20.0, "NAS": 20.0, "orig_wx": "low ceiling/visibility"},
        {**base},                                    # à l'heure
        {**base, "Cancelled": 1.0},                  # annulé : pas compté
        {**base, "scope": "regional", "ArrDel15": 1.0, "CarrierDelay": 15.0, "Carrier": 15.0},
    ])


def test_mainline():
    g = csm.agreger(vols().query("scope == 'mainline'")).iloc[0]
    assert g.flights_flown == 3 and g.late15_flights == 2
    assert g.Carrier_ct == 0.75 and g.NAS_ct == 1.25 and g.Unresolved_ct == 0
    assert g.NASDelay == 10 and g.nas_min_wx_either == 10 and g.nas_min_dest_ts == 10
    assert g.flights_wx_either == 2 and g.flights_dest_ts == 1


def test_network_inclut_les_regionaux():
    g = csm.agreger(vols()).iloc[0]
    assert g.flights_flown == 4 and g.late15_flights == 3 and g.Carrier_ct == 1.75


def test_mois_sans_retard_donne_zero():
    g = csm.agreger(vols().iloc[[2]]).iloc[0]
    assert g.late15_flights == 0 and g.Carrier_ct == 0
