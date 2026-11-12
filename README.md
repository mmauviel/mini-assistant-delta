# Mini-assistant Delta : données automatiques

Projet étudiant (AIB, Partie 3) : un mini-assistant qui aide le responsable d'un aéroport Delta à préparer les mois difficiles. Le code calcule, l'IA rédige, un humain valide. Le mini-assistant tourne dans Dify ; ce dépôt lui fournit les données et les met à jour tout seul chaque mois.

## Ce que fait le dépôt

- **Le 20 de chaque mois**, GitHub Actions lance `src/mise_a_jour.py` :
  1. télécharge les vols du BTS jusqu'au dernier mois publié (le BTS publie environ 2 mois après le mois concerné) ;
  2. refait le fichier des causes de retard à partir de ces vols ;
  3. télécharge la météo heure par heure des 161 aéroports (archives METAR de l'université de l'Iowa) ;
  4. suit chaque avion en retard jusqu'au vol qui a lancé le retard et ajoute la météo ;
  5. publie les deux fichiers que lit Dify dans `donnees/`.
- **Dify lit ces fichiers à leur adresse « raw »**, par exemple :
  `https://raw.githubusercontent.com/<compte>/mini-assistant-delta/main/donnees/Airline_Delay_Cause.csv`

Toutes les données sont publiques et gratuites. Le dépôt peut être public : il ne contient aucun secret.

## Contenu

| Dossier | Contenu |
| --- | --- |
| `donnees/` | Les deux fichiers lus par Dify (`Airline_Delay_Cause.csv`, `suivi_mainline.csv`) et la date de mise à jour |
| `src/` | La chaîne de données (téléchargements, suivi des avions, météo, fichiers pour Dify) |
| `tests/` | Les tests : `python -m pytest -q tests` |
| `dify/` | Le code des nœuds Dify et le guide des workflows automatiques (alerte du matin, fiche du 1er, bilan d'octobre), avec la mise en page des mails aux couleurs de Delta |
| `.github/workflows/` | La mise à jour mensuelle et les tests |

## Mise en route

1. Créer un dépôt **public** vide sur GitHub et y déposer tout ce dossier (bouton « Add file » → « Upload files », ou `git push`).
2. Onglet **Actions** : autoriser les workflows si GitHub le demande.
3. Onglet **Settings** → **Actions** → **General** → **Workflow permissions** : cocher « Read and write permissions », pour que la mise à jour puisse enregistrer `donnees/`.
4. Pour tester tout de suite : **Actions** → « Mise à jour des données » → **Run workflow**. Le premier lancement est le plus long (45 mois de vols, 161 aéroports de météo).
5. Dans Dify, suivre `dify/GUIDE_DIFY.md`.

## Ce qui ne va jamais sur GitHub

Un dépôt public est lisible par tout le monde, et GitHub garde l'historique : un fichier supprimé reste visible dans les anciennes versions. Ne jamais y mettre :

| Information | Où la ranger à la place |
| --- | --- |
| Mot de passe Gmail ou mot de passe d'application | Dify → Plugins → Email → autorisation |
| Clé API du modèle (Gemini, Claude…) | Dify → Paramètres → Model Provider |
| Clé API de Dify | Nulle part dans le dépôt (ce projet n'en a pas besoin) |
| Adresse mail du manager | Dify → variable d'environnement de type **Secret** |
| Export du workflow Dify (fichier `.yml` / DSL) | Sur ton ordinateur : il peut contenir des réglages privés |

**Avant chaque envoi sur GitHub :**
- relire la liste des fichiers envoyés : seulement `README`, `src/`, `tests/`, `dify/`, `donnees/`, `.github/`, `requirements.txt`, `.gitignore` ;
- chercher les mots `password`, `key`, `token`, `@gmail` dans ce que tu ajoutes ;
- laisser activée la protection de GitHub (Settings → Code security → Secret scanning et Push protection) : elle bloque l'envoi de la plupart des clés.

**Si un secret part par erreur :** le changer tout de suite (nouveau mot de passe d'application, nouvelle clé). Supprimer le fichier ne suffit pas, à cause de l'historique.

Le workflow de mise à jour n'utilise aucun secret : le jeton `GITHUB_TOKEN` est fourni par GitHub, limité à ce dépôt, et ne sert qu'à enregistrer `donnees/`.

## Limites

- Les causes de retard sont déclarées par les compagnies ; un retard à plusieurs causes est réparti au prorata des minutes.
- Le BTS ne couvre que les vols intérieurs américains.
- La mise à jour dépend de la disponibilité des sites du BTS et de l'université de l'Iowa. Si l'un d'eux ne répond pas, le workflow échoue sans rien publier, et GitHub envoie un mail au propriétaire du dépôt.
- GitHub met en pause les tâches planifiées d'un dépôt public resté 60 jours sans activité ; la mise à jour mensuelle devrait l'éviter. Sinon, les relancer depuis l'onglet Actions.
