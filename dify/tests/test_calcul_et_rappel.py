# Tests des nœuds « calcul » et « rappel » : l'anglais est la langue par défaut, le français reste possible.
import importlib.util
from pathlib import Path

ICI = Path(__file__).resolve().parents[1]
DONNEES = ICI.parent / "donnees"


def charger(nom):
    spec = importlib.util.spec_from_file_location(nom, ICI / f"{nom}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


calcul = charger("noeud_code_calcul")
rappel = charger("noeud_code_rappel")
BTS = (DONNEES / "Airline_Delay_Cause.csv").read_text(encoding="utf-8")
SUIVI = (DONNEES / "suivi_mainline.csv").read_text(encoding="utf-8")


def test_fiche_en_anglais_par_defaut():
    out = calcul.main(BTS, SUIVI, "MCO", 7)
    assert out["fiche"].startswith("# Operational briefing: MCO, July")
    assert "Write your whole answer in English" in out["prompt"]
    assert calcul.main(BTS, SUIVI, "MCO", 7, "")["fiche"] == out["fiche"]
    assert calcul.main(BTS, SUIVI, "MCO", 0)["fiche"].startswith("# Annual review: MCO")
    assert calcul.main(BTS, SUIVI, "MCO", 13)["fiche"].startswith("The month must be")


def test_fiche_en_francais_sur_demande():
    out = calcul.main(BTS, SUIVI, "MCO", 7, "fr")
    assert out["fiche"].startswith("# Fiche opérationnelle : MCO, juillet")
    assert "Write your whole answer in French" in out["prompt"]
    assert calcul.main(BTS, SUIVI, "MCO", 13, "fr")["fiche"].startswith("Le mois doit")


def test_rappel_en_anglais_par_defaut():
    avril = rappel.main("MCO", "2027-04-01")
    assert avril["mois_cible"] == 7 and avril["annuel"] == "non"
    assert avril["objet"] == "Delta mini-assistant: prepare July at MCO"
    assert avril["message"].startswith("Hello") and "yearly calendar" not in avril["message"]
    octobre = rappel.main(" mco ", "2026-10-01")
    assert octobre["mois_cible"] == 1 and octobre["annuel"] == "oui" and "yearly calendar" in octobre["message"]
    francais = rappel.main("MCO", "2027-04-01", "fr")
    assert francais["objet"] == "Mini-assistant Delta : préparer juillet à MCO" and francais["message"].startswith("Bonjour")
