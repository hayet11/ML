"""
Audit d'integrite de data/final/all_tables.csv (sans CODE_CONTRAT).

Le fichier final ne contient plus la cle. Pour verifier, on la reconstruit
depuis data/processed/agg_cible.csv : le fichier final est construit par une
suite de left join depuis agg_cible, donc l'ordre des lignes est conserve.

1. Structure : nombre de lignes, colonnes attendues, aucune ligne vide
2. Valeurs : recalcul depuis les fichiers BRUTS, ligne par ligne
3. Label : coherence avec statut_next_month
4. Decalage : aucune valeur attribuee au mauvais contrat
"""

# pyright: reportAttributeAccessIssue=false, reportOperatorIssue=false, reportArgumentType=false
#
# Les stubs de pandas declarent df["col"] comme une union qui inclut float/Number,
# sur laquelle .fillna() et + n'existent pas. Ce sont des faux positifs : a
# l'execution, df["col"] est toujours une Series. Sans effet sur le runtime.

import pandas as pd
import numpy as np
from pathlib import Path
from typing import cast

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / 'data' / 'raw'
PROCESSED = ROOT / 'data' / 'processed'
FINAL = ROOT / 'data' / 'final' / 'all_tables.csv'

COLONNES_ATTENDUES = ['ANC_M', 'HANDSET', 'OFFRE', 'STATUT', 'churn',
                      'VOLUME_SESSION', 'MNT_RECH', 'MNT_FORFAIT',
                      'APPEL_TOTAL', 'SMS_TOTAL']

final = pd.read_csv(FINAL, dtype=str, keep_default_na=False)

# la cle, reconstruite pour la verification uniquement
cible = pd.read_csv(RAW / 'CIBLE_CHURN_SAMPLE2_new.csv', sep=';', dtype=str,
                    keep_default_na=False)
cible.columns = [c.strip() for c in cible.columns]
for col in cible.columns:
    cible[col] = cible[col].astype(str).str.strip()

agg_cible = pd.read_csv(PROCESSED / 'agg_cible.csv', dtype=str, keep_default_na=False)
cles = agg_cible['CODE_CONTRAT'].astype(str).str.strip().tolist()

# ---------------------------------------------------------------- 1. structure
print('=' * 70)
print('1. STRUCTURE')
print('=' * 70)
lignes_vides = int(np.asarray(final.isna().all(axis=1)).sum())
print('lignes                  :', len(final))
print('colonnes                :', len(final.columns))
print('CODE_CONTRAT absent     :', 'CODE_CONTRAT' not in final.columns)
print('colonnes attendues      :', list(final.columns) == COLONNES_ATTENDUES)
print('lignes vides (tout NaN) :', lignes_vides)
print('cles reconstruites      :', len(cles))
print('meme nombre de lignes   :', len(cles) == len(final))
print()

oriente = final.copy()
oriente.index = pd.Index(cles, name='CODE_CONTRAT')

# ---------------------------------------------------------------- 2. valeurs
print('=' * 70)
print('2. RECALCUL DES VALEURS DEPUIS LES BRUTS')
print('=' * 70)

def lire_brut(fichier: str) -> pd.DataFrame:
    df: pd.DataFrame = pd.read_csv(RAW / fichier, sep=';', dtype=str,
                                   keep_default_na=False)
    df.columns = [c.strip() for c in df.columns]
    for c in df.columns:
        df[c] = df[c].astype(str).str.strip()
    df['mois'] = pd.to_datetime(
        cast(pd.Series, df['MONTH_DT']).replace('', np.nan),
        format='%d%b%Y:%H:%M:%S', errors='coerce')
    mois = cast(pd.Series, df['mois'])
    masque = mois.notna() & (mois.dt.month <= 11)
    return df.loc[masque].copy()

def colonne_num(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    resultat = df.copy()
    for c in cols:
        resultat[c] = pd.to_numeric(resultat[c])
    return resultat

def moyenne_par_contrat(df: pd.DataFrame, col: str) -> pd.Series:
    groupe = df.groupby('CODE_CONTRAT')[col].mean()
    return cast(pd.Series, groupe)

def somme_par_contrat(df: pd.DataFrame, col: str) -> pd.Series:
    groupe = df.groupby('CODE_CONTRAT')[col].sum()
    return cast(pd.Series, groupe)

d = colonne_num(lire_brut('DATA_CHURN_2NW_2025.csv'), ['VOLUME_SESSION'])
ref_data = moyenne_par_contrat(d, 'VOLUME_SESSION')

r = colonne_num(lire_brut('RECHARGE_CHURN_2NW_2025.csv'), ['MNT_RECH'])
ref_rech = moyenne_par_contrat(r, 'MNT_RECH')

u = colonne_num(lire_brut('USSD_CHURN_2NW_2025.csv'), ['MNT_FORFAIT'])
ref_ussd = moyenne_par_contrat(u, 'MNT_FORFAIT')

e = colonne_num(lire_brut('ENTRANT_CHURN_2NW_2025.csv'), ['DUREE_APPEL_IN', 'NB_SMS_IN'])
s = colonne_num(lire_brut('SORTANT_CHURN_2NW_2025.csv'), ['DUREE_APPEL_TOT', 'nb_sms_tot'])
mensuel = e[['CODE_CONTRAT', 'mois', 'DUREE_APPEL_IN', 'NB_SMS_IN']].merge(
    s[['CODE_CONTRAT', 'mois', 'DUREE_APPEL_TOT', 'nb_sms_tot']],
    on=['CODE_CONTRAT', 'mois'], how='outer')
for col in ['DUREE_APPEL_IN', 'DUREE_APPEL_TOT', 'NB_SMS_IN', 'nb_sms_tot']:
    mensuel[col] = pd.to_numeric(mensuel[col], errors='coerce').fillna(0)
mensuel['APPEL_TOTAL'] = (pd.to_numeric(mensuel['DUREE_APPEL_IN'])
                          + pd.to_numeric(mensuel['DUREE_APPEL_TOT']))
mensuel['SMS_TOTAL'] = (pd.to_numeric(mensuel['NB_SMS_IN'])
                        + pd.to_numeric(mensuel['nb_sms_tot']))
ref_appels = somme_par_contrat(mensuel, 'APPEL_TOTAL')
ref_sms = somme_par_contrat(mensuel, 'SMS_TOTAL')

ref_cible = cible.set_index('CODE_CONTRAT')

def comparer(nom: str, ref: pd.Series, tolerance: float = 1e-5) -> bool:
    a = pd.to_numeric(oriente[nom], errors='coerce').fillna(0).astype(float)
    b = ref.reindex(oriente.index).fillna(0).astype(float)
    ecart = (a - b).abs()
    ok = int(np.asarray(ecart <= tolerance).sum())
    etat = 'OK' if ok == len(a) else 'ECART'
    print(f'{nom:16s} identiques {ok:>6,} / {len(a):,}   ecart max {ecart.max():.6f}   {etat}')
    return ok == len(a)

tout_ok = True
tout_ok &= comparer('VOLUME_SESSION', ref_data)
tout_ok &= comparer('MNT_RECH', ref_rech)
tout_ok &= comparer('MNT_FORFAIT', ref_ussd)
tout_ok &= comparer('APPEL_TOTAL', ref_appels, tolerance=1e-4)
tout_ok &= comparer('SMS_TOTAL', ref_sms)
print()

print('--- colonnes statiques ---')
for col in ['ANC_M', 'HANDSET', 'OFFRE', 'STATUT']:
    a = oriente[col].astype(str).str.strip()
    b = cast(pd.Series, ref_cible[col]).reindex(oriente.index).astype(str).str.strip()
    ok = int(np.asarray(a == b).sum())
    tout_ok &= ok == len(a)
    print(f'{col:16s} identiques {ok:>6,} / {len(a):,}   {"OK" if ok == len(a) else "ECART"}')
print()

# ---------------------------------------------------------------- 3. label
print('=' * 70)
print('3. LE LABEL')
print('=' * 70)
churn = pd.to_numeric(oriente['churn'], errors='coerce')
statut_suivant = cast(pd.Series, ref_cible['statut_next_month']).reindex(oriente.index)
attendu = (statut_suivant != 'A').astype(int)
ok = int(np.asarray(churn == attendu).sum())
tout_ok &= ok == len(churn)
print('churn identique a statut_next_month :', ok, '/', len(churn))
print('taux de churn :', round(float(churn.mean()) * 100, 2), '%')
print()

# ---------------------------------------------------------------- 4. decalage
print('=' * 70)
print('4. DECALAGE ENTRE LIGNES')
print('=' * 70)
x = np.asarray(pd.to_numeric(oriente['APPEL_TOTAL'], errors='coerce').fillna(0), dtype=float)
y = np.asarray(ref_appels.reindex(oriente.index).fillna(0), dtype=float)
correlation = float(np.corrcoef(x, y)[0, 1])
print('correlation APPEL_TOTAL / reference :', round(correlation, 8))
tout_ok &= correlation > 0.9999
print()

print('=' * 70)
print('CONCLUSION :', 'TOUT EST CORRECT' if tout_ok else 'DES ECARTS SUBSISTENT')
print('=' * 70)
