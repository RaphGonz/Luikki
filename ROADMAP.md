# Luikki — mémo

**[€]** = service à souscrire.
Cloud = endpoint GPU authentifié, pas une SaaS. Projet, pages, refs, palette, mémoire = local.

---

## A — App locale (maintenant, sans cloud)

- [ ] Route crop `GET /api/page.png?box=…` si la mémoire navigateur lâche sur une vraie planche (5 calques pleine page).
- [x] Absorption micro-zones, étape 4, **géométrique** (`segmentation/absorb.py`) :
      aire < seuil ET >80% de frontière tenue par un seul voisin, adjacence
      mesurée sous le trait (`border_stats`), jamais dans un noir condamné.
- [x] Seuil en fraction de l'aire de case, jamais en px absolus.
      `max_area_share = 5e-4`, choisi sur les rendus (`reports/microzones/`).
- [x] Ne PAS absorber sur critère couleur après génération (grave un échec du
      modèle). Écrit dans la docstring d'`absorb.py`, pas seulement ici.
- [x] **Rebouchage du résidu** : les zones sont coupées sur le trait extrait et
      poussées sous l'encre réelle, donc tout pixel que l'extracteur appelait
      trait et que l'encre ne couvre pas restait sans zone — invisible partout
      sauf dans le PSD, en blanc. Deuxième passe d'`expand_under_lines` sur le
      reste : 9 509 → 0 (teddy), 10 751 → 0 (laurine). Deux trous restent des
      trous : le protégé, et les noirs de l'artiste. `panel.orphans` le compte
      désormais dans `state()` — c'est ce silence qui a coûté la découverte.
- [ ] Clustering CIELAB à l'export : regroupe les **calques**, pas les zones (même MERGE_DELTA_E que extract.py).
- [x] Test régression absorption sur teddy_page + laurine_page. Se lit sur les
      rendus `result/*_lost.png`, pas sur un compteur : deux discriminateurs
      automatiques (encre sur la frontière partagée, encre sur le pourtour
      propre) rendent 100 % « dessiné » à tous les seuils. Une miette et une
      pupille ont la même forme et la même bordure.
- [ ] Contre-épreuve du seuil sur les 7 planches de `crosspage`, comme pour 0,14.
- [ ] Nommer/créer/renommer entrées de palette (SPEC 17).
- [ ] Vérifier `expand_under_lines` : halo 1px ? jonction 3 zones sous trait épais ? intérieur des aplats noirs ?
- [x] Sous-couche grise : hors sujet ici, c'est un autre procédé. La convention
      est tranchée et déjà en place — la couleur du flat passe **sous l'encre**
      (`expand_under_lines`), pas un gris dédié.
- [ ] Brancher `model/store.py` → SPEC 1–4 (dossier projet, SQLite, ajout de pages, save à chaque édition).
- [x] Interface refaite d'après `UI.md` (rail · canvas · inspecteur), barre de
      progression réelle (`GET /api/progress`), tout le texte dans
      `static/locales/` — une langue = un fichier (`tests/test_locales.py`).
- [x] Français : `locales/fr.json`, sélecteur de langue en bas à droite.
- [ ] Messages d'erreur du serveur traduisibles : les `StepError` Python en `{code, params}`.

### Export final — granularité, compte de calques, garde ΔE (fait)

Une seule cause derrière les trois : **un calque = une entrée de palette**, et
tant que les entrées sont des couleurs *proposées* il y en a une par segment.

**1. Deux granularités, un `<select>` à côté du bouton 7.**

- [x] `colour` — un calque par entrée de palette, sur toute la page, sans
      groupe. La même couleur dans cinq cases fait **un** calque, pas cinq.
      C'est la règle 1 rendue manipulable dans Photoshop : un calque = une
      couleur = partout.
- [x] `panel` — ce qu'on fait aujourd'hui : un groupe par case, un calque par
      couleur dans la case. Pour qui travaille case par case.
- [x] `write_psd(granularity=…)`, un seul chemin de rasterisation : les masques
      par entrée sont déjà construits case par case, `colour` les réunit dans un
      masque page avant d'écrire. `flats_preview` ne bouge pas — le composite
      est identique, seul l'empilement change. Plus `luikki flatten --layers`.
- [x] Défaut : `colour`. Moins de calques, et c'est celui qui répond à
      « change les cheveux partout ».

**2. Prévenir au-delà de 20 calques, au moment d'appuyer.**

- [x] Pas de compteur permanent : l'avertissement s'affiche dans l'étape 7,
      avant le clic, et le bouton devient « Export 47 layers anyway ». Plus de
      `confirm`.
- [x] Sous les 20 calques, il ne dit rien. Au-dessus, il ne bloque pas : le
      studio qui veut ses 200 calques exporte quand même.
- [x] Le compte vient de `state()` (`export: {layers, granularity, warn_at}`), compté par stack sur
      des ids distincts sans rien rasteriser — `panel` = somme par case,
      `colour` = ids de la page. Constante `EXPORT_LAYER_WARNING = 20` dans
      `psd.py`.
- [x] Même avertissement imprimé par `luikki flatten`.

**3. Le garde ΔE, coché par défaut.**

- [x] La case « ignore the guard » est cochée au chargement. Par défaut, tout
      snappe à la palette de l'artiste ; le garde ΔE ne s'applique que s'il le
      décoche. Une ligne dans `index.html`, plus les défauts côté serveur pour
      qu'ils ne divergent pas : `snap_all(threshold=None)` dans `session.py` et
      `app.py`, `--threshold inf` dans `cli.py`.
- [x] Ne **pas** snapper dans `generate_flats` pour autant : l'étape 5 propose,
      l'étape 6 décide. C'est la frontière d'étape, elle ne bouge pas.
- [x] Tests : `test_segments.py` et `test_web.py` sur le défaut inversé, `test_web.py` sur le compte
      de calques annoncé = le compte de calques écrit, dans les deux
      granularités.

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
- [x] Mesurer les trous **avant** de choisir un `max_gap`. Fait sur diagonal_page
      (`reports/new_algo/`) : sur 46 fuites, 22 seulement se ferment à un rayon
      quelconque ≤ 12, les 24 autres à aucun. Le plafond du trapped-ball est là,
      et aucune constante ne le franchit. `max_gap` est une fausse question.
- [x] Pontage d'extrémités en segment droit : mesuré nul (48 → 44 fuites au
      mieux, fragmentation en hausse à chaque réglage). `closure.py` reste
      débranché de `session.py` jusqu'à ce que le pont soit géodésique.
- [ ] Pontage géodésique (elastica / spirale d'Euler) plutôt que segment droit : un trait d'encre se prolonge courbe. `max_angle_deg` filtre les hachures, il ne reconstruit rien.
- [ ] État de l'art à dépouiller : fermeture apprise (gap-filling), simplification de croquis (Simo-Serra), colorisation trait→région vidéo (AniDoc, LVCD), propositions de région type SAM. Pour chacun : licence, poids, coût GPU, inspectabilité.
- [ ] Vérité terrain : **exporter la carte d'étiquettes**, pas une capture
      d'écran. À 604x862 pour une planche 1174x1668, les zones sous ~100 px ne
      survivent pas : la moitié « fragmentation » des mesures est bruitée, la
      moitié « fuite » ne l'est pas.
- [x] **Audit des fuites après coup** (`segmentation/leaks.py`, branché étape 4).
      LineFiller inchangé ; une bille plus petite propose les coupes qu'il n'a
      pas vues, et chaque proposition est jugée sur ce qu'il y a *sous* la
      frontière qu'elle tracerait : un trait troué (bordure encrée, trou court)
      se coupe, un tunnel (bordure ouverte sur toute sa longueur) se recolle.
      Fuite 10,7 % → 6,4 % de la planche pour 13,8 % → 15,5 % de fragmentation,
      +52 zones, +2 % de temps. Ne fait que **diviser** ce que le segmenteur a
      rendu : il ne peut pas inventer une fuite. `max_open_share` = 0,14, mesuré
      (les coupes voulues : bordure 87 % encre ; les refusées : 63 %).
- [x] 0,14 ne casse rien ailleurs : +4 % à +15 % de zones sur 7 planches
      (pinceau, crayon, trame, ligne claire, `reports/new_algo/result/crosspage/`).
      Moebius, la plus à risque, plafonne à +15 % en gardant sa structure. Le
      seuil n'est pas sur le fil.
- [ ] Mais un compte de zones stable ne dit pas que les coupes sont les bonnes :
      il faut une **deuxième planche corrigée** pour ça. Demander la carte
      d'étiquettes, pas une capture.
- [ ] Filet de sécurité mesuré, non retenu : fusionner deux régions dont la
      frontière est ink < 40 %. Zéro fusion fautive sur 907/531/281 paires, mais
      quasi redondant derrière `merge_fill`. À ressortir pour un autre
      segmenteur.
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

- **Export couleur par couleur** : la moitié faite est la bonne — une zone
  stocke un id, pas un RGB. Reste à en tirer l'empilement : un calque par
  entrée sur toute la page, le groupe par case en second choix.
- **Micro-zones** : fait, seuil 5e-4 jugé sur les rendus — 32 zones sur 470,
  56 sur 756, soit 7 % de chaque planche. Ce qu'il emporte est du détail qu'un
  coloriste veut voir partir ; au-delà (1e-3) il prend des marques dessinées
  pour être vues. Le gain en compte reste modeste parce que les vraies miettes
  sont déjà absorbées en amont (`_absorb_residue`, `merge_fill`). Le verdict ne
  bouge pas — l'explosion se paie à
  l'export et se règle par la palette (581 zones → 62 calques), pas par la
  segmentation. Le regroupement CIELAB des calques reste à faire, et seulement
  s'il reste des doublons de couleur une fois le snap fait sur une vraie
  palette : il réunit deux *entrées de palette* voisines, ce que l'absorption
  ne touche jamais.
- **Gris de soutien** : abandonné ici — autre procédé, autre moment. Sous le
  trait, la couleur du flat passe déjà, et c'est la bonne convention.
- **Calques par objet** : faisable = problème de **nommage**, pas de vision. Zone fusionnée = objet. Nomme l'entrée palette, groupe l'export par nom.
- **Calques par objet inter-cases** : non faisable. Cobra échoue dès que les refs montrent des persos différents. Ne pas construire.
- **Lignes ouvertes** : premier poste, avant tout le reste de A. C'est la seule étape dont l'échec se paie en corrections manuelles à chaque page. Recherche d'abord, code ensuite.
- **Animation** : même moteur, deux retraits (cases, bulles) et un ajout (l'image comme unité). Le risque n'est pas la segmentation, c'est la cohérence d'une zone d'une image à la suivante — à prototyper avant de promettre la variante.
