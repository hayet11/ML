# Site de prédiction de churn

Application web locale qui prend les **6 fichiers bruts du mois**,
applique le modèle entraîné, et renvoie un **CSV avec la prédiction
pour chaque client**.

## Démarrage

```bash
python webapp/app.py
```

Puis ouvrir **http://localhost:5001**

Pour arrêter : `Ctrl+C`

## Ce dont le site a besoin

| Élément | Emplacement | Rôle |
|---|---|---|
| Le modèle | `models/modele_churn_sklearn16.joblib` | produit par le notebook 06 |
| Les tables d'encodage | `webapp/encodage.json` | produit par `scripts/build_encodage.py` |

## Les 6 fichiers à déposer

| Champ | Fichier habituel |
|---|---|
| `cible` | `CIBLE_CHURN_SAMPLE4_new.csv` |
| `data` | `DATA_CHURN4_NEW_2025.csv` |
| `entrant` | `ENTRANT_CHURN4_NEW_2025.csv` |
| `sortant` | `SORTANT_CHURN4_NEW_2025.csv` |
| `recharge` | `RECHARGE_CHURN4_NEW_2025.csv` |
| `ussd` | `USSD_CHURN4_NEW_2025.csv` |

Format : CSV séparé par des **points-virgules**.

⚠️ **La table CIBLE ne doit pas contenir le résultat** (`statut_next_month`
ou `churn`). Si la colonne est présente, elle est simplement ignorée —
le site ne s'en sert jamais.

## Le fichier produit

`resultat_churn_<date>.csv` — une ligne par client :

| Colonne | Contenu |
|---|---|
| `CODE_CONTRAT` | identifiant du client |
| `ANC_M` | ancienneté en mois |
| `HANDSET` | terminal |
| `OFFRE` | offre souscrite |
| `STATUT` | `actif` ou `suspendu` |
| `probabilite_churn` | entre 0 et 1 |
| `prediction` | `churn` ou `reste` |

Trié par probabilité décroissante : les clients les plus à risque en premier.

## Le seuil de décision

**Il est figé à 0,54.** Ce n'est plus un réglage sur la page.

C'est la valeur qui maximise le taux de bonnes réponses sur les données de
référence :

| Seuil | Bonnes réponses |
|---|---|
| 0,50 | 30 600 (90,00 %) |
| **0,54** | **30 623 (90,07 %)** |

Le gain est mince (+23 clients sur 34 000), mais c'est le meilleur résultat
mesuré. La constante se change dans `webapp/app.py` :

```python
SEUIL_DECISION = 0.54
```

Le CSV contient de toute façon la probabilité brute : pour un autre seuil,
il suffit de filtrer la colonne `probabilite_churn` dans Excel, sans
relancer le site.

## Comment le site transforme les fichiers

Il reproduit exactement le pipeline du notebook 01 :

```
6 fichiers bruts
      ↓  lecture (séparateur ; et espaces)
      ↓  suppression des lignes sans MONTH_DT (client inactif)
      ↓  exclusion de décembre (le label parle du mois suivant)
      ↓  moyenne pour l'usage, somme pour les volumes d'appels/SMS
      ↓  jointure sur CODE_CONTRAT
34 000 lignes × 9 colonnes
      ↓  encodage HANDSET / OFFRE / STATUT
      ↓  predict_proba
prédiction par client
```

Les colonnes `VOLUME_SESSION`, `MNT_RECH`, `MNT_FORFAIT`, `APPEL_TOTAL`,
`SMS_TOTAL` ont été vérifiées : le site produit exactement les mêmes
valeurs que `data/final/all_tables_new.csv` (écart 0,000000).

**Remplissage des valeurs manquantes.** À l'entraînement (notebook 03),
toutes les colonnes numériques valaient 0 quand la mesure était absente,
et toutes les catégories étaient encodées. Le modèle n'a donc **jamais vu
de NaN**. Le site reproduit ce cas : avant la prédiction, il remplit toutes
les colonnes par 0.

Ce n'est pas un détail : sans ce remplissage, **11 878 clients changeraient
de prédiction**, avec un écart allant jusqu'à 0,43 de probabilité.

## Points d'attention

**Le fichier `encodage.json` est indispensable.** Le modèle attend des codes
numériques pour `HANDSET`, `OFFRE` et `STATUT`. Ce fichier contient la
correspondance exacte utilisée à l'entraînement. S'il manque ou s'il
correspond à un autre modèle, les prédictions seront fausses **sans erreur
visible**.

**À régénérer si tu réentraînes :**

```bash
python scripts/build_encodage.py
```

**Les nouvelles offres.** Si un fichier contient une offre, un terminal ou un
statut jamais vu à l'entraînement, le site **refuse de prédire** et affiche un
message qui liste les valeurs en cause.

C'est volontaire : une modalité inconnue n'a pas de code. La convertir
silencieusement en 0 reviendrait à la déclarer « première catégorie
alphabétique », ce qui produirait une prédiction fausse sans que personne
ne le sache.

Pour obtenir quand même un résultat, cocher **« Continuer malgré les valeurs
inconnues »**. Le CSV contient alors une colonne `donnee_incomplete` qui
marque les lignes concernées (`oui`).

La vraie solution reste de réentraîner le modèle avec ces nouvelles
modalités (notebooks 03 et 06, puis `scripts/build_encodage.py`).

## Refaire une prédiction

L'envoi passe par AJAX : après un téléchargement, le formulaire redevient
immédiatement utilisable, sans recharger la page. En cas d'erreur, le message
s'affiche en haut de page et les fichiers déposés sont conservés.

**Ce site est local.** Il n'a pas d'authentification ni de protection contre
les abus. Ne l'expose pas sur Internet tel quel.

## Structure

```
webapp/
  app.py                  serveur Flask (routes, upload, téléchargement)
  churn.py                transformation et prédiction
  encodage.json           table libellé -> code
  templates/index.html    page du formulaire
  static/style.css        mise en forme
  static/script.js        interactions (noms de fichiers, seuil, chargement)
scripts/
  build_encodage.py       génère encodage.json depuis les données d'entraînement
```
