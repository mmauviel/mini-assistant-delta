# Mise à jour mensuelle des données du mini-assistant, lancée par GitHub Actions (.github/workflows/donnees.yml).
# Enchaîne la chaîne de données et publie les deux fichiers que Dify lit dans le dossier donnees/ du dépôt.
#
#   1. fetch_bts.py : les vols du BTS, mois par mois, jusqu'au dernier mois publié (le BTS publie environ 2 mois après)
#   2. construire_fichier_bts.py : le fichier des causes de retard, refait à partir des vols
#   3. fetch_weather.py : la météo heure par heure de chaque aéroport (retéléchargée en entier, pour inclure le dernier mois)
#   4. trace_root_cause.py, weather_join.py, construire_suivi_mensuel.py : le suivi des avions et la météo
#   5. alleger.py : les colonnes que lit Dify, dans donnees/
#
# Usage : python3 -I src/mise_a_jour.py --data data --publie donnees
import argparse
import datetime as dt
import shutil
import subprocess
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parent
DEBUT_VOLS = (2022, 12)  # décembre 2022 sert seulement à relier les vols du 1er janvier 2023 à leur vol précédent
DEBUT_FICHIER = "2023-01"
ATTENTE_MAX = 4  # mois : au-delà, un mois absent du BTS est une vraie erreur, pas un mois pas encore publié


def lancer(script, *args):
    print(">", script, *args, flush=True)
    subprocess.run([sys.executable, "-I", str(SRC / script), *map(str, args)], check=True)


def mois_suivant(y, m):
    return (y + 1, 1) if m == 12 else (y, m + 1)


def ecart_mois(a, b):
    return (b[0] - a[0]) * 12 + b[1] - a[1]


def telecharger_vols(dossier: Path, aujourd_hui: dt.date):
    """Télécharge les mois manquants ; s'arrête au premier mois pas encore publié. Renvoie le dernier mois disponible."""
    courant, dernier = DEBUT_VOLS, None
    fin = (aujourd_hui.year, aujourd_hui.month)
    while ecart_mois(courant, fin) > 0:
        y, m = courant
        if not (dossier / f"bts_{y}_{m:02d}.parquet").exists():
            try:
                lancer("fetch_bts.py", "--start", f"{y}-{m:02d}", "--end", f"{y}-{m:02d}", "--out", dossier)
            except subprocess.CalledProcessError:
                if ecart_mois(courant, fin) <= ATTENTE_MAX:
                    print(f"{y}-{m:02d} : pas encore publié par le BTS, on s'arrête au mois précédent", flush=True)
                    break
                raise
        dernier, courant = courant, mois_suivant(*courant)
    if dernier is None:
        raise SystemExit("aucun mois de vols disponible")
    return dernier


def main() -> None:
    ap = argparse.ArgumentParser(description="Mise à jour mensuelle des données du mini-assistant")
    ap.add_argument("--data", required=True, type=Path, help="dossier de travail (gros fichiers, non publiés)")
    ap.add_argument("--publie", required=True, type=Path, help="dossier publié que lit Dify")
    a = ap.parse_args()
    bts, meteo, out = a.data / "bts", a.data / "weather", a.data / "out"
    for d in (bts, out):
        d.mkdir(parents=True, exist_ok=True)

    y, m = telecharger_vols(bts, dt.date.today())
    fin_meteo = "{}-{:02d}-01".format(*mois_suivant(y, m))
    print(f"Dernier mois du BTS : {y}-{m:02d}", flush=True)

    lancer("construire_fichier_bts.py", "--bts", bts, "--depuis", DEBUT_FICHIER, "--out", out / "Airline_Delay_Cause.csv")
    shutil.rmtree(meteo, ignore_errors=True)  # les fichiers météo s'arrêtent à l'ancienne date de fin
    lancer("fetch_weather.py", "--airports-csv", out / "Airline_Delay_Cause.csv",
           "--start", "{}-{:02d}-01".format(*DEBUT_VOLS), "--end", fin_meteo, "--out", meteo)
    lancer("trace_root_cause.py", "--bts", bts, "--out", out, "--first-month", DEBUT_FICHIER)
    lancer("weather_join.py", "--flights", out / "flights_root_causes.parquet", "--weather", meteo, "--out", out)
    lancer("construire_suivi_mensuel.py", "--vols", out / "flights_root_causes_weather.parquet",
           "--out", out / "delta_monthly_airport_full.csv")
    lancer("alleger.py", "--bts", out / "Airline_Delay_Cause.csv", "--suivi", out / "delta_monthly_airport_full.csv",
           "--out", a.publie)
    (a.publie / "mise_a_jour.txt").write_text(
        f"Données BTS de janvier 2023 à {m:02d}/{y}, mises à jour le {dt.date.today().isoformat()}.\n", encoding="utf-8")


if __name__ == "__main__":
    main()
