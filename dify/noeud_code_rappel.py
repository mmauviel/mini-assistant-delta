# Nœud « Code » de Dify « rappel » : le workflow planifié du 1er de chaque mois (déclencheur Schedule).
# Il calcule le mois à préparer (dans 3 mois) et écrit le début du mail envoyé au manager avec la fiche de ce mois.
# En octobre, il demande aussi le bilan annuel (mois = 0), car c'est le moment où se décident les créneaux FAA et le
# programme de l'été suivant.
#
# Repères (recherche du 6 novembre 2026) : programme des vols quasi définitif environ 100 jours avant (American),
# recrutement du personnel au sol de l'été 3 à 4 mois avant, dossier des créneaux FAA de l'été à rendre en octobre.
#
# Entrées : aeroport (code IATA, pour le texte) ; aujourd_hui (date ISO, seulement pour les tests ; vide = aujourd'hui).
# Sorties : mois_cible (nombre, 1 à 12), mois_annuel (toujours 0, pour le nœud Code du bilan annuel),
#           annuel (« oui » en octobre), objet et message (début du mail, en français).
from datetime import datetime, timezone

MOIS_FR = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet",
           "août", "septembre", "octobre", "novembre", "décembre"]
AVANCE = 3  # mois


def main(aeroport: str = "", aujourd_hui: str = "") -> dict:
    jour = datetime.fromisoformat(aujourd_hui) if aujourd_hui else datetime.now(timezone.utc)
    ap = "".join(ch for ch in (aeroport or "").upper() if ch.isalpha())[:3]
    cible = (jour.month - 1 + AVANCE) % 12 + 1
    annuel = jour.month == 10
    nom = MOIS_FR[cible - 1]
    message = (f"Bonjour,\n\nVoici la fiche de {nom} pour {ap}. C'est le moment de préparer ce mois : le programme des vols "
               f"est presque définitif environ 100 jours avant, et les renforts au sol se recrutent 3 à 4 mois avant.\n\n"
               f"La fiche est calculée par le code. La note de l'IA, en dessous, est une proposition à vérifier avec la checklist "
               f"avant d'agir.")
    if annuel:
        message += ("\n\nVous recevrez aussi le bilan annuel dans un second mail : les mois difficiles de l'année prochaine. "
                    "Les créneaux FAA et le programme de l'été se décident maintenant.")
    message += "\n\nCe message est envoyé automatiquement le 1er de chaque mois."
    return {"mois_cible": cible, "mois_annuel": 0, "annuel": "oui" if annuel else "non",
            "objet": f"Mini-assistant Delta : préparer {nom} à {ap}",
            "message": message}
