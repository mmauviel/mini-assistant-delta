# Tests du nœud « mail » : mise en page HTML des mails des workflows B et C, et version texte.
import importlib.util
import re
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
mail = charger("noeud_code_mail")
BTS = (DONNEES / "Airline_Delay_Cause.csv").read_text(encoding="utf-8")
SUIVI = (DONNEES / "suivi_mainline.csv").read_text(encoding="utf-8")

ALERTE = """Alert MCO: Thunderstorms are possible on Veterans Day (11/11).
- Veterans Day (11/11): thunderstorms possible (46% chance of precipitation).
Warn passengers on the affected flights through the Fly Delta app.
Prepare rebookings."""
DONNEES_DIRECT = """Live events at MCO (FAA and official weather forecasts)
- FAA: no ground stop, ground delay program or reported delay at this airport right now.
- Next 7 days (National Weather Service, area forecast): thunderstorms possible Veterans Day (11/11), 46% chance of precipitation."""


def passe_le_plugin(html):
    """Le plugin Email (« Convert to HTML ») lit le contenu comme du Markdown, ligne par ligne :
    une seule ligne, sans caractère qu'il transformerait."""
    return "\n" not in html and not re.search(r"[*`\[\]]", html) and not html.lstrip().startswith(("#", "-", "|", ">"))


def test_alerte():
    out = mail.main("alert", "MCO", ALERTE, DONNEES_DIRECT, aujourd_hui="2026-11-11")
    assert passe_le_plugin(out["html"])
    assert "#003366" in out["html"] and "#C01933" in out["html"]  # Delta Blue, Delta Red
    assert "Thunderstorms are possible on Veterans Day (11/11)." in out["html"]
    assert "Prepare rebookings." in out["html"]
    assert "46% chance of precipitation" in out["html"]
    assert out["apercu"] == "Thunderstorms are possible on Veterans Day (11/11)."
    assert "WHAT TO DO" in out["texte"] and "[ ] Prepare rebookings." in out["texte"]
    assert "Wednesday 11 November 2026" in out["texte"]


def test_fiche_du_mois():
    fiche = calcul.main(BTS, SUIVI, "MCO", 7)["fiche"]
    intro = rappel.main("MCO", "2026-04-01")["message"]
    out = mail.main("briefing", "MCO", "1. FACTS\n- Delta network average in July: 25.2%", "", intro, fiche)
    assert passe_le_plugin(out["html"])
    assert "Recurring disruption" in out["html"] and "Next step" in out["html"]
    for chiffre in ("36.2%", "34.4%", "32.8%", "12.8%", "9.1%"):  # les chiffres de la fiche sont tous là
        assert chiffre in out["html"]
    assert "AI note" in out["html"] and "FACTS" in out["html"]
    assert out["apercu"].startswith("Recurring disruption at MCO in July")
    assert "36.2%" in out["texte"] and "AI NOTE" in out["texte"]


def test_mois_normal_et_bilan_annuel():
    out = mail.main("briefing", "MCO", "", "", "", calcul.main(BTS, SUIVI, "MCO", 2)["fiche"])
    assert "Normal month" in out["html"] and "No special preparation needed" in out["html"]
    annuel = mail.main("briefing", "MCO", "", "", "", calcul.main(BTS, SUIVI, "MCO", 0)["fiche"])
    assert passe_le_plugin(annuel["html"])
    assert "Annual review" in annuel["html"] and "Months to prepare" in annuel["html"]
    assert "AI note" not in annuel["html"]  # pas de note vide


def test_texte_du_llm_echappe():
    """Le texte du LLM ne peut pas injecter de HTML, et une adresse de logo non https est ignorée."""
    out = mail.main("alert", "MCO", "Alert MCO: <script>alert(1)</script> **storm**", "", logo="javascript:alert(1)")
    assert "<script>" not in out["html"] and "&lt;script&gt;" in out["html"]
    assert "javascript:" not in out["html"]
    assert "raw.githubusercontent.com/mmauviel/mini-assistant-delta" in out["html"]


def test_en_francais():
    fiche = calcul.main(BTS, SUIVI, "MCO", 7, "fr")["fiche"]
    out = mail.main("briefing", "MCO", "", "", rappel.main("MCO", "2026-04-01", "fr")["message"], fiche)
    assert "Perturbation récurrente" in out["html"] and "À faire" in out["html"]


def test_genre_deduit():
    """Dify n'accepte pas de texte fixe en entrée : sans genre, une fiche = briefing, sinon alerte."""
    alerte = mail.main(aeroport="MCO", ia=ALERTE, donnees=DONNEES_DIRECT)
    assert "Weather and FAA alert" in alerte["html"]
    fiche = mail.main(aeroport="MCO", fiche=calcul.main(BTS, SUIVI, "MCO", 2)["fiche"])
    assert "Normal month" in fiche["html"] and "Weather and FAA alert" not in fiche["html"]
