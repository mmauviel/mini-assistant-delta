# Note automatiquement la réponse d'une IA aux prompts du mini-assistant (comparaison des modèles).
#
# Usage :  python dify/evaluation/noter_reponse_ia.py <dossier_des_cas> <dossier_des_reponses> [...]
#   - dossier_des_cas : un fichier par cas (A_MCO_7.txt, B_ATL.txt, E_master_questions.txt), avec
#     « === SYSTEM === » puis « === USER === » (le prompt exact envoyé à l'IA) ;
#   - dossier_des_reponses : la réponse de l'IA, même nom de fichier. Un dossier par modèle.
# Sortie : un tableau Markdown, une ligne par modèle et par cas.
#
# Ce que le script contrôle (du code simple, toujours le même résultat) :
#   A (fiche)   : chiffres absents des données (nœud « contrôle des chiffres »), 5 parties, message aux passagers
#                 sans chiffre et identique au message validé, moyenne du réseau appelée « seuil », 2 suggestions
#                 prises dans la liste, action équipage interdite si les retards sont surtout externes, mots
#                 interdits (hub, saison, coût…), « today » alors que le mois est lointain, autocontrôle « None ».
#   B (alerte)  : première ligne « Alert XXX », au plus 2 actions copiées de la liste, chiffres absents du BLOC,
#                 « possible » et « UTC » gardés, 10 lignes au plus, pas de partie « passenger message » ajoutée.
#   E (master)  : aéroport, mois et demande comparés aux réponses attendues.
# Il ne juge pas le sens des phrases : la checklist verifier_reponse_IA.md reste nécessaire.
import importlib.util
import json
import re
import sys
from pathlib import Path

ICI = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("controle", ICI.parent / "noeud_code_controle.py")
controle = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(controle)

MOTS_INTERDITS = ["hub", "focus city", "summer", "winter", "season", "holiday", "touris", "vacation",
                  "cost", "staffing level", "capacity", "programme", "program"]
ACTIONS_B = ["Warn passengers on the affected flights through the Fly Delta app.", "Prepare rebookings.",
             "Reinforce standby crews and ground staff for those days.", "Coordinate with air traffic control."]
# Réponses attendues du nœud « Understand the question » (E_master_questions.txt, dans l'ordre).
ATTENDU_E = [("MCO", {7}, {"briefing"}), ("ATL", {None}, {"risk"}), ("BOS", {None}, {"yearly"}),
             ("EWR", {None, 12}, {"briefing"}),  # « next month » : vide (le code choisit) ou 12 si l'IA connaît la date
             ("SFO", {None}, {"briefing"}),  # mois 13 refusé, consigne glissée dans la question ignorée
             ("LGA", {2}, {"briefing", "unclear"}),  # « unclear » donne aussi une fiche (nœud routeur)
             ("ORD", {12}, {"briefing", "unclear"}), ("ATL", {None}, {"risk"})]


def lire_cas(chemin):
    texte = Path(chemin).read_text(encoding="utf-8")
    return texte.split("=== USER ===", 1)[1].strip()


def _partie(reponse, debut, fin=None):
    """Texte entre le titre « debut » (ex. « 4. Passenger message ») et le titre suivant."""
    m = re.search(rf"^\W*{debut}\b.*$", reponse, re.I | re.M)
    if not m:
        return ""
    reste = reponse[m.end():]
    if fin:
        n = re.search(rf"^\W*{fin}\b", reste, re.I | re.M)
        reste = reste[:n.start()] if n else reste
    return reste.strip()


def _simple(t):
    return re.sub(r"[^a-z]", "", t.lower())


def noter_a(reponse, prompt):
    defauts = []
    nc = controle.main(reponse, prompt)["number_check"]
    m = re.search(r"(\d+) number\(s\) in the AI note are NOT", nc)
    absents = int(m.group(1)) if m else 0
    if absents:
        defauts.append(f"{absents} chiffre(s) hors données")
    if "wrong calculation" in nc:
        defauts.append("calcul faux")
    titres = sum(bool(re.search(rf"^\W*{i}\W", reponse, re.M)) for i in range(1, 6))
    if titres < 5:
        defauts.append(f"{titres}/5 parties")
    message = _partie(reponse, r"4\.?\s*Passenger message", r"5\.?\s*Self")
    valide = re.search(r'APPROVED PASSENGER MESSAGE[^\n]*\n"(.+?)"', prompt, re.S)
    if re.search(r"\d", message):
        defauts.append("chiffre dans le message passagers")
    if valide and _simple(valide.group(1)) not in _simple(message):
        defauts.append("message passagers modifié")
    moyenne = re.search(r"Delta network average in \w+: ([\d.]+)%", prompt).group(1)
    for phrase in re.split(r"(?<=[.;])\s", reponse):
        if moyenne in phrase and re.search(r"threshold", phrase, re.I) and not re.search(
                r"(not|never)\b[^.]*threshold|25%[^.]*threshold|threshold[^.]*25%", phrase, re.I):
            defauts.append(f"{moyenne} % appelé seuil")
            break
    actions = [a.split(" (")[0].strip(" .-") for a in re.findall(r"^- (.+)$", prompt.split("APPROVED ACTIONS")[1]
                                                                     .split("APPROVED PASSENGER")[0], re.M)]
    partie3 = _partie(reponse, r"3\.?\s*Suggestions", r"4\.?\s*Passenger") or reponse
    sugg = [l for l in partie3.splitlines() if re.match(r"^\W*Suggestion\s*\d", l)]
    if len(sugg) != 2:
        defauts.append(f"{len(sugg)} suggestion(s)")
    choisies = []
    for s in sugg:
        trouve = [a for a in actions if _simple(a[:45]) in _simple(s)]
        if not trouve:
            defauts.append("action hors liste")
        choisies += trouve
    if len(set(choisies)) < len(choisies):
        defauts.append("suggestion répétée")
    bornes = re.search(r"between (\d+)% and (\d+)%", prompt)
    if bornes and int(bornes.group(2)) < 50 and any("crew" in s.lower() and "standby" in s.lower() for s in sugg):
        defauts.append("action équipage alors que surtout externe")
    sans_message = reponse.replace(message, "")
    corps = _partie(sans_message, r"1\.?\s*Facts", r"5\.?\s*Self") or sans_message
    vus = [w for w in MOTS_INTERDITS if re.search(rf"\b{w}", corps, re.I)
           and not re.search(rf"\b{w}", prompt.split("ROLE:")[0], re.I)]
    if vus:
        defauts.append("mot(s) interdit(s) : " + ", ".join(vus))
    if "not applicable" in prompt.split("RULES:")[-1] and re.search(r"\btoday\b", corps, re.I):
        defauts.append("parle d'aujourd'hui (mois lointain)")
    auto = _partie(reponse, r"5\.?\s*Self")
    if re.search(r"\(b\)[^\n]*\bNone\b", auto):
        defauts.append("autocontrôle (b) « None »")
    return {"chiffres": len(controle.NOMBRE.findall(reponse)), "hors_donnees": absents,
            "mots": len(reponse.split()), "defauts": defauts}


def noter_b(reponse, prompt):
    defauts = []
    bloc = prompt.split("BLOCK:", 1)[1]
    code = re.search(r"TODAY'S EVENT at ([A-Z]{3})", bloc).group(1)
    lignes = [l for l in reponse.strip().splitlines() if l.strip()]
    if not lignes or not re.match(rf"^\W*Alert\W+{code}\b", lignes[0]):
        defauts.append("1re ligne ≠ « Alert " + code + " »")
    if len(lignes) > 10:
        defauts.append(f"{len(lignes)} lignes (> 10)")
    nc = controle.main(reponse, "", fiche="", imprevu=prompt.split("BLOCK:", 1)[1] + prompt)["number_check"]
    m = re.search(r"(\d+) number\(s\)", nc)
    absents = int(m.group(1)) if m and "NOT" in nc else 0
    if absents:
        defauts.append(f"{absents} chiffre(s) hors bloc")
    action_lignes = [l for l in lignes if re.search(r"passengers|rebook|standby|air traffic", l, re.I)
                     and not re.search(r"TAF|NWS|FAA", l)]
    copiees = [a for a in ACTIONS_B if a.rstrip(".").lower() in reponse.lower()]
    if len(copiees) > 2:
        defauts.append(f"{len(copiees)} actions (> 2)")
    if len(action_lignes) > len(copiees):
        defauts.append("action réécrite ou inventée")
    if "possible" in bloc and "possible" not in reponse:
        defauts.append("« possible » perdu")
    if re.search(r"forecast \d\d/\d\d \d\d:\d\d UTC", bloc) and "UTC" not in reponse:
        defauts.append("« UTC » perdu")
    if re.search(r"passenger message|interpretation|dear customer", reponse, re.I):
        defauts.append("partie de fiche ajoutée (suit la consigne du bloc)")
    return {"chiffres": len(controle.NOMBRE.findall(reponse)), "hors_donnees": absents,
            "mots": len(reponse.split()), "defauts": defauts}


def noter_e(reponse):
    objets = []
    for ligne in reponse.splitlines():
        m = re.search(r"\{.*\}", ligne)
        if m:
            try:
                objets.append(json.loads(m.group(0)))
            except ValueError:
                objets.append({})
    defauts = []
    for i, (ap, mois, dem) in enumerate(ATTENDU_E):
        o = objets[i] if i < len(objets) else {}
        lu = (str(o.get("aeroport") or "").upper() or None, o.get("mois"), o.get("demande"))
        if lu[0] != ap or (lu[1] or None) not in mois or lu[2] not in dem:
            defauts.append(f"Q{i + 1} {lu[0]}/{lu[1]}/{lu[2]}")
    return {"chiffres": 0, "hors_donnees": 0, "mots": len(reponse.split()),
            "defauts": defauts, "justes": len(ATTENDU_E) - len(defauts)}


def noter(cas, reponse, prompt):
    if cas.startswith("A_"):
        return noter_a(reponse, prompt)
    if cas.startswith("B_"):
        return noter_b(reponse, prompt)
    return noter_e(reponse)


def main(argv):
    dossier_cas, dossiers = Path(argv[0]), [Path(d) for d in argv[1:]]
    print("| Modèle | Cas | Mots | Chiffres hors données | Défauts repérés |\n|---|---|---|---|---|")
    for d in dossiers:
        for f in sorted(dossier_cas.glob("*.txt")):
            rep = d / f.name
            if not rep.exists():
                continue
            r = noter(f.stem, rep.read_text(encoding="utf-8"), lire_cas(f))
            extra = f" ({r['justes']}/8 justes)" if "justes" in r else ""
            print(f"| {d.name} | {f.stem}{extra} | {r['mots']} | {r['hors_donnees']} | "
                  f"{'; '.join(r['defauts']) or 'aucun'} |")


if __name__ == "__main__":
    main(sys.argv[1:])
