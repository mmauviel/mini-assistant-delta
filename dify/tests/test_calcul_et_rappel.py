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


def test_mois_normal_et_aucune_hausse():
    fevrier = calcul.main(BTS, SUIVI, "MCO", 2)  # MCO en février : sous 25 % chaque année, aucune cause en hausse
    assert "**Normal month**: above 25% in 0 year(s) out of 4" in fevrier["fiche"]
    assert "No cause rises above the airport's average this month." in fevrier["fiche"]
    assert "Cause rising most" not in fevrier["fiche"] and "One-off" not in fevrier["fiche"]
    assert "Disruption level: normal" in fevrier["prompt"] and "Cause rising most: none" in fevrier["prompt"]
    assert "If there is no such block" in fevrier["prompt"]
    assert "**Mois normal**" in calcul.main(BTS, SUIVI, "MCO", 2, "fr")["fiche"]
    juillet = calcul.main(BTS, SUIVI, "MCO", 7)
    assert "**Recurring disruption**" in juillet["fiche"] and "Cause rising most: **airline**" in juillet["fiche"]


def test_rappel_mois_normal():
    assert "Normal month" in rappel.main("MCO", "2026-11-01")["message"]
    assert "Mois normal" in rappel.main("MCO", "2026-11-01", "fr")["message"]


def test_autant_de_suggestions_que_d_actions():
    fevrier = calcul.main(BTS, SUIVI, "MCO", 2)["prompt"]  # une seule action approuvée
    assert "SUGGESTIONS – exactly 1 (there is only one approved action: do not repeat it)" in fevrier
    assert "The suggestion applies in real time" in fevrier
    juillet = calcul.main(BTS, SUIVI, "MCO", 7)["prompt"]
    assert "SUGGESTIONS – exactly 2, most useful first" in juillet and "Both suggestions are part of a plan" in juillet


def test_action_de_repli_sans_chiffre_et_mots_simples():
    # Mail du 1er novembre (MCO, février) : « – 0.5% » au bout de la suggestion et « wholely » dans l'interprétation.
    fevrier = calcul.main(BTS, SUIVI, "MCO", 2)["prompt"]
    assert "fallback action: no cause rises" in fevrier and "addresses: extreme weather" not in fevrier
    assert "a fallback action addresses no rising cause, so it gets no number" in fevrier
    assert "no suggestion is repeated" in fevrier
    assert "entirely above 50%" in fevrier and "whole range" not in fevrier
    juillet = calcul.main(BTS, SUIVI, "MCO", 7)["prompt"]  # une vraie hausse : la suggestion garde son chiffre
    assert "[timing] – [the number from DATA it addresses]" in juillet and "fallback" not in juillet
