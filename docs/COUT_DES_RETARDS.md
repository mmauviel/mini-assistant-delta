# Coût des retards en dollars

La fiche du mois et le bilan annuel donnent un ordre de grandeur du coût des retards à l'arrivée, calculé par le code (pas par l'IA).

**Calcul.** Minutes de retard à l'arrivée des vols Delta (colonne `arr_delay` du BTS) × **98,41 $ par minute**. C'est le coût moyen d'une minute de vol (roulage et vol) des compagnies américaines en 2025, publié par Airlines for America : équipage 37,01 $, carburant 29,34 $, maintenance 18,35 $, avion 9,76 $, autres 3,95 $. Source : https://airlines.org/dataset/u-s-passenger-carrier-delay-costs/

**Ce que la fiche affiche.**
- Fiche du mois : `Estimated cost of arrival delays in July: about $4.9 M per year on average, up to $6.0 M in 2024` (MCO).
- Bilan annuel : une colonne « Delay cost / year » par mois, puis le total annuel et la part des mois à préparer (MCO : environ 33 M$ par an, dont 65 % sur les mois à préparer).

**Limites, à dire à l'oral.** C'est un ordre de grandeur, pas une comptabilité :
- une minute d'attente à la porte coûte moins cher qu'une minute de vol (moins de carburant) ;
- les coûts pour les passagers et les correspondances manquées ne sont pas comptés ;
- les vols annulés n'ont pas de minutes de retard, donc ils ne sont pas comptés non plus.

**Données.** `src/construire_fichier_bts.py` ajoute la colonne `arr_delay` (somme des minutes par cause des vols en retard, même définition que le BTS : vérifié, la somme des cinq causes égale `arr_delay` sur tout le fichier officiel). `src/alleger.py` la garde dans `donnees/Airline_Delay_Cause.csv`. Tant que la mise à jour mensuelle n'a pas tourné, le fichier n'a pas la colonne : la fiche reste alors exactement la même qu'avant, sans ligne de coût.

**Pourquoi pas dans la note de l'IA.** Le prompt interdit à l'IA de parler de coûts. Le chiffre reste dans la partie calculée par le code, et le contrôle des chiffres ne le voit pas comme une invention.

**À faire après la fusion.**
1. GitHub → **Actions** → « Mise à jour des données » → **Run workflow** (environ 45 minutes). Ou attendre le 20 du mois.
2. Dans Dify, recoller `dify/noeud_code_calcul.py` dans **chaque** nœud « calcul » : A (Fiche à la demande), C (Fiche du 1er) et le deuxième calcul de C (bilan d'octobre). Puis Publish, et pour A : **Workflow as Tool → Update**.
