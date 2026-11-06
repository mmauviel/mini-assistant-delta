# Nœud « Code » de Dify n° 2 : transforme les réponses des deux API en texte « imprévu » pour l'IA.
#
# Entrées :
#   aeroport : code IATA (MCO), sortie du nœud Code n° 1
#   taf      : corps de la réponse de https://aviationweather.gov/api/data/taf?ids=<icao>&format=json
#   faa      : corps de la réponse de https://nasstatus.faa.gov/api/airport-status-information (XML)
#   prevision: corps de la prévision à 7 jours de api.weather.gov (JSON), facultatif
# Sorties :
#   imprevu  : bloc en anglais à ajouter au prompt (« TODAY'S EVENT »), qui ne contient que ce que disent les API
#   resume   : le même contenu en français, pour le manager
#   alerte   : « oui » si une API signale un risque (pour envoyer un mail), sinon « non »
#
# Mêmes seuils que l'étude : orage (TS) ; plafond bas (couche BKN/OVC/OVX sous 1 000 pieds) ou visibilité sous
# 3 milles. On signale aussi la neige et les précipitations verglaçantes, utiles en hiver.
# Si une API ne répond pas, on le dit au lieu d'inventer. Heures en UTC, comme dans les API.
import json
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone


def heure(t):
    """Heure d'une période : secondes depuis 1970 (format de l'API) ou date ISO, par sécurité."""
    try:
        if isinstance(t, str) and not t.strip().isdigit():
            d = datetime.fromisoformat(t.strip().replace("Z", "+00:00"))
            d = d if d.tzinfo else d.replace(tzinfo=timezone.utc)
        else:
            d = datetime.fromtimestamp(int(t), tz=timezone.utc)
        return d.astimezone(timezone.utc).strftime("%d/%m %H:%M UTC")
    except (TypeError, ValueError, OSError):
        return "?"


def visibilite(v):
    """La visibilité vient en milles, parfois sous forme de texte (« 6+ », « 1/2 »)."""
    if v is None:
        return None
    s = str(v).replace("+", "").strip()
    try:
        if " " in s:  # « 1 1/2 »
            entier, frac = s.split(" ", 1)
            n, dnm = frac.split("/")
            return float(entier) + float(n) / float(dnm)
        if "/" in s:
            n, dnm = s.split("/")
            return float(n) / float(dnm)
        return float(s)
    except (ValueError, ZeroDivisionError):
        return None


def plafond(clouds):
    bases = [c.get("base") for c in (clouds or []) if isinstance(c, dict)
             and c.get("cover") in ("BKN", "OVC", "OVX") and c.get("base") is not None]
    return min(bases) if bases else None


def lire_taf(texte):
    """Renvoie (liste de périodes à signaler, message d'erreur ou None)."""
    try:
        donnees = json.loads(texte)
    except (TypeError, ValueError):
        return [], "weather forecast unavailable"
    if isinstance(donnees, dict):
        donnees = [donnees]
    if not donnees:
        return [], "no weather forecast (TAF) published for this airport"
    taf = donnees[0]
    periodes = []
    for f in taf.get("fcsts") or []:
        wx = f.get("wxString") or ""
        vis, plaf = visibilite(f.get("visib")), plafond(f.get("clouds"))
        signes_en, signes_fr = [], []
        if "TS" in wx:
            signes_en.append("thunderstorm"); signes_fr.append("orage")
        if (plaf is not None and plaf < 1000) or (vis is not None and vis < 3):
            detail = ", ".join(x for x in [f"ceiling {plaf} ft" if plaf is not None and plaf < 1000 else "",
                                           f"visibility {vis:g} mi" if vis is not None and vis < 3 else ""] if x)
            detail_fr = ", ".join(x for x in [f"plafond {plaf} pieds" if plaf is not None and plaf < 1000 else "",
                                              f"visibilité {vis:g} milles" if vis is not None and vis < 3 else ""] if x)
            signes_en.append(f"low ceiling/visibility ({detail})"); signes_fr.append(f"plafond bas ou visibilité réduite ({detail_fr})")
        if "SN" in wx or "FZ" in wx or "PL" in wx:
            signes_en.append("snow or freezing precipitation"); signes_fr.append("neige ou pluie verglaçante")
        if not signes_en:
            continue
        prob = f.get("probability")
        nature = f.get("fcstChange") or ""
        quand = f"{heure(f.get('timeFrom'))} to {heure(f.get('timeTo'))}"
        precision = " ".join(x for x in [nature, f"{prob}% probability" if prob else ""] if x)
        precision_fr = ", ".join(x for x in [nature, f"probabilité {prob} %" if prob else ""] if x)
        periodes.append((f"{', '.join(signes_en)} forecast {quand}" + (f" ({precision})" if precision else "") + f" [TAF: {wx or 'no weather code'}]",
                         f"{', '.join(signes_fr)} prévu de {quand.replace(' to ', ' à ')}" + (f" ({precision_fr})" if precision_fr else "")))
    return periodes, None


ALIAS_FAA = {"PBI": "DJT"}  # West Palm Beach : PBI dans le fichier BTS, DJT à la FAA


def lire_faa(texte, ap):
    """Renvoie (liste des programmes FAA en cours pour l'aéroport, message d'erreur ou None)."""
    codes = {ap, ALIAS_FAA.get(ap, ap)}
    try:
        racine = ET.fromstring(texte)
    except (ET.ParseError, TypeError):
        return [], "FAA airport status unavailable"
    trouves = []
    for el in racine.iter():
        if (el.findtext("ARPT") or "").strip().upper() not in codes:
            continue
        motif = (el.findtext("Reason") or "").strip()
        if el.tag == "Program":
            trouves.append((f"FAA ground stop, reason: {motif}, until {el.findtext('End_Time') or '?'}",
                            f"arrêt au sol FAA, motif : {motif}, jusqu'à {el.findtext('End_Time') or '?'}"))
        elif el.tag == "Ground_Delay":
            trouves.append((f"FAA ground delay program, reason: {motif}, average {el.findtext('Avg') or '?'}, maximum {el.findtext('Max') or '?'}",
                            f"programme de retards au sol FAA, motif : {motif}, moyenne {el.findtext('Avg') or '?'}, maximum {el.findtext('Max') or '?'}"))
        elif el.tag == "Delay":
            for ad in el.findall("Arrival_Departure"):
                sens = ad.get("Type", "?")
                trouves.append((f"FAA {sens.lower()} delays {ad.findtext('Min') or '?'} to {ad.findtext('Max') or '?'} "
                                f"({(ad.findtext('Trend') or '').lower() or 'trend unknown'}), reason: {motif}",
                                f"retards FAA ({'arrivées' if sens == 'Arrival' else 'départs' if sens == 'Departure' else sens}) "
                                f"de {ad.findtext('Min') or '?'} à {ad.findtext('Max') or '?'}, motif : {motif}"))
        elif el.tag == "Airport" and "TRANSIENT GA" not in motif.upper():  # ignore les fermetures aux petits avions privés
            trouves.append((f"FAA airport closure from {el.findtext('Start') or '?'} to {el.findtext('Reopen') or '?'}: {motif}",
                            f"fermeture de l'aéroport du {el.findtext('Start') or '?'} au {el.findtext('Reopen') or '?'} : {motif}"))
    return trouves, None


# Prévision à 7 jours : mots du service météo américain qui annoncent un risque pour les vols
RISQUES_7J = [
    (r"thunderstorm|t-storm|tstorm", "thunderstorms", "orages"),
    (r"hurricane|tropical storm", "tropical storm or hurricane", "tempête tropicale ou ouragan"),
    (r"snow|blizzard", "snow", "neige"),
    (r"freezing|sleet|\bice\b", "freezing precipitation or ice", "pluie verglaçante ou verglas"),
    (r"(?<!patchy )\bfog\b", "fog", "brouillard"),
]


def lire_prevision(texte):
    """Prévision à 7 jours (périodes de 12 h) : renvoie (périodes à signaler, message d'erreur ou None).
    Les risques faibles (« Slight Chance ») ne sont pas signalés."""
    if not (texte or "").strip():
        return [], None  # nœud absent : rien à dire
    try:
        periodes = json.loads(texte)["properties"]["periods"]
    except (TypeError, ValueError, KeyError):
        return [], "7-day forecast unavailable"
    trouves = []
    for p in periodes if isinstance(periodes, list) else []:
        court = str(p.get("shortForecast") or "")
        if "slight chance" in court.lower():
            continue
        risques = [(en, fr) for motif, en, fr in RISQUES_7J if re.search(motif, court, re.IGNORECASE)]
        if not risques:
            continue
        prob = (p.get("probabilityOfPrecipitation") or {}).get("value")
        nom = str(p.get("name") or "?")
        date = str(p.get("startTime") or "")[:10]
        jour = f"{nom} ({date[8:10]}/{date[5:7]})" if len(date) == 10 else nom
        en = f"{', '.join(e for e, _ in risques)} forecast {jour}" + (f", {prob}% chance of precipitation" if prob else "") + f" [NWS: {court}]"
        fr = f"{', '.join(f for _, f in risques)} prévu(e)s {jour}" + (f", risque de précipitations {prob} %" if prob else "")
        trouves.append((en, fr))
    return trouves, None


MOIS_EN = ["January", "February", "March", "April", "May", "June", "July",
           "August", "September", "October", "November", "December"]
MOIS_FR = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet",
           "août", "septembre", "octobre", "novembre", "décembre"]


def main(aeroport: str, taf: str, faa: str, mois: float = 0, aujourd_hui: str = "", prevision: str = "") -> dict:
    """mois : le mois de la fiche. Les données en direct ne valent que pour aujourd'hui : si la fiche porte sur un
    autre mois (juillet alors qu'on est en novembre), on dit à l'IA de ne pas s'en servir.
    aujourd_hui : date ISO, seulement pour les tests ; vide = la date du jour."""
    ap = (aeroport or "").strip().upper()
    jour = datetime.fromisoformat(aujourd_hui) if aujourd_hui else datetime.now(timezone.utc)
    try:
        m = int(mois or 0)
    except (TypeError, ValueError):
        m = 0
    autre_mois = 1 <= m <= 12 and m != jour.month
    meteo, err_meteo = lire_taf(taf)
    programmes, err_faa = lire_faa(faa, ap)
    semaine, err_7j = lire_prevision(prevision)
    alerte = "oui" if (programmes or meteo or semaine) else "non"
    en = [f"TODAY'S EVENT at {ap} (live data from the FAA airport status and the official weather forecasts, for today and the next 7 days; "
          "use only what is written here, and nothing else about today):"]
    fr = [f"Imprévus à {ap} (données en direct : FAA et prévisions météo officielles)"]
    if err_faa:
        en.append(f"- {err_faa}."); fr.append("- Statut FAA indisponible.")
    elif programmes:
        en += [f"- {e}." for e, _ in programmes]; fr += [f"- {f}." for _, f in programmes]
    else:
        en.append("- FAA: no ground stop, ground delay program or reported delay at this airport right now.")
        fr.append("- FAA : aucun arrêt au sol, programme de retards ou retard signalé en ce moment.")
    if err_meteo:
        en.append(f"- {err_meteo}."); fr.append("- Prévisions météo indisponibles.")
    elif meteo:
        en += [f"- {e}." for e, _ in meteo]; fr += [f"- {f}." for _, f in meteo]
    else:
        en.append("- Weather forecast: no thunderstorm, low ceiling/visibility, snow or freezing precipitation expected.")
        fr.append("- Météo : ni orage, ni plafond bas, ni neige ou verglas prévus.")
    if err_7j:
        en.append(f"- {err_7j}."); fr.append("- Prévision à 7 jours indisponible.")
    elif semaine:
        en += [f"- Next 7 days (National Weather Service): {e}." for e, _ in semaine]
        fr += [f"- 7 prochains jours (service météo américain) : {f}." for _, f in semaine]
    elif (prevision or "").strip():
        en.append("- Next 7 days (National Weather Service): no thunderstorm, snow, ice or fog expected.")
        fr.append("- 7 prochains jours : ni orage, ni neige, ni verglas, ni brouillard prévus.")
    en.append("Adapt the suggestions and the passenger message to these events, without inventing anything about them. "
              "If nothing is reported, say so in one sentence at the end of the interpretation and keep the approved passenger message.")
    if autre_mois:
        fr.append(f"(Non transmis à l'IA : la fiche porte sur {MOIS_FR[m - 1]}, ces données ne valent que pour aujourd'hui, "
                  f"{jour.day} {MOIS_FR[jour.month - 1]}.)")
        return {"alerte": alerte, "imprevu": f"TODAY'S EVENT: not applicable. The briefing is about {MOIS_EN[m - 1]}, and live data only describes today "
                           f"({jour.day} {MOIS_EN[jour.month - 1]}). Do not mention today's conditions.",
                "resume": "\n".join(fr)}
    return {"imprevu": "\n".join(en), "resume": "\n".join(fr), "alerte": alerte}
