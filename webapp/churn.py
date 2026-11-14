"""
Coeur du site : transformer les 6 fichiers bruts puis predire le churn.

Le modele attend 9 colonnes deja agregees. Les fichiers bruts contiennent
des lignes mensuelles : il faut donc reproduire exactement le pipeline du
notebook 01, puis encoder les categories comme a l'entrainement.
"""

# pyright: reportAttributeAccessIssue=false, reportArgumentType=false, reportOperatorIssue=false, reportReturnType=false, reportCallIssue=false
#
# Les stubs de pandas declarent df["col"] comme une union incluant
# float/NDArray, sur laquelle .replace()/.fillna() n'existent pas.
# Faux positifs : a l'execution df["col"] est toujours une Series.

import io
import joblib
import numpy as np
import pandas as pd
from pathlib import Path

# ---------------------------------------------------------------- chemins
ROOT = Path(__file__).resolve().parent.parent
MODELE = ROOT / 'models' / 'modele_churn_sklearn16.joblib'
ENCODAGE = ROOT / 'webapp' / 'encodage.json'
REFERENCE = ROOT / 'data' / 'raw' / 'CIBLE_CHURN_SAMPLE2_new.csv'

# le modele attend ces colonnes, dans cet ordre
COLONNES_MODELE = ['ANC_M', 'VOLUME_SESSION', 'MNT_RECH', 'MNT_FORFAIT',
                   'APPEL_TOTAL', 'SMS_TOTAL', 'HANDSET', 'OFFRE', 'STATUT']

# colonnes de mesures : une absence vaut 0 (aucune activite de ce type)
COLONNES_MESURES = ['ANC_M', 'VOLUME_SESSION', 'MNT_RECH', 'MNT_FORFAIT',
                    'APPEL_TOTAL', 'SMS_TOTAL']

# colonnes categorielles encodees : une valeur inconnue n'a pas de code
COLONNES_CATEGORIES = ['HANDSET', 'OFFRE', 'STATUT']


class ErreurDonnees(Exception):
    """Levee quand un fichier est illisible ou incomplet."""


# ---------------------------------------------------------------- lecture
def lire_csv(contenu: bytes, nom: str) -> pd.DataFrame:
    """Lit un CSV envoye par l'utilisateur (separateur ; et espaces)."""
    try:
        df = pd.read_csv(io.BytesIO(contenu), sep=';', dtype=str,
                         keep_default_na=False, encoding='utf-8')
    except UnicodeDecodeError:
        try:
            df = pd.read_csv(io.BytesIO(contenu), sep=';', dtype=str,
                             keep_default_na=False, encoding='latin-1')
        except Exception:
            raise ErreurDonnees(
                f'{nom} : fichier illisible. Attendu : CSV separe par ";"')
    except Exception:
        raise ErreurDonnees(f'{nom} : impossible de lire le fichier CSV.')

    df.columns = [c.strip() for c in df.columns]
    for c in df.columns:
        df[c] = df[c].astype(str).str.strip()
    return df


def exiger(df: pd.DataFrame, colonnes: list, nom: str) -> None:
    """Verifie que les colonnes attendues sont presentes."""
    manquantes = [c for c in colonnes if c not in df.columns]
    if manquantes:
        raise ErreurDonnees(
            f'{nom} : colonnes manquantes -> {", ".join(manquantes)}')


# ---------------------------------------------------------------- etapes
def extraire_cible(df: pd.DataFrame) -> pd.DataFrame:
    """Recupere le profil client (1 ligne par contrat)."""
    exiger(df, ['CODE_CONTRAT', 'ANC_M', 'HANDSET', 'OFFRE', 'STATUT'], 'CIBLE')
    cible = df[['CODE_CONTRAT', 'ANC_M', 'HANDSET', 'OFFRE', 'STATUT']].copy()
    cible['ANC_M'] = pd.to_numeric(cible['ANC_M'], errors='coerce')
    # meme nettoyage que le notebook 01
    cible['HANDSET'] = cible['HANDSET'].replace({'': 'Inconnu', 'NA': 'Inconnu'})
    # supprime les doublons de contrat s'il y en a
    cible = cible.drop_duplicates(subset=['CODE_CONTRAT'], keep='first')
    return cible


def garder_mois(df: pd.DataFrame, nom: str, dernier_mois: int = 11) -> pd.DataFrame:
    """Convertit MONTH_DT et garde janvier..novembre."""
    if 'MONTH_DT' not in df.columns:
        return pd.DataFrame(columns=['CODE_CONTRAT', 'mois'])
    df = df.copy()
    df['mois'] = pd.to_datetime(df['MONTH_DT'].replace('', np.nan),
                                format='%d%b%Y:%H:%M:%S', errors='coerce')
    masque = df['mois'].notna() & (df['mois'].dt.month <= dernier_mois)
    return df.loc[masque].copy()


def moyenne(df: pd.DataFrame, colonne: str) -> pd.Series:
    """Moyenne par contrat."""
    groupe = df.groupby('CODE_CONTRAT')[colonne].mean()
    return pd.Series(groupe)


def construire_table(fichiers: dict) -> pd.DataFrame:
    """Reconstruit la table agregee a partir des 6 fichiers bruts.

    fiche: dictionnaire {'cible': df, 'data': df, 'entrant': df, ...}
    """
    # --- 1. cible ---
    cible = extraire_cible(fichiers['cible'])
    if len(cible) == 0:
        raise ErreurDonnees('CIBLE : aucun contrat lu.')

    # --- 2. data ---
    d = garder_mois(fichiers['data'], 'DATA')
    exiger(d, ['VOLUME_SESSION'], 'DATA')
    d['VOLUME_SESSION'] = pd.to_numeric(d['VOLUME_SESSION'], errors='coerce')
    volume = moyenne(d, 'VOLUME_SESSION')

    # --- 3. recharge ---
    r = garder_mois(fichiers['recharge'], 'RECHARGE')
    exiger(r, ['MNT_RECH'], 'RECHARGE')
    r['MNT_RECH'] = pd.to_numeric(r['MNT_RECH'], errors='coerce')
    recharge = moyenne(r, 'MNT_RECH')

    # --- 4. ussd ---
    u = garder_mois(fichiers['ussd'], 'USSD')
    exiger(u, ['MNT_FORFAIT'], 'USSD')
    u['MNT_FORFAIT'] = pd.to_numeric(u['MNT_FORFAIT'], errors='coerce')
    forfait = moyenne(u, 'MNT_FORFAIT')

    # --- 5. appels et SMS : somme recu + emis ---
    e = garder_mois(fichiers['entrant'], 'ENTRANT')
    s = garder_mois(fichiers['sortant'], 'SORTANT')
    exiger(e, ['DUREE_APPEL_IN', 'NB_SMS_IN'], 'ENTRANT')
    exiger(s, ['DUREE_APPEL_TOT', 'nb_sms_tot'], 'SORTANT')

    for c in ['DUREE_APPEL_IN', 'NB_SMS_IN']:
        e[c] = pd.to_numeric(e[c], errors='coerce')
    for c in ['DUREE_APPEL_TOT', 'nb_sms_tot']:
        s[c] = pd.to_numeric(s[c], errors='coerce')

    recu = e[['CODE_CONTRAT', 'mois', 'DUREE_APPEL_IN', 'NB_SMS_IN']]
    emis = s[['CODE_CONTRAT', 'mois', 'DUREE_APPEL_TOT', 'nb_sms_tot']]
    mensuel = recu.merge(emis, on=['CODE_CONTRAT', 'mois'], how='outer')

    appel_in = pd.to_numeric(mensuel['DUREE_APPEL_IN'], errors='coerce').fillna(0)
    appel_out = pd.to_numeric(mensuel['DUREE_APPEL_TOT'], errors='coerce').fillna(0)
    sms_in = pd.to_numeric(mensuel['NB_SMS_IN'], errors='coerce').fillna(0)
    sms_out = pd.to_numeric(mensuel['nb_sms_tot'], errors='coerce').fillna(0)

    mensuel['APPEL_TOTAL'] = appel_in + appel_out
    mensuel['SMS_TOTAL'] = sms_in + sms_out
    appels = mensuel.groupby('CODE_CONTRAT')[['APPEL_TOTAL', 'SMS_TOTAL']].sum()

    # --- 6. assemblage ---
    table = cible.set_index('CODE_CONTRAT')
    table['VOLUME_SESSION'] = volume
    table['MNT_RECH'] = recharge
    table['MNT_FORFAIT'] = forfait
    table['APPEL_TOTAL'] = appels['APPEL_TOTAL']
    table['SMS_TOTAL'] = appels['SMS_TOTAL']

    # les sommes absentes valent 0 (aucune activite)
    table[['APPEL_TOTAL', 'SMS_TOTAL']] = table[
        ['APPEL_TOTAL', 'SMS_TOTAL']].fillna(0)

    return table.reset_index()


# ---------------------------------------------------------------- encodage
def charger_encodage() -> dict:
    """Table de correspondance libelle -> code, construite a l'entrainement."""
    import json
    if not ENCODAGE.exists():
        raise ErreurDonnees(
            'Fichier encodage.json introuvable. '
            'Lance d abord : python scripts/build_encodage.py')
    with open(ENCODAGE, 'r', encoding='utf-8') as f:
        return json.load(f)


def encoder(table: pd.DataFrame, encodage: dict) -> tuple:
    """Remplace les libelles par les codes utilises a l'entrainement.

    Les valeurs jamais vues a l'entrainement deviennent NaN ICI, et sont
    signalees dans `inconnues`. Elles ne sont PAS converties en code 0 :
    le code 0 est une vraie categorie (la premiere par ordre alphabetique),
    et l'utiliser donnerait une prediction fausse sans que personne ne le sache.
    """
    resultat = table.copy()
    inconnues = {}

    for colonne in ['HANDSET', 'OFFRE', 'STATUT']:
        table_codes = encodage.get(colonne, {})
        valeurs = resultat[colonne]
        jamais_vues = sorted(set(valeurs) - set(table_codes))
        inconnues[colonne] = {
            'valeurs': jamais_vues,
            'lignes': int(valeurs.isin(jamais_vues).sum()),
        }
        # une valeur absente de la table reste NaN : elle sera traitee
        # explicitement dans predire(), pas silencieusement convertie.
        resultat[colonne] = valeurs.map(table_codes)

    return resultat, inconnues


# ---------------------------------------------------------------- prediction
def predire(table: pd.DataFrame, seuil: float = 0.5,
            accepter_inconnues: bool = False) -> pd.DataFrame:
    """Applique le modele et retourne les resultats.

    accepter_inconnues=False (defaut) : on refuse de predire si une categorie
        n'a jamais ete vue a l'entrainement. Une valeur inconnue n'a pas de
        code, et la convertir en 0 donnerait une prediction fausse en silence.
    accepter_inconnues=True : on predit quand meme, en mettant ces clients
        a 0 (premiere modalite). L'utilisateur doit alors savoir que ces
        lignes-la sont moins fiables.
    """
    if not MODELE.exists():
        raise ErreurDonnees(
            f'Modele introuvable : {MODELE.name}. '
            'Lance le notebook 06 pour le telecharger.')

    modele = joblib.load(MODELE)
    encodage = charger_encodage()

    table_encodee, inconnues = encoder(table, encodage)

    # verification finale : toutes les colonnes attendues
    manquantes = [c for c in COLONNES_MODELE if c not in table_encodee.columns]
    if manquantes:
        raise ErreurDonnees(
            f'Colonnes manquantes pour le modele : {", ".join(manquantes)}')

    X = table_encodee[COLONNES_MODELE].copy()

    # --- 1. mesures : NaN -> 0 ---
    # A l'entrainement (notebook 03), une mesure absente valait 0 : le client
    # n'avait eu aucune activite de ce type. Le modele n'a jamais vu de NaN.
    # Sans ce remplissage, 11 878 clients changeraient de prediction.
    for colonne in COLONNES_MESURES:
        X[colonne] = pd.to_numeric(X[colonne], errors='coerce').fillna(0)

    # --- 2. categories inconnues ---
    # Une categorie jamais vue a l'entrainement n'a pas de code. La convertir
    # en 0 reviendrait a dire "c'est la premiere categorie alphabetique",
    # ce qui produirait une prediction fausse en silence.
    # Par defaut on refuse. Si l'utilisateur l'accepte explicitement,
    # on predit ces clients-la avec le code 0 et on le signale.
    for colonne in COLONNES_CATEGORIES:
        manquantes = X[colonne].isna()
        if not manquantes.any():
            continue

        details = inconnues.get(colonne, {})
        valeurs = details.get('valeurs', [])
        liste = ', '.join(str(v) for v in valeurs[:5])
        if len(valeurs) > 5:
            liste += f' (+{len(valeurs) - 5} autres)'

        if not accepter_inconnues:
            raise ErreurDonnees(
                f'Colonne {colonne} : {int(manquantes.sum())} client(s) ont une '
                f'valeur jamais vue a l\'entrainement ({liste}). '
                f'Reentraine le modele (notebooks 03 et 06) pour integrer ces '
                f'nouvelles modalites, puis relance '
                f'« python scripts/build_encodage.py ». '
                f'Ou coche « Continuer malgre les valeurs inconnues » '
                f'sur la page.')

        X[colonne] = X[colonne].fillna(0)

    probabilites = modele.predict_proba(X)[:, 1]

    # clients dont au moins une modalite etait inconnue : leur prediction
    # repose sur un code invente, donc elle est moins fiable.
    incomplete = np.zeros(len(table_encodee), dtype=bool)
    for colonne in COLONNES_CATEGORIES:
        incomplete |= table_encodee[colonne].isna().to_numpy()

    resultat = pd.DataFrame({
        'CODE_CONTRAT': table['CODE_CONTRAT'].to_numpy(),
        'ANC_M': table['ANC_M'].to_numpy(),
        'HANDSET': table['HANDSET'].to_numpy(),
        'OFFRE': table['OFFRE'].to_numpy(),
        'STATUT': np.where(table['STATUT'].to_numpy() == 'A', 'actif', 'suspendu'),
        # on affiche la probabilite arrondie, mais la decision utilise
        # la valeur exacte : arrondir avant de comparer au seuil decalerait
        # quelques clients d'une classe a l'autre.
        'probabilite_churn': np.round(probabilites, 4),
        'prediction': np.where(probabilites >= seuil, 'churn', 'reste'),
        'donnee_incomplete': np.where(incomplete, 'oui', ''),
    })

    # tri : les plus a risque d'abord
    resultat = resultat.sort_values('probabilite_churn', ascending=False)

    return resultat.reset_index(drop=True), inconnues
