# Comparaison des IA sur les prompts Dify (15 novembre 2026)

## Pourquoi ce test

Au début du projet (5 novembre), le même « prompt 3 » a été donné à ChatGPT, Gemini et Claude, et chaque réponse
a été vérifiée à la main (annexe D de la présentation). ChatGPT s'est trompé de cause principale, Gemini a inventé
la « météo d'été » et son autocontrôle disait « None », Claude était juste. On en a tiré deux règles :
**le code calcule, l'IA rédige**, et **toute réponse d'IA se vérifie** (`dify/verifier_reponse_IA.md`).

Ce test refait l'exercice avec les prompts **tels qu'ils tournent aujourd'hui dans Dify**, et avec une note
automatique, pour voir si les prompts eux-mêmes posent problème.

## Les cas (`dify/evaluation/cas/`)

Chaque fichier contient le message Système et le message Utilisateur exacts envoyés à l'IA, produits par les nœuds
Code du dépôt (données BTS janvier 2023 à août 2026).

| Cas | Workflow | Ce qu'il teste |
|---|---|---|
| A_MCO_7 | Fiche à la demande, Orlando juillet | cas type : récurrent, mixte (48-52 %), météo 60 % |
| A_SFO_7 | San Francisco juillet | retards surtout externes (42-46 %) |
| A_ATL_2 | Atlanta février | mois normal, action de repli sans chiffre |
| A_LGA_6 | LaGuardia juin | « one-off » avec 2 années sur 4 au-dessus de 25 % |
| B_MCO | Alerte du matin, Orlando | arrêt au sol FAA, orages, TAF en UTC |
| B_ATL | Alerte du matin, Atlanta | prévisions NWS à 7 jours (70 %, 60 %) |
| E_master_questions | Master, nœud « Understand the question » | 8 questions, dont une tentative de détournement |

## La note automatique (`dify/evaluation/noter_reponse_ia.py`)

```
python dify/evaluation/noter_reponse_ia.py dify/evaluation/cas dify/evaluation/reponses_apres/*
```

Elle reprend le nœud « contrôle des chiffres » et ajoute des contrôles de règles : 5 parties, message aux passagers
identique au message validé et sans chiffre, moyenne du réseau jamais appelée « seuil », 2 suggestions prises dans
la liste, pas de mot interdit (hub, saison, coût…), pas de « today » pour un mois lointain, autocontrôle (b) qui ne dit
pas « None ». Pour l'alerte : « Alert XXX » en première ligne, au plus 2 actions copiées, rien hors du bloc,
10 lignes au plus. Elle ne juge pas le sens : la checklist reste nécessaire.

## Résultats avec les prompts d'avant (Claude Haiku, Sonnet, Opus)

| Point | Haiku | Sonnet | Opus |
|---|---|---|---|
| Chiffres (vrais chiffres hors données) | 0 | 0 | 0 (corrige l'exemple faux du prompt) |
| Calculs montrés | justes | justes | justes |
| Interprétation (niveau, contrôlable, météo) | juste | juste | juste |
| SFO : 2 suggestions demandées, une seule action permise | **0 suggestion** | **1 suggestion** | coupe une action en deux |
| LGA : « one-off » alors que 2 années sur 4 | recopie | recopie | signale l'incohérence |
| Message aux passagers | copié, sans chiffre | copié, sans chiffre | copié, sans chiffre |
| Autocontrôle | renvoie à des « DATA line 8 » inventées | honnête | honnête |
| Longueur de la fiche | 310-430 mots | 400-430 mots | 465-614 mots |
| Alerte du matin (B) | conforme | conforme | conforme, la plus claire |
| Master (8 questions) | 8/8 utilisables | 8/8 | 8/8 |
| Faux « chiffres inventés » du contrôle automatique | 5 à 7 par fiche | 1 à 2 | 2 à 4 |

Les trois modèles respectent les chiffres : les défauts venaient surtout **des prompts et du contrôle**, pas des IA.

## Défauts trouvés et corrigés

1. **Règle impossible à suivre (SFO juillet et 60 aéroports-mois).** Quand Delta contrôle moins de 50 % des retards,
   le prompt interdisait les actions équipage, mais la liste n'en proposait souvent qu'une autre. Corrigé dans
   `noeud_code_calcul.py` : l'action équipage est retirée de la liste et l'action « système aérien » (réacheminements,
   contrôle aérien, prévenir les passagers) est toujours proposée. La fiche du code suit la même règle.
2. **Exemple de calcul faux dans le prompt.** « 33.8 - 21.4 = 12.3 » (calculé avant arrondi). L'exemple est maintenant
   calculé sur les chiffres arrondis (12.4).
3. **Définition de « one-off » incomplète.** « a single year » ne couvrait pas 2 années non consécutives. Nouveau texte :
   « one-off = one year, or two years that are not in a row » (fiche du mois et bilan annuel).
4. **Faux positifs du contrôle des chiffres.** Les titres en gras (`**2. Interpretation**`), « Suggestion 2 » au milieu
   d'une phrase et « DATA lines 8 and 9 » étaient comptés comme des chiffres inventés. Corrigé dans
   `noeud_code_controle.py`, et le prompt interdit maintenant de citer des numéros de ligne.

L'alerte du matin et le nœud du master n'ont pas besoin de changement : le nœud « routeur » rattrape déjà les
réponses floues (« unclear » donne une fiche).

## Résultats avec les prompts corrigés

12 fiches sur 12 sans aucun défaut repéré (3 modèles × 4 cas), 0 chiffre hors données, 2 suggestions de la liste
à SFO et LGA, « one-off » expliqué correctement. Réponses dans `dify/evaluation/reponses_apres/`.

### Gemini 2.5 Flash (le modèle de production), réponses collées par Maeva

| Point | Gemini 2.5 Flash |
|---|---|
| Chiffres hors données | 0 sur les 7 cas, calculs montrés justes |
| Interprétation | juste partout (« one-off » de LGA bien expliqué) |
| SFO | plus d'action équipage (grâce à la correction 1) |
| Message aux passagers | copié mot pour mot, sans chiffre |
| Suggestions | **les 2 sur une seule ligne** dans les 4 fiches |
| Autocontrôle | juste mais très long (fiches de 400 à 620 mots) |
| Alertes (B) | conformes |
| Master | 8/8 |

Correction 5 : le prompt demande maintenant d'aller à la ligne avant « Suggestion 2 ». « Section 3 » n'est plus compté
comme un chiffre par le contrôle.

Remarque : dans l'application Gemini (et non AI Studio), l'alerte « Write a short alert email » a été prise pour une
demande d'envoi : Gemini a demandé l'accès à Gmail au lieu d'écrire le texte. Dans Dify, le modèle n'a aucun outil, donc
ce cas ne peut pas arriver ; mais la même IA ne se comporte pas pareil selon l'endroit où elle tourne.

## Limites

- Les réponses Claude ont été produites par des sous-agents qui lisaient les deux messages, pas par l'API avec une
  température fixée : c'est une bonne approximation, pas une mesure exacte.
- ChatGPT : pas encore testé (coller les cas, puis `noter_reponse_ia.py` sur ses réponses, un dossier par modèle).
- Les autocontrôles de deux fiches Gemini (MCO, SFO) sont raccourcis dans le dépôt ; le reste est recopié tel quel.

## À faire dans Dify après la fusion

Recoller `noeud_code_calcul.py` dans les nœuds « calcul » de A et de C (les deux de C), et
`noeud_code_controle.py` dans A, puis **Publish → Workflow as Tool → Update** pour le master.
