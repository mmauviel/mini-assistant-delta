# Nœud « Code » de Dify « rappel » : le workflow planifié du 1er de chaque mois (déclencheur Schedule).
# Il calcule le mois à préparer (dans 3 mois) et écrit le début du mail envoyé au manager avec la fiche de ce mois.
# En octobre, il demande aussi le bilan annuel (mois = 0), car c'est le moment où se décident les créneaux FAA et le
# programme de l'été suivant.
#
# Repères (recherche du 6 novembre 2026) : programme des vols quasi définitif environ 100 jours avant (American),
# recrutement du personnel au sol de l'été 3 à 4 mois avant, dossier des créneaux FAA de l'été à rendre en octobre.
#
# Entrées : aeroport (code IATA, pour le texte) ; langue (« en » par défaut, « fr ») ;
#           aujourd_hui (date ISO, seulement pour les tests ; vide = aujourd'hui).
# Sorties : mois_cible (nombre, 1 à 12), mois_annuel (toujours 0, pour le nœud Code du bilan annuel),
#           annuel (« oui » en octobre), objet et message (début du mail, en anglais par défaut).
from datetime import datetime, timezone

MOIS_FR = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet",
           "août", "septembre", "octobre", "novembre", "décembre"]
MOIS_EN = ["January", "February", "March", "April", "May", "June", "July",
           "August", "September", "October", "November", "December"]
AVANCE = 3  # mois


def main(aeroport: str = "", aujourd_hui: str = "", langue: str = "en") -> dict:
    jour = datetime.fromisoformat(aujourd_hui) if aujourd_hui else datetime.now(timezone.utc)
    ap = "".join(ch for ch in (aeroport or "").upper() if ch.isalpha())[:3]
    cible = (jour.month - 1 + AVANCE) % 12 + 1
    annuel = jour.month == 10
    if (langue or "").strip().lower().startswith("fr"):
        nom = MOIS_FR[cible - 1]
        objet = f"Mini-assistant Delta : préparer {nom} à {ap}"
        message = (f"Bonjour,\n\nVoici la fiche de {nom} pour {ap}. C'est le moment de préparer ce mois : le programme des vols "
                   f"est presque définitif environ 100 jours avant, et les renforts au sol se recrutent 3 à 4 mois avant.\n\n"
                   f"La fiche est calculée par le code. La note de l'IA, en dessous, est une proposition à vérifier avec la checklist "
                   f"avant d'agir.")
        if annuel:
            message += ("\n\nVous recevrez aussi le bilan annuel dans un second mail : les mois difficiles de l'année prochaine. "
                        "Les créneaux FAA et le programme de l'été se décident maintenant.")
        message += "\n\nCe message est envoyé automatiquement le 1er de chaque mois."
    else:
        nom = MOIS_EN[cible - 1]
        objet = f"Delta mini-assistant: prepare {nom} at {ap}"
        message = (f"Hello,\n\nHere is the {nom} briefing for {ap}. Now is the time to prepare this month: the flight schedule "
                   f"is almost final about 100 days ahead, and extra ground staff are hired 3 to 4 months ahead.\n\n"
                   f"The briefing is computed by our code. The AI note below is a suggestion: check it with the checklist "
                   f"before acting.")
        if annuel:
            message += ("\n\nYou will also receive the yearly calendar in a second email: next year's difficult months. "
                        "FAA slots and the summer schedule are decided now.")
        message += "\n\nThis message is sent automatically on the 1st of each month."
    return {"mois_cible": cible, "mois_annuel": 0, "annuel": "oui" if annuel else "non",
            "objet": objet, "message": message}
