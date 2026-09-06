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

---

## Verdicts

- **Zoom** : petit. Un seul transform, tout le hit-testing y passe. Vrai travail = route de crop.
- **Export couleur par couleur** : à moitié fait. Zone stocke un id, pas un RGB.
- **Micro-zones** : géométrique étape 4 + regroupement de calques à l'export. L'explosion vient de l'absence de palette (581 zones → 62 calques avec palette).
- **Gris de soutien** : vérifier, pas réécrire. + sous-couche grise. Trancher la convention avec l'artiste.
- **Calques par objet** : faisable = problème de **nommage**, pas de vision. Zone fusionnée = objet. Nomme l'entrée palette, groupe l'export par nom.
- **Calques par objet inter-cases** : non faisable. Cobra échoue dès que les refs montrent des persos différents. Ne pas construire.
