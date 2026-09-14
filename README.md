# Baromètre de crise

Deux tableaux de bord statiques (États-Unis/monde et France) avec jauges et score de crise,
rafraîchis automatiquement chaque lundi par GitHub Actions, hébergés gratuitement sur GitHub Pages.

## Mise en ligne (une fois, 15 min)

1. Créer un compte GitHub si besoin, puis un dépôt **public** nommé `barometre` (Pages gratuit = dépôt public).
2. Y déposer tous les fichiers de ce dossier (glisser-déposer dans l'interface web, ou `git push`).
3. Clé FRED : https://fred.stlouisfed.org/docs/api/api_key.html (gratuit, immédiat).
   Dans le dépôt : Settings → Secrets and variables → Actions → New repository secret → nom `FRED_API_KEY`.
4. Settings → Pages → Source : *Deploy from a branch* → branche `main`, dossier `/ (root)` → Save.
5. Onglet Actions → workflow *refresh-data* → *Run workflow*. Deux minutes plus tard :
   `https://<ton-pseudo>.github.io/barometre/` (US) et `.../france.html`.

Optionnel : token INSEE (https://portail-api.insee.fr, gratuit) dans un secret `INSEE_TOKEN` pour automatiser
climat des affaires, confiance des ménages et règle de Sahm France. Sans lui, ces trois-là restent manuels.

## Au quotidien

- Rien à faire : le lundi matin, `fetch.py` interroge FRED et la BCE, réécrit `data/*.json`, commit, Pages se redéploie.
- Une fois par mois, 5 minutes : éditer `manual/us.json` et `manual/fr.json` directement sur GitHub
  (icône crayon) pour ISM, LEI, CAPE, PMI HCOB, défaillances, logements, trafic Vinci. Le commit relance le workflow.
- Un chiffre automatique paraît faux ? Mettre `"force": true` sur cet indicateur dans `manual/` : ta valeur prime.
- Les erreurs de collecte sont listées dans `data/*.json` (`errors`) et visibles dans le log Actions ;
  l'ancienne valeur est conservée, jamais effacée.

## Fichiers

| Fichier | Rôle |
|---|---|
| `index.html`, `france.html` | Les dashboards. Autonomes : ouverts en local ils affichent les valeurs embarquées ; en ligne ils chargent `data/*.json`. |
| `data/us.json`, `data/fr.json` | Valeurs courantes, écrites par `fetch.py`. Ne pas éditer à la main. |
| `manual/*.json` | Tes saisies manuelles et le bandeau de contexte. |
| `fetch.py` | Collecte. Sans dépendance externe (Python standard). |
| `.github/workflows/refresh.yml` | Planification hebdo + déclenchement sur édition manuelle. |

## Modifier les indicateurs

Seuils, poids, textes et liens sont dans le bloc `DONNÉES` en haut de chaque HTML (tableau `INDICATORS`).
Pour ajouter un indicateur : une ligne dans `INDICATORS` + une ligne dans `US`/`FR` de `fetch.py`
(ou dans `manual/`). Les ids doivent correspondre.

Deux identifiants sont à vérifier lors de la première exécution, ils peuvent avoir changé : la clé de série
CISS de la BCE dans `ecb_ciss()` et les idbanks INSEE dans `INSEE_IDBANK` (le log Actions le dira).

## Lecture

0–25 calme · 25–50 vigilance · 50–75 alerte · > 75 crise probable. Trois jauges rouges de *timing*
valent alerte quelle que soit la moyenne. Les pondérations sont un jugement, pas une calibration économétrique.
