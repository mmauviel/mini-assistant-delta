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


def test_consignes_sans_mot_a_recopier():
    # Fiche à la demande, MCO juillet : l'IA avait écrit « quoting 60% » et 8 faits au lieu de 3 à 5.
    juillet = calcul.main(BTS, SUIVI, "MCO", 7)["prompt"]
    assert "quoting the" not in juillet and "never write the word \"quoting\"" in juillet
    assert "3 to 5 bullet points, never more" in juillet


# --- coût des retards (colonne arr_delay) ----------------------------------------------------------------------------

def _avec_minutes(minutes_par_an):
    """Fichier BTS réduit à MCO en juillet, avec la colonne arr_delay (minutes) donnée pour chaque année."""
    lignes = ["year,month,airport,airport_name,arr_flights,arr_del15,carrier_ct,late_aircraft_ct,nas_ct,weather_ct,arr_delay"]
    for y, mn in minutes_par_an.items():
        lignes.append(f'{y},7,MCO,"Orlando, FL: Orlando International",1000,300,100,80,100,20,{mn}')
        lignes.append(f'{y},1,MCO,"Orlando, FL: Orlando International",1000,100,40,20,30,10,1000')
    return "\n".join(lignes)


def test_cout_des_retards_dans_la_fiche():
    fiche = calcul.main(_avec_minutes({2024: 40000, 2025: 60000}), "", "MCO", 7)["fiche"]
    # moyenne 50 000 min × 98,41 $ = 4,92 M$ ; maximum 60 000 min en 2025 = 5,90 M$
    assert "Estimated cost of arrival delays in July: about $4.9 M per year on average, up to $5.9 M in 2025" in fiche
    assert "$98.41 per minute, A4A 2025" in fiche
    fr = calcul.main(_avec_minutes({2024: 40000, 2025: 60000}), "", "MCO", 7, "fr")["fiche"]
    assert "environ 4,9 M $ par an en moyenne, jusqu'à 5,9 M $ en 2025" in fr


def test_cout_dans_le_bilan_annuel():
    fiche = calcul.main(_avec_minutes({2024: 40000, 2025: 60000}), "", "MCO", 0)["fiche"]
    assert "Delay cost / year |" in fiche and "| $4.9 M |" in fiche and "| $98 k |" in fiche
    assert "about $5.0 M per year at MCO, including $4.9 M (98%) in the months to prepare" in fiche


def test_sans_colonne_arr_delay_pas_de_cout():
    # données publiées avant l'ajout de la colonne : la fiche reste la même qu'avant
    import csv
    import io
    lignes = list(csv.reader(io.StringIO(BTS)))
    if "arr_delay" in lignes[0]:
        i = lignes[0].index("arr_delay")
        lignes = [l[:i] + l[i + 1:] for l in lignes]
    sortie = io.StringIO()
    csv.writer(sortie).writerows(lignes)
    sans = sortie.getvalue()
    assert "cost" not in calcul.main(sans, SUIVI, "MCO", 7)["fiche"].lower()
    assert "Delay cost" not in calcul.main(sans, SUIVI, "MCO", 0)["fiche"]


# Corrections après la comparaison des IA (15 novembre 2026, docs/COMPARAISON_IA.md)
import csv
import re

AEROPORTS = sorted({r["airport"] for r in csv.DictReader(open(DONNEES / "Airline_Delay_Cause.csv", encoding="utf-8"))})


def _actions(prompt):
    return re.findall(r"^- (.+)$", prompt.split("APPROVED ACTIONS")[1].split("APPROVED PASSENGER")[0], re.M)


def test_retards_externes_pas_d_action_equipage_et_action_systeme_aerien():
    vus = 0
    for ap in AEROPORTS:
        for mois in range(1, 13):
            prompt = calcul.main(BTS, SUIVI, ap, mois)["prompt"]
            bornes = re.search(r"Delta controls[^:]*: between (\d+)% and (\d+)%", prompt)
            if not bornes or int(bornes.group(2)) >= 50:
                continue
            vus += 1
            actions = _actions(prompt)
            assert not any(a.startswith("Reinforce standby crews") for a in actions), (ap, mois)
            assert any(a.startswith("Prepare rebookings") for a in actions), (ap, mois)
            assert "do not choose crew" not in prompt  # plus de règle impossible à suivre
    assert vus > 50


def test_exemple_de_difference_juste_avec_les_chiffres_arrondis():
    for ap in ("LGA", "MCO", "ATL", "SFO", "BOS"):
        for mois in range(1, 13):
            a, b, c = re.search(r"for example: ([\d.]+) - ([\d.]+) = (-?[\d.]+) points",
                                calcul.main(BTS, SUIVI, ap, mois)["prompt"]).groups()
            assert abs(float(a) - float(b) - float(c)) < 0.001, (ap, mois, a, b, c)


def test_definition_ponctuelle_couvre_deux_annees_non_consecutives():
    prompt = calcul.main(BTS, SUIVI, "MCO", 7)["prompt"]
    assert "one-off = one year, or two years that are not in a row" in prompt
    assert "one-off = a single year" not in prompt and "one-off = a single year" not in calcul.main(BTS, SUIVI, "MCO", 0)["prompt"]
    assert "never by a line number" in prompt
