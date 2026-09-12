# Installer Luikki (testeurs)

L'application n'est pas encore signée : votre système va d'abord la bloquer
une fois. C'est attendu.

- **Windows** : lancez `Luikki-<version>-setup.exe`, cliquez sur
  « Informations complémentaires » puis « Exécuter quand même ».
- **Mac** : ouvrez Luikki une fois (il sera refusé), puis Réglages Système →
  Confidentialité et sécurité → « Ouvrir quand même ». Depuis macOS 15, le clic
  droit → Ouvrir ne suffit plus.

Ensuite, dans l'application : **Compte** (en bas à gauche), votre adresse
e-mail, puis le code reçu par e-mail. L'étape 5 a besoin de ce compte ; les
autres étapes marchent sans.

Si quelque chose ne va pas, envoyez le fichier `luikki.log` :

- Windows : `%LOCALAPPDATA%\Luikki\Logs\luikki.log` (collez ce chemin dans la
  barre d'adresse de l'Explorateur).
- Mac : `~/Library/Logs/Luikki/luikki.log`.

Désinstaller Luikki ne supprime pas vos planches : elles restent dans
`%LOCALAPPDATA%\Luikki` (Windows) ou `~/Library/Application Support/Luikki`
(Mac).
