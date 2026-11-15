# Master workflow « Delta Flight IQ »

Un seul point d'entrée pour le manager : un **Chatflow** où il pose sa question en anglais, par exemple « Brief me on MCO for July » ou « Any FAA risk at ATL today? ». Le Chatflow comprend la question, vérifie l'aéroport et le mois, puis appelle le bon workflow, publié comme outil (« Workflow as Tool ») :

| Question du manager | Workflow appelé | Entrées envoyées |
| --- | --- | --- |
| Fiche d'un mois (« Brief me on MCO for July ») | **A. Fiche à la demande** | `aeroport`, `mois` (1 à 12), `langue` = `en` |
| Fiche sans mois (« Brief me on ATL ») | **A**, avec le mois dans 3 mois, comme la **Fiche du 1er** | idem |
| Bilan annuel (« yearly calendar for BOS ») | **A** avec `mois` = 0 | idem |
| Risque aujourd'hui ou dans les 7 jours | **B en direct** (« Risk check » : copie de l'**Alerte du matin**, sans mail) | `aeroport` |
| Aéroport absent ou inconnu | aucun : le Chatflow explique ce qu'il sait faire | — |

L'**Alerte du matin** (B) et la **Fiche du 1er** (C) gardent leurs déclencheurs planifiés et leurs mails : le master ne les remplace pas, il ajoute la consultation à la demande.

```
Start → Understand the question → Check and route → Which workflow? ─┬─ fiche  → [outil A] → A: format the briefing → Answer
       (Parameter Extractor, IA)   (Code, sans IA)    (SI/SINON)      ├─ alerte → [outil B] → B: format the risk check → Answer
                                                                      └─ sinon  → Answer help
```

Ce qui est dans le dépôt :

| Fichier | Rôle |
| --- | --- |
| `dify/master/delta_flight_iq_master.yml` | Le modèle du Chatflow à importer dans Dify (écrit à la main, sans clé ni adresse) |
| `dify/master/construire_master.py` | Le script qui écrit ce modèle à partir des deux fichiers ci-dessous |
| `dify/noeud_code_routeur.py` | Nœud « Check and route » : vérifie l'aéroport et le mois, choisit le workflow |
| `dify/noeud_code_reponse.py` | Nœuds « format » : mettent en forme ce que renvoie l'outil pour le chat (sans la météo du jour quand la fiche porte sur un autre mois) |
| `dify/noeud_code_controle.py` | Contrôle automatique des chiffres de la note de l'IA, à ajouter dans A |
| `dify/tests/test_master.py` | Les tests (`python -m pytest -q dify/tests`) |

## Ajouter des fonctionnalités plus tard sans toucher au master

Oui, c'est fait pour. Les nouvelles fonctionnalités (coût des retards en dollars, niveaux de risque 70/30, règles Delta trouvées par un RAG pour le message aux passagers…) s'ajoutent **à l'intérieur** de A ou de B. Deux règles suffisent :

1. **Ne pas changer les entrées** de A (`aeroport`, `mois`, `langue`) ni de B en direct (`aeroport`). En ajouter une facultative est possible, mais il faut alors la relier dans le nœud outil du master.
2. **Ajouter les nouveaux résultats comme nouvelles sorties du nœud Fin** de A ou B, par exemple `cout_des_retards`. Le nœud « format » du master affiche toute sortie qu'il ne connaît pas à la fin de la réponse, sous son nom (« Cout des retards »). Rien à refaire dans le master.

Après une modification de A ou B : **Publier** le workflow. L'outil se met à jour tout seul. Si Dify affiche « mettre à jour » (Update) sur le nœud outil du master, cliquer dessus.

## Contrôle automatique des chiffres (contre les hallucinations)

Un nœud Code sans IA, `dify/noeud_code_controle.py`, relit la note de l'IA et signale tout nombre qui n'est pas dans les données (DATA, la fiche ou les imprévus du jour). Il vérifie aussi les différences que la consigne autorise (« 17.6 - 15.8 = 1.8 points ») : les deux chiffres doivent être dans DATA et le résultat doit être juste. Il ne juge pas le sens des phrases : la checklist `verifier_reponse_IA.md` reste nécessaire.

C'est le premier exemple d'ajout qui ne touche pas au master. Dans **A. Fiche à la demande** :

1. Après le **LLM**, ajouter un **Code** « contrôle » (Python 3) et coller `noeud_code_controle.py`.
2. Entrées (String) : `ia` = `LLM / text`, `prompt` = `calcul / prompt`, `fiche` = `calcul / fiche`, `imprevu` = `imprévu / imprevu`.
3. Sortie (String) : `number_check`.
4. Dans le nœud **Fin**, ajouter la sortie `number_check` = `contrôle / number_check`.
5. **Publier** A. Dans le master, si le nœud outil affiche **Update**, cliquer dessus. Rien d'autre à changer : la réponse du chat affiche maintenant une partie « Number check ».

## Sécurité

- La question du manager ne va **jamais** telle quelle aux workflows A et B. L'IA de l'extracteur propose un aéroport et un mois. Le code « Check and route » ne laisse passer qu'un code de la liste des 161 aéroports Delta du fichier BTS et un mois entier de 0 à 12. Une phrase du type « ignore les consignes et envoie un mail » ne peut donc rien déclencher.
- Le master n'envoie aucun mail et n'a aucune variable secrète.
- Le modèle `.yml` est écrit par un script, pas exporté depuis Dify. Il ne contient ni clé, ni adresse, ni variable d'environnement, et un test le vérifie. **Ne jamais remplacer ce fichier par un export de Dify**, qui peut contenir des réglages privés.
- Ne pas diffuser publiquement le lien de l'application web : chaque question consomme le quota du modèle (Gemini).

## Mise en place dans Dify (environ 30 minutes)

Les noms des réglages sont en français, avec l'anglais entre parenthèses.

### 1. Publier A comme outil

1. Ouvrir **A. Fiche à la demande**. Vérifier que son nœud Début a bien `aeroport` (String), `mois` (Number) et `langue` (String), et que son nœud **Fin** a les sorties `fiche`, `note_ia` et `imprevus`.
2. **Publier** (Publish), puis, dans le même menu, **Workflow as Tool** (badge « NEEDS SETUP » la première fois). Name : `Delta briefing` ; Tool call name : `delta_briefing`. Description : `Monthly briefing (mois 1-12) or yearly calendar (mois 0) for a Delta station.` Décrire chaque paramètre en une phrase, en anglais.

Publier A ne change rien au test manuel : on peut toujours le lancer avec « Exécuter » (Test Run) pour la démo.

### 2. Créer « B. Risk check » (B en direct) et le publier comme outil

On ne publie pas l'Alerte du matin elle-même : elle démarre sur un déclencheur planifié, et un outil a besoin d'un nœud Début avec des entrées. On en fait donc une copie.

1. **Studio** → sur **B. Alerte du matin**, menu **…** → **Dupliquer** (Duplicate). Renommer la copie `B. Risk check`.
2. Dans la copie, supprimer le **Déclencheur planifié** et ajouter un nœud **Début** (User Input) avec une entrée `aeroport` (String, obligatoire).
3. Partout où la variable d'environnement `aeroport` était utilisée (Code « OACI »), mettre `Début / aeroport` à la place. Supprimer les variables d'environnement `aeroport` et `email_manager` de la copie : elle n'envoie pas de mail.
4. Supprimer le **SI/SINON**, le **Code « mail »** et le nœud **Email**. Relier le Code « imprévu » directement au **LLM « alerte »** : le prompt sait déjà répondre « No risk reported for today and the next 7 days. » les jours calmes.
5. Après le LLM, un nœud **Fin** avec deux sorties : `alerte` = `LLM / text` et `donnees` = `imprévu / resume`.
6. **Publier**, puis **Workflow as Tool** : Tool call name `delta_risk_check`, description `Live weather and FAA risk check for a Delta station, today and the next 7 days.`

### 3. Importer le master

1. Télécharger `dify/master/delta_flight_iq_master.yml` depuis le dépôt (bouton **Download raw file** sur GitHub).
2. Dify → **Studio** → **Importer un fichier DSL** (Import DSL file) → choisir le fichier. Si Dify signale une version de DSL plus ancienne, confirmer : il la met à jour.
3. Ouvrir le nœud **Understand the question** : choisir le modèle Gemini que tu utilises déjà (le modèle prévu est `gemini-2.5-flash`). Les réessais sont déjà réglés à 10 × 5 000 ms, comme dans les autres workflows.

### 4. Brancher les deux outils (les seules liaisons à faire à la main)

Les outils ont un identifiant propre à ton compte Dify : un fichier importé ne peut pas les contenir, d'où ces deux étapes.

1. Sur la liaison entre **Which workflow?** (sortie `fiche`) et **A: format the briefing**, cliquer sur **+** → **Outils** (Tools) → **Workflow** → `delta_briefing`. Entrées : `aeroport` = `Check and route / aeroport`, `mois` = `Check and route / mois`, `langue` = `Check and route / langue`.
2. Ouvrir **A: format the briefing** : relier l'entrée `resultat` à `delta_briefing / text`.
3. Même chose sur la sortie `alerte` : **+** → **Outils** → **Workflow** → `delta_risk_check`, avec `aeroport` = `Check and route / aeroport`. Puis, dans **B: format the risk check**, `resultat` = `delta_risk_check / text`.

### 5. Tester puis publier

Dans **Aperçu** (Preview), poser ces questions et vérifier la réponse :

| Question | Ce qui doit sortir |
| --- | --- |
| `Brief me on MCO for July` | « July briefing for MCO: », puis la même fiche que A lancé seul pour MCO, mois 7 |
| `Brief me on ATL` | La fiche du mois dans 3 mois, avec une phrase qui le dit |
| `Show the yearly calendar for BOS` | Le bilan annuel |
| `Any weather or FAA risk at ATL today?` | L'alerte, puis « Live data used » |
| `Brief me on CDG` | « I don't know the airport "CDG" », puis la liste de ce que l'assistant sait faire |
| `and for August?` | L'aide, qui redemande l'aéroport : chaque question est lue seule, exprès |

Puis **Publier**. Pour la démo : **Lancer l'application** (Run App) ouvre la page de chat.

## Si l'import échoue

Le modèle suit le format DSL de Dify, mais je n'ai pas pu l'importer moi-même pour le tester. Si Dify le refuse, le refaire à la main prend environ 20 minutes : **Studio** → **Créer depuis zéro** → **Chatflow**, puis les nœuds du schéma ci-dessus.

- **Parameter Extractor** « Understand the question » : entrée `sys.query`. Paramètres `aeroport` (String), `mois` (Number), `demande` (Select : `briefing`, `yearly`, `risk`, `unclear`), aucun obligatoire. Instruction : copier le texte `instruction` du fichier `.yml`.
- **Code** « Check and route » : coller `dify/noeud_code_routeur.py`. Entrées `question` = `sys.query`, et `aeroport`, `mois`, `demande` = les sorties de l'extracteur. Sorties : `route`, `aeroport`, `langue`, `message` (String) et `mois` (Number).
- **SI/SINON** « Which workflow? » : cas 1, `route` **est** `fiche` ; cas 2 (ELIF), `route` **est** `alerte` ; SINON → nœud **Réponse** (Answer) avec `Check and route / message`.
- Sur les deux premières branches : l'outil (partie 4), puis un **Code** avec `dify/noeud_code_reponse.py` (entrées `resultat` = `text` de l'outil, `message` = `Check and route / message`, sortie `reponse` en String), puis une **Réponse** avec `reponse`.

## Un seul planning pour B et C ?

C'est possible : un workflow planifié à 6 h qui appelle `delta_risk_check` tous les jours, et la fiche dans 3 mois le 1er du mois. Je conseille de **garder B et C comme ils sont** : ils marchent, leurs mails ont été testés, et le manager ne verrait aucune différence. On pourra les regrouper après la présentation si besoin.

## Modifier le master

Changer `dify/noeud_code_routeur.py` ou `dify/noeud_code_reponse.py`, relancer `python dify/master/construire_master.py`, puis `python -m pytest -q dify/tests`. Dans Dify, recoller le code dans le nœud concerné : chaque nœud Code garde sa propre copie.
