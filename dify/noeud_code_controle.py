# Nœud « Code » de Dify « contrôle des chiffres » : repère les chiffres inventés par l'IA (hallucinations).
# À placer après le LLM des workflows A (et C si on veut). Sans IA : du code simple, donc toujours le même résultat.
#
# Principe : la consigne dit à l'IA de n'utiliser que les chiffres de DATA, ou une différence entre deux d'entre eux
# avec le calcul écrit (« 17.6 - 15.8 = 1.8 points »). Le nœud relève chaque nombre de la note de l'IA et vérifie :
#   - qu'il apparaît dans DATA (le début du prompt, avant « ROLE: », pas les consignes et leurs exemples), dans la
#     fiche ou dans le bloc des imprévus du jour ;
#   - pour une différence écrite « a - b = c » : que a et b sont dans les données et que le résultat c est juste.
# Un nombre absent ou un calcul faux est signalé, avec la ligne où il apparaît.
# Il ne juge pas le sens des phrases : un chiffre juste mal interprété n'est pas repéré. La checklist
# verifier_reponse_IA.md reste nécessaire.
#
# Entrées : ia (LLM / text), prompt (calcul / prompt), fiche (calcul / fiche, facultatif),
#           imprevu (imprévu / imprevu, facultatif : seulement s'il est envoyé à l'IA).
# Sortie  : number_check (texte en anglais). Dans le master « Delta Flight IQ », ajouter cette sortie au nœud Fin de A
#           suffit : elle s'affiche toute seule sous le titre « Number check ».
import re

# Nombre : 36.2, 1,8 (virgule française), 25, 2026… Les signes et les % sont ignorés (« +3.7 pt » = 3.7).
NOMBRE = re.compile(r"(?<![\w.])(\d+(?:[.,]\d+)?)(?![\w])")
# Différence écrite par l'IA : « 17.6 - 15.8 = 1.8 ».
DIFFERENCE = re.compile(r"(\d+(?:[.,]\d+)?)\s*[-\u2212\u2013]\s*(\d+(?:[.,]\d+)?)\s*=\s*([-\u2212\u2013+]?\d+(?:[.,]\d+)?)")
# Numéros de partie ou de liste en début de ligne (« 1. FACTS », « **2. Interpretation** », « ### 3) »), à ne pas contrôler.
NUMERO_DE_LISTE = re.compile(r"^\s*(?:[-*#_]+\s*)?\(?\d{1,2}[.)]\s")

# Seuils écrits dans les consignes elles-mêmes, que l'IA doit citer : « the range is entirely above 50% ».
SEUILS_DES_CONSIGNES = {"50"}


def _normal(n):
    n = n.replace(",", ".")
    if "." in n:
        n = n.rstrip("0").rstrip(".")
    return n.lstrip("0") or "0"


def _nombres(texte):
    return {_normal(n) for n in NOMBRE.findall(texte or "")}


def _valeur(n):
    signe = -1 if n[:1] in "-\u2212\u2013" else 1
    return signe * float(n.lstrip("+-\u2212\u2013").replace(",", "."))


def main(ia: str = "", prompt: str = "", fiche: str = "", imprevu: str = "") -> dict:
    donnees = str(prompt or "").split("ROLE:", 1)[0]  # DATA seulement, sans les exemples des consignes
    connus = _nombres(donnees) | _nombres(fiche) | _nombres(imprevu) | SEUILS_DES_CONSIGNES
    total, absents, faux = 0, [], []
    for ligne in str(ia or "").splitlines():
        for a, b, c in DIFFERENCE.findall(ligne):
            if _normal(a) in connus and _normal(b) in connus:
                if abs(_valeur(a) - _valeur(b) - _valeur(c)) <= 0.051:
                    connus = connus | {_normal(c.lstrip("+-\u2212\u2013"))}  # différence juste entre deux chiffres de DATA : permise
                else:
                    faux.append(f"{a} - {b} = {c}")
        a_lire = NUMERO_DE_LISTE.sub(" ", ligne, count=1)
        # « Suggestion 1 », « Suggestions 1 and 2 », « DATA line 8 », « sentence (3) » : des numéros, pas des chiffres
        a_lire = re.sub(r"\b(Suggestions?|line|lines|sentence|part)\s+\(?\d{1,2}\)?(?:\s*(?:and|,|-)\s*\d{1,2})?", r"\1", a_lire, flags=re.I)
        for brut in NOMBRE.findall(a_lire):
            total += 1
            if _normal(brut) not in connus:
                absents.append((brut, ligne.strip()))
    if not str(ia or "").strip():
        return {"number_check": "Number check: no AI note to check."}
    if faux:
        absents = [(c.split("= ")[1], f"wrong calculation: {c}") for c in faux] + absents
    if not absents:
        return {"number_check": f"Number check: all {total} numbers in the AI note are in the data. "
                                f"Still check the meaning with the checklist."}
    vus, lignes = set(), []
    for brut, ligne in absents:
        if brut in vus:
            continue
        vus.add(brut)
        lignes.append(f"- {brut} in: \"{ligne[:160]}\"")
    return {"number_check": (f"Number check: {len(vus)} number(s) in the AI note are NOT in the data. "
                             f"The AI may have computed or invented them: check or remove before use.\n"
                             + "\n".join(lignes))}
