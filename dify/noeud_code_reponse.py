# Nœud « Code » du master workflow « Delta Flight IQ » : met en forme, pour le chat, ce que renvoie un outil
# (workflow A ou B publié comme outil, « Workflow as Tool »).
#
# Pourquoi un nœud à part : un workflow publié comme outil renvoie toutes ses sorties (nœud Fin) d'un bloc, en JSON
# dans la sortie `text` de l'outil. Ce nœud les remet dans l'ordre et en Markdown. Toute sortie AJOUTÉE plus tard
# dans A ou B (coût des retards en dollars, niveau de risque 70/30, règles Delta trouvées par le RAG…) s'affiche
# toute seule à la fin, sous son nom : le master n'a pas à changer.
#
# Entrées : resultat (sortie `text` de l'outil), message (sortie `message` du nœud « routeur »).
# Sortie  : reponse (texte Markdown en anglais, affiché par le nœud Réponse).
import json

# Sorties connues, dans l'ordre d'affichage, avec leur titre. Les autres suivent, titrées d'après leur nom.
CONNUES = [
    ("fiche", ""),                     # A : la fiche (elle a déjà son propre titre)
    ("alerte", ""),                    # B en direct : le texte de l'IA (il commence déjà par « Alert MCO: »)
    ("note_ia", "AI note (to check before acting)"),
    ("imprevus", "Live data used"),    # A : ce que disent les API du jour
    ("donnees", "Live data used"),     # B en direct : le résumé des API
]
# Le nœud « imprévu » ajoute cette phrase quand la fiche porte sur un autre mois : la météo du jour ne sert alors à
# rien dans le chat, on ne l'affiche pas.
HORS_SUJET = "(Not sent to the AI"
MAX_SORTIE = 20000  # caractères : au-delà, la réponse est coupée (le chat de Dify reste lisible)


def _titre(nom):
    return str(nom).replace("_", " ").strip().capitalize()


def _lire(resultat):
    """Rend un dict des sorties de l'outil, ou None si ce n'est pas du JSON objet."""
    if isinstance(resultat, dict):
        return resultat
    if isinstance(resultat, list):  # sortie `json` de l'outil : une liste d'objets
        fusion = {}
        for el in resultat:
            if isinstance(el, dict):
                fusion.update(el)
        return fusion or None
    try:
        lu = json.loads(str(resultat or ""))
    except (TypeError, ValueError):
        return None
    return _lire(lu) if isinstance(lu, (dict, list)) else None


def _texte(valeur):
    if valeur is None:
        return ""
    if isinstance(valeur, str):
        return valeur.strip()
    return json.dumps(valeur, ensure_ascii=False, indent=2)


def main(resultat: str = "", message: str = "") -> dict:
    parties = [str(message or "").strip()] if str(message or "").strip() else []
    sorties = _lire(resultat)
    if sorties is None:
        brut = str(resultat or "").strip()
        parties.append(brut or "The workflow returned nothing. Please try again in a minute.")
    else:
        deja = set()
        avant = len(parties)
        for nom, titre in CONNUES:
            contenu = _texte(sorties.get(nom))
            if nom in ("imprevus", "donnees") and HORS_SUJET in contenu:
                continue
            if contenu and contenu not in deja:  # imprevus et donnees peuvent être le même texte
                parties.append(f"### {titre}\n\n{contenu}" if titre else contenu)
                deja.add(contenu)
        for nom, valeur in sorties.items():
            if nom in dict(CONNUES):
                continue
            contenu = _texte(valeur)
            if contenu:
                parties.append(f"### {_titre(nom)}\n\n{contenu}")
        if len(parties) == avant:
            parties.append("The workflow ran but returned no text.")
    reponse = "\n\n".join(parties)
    if len(reponse) > MAX_SORTIE:
        reponse = reponse[:MAX_SORTIE] + "\n\n(cut: the full result is in the workflow logs)"
    return {"reponse": reponse}
