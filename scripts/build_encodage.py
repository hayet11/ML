# pyright: reportAttributeAccessIssue=false, reportArgumentType=false, reportOperatorIssue=false
"""
Construit webapp/encodage.json : la correspondance libelle -> code
utilisee a l'entrainement.

Sans ce fichier, le site ne pourrait pas encoder HANDSET / OFFRE / STATUT
de la meme maniere que le notebook. Un "4G" doit devenir exactement le meme
nombre que pendant l'entrainement.

A relancer si l'on reentraine le modele.
"""

import json
import pandas as pd
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CIBLE = ROOT / 'data' / 'raw' / 'CIBLE_CHURN_SAMPLE2_new.csv'
SORTIE = ROOT / 'webapp' / 'encodage.json'

# on relit le brut d'entrainement
cible: pd.DataFrame = pd.read_csv(CIBLE, sep=';', dtype=str,
                                  keep_default_na=False)
cible.columns = [c.strip() for c in cible.columns]
for c in cible.columns:
    cible[c] = cible[c].astype(str).str.strip()

# meme nettoyage que le notebook 01
cible['HANDSET'] = cible['HANDSET'].replace({'': 'Inconnu', 'NA': 'Inconnu'})

# libelle -> code, ordre alphabetique (comme .astype('category').cat.codes)
encodage = {}
for colonne in ['HANDSET', 'OFFRE', 'STATUT']:
    categories = sorted(cible[colonne].unique())
    encodage[colonne] = {str(lib): i for i, lib in enumerate(categories)}
    print(f'{colonne:8s} {len(categories):>3} modalites')

SORTIE.parent.mkdir(exist_ok=True)
with open(SORTIE, 'w', encoding='utf-8') as f:
    json.dump(encodage, f, ensure_ascii=False, indent=2)

print()
print('fichier ecrit :', SORTIE)
print('exemple STATUT :', encodage['STATUT'])
print('exemple HANDSET:', encodage['HANDSET'])
