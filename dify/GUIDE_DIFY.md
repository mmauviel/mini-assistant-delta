# Le mini-assistant dans Dify, avec les données de GitHub et les mails automatiques

Trois workflows, tous dans https://cloud.dify.ai :

| Workflow | Quand | Ce que reçoit le manager |
| --- | --- | --- |
| **A. Fiche à la demande** | Quand le manager le lance | La fiche d'un mois (ou le bilan annuel avec mois = 0) et la note de l'IA |
| **B. Alerte du matin** | Tous les jours à 6 h | Un mail **seulement** s'il y a un risque : orage, neige, verglas ou brouillard dans les 7 jours, programme de la FAA |
| **C. Fiche du 1er** | Le 1er de chaque mois à 7 h | La fiche du mois qui arrive dans 3 mois (le 1er avril : juillet). En octobre, aussi le bilan annuel de l'année suivante |

Pourquoi ces délais : le programme des vols est presque définitif environ 100 jours avant ; le personnel au sol de l'été se recrute 3 à 4 mois avant ; le dossier des créneaux FAA de l'été est à rendre en octobre ; les plannings mensuels des pilotes sortent vers le 15 du mois précédent.

Tout ce que voit le manager (fiche, note de l'IA, alertes, mails) sort en **anglais** par défaut ; pour le français, mettre `langue` = `fr`. Les noms des réglages sont donnés en français, avec l'anglais entre parenthèses. Remplacer `<compte>` par ton nom de compte GitHub.

## 1. Une seule fois : les réglages

1. **Le mail d'envoi.** Créer une adresse Gmail réservée au projet (pas ton adresse personnelle). Activer la validation en deux étapes, puis créer un **mot de passe d'application** (compte Google → Sécurité → Mots de passe des applications). Gmail refuse les envois avec le mot de passe normal.
2. **Le plugin Email.** Dify → **Plugins** → Marketplace → « Email » (éditeur langgenius) → Installer. Dans son autorisation : serveur `smtp.gmail.com`, port `587`, chiffrement STARTTLS, identifiant = l'adresse Gmail du projet, mot de passe = le mot de passe d'application. Ces informations restent dans Dify, jamais sur GitHub.
3. **Le modèle.** Dify → Paramètres → **Model Provider** : la clé Gemini (gratuite) ou Claude (payante). Choisir le plus fort disponible : Flash-Lite suit mal les consignes.

## 2. Les adresses des données

Les deux requêtes HTTP de chaque workflow utilisent :
- BTS : `https://raw.githubusercontent.com/<compte>/mini-assistant-delta/main/donnees/Airline_Delay_Cause.csv`
- Suivi : `https://raw.githubusercontent.com/<compte>/mini-assistant-delta/main/donnees/suivi_mainline.csv`

Les fichiers font environ 540 Ko et 350 Ko, sous la limite des requêtes HTTP de Dify. Ils sont mis à jour par GitHub le 20 de chaque mois.

## 3. Workflow A : fiche à la demande

On repart du workflow existant (voir le mode d'emploi du zip), avec deux changements.

1. **Début** : garder `aeroport`, `mois` et `langue` (`en` pour l'anglais). Supprimer `fichier_bts` et `fichier_suivi`. `mois` peut valoir 0 : le bilan annuel des 12 mois.
2. Remplacer les deux **Extracteurs de documents** par deux **Requêtes HTTP** (HTTP Request), méthode GET, avec les adresses de la partie 2. Dans **Gestion des erreurs** (Error Handling), laisser « Aucune » : si GitHub ne répond pas, mieux vaut un arrêt qu'une fiche vide.
3. **Code « calcul »** : `bts` = `HTTP BTS / body`, `suivi` = `HTTP suivi / body`. Le reste ne change pas.
4. **Mettre le code à jour** : coller dans les nœuds Code les versions de ce dossier (`noeud_code_calcul.py`, `noeud_code_imprevu.py`, `noeud_code_icao.py`). Dans le **LLM**, message Système : `You write short operational briefings for Delta Air Lines managers. Use only the numbers in DATA. Follow the format and the rules exactly. When something is not in DATA, leave it out.` Déclarer leurs sorties (Output Variables, toutes en String) : OACI = `aeroport`, `icao`, `lat`, `lon` ; imprévu = `imprevu`, `resume`, `alerte` ; calcul = `fiche`, `prompt`. Dans le Code « imprévu », relier l'entrée `mois` (Number) à `Début / mois` : pour un autre mois que le mois en cours, l'IA ne reçoit pas la météo du jour. Une sortie non déclarée donne l'erreur « Not all output parameters are validated ». Signe que l'ancien code est encore là : une note en anglais quand `langue` = `fr`, une partie « SELF-CHECK » quand `langue` = `fr`, des chiffres dans le message aux passagers, la même suggestion écrite deux fois, un pourcentage au bout d'une suggestion d'un « Normal month », ou la phrase « There is no TODAY'S EVENT block ».

## 4. Workflow B : alerte du matin

Créer un nouveau workflow : **Studio** → **Créer depuis zéro** → **Workflow**.

1. Supprimer le nœud Début, puis ajouter un **Déclencheur planifié** (clic droit → Ajouter un nœud → Start → **Schedule Trigger**) : tous les jours à 6 h, ou l'expression `0 6 * * *`. Vérifier le fuseau horaire affiché dans les 5 prochaines exécutions.
2. **Variables d'environnement** (bouton ENV en haut du workflow) :
   - `aeroport` : type String, valeur `MCO` ;
   - `email_manager` : type **Secret**, l'adresse du manager.
3. Les nœuds des imprévus, comme dans le mode d'emploi du zip : **Code « OACI »** (entrée `aeroport` = la variable d'environnement `aeroport`), **Requête HTTP « météo »**, **Requête HTTP « FAA »**, **Requête HTTP « points »**, **Code « lien prévision »**, **Requête HTTP « prévision 7 jours »**. Pour les quatre requêtes : Gestion des erreurs → Valeur par défaut.
4. **Code « imprévu »** : `aeroport`, `taf`, `faa`, `prevision` comme dans le zip. Ne pas relier `langue` : le résumé sort en anglais. **Ne pas** relier `mois` : sans mois, le nœud décrit aujourd'hui et les 7 prochains jours. Sorties `imprevu`, `resume`, `alerte`.
5. **SI/SINON** (IF/ELSE) : `imprévu / alerte` **est** `oui`.
6. Branche SI : nœud **LLM** « alerte ». Système : `You write short operational alerts for Delta Air Lines managers. Use only the facts given. When something is not given, leave it out.` Utilisateur : le texte ci-dessous ; à la place de `{{imprevu}}`, insérer la variable `imprévu / imprevu` (taper `/`). Vérifier qu'elle apparaît en bleu : sans elle, le modèle invente (aéroport, neige…). Le mail sort en anglais.

   Les deux prévisions météo ne disent pas la même chose, et c'est normal : la **prévision de l'aéroport** (TAF, aviationweather.gov) ne couvre que les 24 à 30 prochaines heures, mais elle est précise ; la **prévision de la zone** (service météo américain, NWS) couvre 7 jours, par périodes de 12 heures, avec une probabilité. Le nœud « imprévu » nomme chaque ligne d'après sa source, écrit « possible » quand le NWS dit « Chance » (30 à 50 %), ajoute « not confirmed » quand la TAF couvre la même période sans rien signaler, et ignore les périodes déjà passées.

   ```
   Write a short alert email in English for the manager of the Delta Air Lines station named in the BLOCK below.
   Use only the BLOCK. If the BLOCK is empty, reply only: "Data unavailable: no alert."
   1. First line: "Alert" followed by the airport code written in the BLOCK, then one sentence with the main risk and its day.
      If the BLOCK says the risk is "possible" or "not confirmed", say it in that sentence.
   2. List each risk with its day and time exactly as in the BLOCK (weather times are in UTC: write "UTC").
      Keep the words "possible", "not confirmed" and the chance of precipitation exactly as in the BLOCK.
      Never write that a risk is "forecast" when the BLOCK says "possible".
      If the BLOCK reports no risk, write only "No risk reported for today and the next 7 days." and stop.
   3. Suggest at most 2 actions, copied word for word from this list only:
      "Warn passengers on the affected flights through the Fly Delta app."
      "Prepare rebookings."
      "Reinforce standby crews and ground staff for those days."
      "Coordinate with air traffic control."
   4. No number that is not in the BLOCK. No promise to passengers. 10 lines maximum.

   BLOCK:
   {{imprevu}}
   ```
7. Nœud **Email** (outil du plugin) : destinataire = la variable d'environnement `email_manager` ; objet = `Weather and FAA alert ` suivi de la variable `OACI / aeroport` ; contenu = `LLM / text`, puis une ligne vide et `imprévu / resume` (les données brutes, pour vérifier).
8. Relier la branche SINON directement à un nœud **Fin** : les jours calmes, aucun mail.
9. **Publier** (Publish) : le déclencheur ne tourne qu'une fois le workflow publié. Pour tester sans attendre 6 h : sur le déclencheur, « Exécuter cette étape » (Run this step).

## 5. Workflow C : fiche du 1er

1. **Déclencheur planifié** : mensuel, le 1er à 7 h, ou `0 7 1 * *`.
2. **Variables d'environnement** : `aeroport` (String) et `email_manager` (Secret), comme pour B.
3. **Code « rappel »** (Python 3) : entrée `aeroport` = variable d'environnement `aeroport` ; coller `noeud_code_rappel.py` ; sorties `mois_cible` (Number), `mois_annuel` (Number), `annuel` (String), `objet` (String), `message` (String).
4. **Requête HTTP « BTS »** et **Requête HTTP « suivi »** : les adresses de la partie 2.
5. **Code « calcul »** : coller `noeud_code_calcul.py` (la dernière version du dépôt : chaque nœud Code garde sa propre copie, celle du workflow A ne met pas à jour celle de C) ; entrées `bts` = `HTTP BTS / body`, `suivi` = `HTTP suivi / body`, `aeroport` = variable d'environnement, `mois` = `rappel / mois_cible`. Ne pas relier `langue` : la fiche sort en anglais. Sorties `fiche` et `prompt`.
6. **LLM** : le même message Système que dans le workflow A ; Utilisateur = `calcul / prompt`. Pas de bloc d'imprévus : le mois est dans 3 mois.
7. **Email** : destinataire `email_manager` ; objet = `rappel / objet` ; contenu = `rappel / message`, une ligne vide, `calcul / fiche`, une ligne vide, `AI note (to check):` et `LLM / text`.
8. **En octobre, le bilan annuel** : après l'Email, un **SI/SINON** sur `rappel / annuel` **est** `oui`. Branche SI : un deuxième **Code « calcul »** (même code ; `mois` = `rappel / mois_annuel`), un deuxième **LLM** (Utilisateur = son `prompt`) et un deuxième **Email** (objet `Yearly calendar`, contenu = sa `fiche` puis la note de l'IA). Les deux branches finissent sur **Fin**.
9. **Publier**.

## 6. Avant la présentation

- Lancer A pour MCO, mois 7 : la fiche doit être identique à celle d'avant (mêmes chiffres).
- Lancer B avec « Exécuter cette étape » sur le déclencheur. Les jours calmes, rien n'arrive : c'est normal. Pour voir un mail, changer provisoirement la condition en `alerte` **n'est pas vide** (is not empty), lancer, puis remettre **est** `oui`.
- Si un champ des en-têtes (Headers) refuse le texte : **Import from cURL** avec `curl -H "User-Agent: mini-assistant-delta (projet etudiant)" "https://api.weather.gov/x"`, puis remettre l'URL avec les variables.
- Lancer C de la même façon : un mail avec la fiche du mois dans 3 mois.
- Vérifier chaque note de l'IA avec `verifier_reponse_IA.md`.

## Ce qui reste privé

L'adresse du manager, le mot de passe d'application Gmail et la clé du modèle restent dans Dify (variable Secret, autorisation du plugin, Model Provider). Ne pas exporter le workflow (DSL) dans le dépôt GitHub.
