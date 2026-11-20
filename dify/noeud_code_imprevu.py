# Nœud « Code » de Dify n° 2 : transforme les réponses des deux API en texte « imprévu » pour l'IA.
#
# Entrées :
#   aeroport : code IATA (MCO), sortie du nœud Code n° 1
#   taf      : corps de la réponse de https://aviationweather.gov/api/data/taf?ids=<icao>&format=json
#   faa      : corps de la réponse de https://nasstatus.faa.gov/api/airport-status-information (XML)
#   prevision: corps de la prévision à 7 jours de api.weather.gov (JSON), facultatif
# Sorties :
#   imprevu  : bloc en anglais à ajouter au prompt (« TODAY'S EVENT »), qui ne contient que ce que disent les API
#   resume   : le même contenu pour le manager, en anglais (ou en français si langue = « fr »)
#   alerte   : « oui » si une API signale un risque (pour envoyer un mail), sinon « non »
#   evenements : les mêmes faits rangés pour le mail de l'alerte du matin (JSON) : statut FAA en direct, niveau de
#                risque (High / Medium / Low), une seule liste de créneaux (créneaux qui se suivent fusionnés, heure
#                locale de l'aéroport à côté de l'UTC, codes météo traduits en mots) et les actions liées aux créneaux.
#                Règles dans docs/ALERTE_DU_MATIN.md. À déclarer en sortie (String) dans Dify, sinon erreur
#                « Not all output parameters are validated ».
#
# Mêmes seuils que l'étude : orage (TS) ; plafond bas (couche BKN/OVC/OVX sous 1 000 pieds) ou visibilité sous
# 3 milles. On signale aussi la neige et les précipitations verglaçantes, utiles en hiver.
# Si une API ne répond pas, on le dit au lieu d'inventer. Heures en UTC, comme dans les API.
import json
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone


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


def instant(t):
    """Date d'une période ou d'une prévision (secondes depuis 1970 ou date ISO), en UTC ; None si illisible."""
    try:
        if isinstance(t, str) and not t.strip().isdigit():
            d = datetime.fromisoformat(t.strip().replace("Z", "+00:00"))
            return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
        return datetime.fromtimestamp(int(t), tz=timezone.utc)
    except (TypeError, ValueError, OSError):
        return None


def fin_taf(texte):
    """Heure de fin de la prévision de l'aéroport (TAF) : elle ne couvre que les 24 à 30 prochaines heures."""
    try:
        donnees = json.loads(texte)
    except (TypeError, ValueError):
        return None
    if isinstance(donnees, dict):
        donnees = [donnees]
    if not donnees or not isinstance(donnees[0], dict):
        return None
    taf = donnees[0]
    fins = [instant(taf.get("validTimeTo"))] + [instant(f.get("timeTo")) for f in taf.get("fcsts") or [] if isinstance(f, dict)]
    fins = [f for f in fins if f is not None]
    return max(fins) if fins else None


def lire_prevision(texte, maintenant=None, fin_aeroport=None, risque_aeroport=False):
    """Prévision à 7 jours de la zone (périodes de 12 h) : renvoie (périodes à signaler, message d'erreur ou None).
    - Les risques faibles (« Slight Chance ») ne sont pas signalés ; « Chance » (30 à 50 %) est écrit « possible ».
    - Les périodes déjà terminées ne sont pas signalées.
    - Le jour et la nuit d'une même date, avec les mêmes risques, tiennent sur une ligne.
    - Si la prévision de l'aéroport (TAF) couvre la période et ne signale rien, on le dit : le risque n'est pas confirmé.
      Sans cette précision, le mail annonce un orage et dit en même temps qu'aucun orage n'est prévu."""
    if not (texte or "").strip():
        return [], None  # nœud absent : rien à dire
    try:
        periodes = json.loads(texte)["properties"]["periods"]
    except (TypeError, ValueError, KeyError):
        return [], "7-day forecast unavailable"
    groupes = []  # [date, noms, risques, prob max, possible, non confirmé, textes NWS]
    for p in periodes if isinstance(periodes, list) else []:
        if not isinstance(p, dict):
            continue
        court = str(p.get("shortForecast") or "")
        if "slight chance" in court.lower():
            continue
        risques = [(en, fr) for motif, en, fr in RISQUES_7J if re.search(motif, court, re.IGNORECASE)]
        if not risques:
            continue
        fin = instant(p.get("endTime"))
        if maintenant is not None and fin is not None and fin <= maintenant:
            continue  # période passée
        debut = instant(p.get("startTime"))
        non_confirme = (not risque_aeroport and fin_aeroport is not None and debut is not None and debut < fin_aeroport)
        prob = (p.get("probabilityOfPrecipitation") or {}).get("value")
        nom = str(p.get("name") or "?")
        date = str(p.get("startTime") or "")[:10]
        if groupes and date and groupes[-1][0] == date and groupes[-1][2] == risques:
            g = groupes[-1]
            g[1].append(nom); g[4] = g[4] and "chance" in court.lower(); g[5] = g[5] or non_confirme; g[6].append(court)
            if prob is not None and (g[3] is None or prob > g[3]):
                g[3] = prob
        else:
            groupes.append([date, [nom], risques, prob, "chance" in court.lower(), non_confirme, [court]])
    trouves = []
    for date, noms, risques, prob, possible, non_confirme, courts in groupes:
        jj = f" ({date[8:10]}/{date[5:7]})" if len(date) == 10 else ""
        quand_en, quand_fr = " and ".join(noms) + jj, " et ".join(noms) + jj
        haut = "up to " if len(noms) > 1 else ""
        haut_fr = "jusqu'à " if len(noms) > 1 else ""
        en = (f"{', '.join(e for e, _ in risques)} {'possible' if possible else 'forecast'} {quand_en}"
              + (f", {haut}{prob}% chance of precipitation" if prob else ""))
        fr = (f"{', '.join(f for _, f in risques)} {'possible(s)' if possible else 'prévu(e)s'} {quand_fr}"
              + (f", risque de précipitations {haut_fr}{prob} %" if prob else ""))
        if non_confirme:
            en += "; not in the airport forecast (TAF) for that time, so not confirmed"
            fr += " ; absent(e)s de la prévision de l'aéroport (TAF) pour ce moment, donc non confirmé(e)s"
        en += f" [NWS: {' / '.join(courts)}]"
        trouves.append((en, fr))
    return trouves, None


# ---------- Alerte du matin : les faits rangés pour le mail (sortie « evenements ») ----------
# Rien n'est ajouté aux API : on regroupe, on traduit les codes et on convertit les heures.

# Codes météo des prévisions d'aéroport (TAF, format METAR) -> mots simples
CODES_INTENSITE = {"-": "light", "+": "heavy", "VC": "nearby"}
CODES_DESCRIPTION = {"MI": "shallow", "PR": "partial", "BC": "patches of", "DR": "low drifting", "BL": "blowing",
                     "SH": "showers", "TS": "thunderstorm", "FZ": "freezing"}
CODES_PRECIPITATION = {"DZ": "drizzle", "RA": "rain", "SN": "snow", "SG": "snow grains", "IC": "ice crystals",
                       "PL": "ice pellets", "GR": "hail", "GS": "small hail", "UP": "unknown precipitation"}
CODES_AUTRES = {"BR": "mist", "FG": "fog", "FU": "smoke", "VA": "volcanic ash", "DU": "dust", "SA": "sand",
                "HZ": "haze", "PY": "spray", "PO": "dust whirls", "SQ": "squalls", "FC": "funnel cloud",
                "SS": "sandstorm", "DS": "duststorm"}


def groupe_en_mots(code):
    """Un groupe de temps présent (« -SHRA », « VCTS », « FZFG ») en mots ; le code tel quel s'il est inconnu."""
    c = (code or "").strip().upper()
    if c == "NSW":
        return "no significant weather"
    if c == "+FC":
        return "tornado"
    reste, intensite = c, ""
    for p in ("VC", "-", "+"):
        if reste.startswith(p):
            intensite, reste = CODES_INTENSITE[p], reste[len(p):]
            break
    morceaux = [reste[i:i + 2] for i in range(0, len(reste), 2)]
    if not morceaux or any(len(m) != 2 for m in morceaux):
        return code
    desc = morceaux.pop(0) if morceaux[0] in CODES_DESCRIPTION else ""
    if any(m not in CODES_PRECIPITATION and m not in CODES_AUTRES for m in morceaux):
        return code
    noms = " and ".join(CODES_PRECIPITATION.get(m) or CODES_AUTRES[m] for m in morceaux)
    if desc == "TS":
        mots = "thunderstorm" + (f" with {noms}" if noms else "")
        if intensite == "nearby":
            return "thunderstorms nearby"
    elif desc == "SH":
        mots = f"{noms} showers" if noms else "showers"
    elif desc:
        mots = f"{CODES_DESCRIPTION[desc]} {noms}".strip()
    else:
        mots = noms
    if intensite == "nearby":
        return f"{mots} nearby"
    return f"{intensite} {mots}".strip()


def temps_en_mots(wx):
    """« -SHRA VCTS » -> « light rain showers, thunderstorms nearby »."""
    return ", ".join(groupe_en_mots(g) for g in str(wx or "").split() if g)


def decalages(prevision):
    """Décalage horaire de l'aéroport, lu dans la prévision à 7 jours du service météo américain : chaque période
    donne son heure locale (« 2026-11-19T06:00:00-05:00 »). Pas de base de fuseaux horaires à installer, et le
    changement d'heure est juste. Renvoie [(début UTC, fin UTC, décalage)] ; vide si la prévision manque."""
    try:
        periodes = json.loads(prevision)["properties"]["periods"]
    except (TypeError, ValueError, KeyError):
        return []
    sortie = []
    for p in periodes if isinstance(periodes, list) else []:
        if not isinstance(p, dict):
            continue
        try:
            debut = datetime.fromisoformat(str(p.get("startTime")))
        except ValueError:
            continue
        if debut.utcoffset() is None:
            continue
        fin = instant(p.get("endTime")) or (debut + timedelta(hours=12))
        sortie.append((debut.astimezone(timezone.utc), fin.astimezone(timezone.utc), debut.utcoffset()))
    return sortie


def locale(d, decs):
    """Heure locale de l'aéroport pour un instant UTC (la période NWS qui le contient, sinon la plus proche)."""
    if d is None or not decs:
        return None
    for debut, fin, dec in decs:
        if debut <= d < fin:
            return d + dec
    proche = min(decs, key=lambda x: min(abs((x[0] - d).total_seconds()), abs((x[1] - d).total_seconds())))
    return d + proche[2]


JOURS_COURTS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def creneau(debut, fin, decs, ap):
    """« 19/11 15:00 to 20/11 01:00 UTC » et « Thu 19/11 10:00 to 20:00 MCO time » (même jour : la date une fois)."""
    utc = f"{debut:%d/%m %H:%M} to {fin:%d/%m %H:%M} UTC" if debut and fin else "?"
    ld, lf = locale(debut, decs), locale(fin, decs)
    if ld is None or lf is None:
        return utc, ""
    if lf.date() == ld.date() or (lf - ld <= timedelta(hours=24) and lf.hour == 0 and lf.minute == 0
                                  and lf.date() == ld.date() + timedelta(days=1)):
        loc = f"{JOURS_COURTS[ld.weekday()]} {ld:%d/%m %H:%M} to {lf:%H:%M} {ap} time"
    else:
        loc = f"{JOURS_COURTS[ld.weekday()]} {ld:%d/%m %H:%M} to {JOURS_COURTS[lf.weekday()]} {lf:%d/%m %H:%M} {ap} time"
    return utc, loc


NATURE_TAF = {"TEMPO": "at times", "BECMG": "becoming", "INTER": "at times"}


def taf_creneaux(texte):
    """Périodes à risque de la prévision de l'aéroport, fusionnées quand le même risque continue sans pause.
    Renvoie (liste de dict, erreur ou None)."""
    try:
        donnees = json.loads(texte)
    except (TypeError, ValueError):
        return [], "weather forecast unavailable"
    if isinstance(donnees, dict):
        donnees = [donnees]
    if not donnees or not isinstance(donnees[0], dict):
        return [], "no weather forecast (TAF) published for this airport"
    brutes = []
    for f in donnees[0].get("fcsts") or []:
        if not isinstance(f, dict):
            continue
        wx = f.get("wxString") or ""
        vis, plaf = visibilite(f.get("visib")), plafond(f.get("clouds"))
        risques = []
        if "TS" in wx:
            risques.append("thunderstorm")
        if (plaf is not None and plaf < 1000) or (vis is not None and vis < 3):
            risques.append("low ceiling/visibility")
        if "SN" in wx or "FZ" in wx or "PL" in wx:
            risques.append("snow or freezing precipitation")
        debut, fin = instant(f.get("timeFrom")), instant(f.get("timeTo"))
        debut, fin = (debut.astimezone(timezone.utc) if debut else None), (fin.astimezone(timezone.utc) if fin else None)
        if not risques or debut is None or fin is None:
            continue
        brutes.append({"debut": debut, "fin": fin, "risques": risques, "nature": (f.get("fcstChange") or "").upper(),
                       "prob": f.get("probability"),
                       "plafonds": [plaf] if plaf is not None and plaf < 1000 else [],
                       "visibilites": [vis] if vis is not None and vis < 3 else [], "temps": [wx] if wx else []})
    fusion = []
    for b in sorted(brutes, key=lambda x: x["debut"]):
        cle = (tuple(b["risques"]), "FM" if b["nature"] in ("", "FM") else b["nature"], b["prob"])
        for c in fusion:
            if c["cle"] == cle and c["fin"] == b["debut"]:
                c["fin"] = b["fin"]
                c["plafonds"] += b["plafonds"]; c["visibilites"] += b["visibilites"]
                c["temps"] += [w for w in b["temps"] if w not in c["temps"]]
                break
        else:
            fusion.append(dict(b, cle=cle))
    return fusion, None


def detail_taf(c):
    """« ceiling down to 700 ft, visibility 2 mi; light rain showers, thunderstorms nearby »."""
    morceaux = []
    if c["plafonds"]:
        bas = min(c["plafonds"])
        morceaux.append(f"ceiling {'down to ' if len(set(c['plafonds'])) > 1 else ''}{bas} ft")
    if c["visibilites"]:
        bas = min(c["visibilites"])
        morceaux.append(f"visibility {'down to ' if len(set(c['visibilites'])) > 1 else ''}{bas:g} mi")
    mots = []
    for w in c["temps"]:
        for m in temps_en_mots(w).split(", "):
            if m and m not in mots:
                mots.append(m)
    return "; ".join(x for x in [", ".join(morceaux), ", ".join(mots)] if x)


def certitude_taf(c):
    if c["nature"] == "PROB" or (c["prob"] and c["nature"] not in NATURE_TAF):
        return f"{c['prob']}% chance" if c["prob"] else "possible"
    texte = NATURE_TAF.get(c["nature"], "forecast")
    return f"{texte}, {c['prob']}% chance" if c["prob"] else texte


def nws_creneaux(texte, maintenant=None, fin_aeroport=None, risque_aeroport=False):
    """Périodes à risque de la prévision à 7 jours, fusionnées quand le même risque continue d'une période à la
    suivante (ce soir, demain, demain soir…). Mêmes filtres que lire_prevision."""
    if not (texte or "").strip():
        return [], None
    try:
        periodes = json.loads(texte)["properties"]["periods"]
    except (TypeError, ValueError, KeyError):
        return [], "7-day forecast unavailable"
    fusion = []
    for p in periodes if isinstance(periodes, list) else []:
        if not isinstance(p, dict):
            continue
        court = str(p.get("shortForecast") or "")
        if "slight chance" in court.lower():
            continue
        risques = [en for motif, en, _ in RISQUES_7J if re.search(motif, court, re.IGNORECASE)]
        if not risques:
            continue
        debut = instant(p.get("startTime"))
        debut = debut.astimezone(timezone.utc) if debut else None
        fin = instant(p.get("endTime")) or (debut + timedelta(hours=12) if debut else None)
        fin = fin.astimezone(timezone.utc) if fin else None
        if maintenant is not None and fin is not None and fin <= maintenant:
            continue
        possible = "chance" in court.lower()
        non_confirme = (not risque_aeroport and fin_aeroport is not None and debut is not None and debut < fin_aeroport)
        prob = (p.get("probabilityOfPrecipitation") or {}).get("value")
        date = str(p.get("startTime") or "")[:10]
        nom = str(p.get("name") or "?") + (f" ({date[8:10]}/{date[5:7]})" if len(date) == 10 else "")
        cle = (tuple(risques), possible, non_confirme)
        d = fusion[-1] if fusion else None
        if d and d["cle"] == cle and d["fin"] is not None and debut is not None and d["fin"] == debut:
            d["fin"] = fin; d["noms"].append(nom)
            if prob is not None:
                d["probs"].append(prob)
            if court not in d["courts"]:
                d["courts"].append(court)
        else:
            fusion.append({"cle": cle, "debut": debut, "fin": fin, "noms": [nom], "risques": risques,
                           "possible": possible, "non_confirme": non_confirme,
                           "probs": [prob] if prob is not None else [], "courts": [court]})
    return fusion, None


def niveau_de_risque(programmes, taf, nws):
    """High / Medium / Low, d'après des règles fixes (docs/ALERTE_DU_MATIN.md)."""
    if programmes:
        return "High", "FAA program or delay at the airport right now"
    for c in taf:
        if ("thunderstorm" in c["risques"] or "snow or freezing precipitation" in c["risques"]) and \
                (c["nature"] != "PROB" or (c["prob"] or 0) >= 40):
            return "High", f"{c['risques'][0].capitalize()} in the airport forecast (TAF)"
    for c in nws:
        if "tropical storm or hurricane" in c["risques"] and not c["possible"] and not c["non_confirme"]:
            return "High", "Tropical storm or hurricane in the 7-day forecast"
    if taf:
        return "Medium", f"{taf[0]['risques'][0].capitalize()} in the airport forecast (TAF)"
    for c in nws:
        if not c["possible"] and not c["non_confirme"]:
            return "Medium", f"{c['risques'][0].capitalize()} in the 7-day forecast"
    if nws:
        return "Low", "Only possible or unconfirmed risks in the 7-day forecast"
    return "None", "No risk reported"


def construire_evenements(ap, programmes, err_faa, err_meteo, err_7j, taf, nws, decs):
    """Le dictionnaire de la sortie « evenements » (mis en JSON dans main)."""
    if err_faa:
        faa = {"etat": "unavailable", "lignes": [f"{err_faa[0].upper()}{err_faa[1:]}."]}
    elif programmes:
        faa = {"etat": "active", "lignes": [f"{e[0].upper()}{e[1:]}." for e, _ in programmes]}
    else:
        faa = {"etat": "clear", "lignes": ["No ground stop, ground delay program or reported delay right now."]}
    lignes, actions = [], []

    def ajouter(action):
        if action not in actions and len(actions) < 4:
            actions.append(action)

    for c in taf:
        utc, loc = creneau(c["debut"], c["fin"], decs, ap)
        lignes.append({"debut": c["debut"].isoformat(), "source": "TAF", "source_long": "Airport forecast (TAF)",
                       "risque": ", ".join(c["risques"]), "quand_utc": utc, "quand_local": loc, "titre": "",
                       "certitude": certitude_taf(c), "detail": detail_taf(c), "pluie": ""})
    for c in nws:
        utc, loc = creneau(c["debut"], c["fin"], decs, ap) if c["debut"] and c["fin"] else ("", "")
        titre = c["noms"][0] if len(c["noms"]) == 1 else f"{c['noms'][0]} to {c['noms'][-1]}"
        probs = sorted(set(c["probs"]))
        pluie = "" if not probs or not probs[-1] else (
            f"{probs[0]}% chance of precipitation" if len(probs) == 1 else f"{probs[0]} to {probs[-1]}% chance of precipitation")
        certitude = "not confirmed by the airport forecast" if c["non_confirme"] else ("possible" if c["possible"] else "forecast")
        lignes.append({"debut": c["debut"].isoformat() if c["debut"] else "", "source": "NWS",
                       "source_long": "7-day area forecast (NWS)", "risque": ", ".join(c["risques"]),
                       "quand_utc": utc, "quand_local": loc, "titre": titre, "certitude": certitude,
                       "detail": " / ".join(x.lower() for x in c["courts"]).capitalize(), "pluie": pluie})
    lignes.sort(key=lambda l: l["debut"] or "9999")

    # Actions : les phrases approuvées, liées aux créneaux concernés (heure locale, sinon UTC).
    # Ordre : FAA, orages, neige ou verglas, prévision à 7 jours, plafond bas ; 4 actions au plus.
    def quand(c):
        utc, loc = creneau(c["debut"], c["fin"], decs, ap)
        return loc or utc

    def liste(creneaux):
        q = [quand(c) for c in creneaux]
        return q[0] if len(q) == 1 else ", ".join(q[:-1]) + " and " + q[-1]

    if programmes:
        ajouter("Coordinate with air traffic control on the FAA program.")
        ajouter("Prepare rebookings for the flights held by the FAA.")
    orages = [c for c in taf if "thunderstorm" in c["risques"]]
    neige = [c for c in taf if "snow or freezing precipitation" in c["risques"]]
    bas = [c for c in taf if c["risques"] == ["low ceiling/visibility"]]
    if orages:
        ajouter(f"Warn passengers on flights {liste(orages)} through the Fly Delta app.")
        ajouter(f"Prepare rebookings for flights {liste(orages)}.")
    if neige:
        ajouter(f"Reinforce standby crews and ground staff {liste(neige)}.")
    fin_taf_ = max((c["fin"] for c in taf), default=None)
    suite = [c for c in nws if not c["possible"] and not c["non_confirme"]
             and not (fin_taf_ is not None and c["fin"] is not None and c["fin"] <= fin_taf_)]
    if suite:
        jours = [c["noms"][0] if len(c["noms"]) == 1 else f"{c['noms'][0]} to {c['noms'][-1]}" for c in suite]
        ajouter(f"Reinforce standby crews and ground staff for {', '.join(jours)}.")
    if bas:
        ajouter(f"Coordinate with air traffic control for the low ceiling/visibility {liste(bas)}.")
    niveau, raison = niveau_de_risque(programmes, taf, nws)
    erreurs = [f"{e[0].upper()}{e[1:]}." for e in (err_meteo, err_7j) if e]
    fuseau = f"{ap} time" if decs else ""
    return {"aeroport": ap, "niveau": niveau, "raison": raison, "faa": faa, "lignes": lignes,
            "actions": actions, "erreurs": erreurs, "fuseau": fuseau}


MOIS_EN = ["January", "February", "March", "April", "May", "June", "July",
           "August", "September", "October", "November", "December"]
MOIS_FR = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet",
           "août", "septembre", "octobre", "novembre", "décembre"]


def main(aeroport: str, taf: str, faa: str, mois: float = 0, aujourd_hui: str = "", prevision: str = "",
         langue: str = "en") -> dict:
    """mois : le mois de la fiche. Les données en direct ne valent que pour aujourd'hui : si la fiche porte sur un
    autre mois (juillet alors qu'on est en novembre), on dit à l'IA de ne pas s'en servir.
    aujourd_hui : date ISO, seulement pour les tests ; vide = la date du jour.
    langue : langue du résumé pour le manager (« en » par défaut, « fr » pour le français)."""
    anglais = not (langue or "").strip().lower().startswith("fr")
    ap = (aeroport or "").strip().upper()
    jour = datetime.fromisoformat(aujourd_hui) if aujourd_hui else datetime.now(timezone.utc)
    if jour.tzinfo is None:
        jour = jour.replace(tzinfo=timezone.utc)
    try:
        m = int(mois or 0)
    except (TypeError, ValueError):
        m = 0
    autre_mois = 1 <= m <= 12 and m != jour.month
    meteo, err_meteo = lire_taf(taf)
    programmes, err_faa = lire_faa(faa, ap)
    fin_aeroport = None if err_meteo else fin_taf(taf)
    semaine, err_7j = lire_prevision(prevision, jour, fin_aeroport, bool(meteo))
    alerte = "oui" if (programmes or meteo or semaine) else "non"
    taf_c, _ = taf_creneaux(taf)
    nws_c, _ = nws_creneaux(prevision, jour, fin_aeroport, bool(meteo))
    evenements = json.dumps(construire_evenements(ap, programmes, err_faa, err_meteo, err_7j, taf_c, nws_c,
                                                  decalages(prevision)), ensure_ascii=False)
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
        en += [f"- Airport forecast (TAF): {e}." for e, _ in meteo]
        fr += [f"- Prévision de l'aéroport (TAF) : {f}." for _, f in meteo]
    else:
        jusqu = f", until {heure(fin_aeroport.timestamp())}" if fin_aeroport else ""
        jusqu_fr = f", jusqu'au {heure(fin_aeroport.timestamp())}" if fin_aeroport else ""
        en.append(f"- Airport forecast (TAF, next 24 to 30 hours{jusqu}): no thunderstorm, low ceiling/visibility, "
                  "snow or freezing precipitation expected.")
        fr.append(f"- Prévision de l'aéroport (TAF, 24 à 30 prochaines heures{jusqu_fr}) : ni orage, ni plafond bas, "
                  "ni neige ou verglas prévus.")
    if err_7j:
        en.append(f"- {err_7j}."); fr.append("- Prévision à 7 jours indisponible.")
    elif semaine:
        en += [f"- Next 7 days (National Weather Service, area forecast): {e}." for e, _ in semaine]
        fr += [f"- 7 prochains jours (service météo américain, prévision de la zone) : {f}." for _, f in semaine]
    elif (prevision or "").strip():
        en.append("- Next 7 days (National Weather Service, area forecast): no thunderstorm, snow, ice or fog expected.")
        fr.append("- 7 prochains jours : ni orage, ni neige, ni verglas, ni brouillard prévus.")
    en.append("Adapt the suggestions and the passenger message to these events, without inventing anything about them. "
              "If nothing is reported, say so in one sentence at the end of the interpretation and keep the approved passenger message.")
    if autre_mois:
        fr.append(f"(Non transmis à l'IA : la fiche porte sur {MOIS_FR[m - 1]}, ces données ne valent que pour aujourd'hui, "
                  f"{jour.day} {MOIS_FR[jour.month - 1]}.)")
        resume = "\n".join(fr)
        if anglais:
            resume = "\n".join([f"Live events at {ap} (FAA and official weather forecasts)"] + en[1:-1] + [
                f"(Not sent to the AI: the briefing is about {MOIS_EN[m - 1]}, and this data only describes today, "
                f"{MOIS_EN[jour.month - 1]} {jour.day}.)"])
        return {"alerte": alerte, "imprevu": f"TODAY'S EVENT: not applicable. The briefing is about {MOIS_EN[m - 1]}, and live data only describes today "
                           f"({jour.day} {MOIS_EN[jour.month - 1]}). Do not mention today's conditions.",
                "resume": resume, "evenements": evenements}
    resume = "\n".join(fr)
    if anglais:  # même contenu que le bloc pour l'IA, sans l'en-tête ni la consigne
        resume = "\n".join([f"Live events at {ap} (FAA and official weather forecasts)"] + en[1:-1])
    return {"imprevu": "\n".join(en), "resume": resume, "alerte": alerte, "evenements": evenements}
