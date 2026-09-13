# Installer Luikki (testeurs)

L'application n'est pas encore signée : votre système va d'abord la bloquer
une fois. C'est attendu.

- **Windows** : lancez `Luikki-<version>-setup.exe`, cliquez sur
  « Informations complémentaires » puis « Exécuter quand même ».
- **Mac** : ouvrez le fichier `.dmg`, glissez Luikki dans Applications, puis
  ouvrez Luikki une fois (il sera refusé) : Réglages Système → Confidentialité
  et sécurité → « Ouvrir quand même ». Depuis macOS 15, le clic droit → Ouvrir
  ne suffit plus.

## Se connecter et générer

Dans l'application : **Compte** (en bas à gauche), votre adresse e-mail, puis
le code reçu par e-mail. Donnez cette adresse à Raph : il passe votre compte
en compte testeur, et l'étape 5 génère alors avec Cobra sans rien acheter.

À l'étape 5, **Couleurs** choisit entre Cobra (d'après vos références) et les
couleurs distinctes, gratuites, sans GPU. Cobra compte en cases : chaque case
générée en consomme une, deuxième essai compris. **Compte** et l'étape 5
disent ce qu'il reste.

Les boutons d'achat de **Compte** ouvrent la page de paiement Stripe dans votre
navigateur. Pendant les tests, Stripe tourne en mode test : aucune somme ne
peut être prélevée, même avec une vraie carte.

## Où vont vos planches

Les étapes 1 à 4, 6 et 7 tournent sur votre ordinateur. Seule l'étape 5 envoie
quelque chose : chaque case et vos images de référence partent vers le GPU,
chez Modal, aux États-Unis. Rien n'y est conservé après la génération, et rien
ne sert à entraîner un modèle.

## Mises à jour

Quand une nouvelle version sort, un bouton apparaît en haut de la fenêtre.
Sous Windows, **Mettre à jour** la télécharge, l'installe et rouvre Luikki. Sur
Mac, le bouton télécharge le nouveau `.dmg` : remplacez l'application comme à
l'installation. Vos planches ne bougent pas.

## Si quelque chose ne va pas

Envoyez le fichier `luikki.log` :

- Windows : `%LOCALAPPDATA%\Luikki\Logs\luikki.log` (collez ce chemin dans la
  barre d'adresse de l'Explorateur).
- Mac : `~/Library/Logs/Luikki/luikki.log`.

Désinstaller Luikki ne supprime pas vos planches : elles restent dans
`%LOCALAPPDATA%\Luikki` (Windows) ou `~/Library/Application Support/Luikki`
(Mac).
