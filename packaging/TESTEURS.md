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
le code reçu par e-mail. L'étape 5 (les aplats) a besoin de ce compte ; les
autres étapes marchent sans.

Générer demande un abonnement. Raph vous donne un code `TESTEUR-XXXXXX` :
dans **Compte**, cliquez **S'abonner** ; la page de paiement s'ouvre dans votre
navigateur. Saisissez-y le code (« Ajouter un code promotionnel ») : aucune
carte n'est demandée, les trois premiers mois sont offerts. Revenez ensuite
dans Luikki. Vous pouvez résilier quand vous voulez depuis **Compte → Gérer
l'abonnement**.

Pendant les tests, Stripe tourne en mode test : aucune somme ne peut être
prélevée, même avec une vraie carte.

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
