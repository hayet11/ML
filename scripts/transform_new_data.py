# pyright: reportAttributeAccessIssue=false, reportArgumentType=false, reportOperatorIssue=false
#
# Les stubs de pandas declarent df["col"] comme une union incluant float/Number,
# sur laquelle .fillna() et .map() n'existent pas. Ce sont des faux positifs :
# a l'execution, df["col"] est toujours une Series.

"""
Transforme les fichiers de data/raw/new/ en une table unique,
au meme format que data/final/modele_operationnel.csv.

Entree  : data/raw/new/*.csv  (6 fichiers)
Sortie  : data/final/all_tables_new.csv

Memes regles que pour l'ancien jeu :
  - janvier a novembre (decembre exclu : le label parle du mois suivant)
  - lignes sans MONTH_DT supprimees (client inactif)
  - moyennes pour les niveaux d'usage, sommes pour les volumes d'appels/SMS
  - HANDSET / OFFRE / STATUT encodes avec la MEME table qu'a l'entrainement
"""

import pandas as pd
import numpy as np
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NEW = ROOT / 'data' / 'raw' / 'new'
FINAL = ROOT / 'data' / 'final'
ANCIEN = FINAL / 'modele_operationnel.csv'

FICHIERS = {
    'cible':    'CIBLE_CHURN_SAMPLE4_new.csv',
    'data':     'DATA_CHURN4_NEW_2025.csv',
    'entrant':  'ENTRANT_CHURN4_NEW_2025.csv',
    'sortant':  'SORTANT_CHURN4_NEW_2025.csv',
    'recharge': 'RECHARGE_CHURN4_NEW_2025.csv',
    'ussd':     'USSD_CHURN4_NEW_2025.csv',
}


def charger(nom: str) -> pd.DataFrame:
    """Lit un fichier brut et enleve les espaces autour des noms et valeurs."""
    df: pd.DataFrame = pd.read_csv(NEW / FICHIERS[nom], sep=';', dtype=str,
                                   keep_default_na=False)
    df.columns = [c.strip() for c in df.columns]
    for c in df.columns:
        df[c] = df[c].str.strip()
    return df


def garder_mois(df: pd.DataFrame, dernier_mois: int = 11) -> pd.DataFrame:
    """Convertit la date et garde janvier..novembre."""
    df = df.copy()
    df['mois'] = pd.to_datetime(df['MONTH_DT'], format='%d%b%Y:%H:%M:%S',
                                errors='coerce')
    mois = pd.Series(df['mois'])
    masque = mois.notna() & (mois.dt.month <= dernier_mois)
    return df.loc[masque].copy()


def moyenne_par_contrat(df: pd.DataFrame, colonne: str) -> pd.Series:
    valeurs = pd.Series(df[colonne])
    groupe = df.assign(_valeur=valeurs).groupby('CODE_CONTRAT')['_valeur'].mean()
    return pd.Series(groupe)


# ---------------------------------------------------------------- 1. cible
print('=== 1. table cible ===')
cible = charger('cible')
cible['churn'] = (cible['statut_next_month'] != 'A').astype(int)
cible['ANC_M'] = pd.to_numeric(cible['ANC_M'])
print(f'  {len(cible):,} contrats | churn {cible["churn"].mean()*100:.2f} %')

# ---------------------------------------------------------------- 2. mesures
print()
print('=== 2. tables mensuelles ===')

d = garder_mois(charger('data'))
d['VOLUME_SESSION'] = pd.to_numeric(d['VOLUME_SESSION'], errors='coerce')
volume = moyenne_par_contrat(d, 'VOLUME_SESSION')
print(f'  data      : {len(d):>7,} lignes -> {len(volume):>6,} contrats')

r = garder_mois(charger('recharge'))
r['MNT_RECH'] = pd.to_numeric(r['MNT_RECH'], errors='coerce')
recharge = moyenne_par_contrat(r, 'MNT_RECH')
print(f'  recharge  : {len(r):>7,} lignes -> {len(recharge):>6,} contrats')

u = garder_mois(charger('ussd'))
u['MNT_FORFAIT'] = pd.to_numeric(u['MNT_FORFAIT'], errors='coerce')
forfait = moyenne_par_contrat(u, 'MNT_FORFAIT')
print(f'  ussd      : {len(u):>7,} lignes -> {len(forfait):>6,} contrats')

# --- appels et SMS : somme recu + emis, mois par mois ---
e = garder_mois(charger('entrant'))
s = garder_mois(charger('sortant'))
for c in ['DUREE_APPEL_IN', 'NB_SMS_IN']:
    e[c] = pd.to_numeric(e[c], errors='coerce')
for c in ['DUREE_APPEL_TOT', 'nb_sms_tot']:
    s[c] = pd.to_numeric(s[c], errors='coerce')

recu: pd.DataFrame = pd.DataFrame(
    e[['CODE_CONTRAT', 'mois', 'DUREE_APPEL_IN', 'NB_SMS_IN']])
emis: pd.DataFrame = pd.DataFrame(
    s[['CODE_CONTRAT', 'mois', 'DUREE_APPEL_TOT', 'nb_sms_tot']])

mensuel: pd.DataFrame = recu.merge(emis, on=['CODE_CONTRAT', 'mois'], how='outer')

col_in = pd.to_numeric(mensuel['DUREE_APPEL_IN'], errors='coerce').fillna(0)
col_out = pd.to_numeric(mensuel['DUREE_APPEL_TOT'], errors='coerce').fillna(0)
sms_in = pd.to_numeric(mensuel['NB_SMS_IN'], errors='coerce').fillna(0)
sms_out = pd.to_numeric(mensuel['nb_sms_tot'], errors='coerce').fillna(0)

mensuel['APPEL_TOTAL'] = col_in + col_out
mensuel['SMS_TOTAL'] = sms_in + sms_out

appels = mensuel.groupby('CODE_CONTRAT')[['APPEL_TOTAL', 'SMS_TOTAL']].sum()
print(f'  appels    : {len(mensuel):>7,} lignes -> {len(appels):>6,} contrats')

# ---------------------------------------------------------------- 3. encodage
print()
print('=== 3. encodage des categories ===')
print("  on reutilise la MEME correspondance qu'a l'entrainement.")

ancien: pd.DataFrame = pd.read_csv(ANCIEN, keep_default_na=False,
                                   na_values=[''], low_memory=False)

ancien_brut: pd.DataFrame = pd.read_csv(
    ROOT / 'data' / 'raw' / 'CIBLE_CHURN_SAMPLE2_new.csv',
    sep=';', dtype=str, keep_default_na=False)
ancien_brut.columns = [c.strip() for c in ancien_brut.columns]
for c in ancien_brut.columns:
    ancien_brut[c] = ancien_brut[c].str.strip()
ancien_brut['HANDSET'] = ancien_brut['HANDSET'].replace(
    {'': 'Inconnu', 'NA': 'Inconnu'})

# libelle -> code, dans l'ordre alphabetique
# (exactement ce que fait pandas avec .astype('category').cat.codes)
correspondances = {}
for colonne in ['HANDSET', 'OFFRE', 'STATUT']:
    categories = sorted(ancien_brut[colonne].unique())
    correspondances[colonne] = {lib: i for i, lib in enumerate(categories)}
    print(f'  {colonne:8s} {len(categories):>3} modalites')

# ---------------------------------------------------------------- 4. valeurs inconnues
print()
print('=== 4. valeurs jamais vues a l entrainement ===')

cible['HANDSET'] = cible['HANDSET'].replace({'': 'Inconnu', 'NA': 'Inconnu'})

for colonne in ['HANDSET', 'OFFRE', 'STATUT']:
    table = correspondances[colonne]
    valeurs = set(cible[colonne].unique())
    manquants = sorted(valeurs - set(table))
    if manquants:
        lignes = int(cible[colonne].isin(manquants).sum())
        print(f'  {colonne} : {len(manquants)} valeur(s) inconnue(s), '
              f'{lignes} lignes concernees')
        for m in manquants[:6]:
            print(f'     - {m!r}')
    else:
        print(f'  {colonne} : toutes les valeurs sont connues')

# ---------------------------------------------------------------- 5. assemblage
print()
print('=== 5. assemblage ===')

final: pd.DataFrame = pd.DataFrame(
    cible[['CODE_CONTRAT', 'ANC_M', 'HANDSET', 'OFFRE', 'STATUT', 'churn']]).copy()

# .map() renvoie NaN pour une valeur absente de la table -> le modele
# traite ces lignes comme "offre inconnue", ce qui est correct.
final['HANDSET'] = final['HANDSET'].map(correspondances['HANDSET'])
final['OFFRE'] = final['OFFRE'].map(correspondances['OFFRE'])
final['STATUT'] = final['STATUT'].map(correspondances['STATUT'])

final = final.set_index('CODE_CONTRAT')
final['VOLUME_SESSION'] = volume
final['MNT_RECH'] = recharge
final['MNT_FORFAIT'] = forfait
final['APPEL_TOTAL'] = appels['APPEL_TOTAL']
final['SMS_TOTAL'] = appels['SMS_TOTAL']
final = final.reset_index()

final[['APPEL_TOTAL', 'SMS_TOTAL']] = final[
    ['APPEL_TOTAL', 'SMS_TOTAL']].fillna(0)

ordre = list(ancien.columns)
final = pd.DataFrame(final.loc[:, ordre])

final.to_csv(FINAL / 'all_tables_new.csv', index=False)

print(f'  fichier ecrit : {FINAL / "all_tables_new.csv"}')
print(f'  forme         : {final.shape}')

# ---------------------------------------------------------------- 6. controle
print()
print('=== 6. controle de compatibilite ===')
print('  memes colonnes que le modele :', list(final.columns) == ordre)
print(f'  taux de churn : {final["churn"].mean()*100:.2f} %')
print()
print('  valeurs manquantes par colonne :')
manquants = final.isna().sum()
for c in final.columns:
    n = int(manquants[c])
    if n:
        print(f'    {c:16s} {n:>6,}  ({n / len(final) * 100:.1f} %)')
