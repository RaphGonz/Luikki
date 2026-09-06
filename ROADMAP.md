# Luikki — mémo

**[€]** = service à souscrire.
Cloud = endpoint GPU authentifié, pas une SaaS. Projet, pages, refs, palette, mémoire = local.

---

## A — App locale (maintenant, sans cloud)

- [ ] Zoom + pan : échelle/offset dans `view` (app.js). Ancrer sur curseur, redraw en devicePixelRatio.
- [ ] Route crop natif `GET /api/page.png?box=…` (sinon page suréchantillonnée au zoom).
- [ ] Absorption micro-zones, étape 4, **géométrique** : aire < seuil ET >80% frontière partagée avec 1 seul voisin.
- [ ] Seuil en fraction de l'aire de case, jamais en px absolus.
- [ ] Ne PAS absorber sur critère couleur après génération (grave un échec du modèle).
- [ ] Clustering CIELAB à l'export : regroupe les **calques**, pas les zones (même MERGE_DELTA_E que extract.py).
- [ ] Test régression absorption sur teddy_page + laurine_page : compter pupilles / reflets / boutons perdus.
- [ ] Nommer/créer/renommer entrées de palette (SPEC 17).
- [ ] Granularités export : `colour` / `segment` / `object` + export PNG par couleur.
- [ ] Vérifier `expand_under_lines` : halo 1px ? jonction 3 zones sous trait épais ? intérieur des aplats noirs ?
- [ ] Sous-couche grise optionnelle par case, sous tout (~5 lignes dans psd.py).
- [ ] Demander à l'artiste : couleur-sous-trait (standard flatting) ou gris dédié (encrage couleur) ? Implémentations différentes.
- [ ] Brancher `model/store.py` → SPEC 1–4 (dossier projet, SQLite, ajout de pages, save à chaque édition).

## B — Installable + vendable

- [ ] MangaLineExtraction → ONNX (MIT, version transformers dispo). Client sans torch/CUDA.
- [ ] Ligne nette : client = onnxruntime CPU. Serveur = torch/diffusers/CUDA.
- [ ] Packaging PyInstaller/Briefcase + fenêtre pywebview. Poids téléchargés au 1er lancement.
- [ ] **[€]** Certif signature code Windows (OV, token/HSM). Sans = alerte SmartScreen rouge.
- [ ] **[€]** Apple Developer Program si build macOS (notarisation).
- [ ] Projet d'exemple embarqué : 1 page + character sheet + palette → PSD au 1er lancement.
- [ ] **[€]** Statut juridique + facturation (comptable).
- [ ] **[€]** Paddle ou Lemon Squeezy (merchant of record = TVA gérée) plutôt que Stripe seul.
- [ ] Serveur de licences : `POST /activate` → JWT signé (features + expiration), revalidation hebdo.
- [ ] Grâce hors ligne 14–30 j.
- [ ] **[€]** VPS licences (Hetzner, ~5 €/mois).
- [ ] Licences « fondateur » vendues **avant** le cloud → teste paiement/facturation/activation.

## C — Endpoint GPU

- [ ] Supprimer T5 : Cobra tourne sur prompt vide. Cacher le tenseur, ne jamais charger l'encodeur.
- [ ] Poids cuits dans l'image ou volume réseau, pas de pull au démarrage. Cible : <30 s à froid, <2 s à chaud.
- [ ] Protocole client→serveur, 1 requête = 1 case. In : crop masqué + tuiles refs + hint + top_k + steps. Out : raster. Versionné dès v1.
- [ ] Retrieval CLIP côté client (onnxruntime CPU) → pool jamais uploadé.
- [ ] **[€]** Serverless 16–24 Go (9,3 Go mesurés @12 refs). ~0,58 $/h 16 Go, ~0,68 $/h L4/A5000. Scale-to-zero. Pas de dédié sous ~50% d'usage.
- [ ] Secure Cloud ou hébergeur UE. **Jamais Community Cloud** (hôtes tiers, kill à 5 s).
- [ ] File d'attente + retries + quota mensuel en pages, affiché avant lancement du job.
- [ ] Dégradation propre : quota/serveur/réseau KO → fallback proposer `distinct`, jamais de blocage.
- [ ] **[€]** Stockage objet (R2 / Scaleway) pour installeurs + updates.
- [ ] **[€]** Sentry client + serveur.
- [ ] CGU/CGV : répercuter Attachment A OpenRAIL++-M (hérité PixArt) + non-rétention + non-entraînement.
- [ ] Mesurer coût réel/page sur 10 abonnés avant de figer le quota.

## D — Site + vidéos (parallèle, dès maintenant)

- [ ] Boucle héros 30–60 s, sans voix : trait noir → page couleur.
- [ ] 3 clips courts : coins de case, balayage+fusion de zones, coupe d'une zone qui fuit.
- [ ] Démo longue 5–8 min sur vraie page, avec l'artiste, erreurs comprises.
- [ ] Avant/après sur planche d'album réelle (autorisation écrite).
- [ ] Bloc « vos couleurs, vos références » sur page tarifs : refs de l'artiste uniquement / sortie brute jamais montrée ni exportée / aucun trait dans l'export / aucun entraînement.
- [ ] Page tarifs 2 colonnes (mini gratuit installé / abonnement cloud), même avant le cloud.
- [ ] **[€]** Hébergement vidéo : YouTube non répertorié au début, Bunny/Mux ensuite.
- [ ] **[€]** Email transactionnel (Resend/Postmark).
- [ ] 3 emails liste d'attente : démo vidéo → licences fondateur → ouverture cloud.

## E — Lignes ouvertes (recherche, transverse)

Le trait ouvert reste LE défaut du produit : une zone qui fuit = une correction
manuelle par fuite. Deux mécanismes en place (`segmentation/closure.py`) :
échelle de rayons trapped-ball, puis pontage d'extrémités. Insuffisants sur
encre réelle. Objectif : trancher une bonne fois, sur mesures, pas sur
impressions.

- [ ] Jeu d'évaluation : calques d'encre **réels** uniquement, jamais de trait extrait (SPEC §7 — le trait extrait est fermé, il ferait croire l'étape résolue). 10–20 pages, styles contrastés : pinceau, plume, hachures, crayon.
- [ ] Vérité terrain = les flats de l'artiste, pas une annotation maison. La zone correcte est celle qu'il a peinte.
- [ ] Deux métriques, toujours ensemble : fuites (zones fusionnées à tort) et sur-coupes (zone unique fendue). Tout seuil qui améliore l'une dégrade l'autre.
- [ ] Mesurer la distribution des largeurs de trou par style **avant** de choisir un `max_gap`. Aujourd'hui 12.0 px, constante globale, jamais justifiée.
- [ ] `max_gap` fonction de la largeur de trait locale, pas en px absolus — même faute que les micro-zones (§A).
- [ ] Pontage géodésique (elastica / spirale d'Euler) plutôt que segment droit : un trait d'encre se prolonge courbe. `max_angle_deg` filtre les hachures, il ne reconstruit rien.
- [ ] État de l'art à dépouiller : fermeture apprise (gap-filling), simplification de croquis (Simo-Serra), colorisation trait→région vidéo (AniDoc, LVCD), propositions de région type SAM. Pour chacun : licence, poids, coût GPU, inspectabilité.
- [ ] Ne retenir qu'une méthode dont la sortie reste corrigeable : le pont n'entre jamais dans l'export, seulement dans le raster consommé par la segmentation. Invariant actuel, à ne pas perdre.
- [ ] Rapport dans `reports/`, même forme que p3/ab : rendus côte à côte, verdict sur images, pas sur compteurs.
- [ ] Décision finale en une ligne : garder l'heuristique, la remplacer, ou empiler apprise → trapped-ball.

## F — Luikki animation (variante, tweaks)

Même problème, même pipeline, autre unité de travail : le plan, pas la planche.
Rien à réinventer côté segmentation — c'est de l'UI et de la persistance.

- [ ] Retirer les étapes 2 et 3 (cases, bulles) : upload → zones → flats → snap → export. Cinq boutons au lieu de sept, même ordre, même règle « re-lancer une étape détruit ce qui en dépend ».
- [ ] Une « page » devient un plan ; l'unité affichée est l'image. Import : séquence numérotée (PNG/TGA) ou dossier.
- [ ] UI image par image : navigation clavier (←/→), timeline, numéro d'image toujours visible.
- [ ] Pelure d'oignon : image précédente/suivante en surimpression, opacité réglable. Pour juger la cohérence, pas pour dessiner.
- [ ] Cohérence couleur entre images = le vrai travail. Une zone garde son `palette_entry_id` d'une image à l'autre ; la correspondance de régions entre images consécutives est à construire (recouvrement, flot, appariement de contours).
- [ ] Corriger une couleur sur une image la corrige sur tout le plan — règle 1 étendue à la séquence.
- [ ] Palette portée-plan (aujourd'hui portée-album, `<workdir>/palette.json`). Même contrainte : ids jamais réutilisés.
- [ ] Traitement par lot : `luikki flatten` est déjà headless ; un plan = des centaines d'images → file, reprise, progression affichée.
- [ ] Une image en vol à la fois ne tient plus (SPEC : la page n'est pas persistée). Le plan doit vivre sur disque, pas en mémoire.
- [ ] Export : séquence PSD, ou PNG/TGA numérotée par couleur. Vérifier ce qu'avalent TVPaint, Harmony, CSP, After Effects avant de trancher.
- [ ] Observer un animateur comme on observe un coloriste : appel vidéo, son plan à lui, avant d'écrire l'UI.
- [ ] Proposer : Cobra est pensé planche. Mesurer sa stabilité temporelle sur 24 images avant de supposer qu'elle tient.

---

## Verdicts

- **Zoom** : petit. Un seul transform, tout le hit-testing y passe. Vrai travail = route de crop.
- **Export couleur par couleur** : à moitié fait. Zone stocke un id, pas un RGB.
- **Micro-zones** : géométrique étape 4 + regroupement de calques à l'export. L'explosion vient de l'absence de palette (581 zones → 62 calques avec palette).
- **Gris de soutien** : vérifier, pas réécrire. + sous-couche grise. Trancher la convention avec l'artiste.
- **Calques par objet** : faisable = problème de **nommage**, pas de vision. Zone fusionnée = objet. Nomme l'entrée palette, groupe l'export par nom.
- **Calques par objet inter-cases** : non faisable. Cobra échoue dès que les refs montrent des persos différents. Ne pas construire.
- **Lignes ouvertes** : premier poste, avant tout le reste de A. C'est la seule étape dont l'échec se paie en corrections manuelles à chaque page. Recherche d'abord, code ensuite.
- **Animation** : même moteur, deux retraits (cases, bulles) et un ajout (l'image comme unité). Le risque n'est pas la segmentation, c'est la cohérence d'une zone d'une image à la suivante — à prototyper avant de promettre la variante.
