# Nœud « Code » du master workflow « Delta Flight IQ » (Chatflow) : vérifie ce que l'IA a compris de la question
# du manager et choisit le workflow à appeler.
#   route = "fiche"  → outil A (Fiche à la demande / On-demand briefing) avec aeroport, mois, langue
#   route = "alerte" → outil B en direct (Risk check, copie de l'Alerte du matin sans mail) avec aeroport
#   route = "aide"   → pas d'outil : le Chatflow répond avec `message` (aéroport manquant ou inconnu…)
#
# Sécurité : la question du manager ne va jamais telle quelle aux workflows A et B. Seuls un code d'aéroport de la
# liste des 161 aéroports Delta du fichier BTS et un mois entre 0 et 12 passent. Si l'IA de l'extracteur se trompe ou
# est manipulée (« ignore les consignes… »), le code refuse au lieu de transmettre.
#
# Entrées (venues du Parameter Extractor, toutes facultatives) :
#   question : la question du manager (sys.query), sert de secours si l'extracteur n'a rien rendu
#   aeroport : code IATA compris par l'IA (MCO), ou vide
#   mois     : 1 à 12 compris par l'IA, ou vide / 0
#   demande  : "briefing", "yearly", "risk" ou "unclear"
#   aujourd_hui : date ISO, seulement pour les tests (vide = aujourd'hui)
# Sorties : route, aeroport, mois (Number), langue (toujours "en"), message (texte en anglais pour le manager).
import re
from datetime import datetime, timezone

# Les 161 aéroports du fichier BTS de Delta (src/noms_aeroports.csv) : les mêmes que la table du nœud « OACI ».
AEROPORTS = set("""
ABE ABQ AGS ALB ANC ATL ATW AUS AVL BDL BGR BHM BIL BIS BNA BOI BOS BTR BTV BUF BUR BWI BZN CAE CHA CHO CHS
CID CLE CLT CMH COS CSG CVG DAB DAL DAY DCA DEN DFW DJT DLH DSM DTW ECP EGE ELP EUG EVV EWR EYW FAI FAR FAT
FAY FCA FLL FSD GEG GFK GNV GPT GRB GRR GSO GSP HDN HNL HOU HPN HRL HSV IAD IAH ICT IDA ILM IND JAC JAN JAX
JFK JNU KOA LAS LAX LEX LGA LGB LIH LIT MCI MCO MDT MDW MEM MIA MKE MLB MOB MSN MSO MSP MSY MTJ MYR OAJ OAK
OGG OKC OMA ONT ORD ORF PBI PDX PHL PHX PIT PNS PSC PSP PVD PWM RAP RDU RIC RNO ROA ROC RST RSW SAN SAT SAV
SBA SBN SDF SEA SFO SGF SHV SJC SJU SLC SMF SNA SRQ STL STT STX SYR TLH TPA TRI TUL TUS TVC TYS VPS XNA
""".split())
MOIS_EN = ["January", "February", "March", "April", "May", "June", "July",
           "August", "September", "October", "November", "December"]
AVANCE = 3  # sans mois précis : la fiche dans 3 mois, comme la Fiche du 1er
MAX_QUESTION = 500  # caractères lus au plus dans la question (le reste est ignoré)

MOTS_RISQUE = ("today", "tonight", "tomorrow", "this week", "next days", "right now", "now", "alert", "risk",
               "storm", "snow", "fog", "ice", "weather", "faa", "ground stop", "delay program")
MOTS_ANNUEL = ("year", "yearly", "annual", "calendar", "12 months", "all months")

AIDE = ("I can help with three things for a Delta station:\n"
        "- **Monthly briefing**: \"Brief me on MCO for July\" (without a month, I prepare the month in 3 months).\n"
        "- **Yearly calendar**: \"Show the yearly calendar for ATL\".\n"
        "- **Risk check now**: \"Any weather or FAA risk at BOS today?\"\n"
        "Please name the airport with its 3-letter code (for example MCO, ATL, BOS).")


def _code(texte):
    ap = "".join(ch for ch in str(texte or "").upper() if ch.isalpha())
    return ap if len(ap) == 3 and ap in AEROPORTS else ""


def _code_dans_question(question):
    # Codes écrits en majuscules dans la question (« MCO »), dans la liste des aéroports Delta seulement.
    trouves = [c for c in re.findall(r"\b[A-Z]{3}\b", question) if c in AEROPORTS]
    return trouves[0] if len(set(trouves)) == 1 else ""


def _contient(q, mots):
    return any(re.search(rf"\b{re.escape(m)}\b", q) for m in mots)


def _mois(valeur):
    try:
        m = float(valeur)
    except (TypeError, ValueError):
        return None
    if m != m or m != int(m):  # NaN ou décimal
        return None
    return int(m) if 1 <= m <= 12 else None


def _mois_dans_question(q_brut):
    for i, nom in enumerate(MOIS_EN):
        if nom == "May":  # « may » est aussi un verbe : seulement « May » avec la majuscule
            trouve = re.search(r"\bMay\b", q_brut)
        else:
            trouve = re.search(rf"\b({nom}|{nom[:3]})\b", q_brut, re.IGNORECASE)
        if trouve:
            return i + 1
    return None


def main(question: str = "", aeroport: str = "", mois: float = 0, demande: str = "",
         aujourd_hui: str = "") -> dict:
    q_brut = str(question or "")[:MAX_QUESTION]
    q = q_brut.lower()
    jour = datetime.fromisoformat(aujourd_hui) if aujourd_hui else datetime.now(timezone.utc)

    ap = _code(aeroport) or _code_dans_question(q_brut)
    if not ap:
        demande_ap = str(aeroport or "").strip()
        debut = (f"I don't know the airport \"{demande_ap[:20]}\": I only cover the 161 airports in Delta's "
                 f"BTS file.\n\n") if demande_ap else ""
        return {"route": "aide", "aeroport": "", "mois": 0, "langue": "en", "message": debut + AIDE}

    d = str(demande or "").strip().lower()
    if d not in ("briefing", "yearly", "risk"):
        if _contient(q, MOTS_RISQUE):
            d = "risk"
        elif _contient(q, MOTS_ANNUEL):
            d = "yearly"
        else:
            d = "briefing"

    if d == "risk":
        return {"route": "alerte", "aeroport": ap, "mois": 0, "langue": "en",
                "message": f"Live risk check for {ap} (airport forecast, FAA status, 7-day area forecast):"}
    if d == "yearly":
        return {"route": "fiche", "aeroport": ap, "mois": 0, "langue": "en",
                "message": f"Yearly calendar for {ap} (all 12 months):"}

    m = _mois(mois) or _mois_dans_question(q_brut)
    if m:
        message = f"{MOIS_EN[m - 1]} briefing for {ap}:"
    else:
        m = (jour.month - 1 + AVANCE) % 12 + 1
        message = (f"No month given, so here is the {MOIS_EN[m - 1]} briefing for {ap} "
                   f"(3 months ahead, the right time to prepare):")
    return {"route": "fiche", "aeroport": ap, "mois": m, "langue": "en", "message": message}
