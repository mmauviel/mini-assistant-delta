"""Tests de mise_a_jour.py (arrêt au dernier mois publié) et de alleger.py, sans téléchargement."""
import datetime as dt
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import alleger  # noqa: E402
import mise_a_jour as maj  # noqa: E402


def test_s_arrete_au_premier_mois_pas_encore_publie(tmp_path, monkeypatch):
    publies = {(2022, 12), (2023, 1), (2023, 2)}

    def faux(script, *args):
        y, m = map(int, args[1].split("-"))
        if (y, m) not in publies:
            raise subprocess.CalledProcessError(1, script)
        (tmp_path / f"bts_{y}_{m:02d}.parquet").write_text("x")

    monkeypatch.setattr(maj, "lancer", faux)
    assert maj.telecharger_vols(tmp_path, dt.date(2023, 5, 20)) == (2023, 2)
    assert maj.telecharger_vols(tmp_path, dt.date(2023, 5, 20)) == (2023, 2)  # deuxième fois : rien à retélécharger


def test_un_vieux_mois_absent_est_une_vraie_erreur(tmp_path, monkeypatch):
    def faux(script, *args):
        raise subprocess.CalledProcessError(1, script)

    monkeypatch.setattr(maj, "lancer", faux)
    with pytest.raises(subprocess.CalledProcessError):
        maj.telecharger_vols(tmp_path, dt.date(2026, 11, 20))


def test_alleger():
    bts = pd.DataFrame([{c: 1 for c in alleger.COLS_BTS} | {"carrier": "DL", "arr_delay": 5}])
    assert list(alleger.alleger_bts(bts).columns) == alleger.COLS_BTS
    suivi = pd.DataFrame([{c: 1 for c in alleger.COLS_SUIVI} | {"scope": s, "faa_total_min": 3} for s in ("mainline", "network")])
    s = alleger.alleger_suivi(suivi)
    assert list(s.columns) == alleger.COLS_SUIVI and len(s) == 1 and s.iloc[0].scope == "mainline"
