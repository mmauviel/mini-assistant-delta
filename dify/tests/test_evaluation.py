# Tests du script de note des réponses d'IA (docs/COMPARAISON_IA.md).
import importlib.util
from pathlib import Path

EVAL = Path(__file__).resolve().parents[1] / "evaluation"
spec = importlib.util.spec_from_file_location("noter", EVAL / "noter_reponse_ia.py")
noter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(noter)


def _note(dossier_cas, modele, cas):
    prompt = noter.lire_cas(EVAL / dossier_cas / f"{cas}.txt")
    return noter.noter(cas, (EVAL / modele / f"{cas}.txt").read_text(encoding="utf-8"), prompt)


def test_reponses_apres_correction_sans_defaut():
    for modele in ("claude_haiku", "claude_sonnet", "claude_opus"):
        for f in sorted((EVAL / "cas").glob("*.txt")):
            r = _note("cas", f"reponses_apres/{modele}", f.stem)
            assert r["defauts"] == [], (modele, f.stem, r["defauts"])


def test_repere_la_regle_impossible_d_avant():
    # Avec l'ancien prompt de SFO, Haiku ne donnait aucune suggestion et Sonnet une seule.
    assert "0 suggestion(s)" in _note("cas_avant", "reponses_avant/claude_haiku", "A_SFO_7")["defauts"]
    assert "1 suggestion(s)" in _note("cas_avant", "reponses_avant/claude_sonnet", "A_SFO_7")["defauts"]


def test_defauts_classiques_reperes():
    prompt = noter.lire_cas(EVAL / "cas" / "A_MCO_7.txt")
    bonne = (EVAL / "reponses_apres/claude_sonnet/A_MCO_7.txt").read_text(encoding="utf-8")
    mauvaise = bonne.replace("Dear Customer,", "Dear Customer, 32.8% of flights were late, a summer issue.", 1)
    mauvaise = mauvaise.replace("25%", "25.2% threshold", 1)
    d = noter.noter("A_MCO_7", mauvaise, prompt)["defauts"]
    assert "chiffre dans le message passagers" in d and "message passagers modifié" in d
    alerte = noter.noter("B_MCO", "Snow at MCO.\n- Offer free hotels.", noter.lire_cas(EVAL / "cas" / "B_MCO.txt"))
    assert any("1re ligne" in x for x in alerte["defauts"])
