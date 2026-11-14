"""
Construit data/final/all_tables.csv.

Entree  : data/processed/agg_cible.csv + les agg_* de mesures
          + les 2 fichiers BRUTS entrant/sortant (pour les totaux appels/SMS)
Sortie  : data/final/all_tables.csv

Regles :
  - Canal_De_Vente est retiree
  - APPEL_TOTAL et SMS_TOTAL = SOMME de recu + emis sur toute la periode.
    On additionne mois par mois, puis on additionne les 11 mois.
    Un client qui recoit 100 min en janvier et emet 50 min en fevrier
    a bien 150 min au total.
"""

import pandas as pd
import numpy as np
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROCESSED = ROOT / 'data' / 'processed'
RAW = ROOT / 'data' / 'raw'
OUT = ROOT / 'data' / 'final'
OUT.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------- 1. brut
def lire_brut(fichier: str, colonnes: list[str]) -> pd.DataFrame:
    df: pd.DataFrame = pd.read_csv(RAW / fichier, sep=';', dtype=str,
                                   keep_default_na=False)
    df.columns = [c.strip() for c in df.columns]
    for c in df.columns:
        df[c] = df[c].str.strip()
    df['mois'] = pd.to_datetime(df['MONTH_DT'].replace('', np.nan),
                                format='%d%b%Y:%H:%M:%S', errors='coerce')

    # ne garde que les lignes avec une date, et seulement janvier->novembre
    masque = df['mois'].notna() & (df['mois'].dt.month <= 11)
    df = df.loc[masque].copy()

    resultat: pd.DataFrame = df.loc[:, ['CODE_CONTRAT', 'mois'] + colonnes].copy()
    for c in colonnes:
        resultat[c] = pd.to_numeric(resultat[c])
    return resultat

recu  = lire_brut('ENTRANT_CHURN_2NW_2025.csv', ['DUREE_APPEL_IN', 'NB_SMS_IN'])
emis  = lire_brut('SORTANT_CHURN_2NW_2025.csv', ['DUREE_APPEL_TOT', 'nb_sms_tot'])

# un contrat peut etre dans une table sans etre dans l'autre
mensuel = recu.merge(emis, on=['CODE_CONTRAT', 'mois'], how='outer')

# total par mois = recu + emis (une absence vaut 0 activite)
mensuel['APPEL_TOTAL'] = mensuel['DUREE_APPEL_IN'].fillna(0) + mensuel['DUREE_APPEL_TOT'].fillna(0)
mensuel['SMS_TOTAL']   = mensuel['NB_SMS_IN'].fillna(0) + mensuel['nb_sms_tot'].fillna(0)

# SOMME sur les 11 mois, par contrat
totaux = mensuel.groupby('CODE_CONTRAT')[['APPEL_TOTAL', 'SMS_TOTAL']].sum()

# ---------------------------------------------------------------- 2. assemblage
final = pd.read_csv(PROCESSED / 'agg_cible.csv', keep_default_na=False)

# retire Canal_De_Vente
final = final.drop(columns=['Canal_De_Vente'])

# ajoute la data et les montants
for nom in ['data', 'recharge', 'ussd']:
    bloc = pd.read_csv(PROCESSED / f'agg_{nom}.csv', keep_default_na=False)
    final = final.merge(bloc, on='CODE_CONTRAT', how='left')

# ajoute les totaux appels / SMS
# les contrats absents de `totaux` n'ont eu aucune activite sur janvier->novembre :
# leur SOMME vaut 0, ce n'est pas une valeur inconnue.
final = final.merge(totaux.reset_index(), on='CODE_CONTRAT', how='left')
final = final.fillna({'APPEL_TOTAL': 0, 'SMS_TOTAL': 0})

# ---------------------------------------------------------------- 3. controle
# le controle se fait AVANT de retirer la cle, sinon il n'y a plus rien a verifier
assert len(final) == final['CODE_CONTRAT'].nunique(), 'doublon sur CODE_CONTRAT'
print('controle : 1 ligne par contrat OK')

# retire la cle : le fichier ne contient plus que les features et le label
final = final.drop(columns=['CODE_CONTRAT'])

final.to_csv(OUT / 'all_tables.csv', index=False)

print('fichier ecrit :', OUT / 'all_tables.csv')
print('forme         :', final.shape)
print('colonnes      :', list(final.columns))
print()
print('contrats avec somme appels = 0 :', int((final['APPEL_TOTAL'] == 0).sum()))
print('contrats avec somme SMS    = 0 :', int((final['SMS_TOTAL'] == 0).sum()))
print('NaN restants dans APPEL_TOTAL  :', int(final['APPEL_TOTAL'].isna().sum()))
print('NaN restants dans SMS_TOTAL    :', int(final['SMS_TOTAL'].isna().sum()))
