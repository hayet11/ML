"""
Serveur du site de prediction de churn.

Lancement :
    python webapp/app.py
    puis ouvrir http://localhost:5001
"""

import io
import sys
from datetime import datetime
from pathlib import Path

from flask import (Flask, render_template, request, send_file,
                   flash, redirect, url_for)

# le module de traitement est dans le meme dossier
sys.path.insert(0, str(Path(__file__).resolve().parent))
import churn

app = Flask(__name__)
app.secret_key = 'churn-prediction-local'

# les fichiers bruts sont volumineux (ENTRANT depasse 25 Mo).
# sans cette limite, Flask rejette l'envoi et redirige sans explication.
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024   # 500 Mo

# seuil de decision, fige. Mesure sur les donnees de reference :
# 0,54 -> 90,07 % de bonnes reponses (le maximum)
# 0,50 -> 90,00 %
SEUIL_DECISION = 0.54

# les 6 fichiers attendus, avec leur libelle affiche
FICHIERS_ATTENDUS = {
    'cible':    'Table CIBLE (profil du client)',
    'data':     'Table DATA (consommation internet)',
    'entrant':  'Table ENTRANT (appels et SMS recus)',
    'sortant':  'Table SORTANT (appels et SMS emis)',
    'recharge': 'Table RECHARGE (recharges)',
    'ussd':     'Table USSD (achats de forfaits)',
}


@app.route('/')
def accueil():
    """Page principale : le formulaire de depot des fichiers."""
    return render_template('index.html', fichiers=FICHIERS_ATTENDUS)


@app.route('/predire', methods=['POST'])
def predire():
    """Recoit les 6 fichiers, les transforme, predit, et renvoie le CSV."""
    # Le seuil n'est plus reglable sur la page : il est fige.
    # 0,54 est la valeur qui maximise le taux de bonnes reponses sur les
    # donnees de reference (90,07 % contre 90,00 % a 0,50). L'ecart est
    # mince, mais c'est le meilleur resultat mesure.
    # Le CSV contient de toute facon la probabilite brute : l'utilisateur
    # peut recalculer avec un autre seuil s'il le souhaite.
    seuil = SEUIL_DECISION

    # case a cocher : accepter de predire malgre des modalites inconnues
    accepter = request.form.get('accepter_inconnues') == 'oui'

    # --- 1. verifier que les 6 fichiers sont la ---
    contenus = {}
    for cle, libelle in FICHIERS_ATTENDUS.items():
        fichier = request.files.get(cle)
        if fichier is None or fichier.filename == '':
            flash(f'Fichier manquant : {libelle}', 'erreur')
            return redirect(url_for('accueil'))
        contenus[cle] = fichier.read()

    # --- 2. lire les CSV ---
    try:
        tables = {}
        for cle, contenu in contenus.items():
            tables[cle] = churn.lire_csv(contenu, cle.upper())
    except churn.ErreurDonnees as ex:
        flash(str(ex), 'erreur')
        return redirect(url_for('accueil'))

    # --- 3. construire la table agregee ---
    try:
        table = churn.construire_table(tables)
    except churn.ErreurDonnees as ex:
        flash(str(ex), 'erreur')
        return redirect(url_for('accueil'))
    except Exception as ex:
        flash(f'Erreur pendant la transformation : {ex}', 'erreur')
        return redirect(url_for('accueil'))

    # --- 4. predire ---
    try:
        resultat, inconnues = churn.predire(
            table, seuil=seuil, accepter_inconnues=accepter)
    except churn.ErreurDonnees as ex:
        flash(str(ex), 'erreur')
        return redirect(url_for('accueil'))
    except Exception as ex:
        flash(f'Erreur pendant la prediction : {ex}', 'erreur')
        return redirect(url_for('accueil'))

    # --- 4b. signaler les lignes peu fiables ---
    # le drapeau est pose par churn.predire(), ligne par ligne.
    if 'donnee_incomplete' in resultat.columns:
        nombre = int((resultat['donnee_incomplete'] == 'oui').sum())
        if nombre:
            flash(
                f'{nombre} client(s) ont une modalite jamais vue a '
                f'entrainement. Leur prediction est moins fiable : voir la '
                f'colonne "donnee_incomplete" du CSV.',
                'avertissement')

    # --- 5. preparer le CSV de sortie ---
    sortie = io.BytesIO()
    resultat.to_csv(sortie, index=False, encoding='utf-8-sig')
    sortie.seek(0)

    horodatage = datetime.now().strftime('%Y%m%d_%H%M%S')
    nom = f'resultat_churn_{horodatage}.csv'

    return send_file(
        sortie,
        mimetype='text/csv',
        as_attachment=True,
        download_name=nom,
    )


@app.errorhandler(413)
def trop_volumineux(_erreur):
    """Envoi trop gros : message clair plutot qu'une page d'erreur brute."""
    flash('Les fichiers envoyes depassent la limite de 500 Mo.', 'erreur')
    return redirect(url_for('accueil'))


@app.route('/sante')
def sante():
    """Verification rapide que le serveur et le modele sont prets."""
    try:
        encodage = churn.charger_encodage()
        return {
            'serveur': 'ok',
            'modele': churn.MODELE.name,
            'modele_present': churn.MODELE.exists(),
            'colonnes': churn.COLONNES_MODELE,
            'modalites': {k: len(v) for k, v in encodage.items()},
        }
    except Exception as ex:
        return {'serveur': 'ok', 'erreur': str(ex)}, 500


if __name__ == '__main__':
    print('=' * 56)
    print('  Site de prediction de churn')
    print('=' * 56)
    print()
    print('  Ouvre ton navigateur sur : http://localhost:5001')
    print()
    print('  Pour arreter : Ctrl+C')
    print()
    app.run(debug=True, port=5001)
