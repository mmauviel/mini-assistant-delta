"""Tests des 6 améliorations du mail « Alerte du matin » (sortie « evenements » du nœud imprévu + nœud mail),
sur le cas réel de MCO du 18-19 novembre 2026."""
import importlib.util
import json
import re
import sys
from pathlib import Path

ICI = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent / "exemples"))
import mco_19_11_2026 as ex  # noqa: E402


def charger(nom):
    spec = importlib.util.spec_from_file_location(nom, ICI / f"{nom}.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


imprevu, mail = charger("noeud_code_imprevu"), charger("noeud_code_mail")
PHRASE = "Alert MCO: Thunderstorms are forecast on Thursday 19/11."


def evenements(taf=ex.TAF, faa=ex.SANS_FAA, nws=ex.NWS, quand=ex.MAINTENANT):
    return imprevu.main("MCO", taf, faa, prevision=nws, aujourd_hui=quand)["evenements"]


def test_codes_meteo_en_mots():
    assert imprevu.temps_en_mots("-SHRA VCTS") == "light rain showers, thunderstorms nearby"
    assert imprevu.temps_en_mots("SHRA BR") == "rain showers, mist"
    assert imprevu.temps_en_mots("+TSRA") == "heavy thunderstorm with rain"
    assert imprevu.temps_en_mots("FZRA FZFG") == "freezing rain, freezing fog"
    assert imprevu.temps_en_mots("VCSH") == "showers nearby"
    assert imprevu.temps_en_mots("XYZQ") == "XYZQ"  # code inconnu : laissé tel quel, rien d'inventé


def test_creneaux_qui_se_suivent_fusionnes():
    taf, err = imprevu.taf_creneaux(ex.TAF)
    assert err is None
    orages = [c for c in taf if "thunderstorm" in c["risques"]]
    assert len(orages) == 1  # 15:00-18:00 puis 18:00-01:00 = un seul créneau
    assert f"{orages[0]['debut']:%d/%m %H:%M}" == "19/11 15:00" and f"{orages[0]['fin']:%d/%m %H:%M}" == "20/11 01:00"
    nws, _ = imprevu.nws_creneaux(ex.NWS)
    assert len(nws) == 1 and nws[0]["noms"] == ["Tonight (18/11)", "Thursday (19/11)", "Thursday Night (19/11)", "Friday (20/11)"]


def test_heure_locale_a_cote_de_l_utc():
    ev = json.loads(evenements())
    orage = [l for l in ev["lignes"] if l["source"] == "TAF" and l["risque"] == "thunderstorm"][0]
    assert orage["quand_utc"] == "19/11 15:00 to 20/11 01:00 UTC"
    assert orage["quand_local"] == "Thu 19/11 10:00 to 20:00 MCO time"  # Orlando = UTC-5 en novembre
    plafond = [l for l in ev["lignes"] if "ceiling 900 ft" in l["detail"]][0]
    assert plafond["quand_local"] == "Thu 19/11 03:00 to 10:00 MCO time"


def test_heure_locale_suit_le_changement_d_heure():
    decs = imprevu.decalages(json.dumps({"properties": {"periods": [
        {"startTime": "2026-03-07T18:00:00-05:00", "endTime": "2026-03-08T06:00:00-04:00"},
        {"startTime": "2026-03-08T06:00:00-04:00", "endTime": "2026-03-08T18:00:00-04:00"}]}}))
    from datetime import datetime, timezone
    assert imprevu.locale(datetime(2026, 3, 8, 15, tzinfo=timezone.utc), decs).hour == 11


def test_une_seule_liste_avec_la_source_et_faa_en_tete():
    ev = json.loads(evenements())
    assert ev["faa"]["etat"] == "clear"
    assert {l["source"] for l in ev["lignes"]} == {"TAF", "NWS"}
    assert [l["debut"] for l in ev["lignes"]] == sorted(l["debut"] for l in ev["lignes"])
    assert "rain showers, mist" in json.dumps(ev) and "VCTS" not in json.dumps(ev)  # codes traduits


def test_niveau_de_risque():
    assert json.loads(evenements())["niveau"] == "High"  # orage dans la prévision de l'aéroport
    calme = json.dumps([{"fcsts": [{"timeFrom": "2026-11-18T23:00:00Z", "timeTo": "2026-11-20T00:00:00Z",
                                    "visib": "6+", "clouds": [{"cover": "OVC", "base": 800}]}]}])
    assert json.loads(evenements(taf=calme, nws=""))["niveau"] == "Medium"  # plafond bas seulement
    chance = ex.NWS.replace("Showers And Thunderstorms", "Chance Showers And Thunderstorms")
    sans_taf = json.dumps([{"fcsts": []}])
    assert json.loads(evenements(taf=sans_taf, nws=chance))["niveau"] == "Low"  # « possible » seulement
    faa = ("<AIRPORT_STATUS_INFORMATION><Delay_type><Ground_Stop_List><Program><ARPT>MCO</ARPT><Reason>wx</Reason>"
           "<End_Time>5 pm</End_Time></Program></Ground_Stop_List></Delay_type></AIRPORT_STATUS_INFORMATION>")
    ev = json.loads(evenements(taf=sans_taf, faa=faa, nws=""))
    assert ev["niveau"] == "High" and ev["faa"]["etat"] == "active"


def test_actions_liees_aux_creneaux():
    actions = json.loads(evenements())["actions"]
    assert actions[0] == "Warn passengers on flights Thu 19/11 10:00 to 20:00 MCO time through the Fly Delta app."
    assert "Prepare rebookings for flights Thu 19/11 10:00 to 20:00 MCO time." in actions
    assert len(actions) <= 4 and len(set(actions)) == len(actions)


def test_mail_sans_doublon_et_stylise():
    out = mail.main(aeroport="MCO", ia=PHRASE, evenements=evenements(), aujourd_hui="2026-11-19")
    h = out["html"]
    assert "\n" not in h and not re.search(r"[*`\[\]]", h)  # passe le plugin Email (Convert to HTML)
    assert "High risk" in h and "#C01933" in h and "FAA live status" in h
    assert h.count("Thu 19/11 10:00 to 20:00") == 1 + 2  # une ligne dans la liste + deux actions
    assert "Live events" not in h  # l'ancien bloc en double a disparu
    assert "Thunderstorms are forecast on Thursday 19/11." in h and "Alert MCO:" not in h
    assert out["apercu"].startswith("High risk:")
    t = out["texte"]
    assert t.count("19/11 15:00 to 20/11 01:00 UTC") == 1 and "[ ] Prepare rebookings" in t
    assert "HIGH RISK" in t and "FAA LIVE STATUS" in t


def test_mail_echappe_le_texte_et_garde_l_ancien_branchement():
    ev = json.loads(evenements())
    ev["lignes"][0]["detail"] = "<script>x</script>"
    out = mail.main(aeroport="MCO", ia="<b>hi</b>", evenements=json.dumps(ev))
    assert "<script>" not in out["html"] and "<b>hi" not in out["html"]
    vieux = mail.main(aeroport="MCO", ia=PHRASE, donnees="Live events at MCO\n- FAA: none.", evenements="")
    assert "Risks reported" in vieux["html"] or "Live events" in vieux["html"]
