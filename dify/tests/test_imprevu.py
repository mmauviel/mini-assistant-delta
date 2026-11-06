"""Tests des nœuds Code des imprévus, sur des réponses d'API d'exemple (format réel de la FAA et de aviationweather.gov)."""
import importlib.util
import json
from pathlib import Path

ICI = Path(__file__).resolve().parent.parent
BTS = ICI.parent / "donnees" / "Airline_Delay_Cause.csv"


def charger(nom):
    spec = importlib.util.spec_from_file_location(nom, ICI / f"{nom}.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


icao, imprevu, lien = charger("noeud_code_icao"), charger("noeud_code_imprevu"), charger("noeud_code_lien_prevision")

FAA = """<AIRPORT_STATUS_INFORMATION><Update_Time>Thu Nov 6 13:00:00 2026 GMT</Update_Time>
<Delay_type><Name>Ground Stop Programs</Name><Ground_Stop_List><Program><ARPT>MCO</ARPT><Reason>thunderstorms</Reason><End_Time>5:00 pm EST</End_Time></Program></Ground_Stop_List></Delay_type>
<Delay_type><Name>Ground Delay Programs</Name><Ground_Delay_List><Ground_Delay><ARPT>LGA</ARPT><Reason>thunderstorms</Reason><Avg>33 minutes</Avg><Max>1 hour and 53 minutes</Max></Ground_Delay></Ground_Delay_List></Delay_type>
<Delay_type><Name>General Arrival/Departure Delay Info</Name><Arrival_Departure_Delay_List><Delay><ARPT>MCO</ARPT><Reason>WX:Thunderstorms</Reason><Arrival_Departure Type="Arrival"><Min>31 minutes</Min><Max>45 minutes</Max><Trend>Increasing</Trend></Arrival_Departure></Delay></Arrival_Departure_Delay_List></Delay_type>
<Delay_type><Name>Airport Closures</Name><Airport_Closure_List><Airport><ARPT>MCO</ARPT><Reason>!MCO AD AP CLSD TO NON SKED TRANSIENT GA ACFT</Reason><Start>Nov 03</Start><Reopen>Nov 08</Reopen></Airport></Airport_Closure_List></Delay_type>
</AIRPORT_STATUS_INFORMATION>"""

TAF = json.dumps([{"icaoId": "KMCO", "rawTAF": "TAF KMCO ...", "fcsts": [
    {"timeFrom": 1793970000, "timeTo": 1793984400, "fcstChange": None, "probability": None, "visib": "6+", "wxString": None,
     "clouds": [{"cover": "SCT", "base": 4000}]},
    {"timeFrom": 1793984400, "timeTo": 1793998800, "fcstChange": "TEMPO", "probability": None, "visib": 2, "wxString": "TSRA",
     "clouds": [{"cover": "BKN", "base": 800, "type": "CB"}]},
    {"timeFrom": 1793998800, "timeTo": 1794006000, "fcstChange": "PROB", "probability": 30, "visib": "1/2", "wxString": "FG",
     "clouds": [{"cover": "OVC", "base": 200}]},
]}])


def test_icao():
    assert icao.main("mco") == {"aeroport": "MCO", "icao": "KMCO", "lat": "28.4294", "lon": "-81.3090"}
    assert icao.main("HNL")["icao"] == "PHNL" and icao.main(" sju ")["icao"] == "TJSJ"
    assert icao.main("FCA")["icao"] == "KGPI"  # Kalispell : le code OACI n'est pas K + IATA
    assert icao.main("XYZ") == {"aeroport": "XYZ", "icao": "KXYZ", "lat": "", "lon": ""}


def test_icao_couvre_tous_les_aeroports_du_fichier_bts():
    import csv
    aps = {r["airport"] for r in csv.DictReader(open(BTS, encoding="utf-8"))}
    assert aps <= set(icao.AEROPORTS)


def test_faa_garde_seulement_l_aeroport_et_ignore_les_fermetures_aviation_privee():
    progs, err = imprevu.lire_faa(FAA, "MCO")
    assert err is None and len(progs) == 2
    assert "ground stop" in progs[0][0] and "5:00 pm EST" in progs[0][0]
    assert "arrival delays 31 minutes to 45 minutes (increasing)" in progs[1][0]


def test_taf_signale_orage_plafond_bas_et_visibilite():
    periodes, err = imprevu.lire_taf(TAF)
    assert err is None and len(periodes) == 2  # la période de beau temps n'est pas signalée
    assert periodes[0][0].startswith("thunderstorm, low ceiling/visibility (ceiling 800 ft, visibility 2 mi)") and "TEMPO" in periodes[0][0]
    assert "visibility 0.5 mi" in periodes[1][0] and "30% probability" in periodes[1][0]
    assert "UTC" in periodes[0][0]


def test_sortie_complete():
    out = imprevu.main("MCO", TAF, FAA)
    assert out["imprevu"].startswith("TODAY'S EVENT at MCO") and "ground stop" in out["imprevu"]
    assert "arrêt au sol FAA" in out["resume"] and "orage" in out["resume"]


def test_rien_a_signaler():
    calme = json.dumps([{"fcsts": [{"timeFrom": 1793970000, "timeTo": 1793984400, "visib": "6+", "clouds": []}]}])
    out = imprevu.main("ATL", calme, FAA)
    assert "no ground stop" in out["imprevu"] and "no thunderstorm" in out["imprevu"]


def test_api_en_panne_ne_fait_pas_inventer():
    out = imprevu.main("MCO", "", "<html>erreur</html")
    assert "weather forecast unavailable" in out["imprevu"] and "FAA airport status unavailable" in out["imprevu"]
    assert imprevu.main("MCO", "[]", FAA)["imprevu"].count("no weather forecast") == 1


def test_heure_iso():
    assert imprevu.heure("2026-11-06T15:00:00Z") == "06/11 15:00 UTC"


def test_autre_mois_que_aujourd_hui_n_est_pas_transmis():
    out = imprevu.main("MCO", TAF, FAA, 7, "2026-11-06")
    assert out["imprevu"].startswith("TODAY'S EVENT: not applicable") and "ground stop" not in out["imprevu"]
    assert "arrêt au sol FAA" in out["resume"] and "Non transmis" in out["resume"]
    assert "ground stop" in imprevu.main("MCO", TAF, FAA, 11, "2026-11-06")["imprevu"]


POINTS = json.dumps({"properties": {"gridId": "MLB", "gridX": 26, "gridY": 68,
                                    "forecast": "https://api.weather.gov/gridpoints/MLB/26,68/forecast"}})
SEMAINE = json.dumps({"properties": {"periods": [
    {"name": "Today", "startTime": "2026-11-06T06:00:00-05:00", "shortForecast": "Sunny", "probabilityOfPrecipitation": {"value": None}},
    {"name": "Saturday", "startTime": "2026-11-07T06:00:00-05:00", "shortForecast": "Showers And Thunderstorms Likely",
     "probabilityOfPrecipitation": {"value": 70}},
    {"name": "Sunday", "startTime": "2026-11-08T06:00:00-05:00", "shortForecast": "Slight Chance Showers And Thunderstorms",
     "probabilityOfPrecipitation": {"value": 20}},
    {"name": "Monday Night", "startTime": "2026-11-09T18:00:00-05:00", "shortForecast": "Patchy Fog", "probabilityOfPrecipitation": {"value": 0}},
    {"name": "Tuesday", "startTime": "2026-11-10T06:00:00-05:00", "shortForecast": "Freezing Rain", "probabilityOfPrecipitation": {"value": 60}},
]}})
CALME_TAF = json.dumps([{"fcsts": [{"timeFrom": 1793970000, "timeTo": 1793984400, "visib": "6+", "clouds": []}]}])
SANS_FAA = "<AIRPORT_STATUS_INFORMATION><Update_Time>x</Update_Time></AIRPORT_STATUS_INFORMATION>"


def test_lien_prevision():
    assert lien.main(POINTS) == {"url": "https://api.weather.gov/gridpoints/MLB/26,68/forecast"}
    assert lien.main("pas du json") == {"url": ""}
    assert lien.main(json.dumps({"properties": {"forecast": "https://exemple.com/x"}})) == {"url": ""}


def test_prevision_7_jours():
    periodes, err = imprevu.lire_prevision(SEMAINE)
    assert err is None and len(periodes) == 2  # beau temps, risque faible et brouillard épars ignorés
    assert periodes[0][0].startswith("thunderstorms forecast Saturday (07/11), 70% chance")
    assert "verglas" in periodes[1][1]
    assert imprevu.lire_prevision("") == ([], None)
    assert imprevu.lire_prevision("<html>")[1] == "7-day forecast unavailable"


def test_alerte_pour_le_mail():
    assert imprevu.main("ATL", CALME_TAF, SANS_FAA)["alerte"] == "non"
    out = imprevu.main("ATL", CALME_TAF, SANS_FAA, prevision=SEMAINE)
    assert out["alerte"] == "oui" and "Next 7 days" in out["imprevu"] and "7 prochains jours" in out["resume"]
    assert imprevu.main("MCO", TAF, FAA)["alerte"] == "oui"
    calme_7j = json.dumps({"properties": {"periods": [{"name": "Today", "shortForecast": "Sunny"}]}})
    assert "no thunderstorm, snow, ice or fog" in imprevu.main("ATL", CALME_TAF, SANS_FAA, prevision=calme_7j)["imprevu"]


def test_west_palm_beach_s_appelle_djt_a_la_faa():
    faa = FAA.replace("<ARPT>LGA</ARPT>", "<ARPT>DJT</ARPT>")
    progs, _ = imprevu.lire_faa(faa, "PBI")
    assert len(progs) == 1 and "ground delay program" in progs[0][0]


def test_resume_en_anglais_pour_le_mail():
    out = imprevu.main("ATL", CALME_TAF, SANS_FAA, prevision=SEMAINE, langue="en")
    assert out["resume"].startswith("Live events at ATL")
    assert "Next 7 days" in out["resume"] and "Adapt the suggestions" not in out["resume"]
    assert "TODAY'S EVENT" not in out["resume"] and "prochains" not in out["resume"]
    assert out["imprevu"] == imprevu.main("ATL", CALME_TAF, SANS_FAA, prevision=SEMAINE)["imprevu"]
    autre = imprevu.main("MCO", TAF, FAA, mois=7, aujourd_hui="2026-11-06", langue="en")
    assert "Not sent to the AI" in autre["resume"] and "juillet" not in autre["resume"]
    assert imprevu.main("ATL", CALME_TAF, SANS_FAA)["resume"].startswith("Imprévus à ATL")
