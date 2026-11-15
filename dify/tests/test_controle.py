# Tests du nœud « contrôle des chiffres » (hallucinations de l'IA).
import importlib.util
from pathlib import Path

ICI = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("controle", ICI / "noeud_code_controle.py")
controle = importlib.util.module_from_spec(spec)
spec.loader.exec_module(controle)

PROMPT = """DATA
Share of flights delayed in February, by year: 2023 = 10.8% ; 2024 = 8.8% ; 2025 = 17.6% ; 2026 = 11.6%
Delta network average in February: 15.8%
Disruption level: normal (above 25% in 0 year(s) out of 4)"""


def test_tout_est_dans_les_donnees():
    ia = "1. FACTS\n* 2025 = 17.6% ; network 15.8%\nSuggestion 1: monitor – 0 year(s) out of 4\n2. INTERPRETATION"
    out = controle.main(ia, PROMPT)["number_check"]
    assert out.startswith("Number check: all") and "NOT" not in out


def test_difference_juste_permise_fausse_reperee():
    assert "all" in controle.main("* Gap: 17.6 - 15.8 = 1.8 points.\n* Rate 17,6 %", PROMPT)["number_check"]
    # différence négative (« 8.8 - 10.8 = -2.0 ») : juste
    assert "all" in controle.main("* Gap: 8.8 - 10.8 = -2.0 points.", PROMPT)["number_check"]
    assert "wrong" in controle.main("* Gap: 8.8 - 10.8 = 2.0 points.", PROMPT)["number_check"]
    out = controle.main("* Gap: 17.6 - 15.8 = 2.8 points.", PROMPT)["number_check"]
    assert "NOT" in out and "wrong calculation: 17.6 - 15.8 = 2.8" in out


def test_chiffre_invente_repere_meme_s_il_est_dans_les_exemples_des_consignes():
    prompt = PROMPT + "\nROLE: analyst.\nTASK: for example 17.6 - 15.8 = 1.8 points; 42% of delays"
    out = controle.main("* 42% of delays are due to crews.\n* Gap is 1.8 points.", prompt)["number_check"]
    assert "2 number(s)" in out and "- 42 in:" in out and "- 1.8 in:" in out


def test_zeros_et_fiche():
    assert "all" in controle.main("Rate 10.80% then 8.8", PROMPT)["number_check"]
    assert "all" in controle.main("Threshold 42%", PROMPT, fiche="threshold 42 %")["number_check"]
    assert "all" in controle.main("27% chance of storms", PROMPT, imprevu="Chance: 27%")["number_check"]
    assert "no AI note" in controle.main("", PROMPT)["number_check"]


def test_titres_en_gras_et_numeros_de_suggestion_ne_sont_pas_des_chiffres():
    # Faux positifs vus pendant la comparaison des IA (15 novembre 2026)
    ia = ("**1. Facts**\n- 2025 = 17.6%\n**2. Interpretation**\n### 3. Suggestions\n"
          "- Suggestion 1 and Suggestion 2 are recommendations.\n- Suggestions 1 and 2 come from the list.\n"
          "- 17.6%: DATA lines 8 and 9.")
    out = controle.main(ia, PROMPT)["number_check"]
    assert out.startswith("Number check: all"), out
    assert "NOT" in controle.main("**2. Interpretation**\n- 33% of delays.", PROMPT)["number_check"]
