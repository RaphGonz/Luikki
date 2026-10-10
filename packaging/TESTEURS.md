# Installer Luikki (testeurs)

L'application n'est pas encore signée : votre système va d'abord la bloquer
une fois. C'est attendu.

- **Windows** : lancez `Luikki-<version>-setup.exe`, cliquez sur
  « Informations complémentaires » puis « Exécuter quand même ».
- **Mac** : ouvrez le fichier `.dmg`, glissez Luikki dans Applications, puis
  ouvrez Luikki une fois (il sera refusé) : Réglages Système → Confidentialité
  et sécurité → « Ouvrir quand même ». Depuis macOS 15, le clic droit → Ouvrir
  ne suffit plus.

## Les étapes
1. Charger la planche (ou la glisser sur la fenêtre).
2. Cases, 3. Bulles : corrigez les formes si besoin.
4. Découper en zones : sélectionnez des zones (appui, ou appui maintenu en
   balayant), clic droit pour fusionner ou couper. Ctrl+Z annule. Les réglages
   rares sont sous « Avancé ».
5. Plans (facultatif) : Luikki range les zones en 1er plan, 2e plan et fond
   d'après la profondeur du dessin. Sélectionnez des zones pour les changer de
   plan, ou pour en faire des personnages. « Passer » va droit à l'export.
6. Exporter le PSD : un calque par plan, plus les bulles. Les couleurs sont
   factices : deux zones qui se touchent n'ont jamais la même, la baguette
   magique prend donc une zone. Remplacez-les par les vôtres.

Luikki ne propose aucune couleur.

## Compte et licence
**Se connecter**, en haut à droite : votre adresse e-mail, puis le code reçu.
Une seule licence, 10 € par an ; un compte testeur n'a rien à acheter. Le
bouton d'achat ouvre la page de paiement Stripe dans votre navigateur.

## Où vont vos planches
Tout tourne sur votre ordinateur : vos planches ne partent nulle part. Seuls
la connexion et le paiement passent par Internet.

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
