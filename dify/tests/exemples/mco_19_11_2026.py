"""Réponses d'API qui reproduisent l'alerte reçue à MCO le 18 novembre 2026 au soir (orages du 18 au 20/11)."""
import json

TAF = json.dumps([{"icaoId": "KMCO", "validTimeTo": "2026-11-20T00:00:00Z", "fcsts": [
    {"timeFrom": "2026-11-18T23:00:00Z", "timeTo": "2026-11-19T08:00:00Z", "fcstChange": None, "visib": "6+",
     "wxString": "VCSH", "clouds": [{"cover": "BKN", "base": 3000}]},
    {"timeFrom": "2026-11-19T03:00:00Z", "timeTo": "2026-11-19T04:00:00Z", "fcstChange": "TEMPO", "visib": 2,
     "wxString": "SHRA BR", "clouds": [{"cover": "BKN", "base": 1500}]},
    {"timeFrom": "2026-11-19T08:00:00Z", "timeTo": "2026-11-19T15:00:00Z", "fcstChange": "FM", "visib": "6+",
     "wxString": "-SHRA", "clouds": [{"cover": "OVC", "base": 900}]},
    {"timeFrom": "2026-11-19T15:00:00Z", "timeTo": "2026-11-19T18:00:00Z", "fcstChange": "FM", "visib": "6+",
     "wxString": "-SHRA VCTS", "clouds": [{"cover": "BKN", "base": 2500, "type": "CB"}]},
    {"timeFrom": "2026-11-19T18:00:00Z", "timeTo": "2026-11-20T01:00:00Z", "fcstChange": "FM", "visib": "6+",
     "wxString": "SHRA VCTS", "clouds": [{"cover": "BKN", "base": 2000, "type": "CB"}]},
]}])


def periode(nom, debut, fin, court, prob):
    return {"name": nom, "startTime": debut, "endTime": fin, "shortForecast": court,
            "probabilityOfPrecipitation": {"value": prob}}


NWS = json.dumps({"properties": {"periods": [
    periode("Tonight", "2026-11-18T18:00:00-05:00", "2026-11-19T06:00:00-05:00", "Showers And Thunderstorms", 91),
    periode("Thursday", "2026-11-19T06:00:00-05:00", "2026-11-19T18:00:00-05:00", "Showers And Thunderstorms", 94),
    periode("Thursday Night", "2026-11-19T18:00:00-05:00", "2026-11-20T06:00:00-05:00",
            "Showers And Thunderstorms Likely", 71),
    periode("Friday", "2026-11-20T06:00:00-05:00", "2026-11-20T18:00:00-05:00", "Showers And Thunderstorms", 78),
    periode("Friday Night", "2026-11-20T18:00:00-05:00", "2026-11-21T06:00:00-05:00", "Mostly Clear", 10),
]}})

SANS_FAA = "<AIRPORT_STATUS_INFORMATION><Update_Time>x</Update_Time></AIRPORT_STATUS_INFORMATION>"
MAINTENANT = "2026-11-18T23:30:00+00:00"
