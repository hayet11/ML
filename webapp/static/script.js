/* Affichage du nom du fichier choisi et de l'etat du formulaire */

// --- 1. afficher le nom du fichier selectionne ---
document.querySelectorAll('input[type="file"]').forEach(function (champ) {
    champ.addEventListener('change', function () {
        var bloc = champ.closest('.champ-fichier');
        var etat = bloc.querySelector('.etat-fichier');

        if (champ.files.length > 0) {
            var nom = champ.files[0].name;
            // tronque les noms trop longs
            if (nom.length > 30) {
                nom = nom.slice(0, 27) + '...';
            }
            etat.textContent = nom;
            bloc.classList.add('rempli');
        } else {
            etat.textContent = 'aucun fichier';
            bloc.classList.remove('rempli');
        }
        verifierComplet();
    });
});

// --- 2. le bouton reste desactive tant que les 6 fichiers ne sont pas la ---
var bouton = document.getElementById('bouton');
var formulaire = document.getElementById('formulaire');

function verifierComplet() {
    var tousRemplis = true;
    document.querySelectorAll('input[type="file"]').forEach(function (champ) {
        if (champ.files.length === 0) {
            tousRemplis = false;
        }
    });
    bouton.disabled = !tousRemplis;
    return tousRemplis;
}

verifierComplet();

// --- 3. envoi en AJAX, pour pouvoir recommencer ---
//
// Pourquoi pas un envoi classique ? La reponse est un fichier CSV joint
// (Content-Disposition: attachment). Le navigateur telecharge le fichier
// SANS recharger la page : le voile de chargement resterait affiche et le
// bouton desactive pour toujours. On gere donc l'envoi a la main.

var voile = document.getElementById('voile');

function afficherErreur(message) {
    var zone = document.getElementById('zone-alerte');
    // textContent et non innerHTML : le message peut contenir des noms
    // d'offres lus dans le fichier envoye. Avec innerHTML, une valeur
    // comme <img onerror=...> serait interpretee comme du HTML.
    zone.textContent = '';

    var bloc = document.createElement('div');
    bloc.className = 'alerte erreur';
    bloc.textContent = message;
    zone.appendChild(bloc);

    zone.scrollIntoView({behavior: 'smooth', block: 'center'});
}

function effacerErreur() {
    document.getElementById('zone-alerte').textContent = '';
}

function remettreBouton() {
    voile.classList.remove('actif');
    bouton.textContent = 'Analyser et telecharger les predictions';
    bouton.disabled = !verifierComplet();
}

formulaire.addEventListener('submit', function (evenement) {
    evenement.preventDefault();

    if (!verifierComplet()) {
        return;
    }

    effacerErreur();
    bouton.disabled = true;
    bouton.textContent = 'Traitement en cours...';
    voile.classList.add('actif');

    fetch(formulaire.action, {
        method: 'POST',
        body: new FormData(formulaire)
    })
    .then(function (reponse) {
        var type = reponse.headers.get('Content-Type') || '';

        // le serveur renvoie du HTML quand il y a une erreur (redirection)
        if (!reponse.ok || type.indexOf('text/csv') === -1) {
            return reponse.text().then(function (html) {
                // on extrait le message d'erreur de la page renvoyee
                var analyse = new DOMParser().parseFromString(html, 'text/html');
                var alerte = analyse.querySelector('.alerte');
                throw new Error(alerte
                    ? alerte.textContent.trim()
                    : 'Le traitement a echoue. Verifie les fichiers envoyes.');
            });
        }

        return reponse.blob().then(function (blob) {
            // nom du fichier indique par le serveur
            var disposition = reponse.headers.get('Content-Disposition') || '';
            var trouve = disposition.match(/filename=([^;]+)/);
            var nom = trouve ? trouve[1].replace(/"/g, '') : 'resultat_churn.csv';

            // on declenche le telechargement
            var url = URL.createObjectURL(blob);
            var lien = document.createElement('a');
            lien.href = url;
            lien.download = nom;
            document.body.appendChild(lien);
            lien.click();
            lien.remove();
            URL.revokeObjectURL(url);

            remettreBouton();
        });
    })
    .catch(function (erreur) {
        remettreBouton();
        afficherErreur(erreur.message);
    });
});
