"""
Diagnostic complet de data/final/all_tables.csv
pour decider du nettoyage avant modelisation.
"""
import pandas as pd
import numpy as np

F = 'data/final/all_tables.csv'

# keep_default_na=False : preserve HANDSET='NA' comme CATEGORIE (terminal non
# identifie, 1302 clients), au lieu de le relire comme une valeur manquante.
# na_values=[''] : les cellules vides deviennent quand meme NaN, sinon elles
# resteraient des chaines '' invisibles pour df[c].isna().sum().
df = pd.read_csv(F, keep_default_na=False, na_values=[''], low_memory=False)

NUM = ['ANC_M', 'VOLUME_SESSION', 'MNT_RECH', 'MNT_FORFAIT', 'APPEL_TOTAL', 'SMS_TOTAL']
CAT = ['HANDSET', 'OFFRE', 'STATUT']

for c in NUM + ['churn']:
    df[c] = pd.to_numeric(df[c], errors='coerce')

print('=' * 72)
print('1. DIMENSIONS ET TYPES')
print('=' * 72)
print('lignes :', len(df), '| colonnes :', df.shape[1])
print()
print(df.dtypes.to_string())
print()
print('lignes entierement dupliquees :', int(df.duplicated().sum()))
print()

print('=' * 72)
print('2. VALEURS MANQUANTES')
print('=' * 72)
for c in df.columns:
    n = int(df[c].isna().sum())
    if n:
        print(f'  {c:16s} {n:>6,}  ({n/len(df)*100:>5.1f} %)')


# relation entre les manquants et le churn
print()
print('  --- un manquant est-il lie au churn ? ---')
for c in ['VOLUME_SESSION', 'MNT_FORFAIT', 'MNT_RECH']:
    absent = df[c].isna()
    print(f'  {c:16s} absent -> churn {df.loc[absent,"churn"].mean()*100:>5.1f} %  |  '
          f'present -> churn {df.loc[~absent,"churn"].mean()*100:>5.1f} %')

print()
print('=' * 72)
print('3. VALEURS EXTREMES (outliers)')
print('=' * 72)
print(f'{"colonne":16s} {"P99":>10s} {"max":>10s} {"max/P99":>9s} {"nb>3xP99":>10s}')
for c in NUM:
    s = df[c].dropna()
    if len(s) == 0:
        continue
    p99 = s.quantile(0.99)
    mx = s.max()
    ratio = mx / p99 if p99 > 0 else np.nan
    nb = int((s > 3 * p99).sum()) if p99 > 0 else 0
    print(f'{c:16s} {p99:>10.1f} {mx:>10.1f} {ratio:>9.1f} {nb:>10,}')

print()
print('=' * 72)
print('4. COLONNES CATEGORIELLES')
print('=' * 72)
for c in CAT:
    vc = df[c].value_counts()
    print(f'{c}: {len(vc)} modalites')
    if len(vc) <= 8:
        print('   ', dict(vc.head(8)))
    else:
        print('    top 5 :', dict(vc.head(5)))
        print(f'    modalites avec < 50 contrats : {int((vc < 50).sum())}')
        rares = int(vc[vc < 50].sum())
        part = rares / len(df) * 100
        print(f'    contrats concernes : {rares:,} ({part:.1f} %)')
    print()

print('=' * 72)
print('5. VALEURS NEGATIVES OU ZERO')
print('=' * 72)
for c in NUM:
    s = df[c].dropna()
    print(f'{c:16s} negatifs: {int((s<0).sum()):>5} | zeros: {int((s==0).sum()):>6,}')

print()
print('=' * 72)
print('6. CORRELATIONS (colinearite)')
print('=' * 72)
corr = pd.DataFrame(df[NUM]).corr()
paires = []
for i, a in enumerate(NUM):
    for b in NUM[i + 1:]:
        r = float(corr.loc[a, b])
        if abs(r) > 0.4:
            paires.append((a, b, r))
if paires:
    for a, b, r in sorted(paires, key=lambda x: -abs(x[2])):
        print(f'  {a:16s} / {b:16s}  r = {r:+.3f}')
else:
    print('  aucune paire > 0.4')

print()
print('=' * 72)
print('7. DISTRIBUTION DU CHURN PAR MODALITE (OFFRE)')
print('=' * 72)
stats_offre = df.groupby('OFFRE')['churn'].agg(nb='size', taux='mean')
t = pd.DataFrame({
    'size': stats_offre['nb'],
    'mean': (stats_offre['taux'] * 100).round(1),
})
t = t.sort_values('size', ascending=False)
print('top 10 offres par effectif :')
print(t.head(10).to_string())
print()
rares = t[t['size'] < 100]
print(f'offres avec >= 100 contrats : {len(t) - len(rares)}')
print(f'offres avec < 100 contrats  : {len(rares)}')
print(f'contrats dans ces offres rares : {int(rares["size"].sum()):,}')

print()
print('=' * 72)
print('8. SEUIL : combien de modalites OFFRE pour couvrir 95 % ?')
print('=' * 72)
vc = df['OFFRE'].value_counts()
cum = (vc.cumsum() / len(df)).to_numpy()
for seuil in [0.80, 0.90, 0.95, 0.99]:
    # nombre d'offres qu'il faut pour ATTEINDRE le seuil.
    # on cherche la premiere couverture >= seuil : d'ou le '<' et le +1.
    # (un '<=' avec +1 surcompterait quand une couverture egale le seuil)
    n = int((cum < seuil).sum()) + 1
    couverture = cum[n - 1] * 100
    print(f'  {int(seuil*100)} % des contrats -> {n} offres sur {len(vc)}'
          f'  (couvre {couverture:.1f} %)')
