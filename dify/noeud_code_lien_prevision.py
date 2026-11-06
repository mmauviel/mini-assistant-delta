# Nœud « Code » de Dify « lien prévision » : entre les deux requêtes vers api.weather.gov (service météo américain).
# La première requête (/points/<lat>,<lon>) renvoie l'adresse de la prévision à 7 jours de la zone de l'aéroport ;
# ce nœud la lit pour que la deuxième requête aille la chercher.
# Entrée : points (corps de la réponse de https://api.weather.gov/points/<lat>,<lon>).
# Sortie : url (adresse de la prévision à 7 jours, ou adresse vide si la réponse est illisible).
import json

PREFIXE = "https://api.weather.gov/"


def main(points: str) -> dict:
    try:
        url = json.loads(points)["properties"]["forecast"]
    except (TypeError, ValueError, KeyError):
        return {"url": ""}
    # on ne suit que les adresses du service météo lui-même
    return {"url": url if isinstance(url, str) and url.startswith(PREFIXE) else ""}
