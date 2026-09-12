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
- [x] SPEC 1–4 : dossier projet, ajout de pages, sauvegarde à chaque édition.
      **Fichiers, pas SQLite** (`web/project.py`) : JSON + zones en `.npy`,
      lisible et facile à déboguer. `model/store.py` reste débranché.
      Liste des planches dans le rail. Une référence supprimée **avertit**
      (`flats_stale`), elle n'invalide plus les aplats. Validé dans l'app par
      Raph le 2026-09-11.
- [ ] Sélecteur de dossier projet dans l'app — indispensable, attend l'app
      installée (B3/B4) ; aujourd'hui le projet = `--workdir`.
- [x] Interface refaite d'après `UI.md` (rail · canvas · inspecteur), barre de
      progression réelle (`GET /api/progress`), tout le texte dans
      `static/locales/` — une langue = un fichier (`tests/test_locales.py`).
- [x] Français : `locales/fr.json`, sélecteur de langue en bas à droite.
- [x] Messages d'erreur du serveur traduisibles : les `StepError` Python en `{code, params}`.
      Fait (2026-09-12) : le code est la clé `error.<code>` des locales,
      écrit en toutes lettres au `raise` ; `tests/test_locales.py` vérifie
      que chaque code a sa phrase. Restent en anglais : le 503 d'un proposer
      qui ne répond pas (c'est l'item réseau de B2).

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

## B — App installable + cloud (plan fixé le 2026-09-10)

Décidé : **pas de mesure avant de construire**, perte sèche acceptée. Raph
teste lui-même, puis fait tester des artistes ; on mesure après (section C).
Micro-entreprise existante : Stripe live est possible dès que l'app l'est.

**Comptes ouverts (2026-09-12)** : Supabase, Resend (domaine du site vérifié),
Stripe en mode test. **Pas de signature de code pendant les tests** : ni Apple
Developer ni Azure Artifact Signing, trop chers avant d'avoir fait tester
l'app. Le testeur passe l'avertissement de l'OS. Les deux passent en B6.

**Principe de sécurité.** Le client est open source : on ne le protège pas.
Tout ce qui coûte — le GPU — se décide côté serveur, à chaque requête : token,
abonnement, quota, concurrence. Donc **pas** de clé de licence, pas de JWT hors
ligne, pas d'obfuscation, pas de VPS de licences. Faire tourner Cobra sur son
propre GPU depuis les sources est permis et n'est pas le client visé.

```
App installée (Win/Mac)                    Modal (GPU)                      Supabase (UE)
étapes 1-4, 6, 7 en local ─ HTTPS+token ─► FastAPI : token, abo, quota,  ─► comptes, abo,
(CPU, onnxruntime)                         1 job/compte → CobraProposer     usage, appareils
étape 5 : RemoteProposer                                                    ◄── webhook Stripe
```

### Pile retenue

- **GPU : Modal.** La FastAPI tourne dans Modal (`@modal.asgi_app`) : l'auth
  vit dans le serveur, aucune clé fournisseur dans le client, pas de passerelle
  à héberger. L4 24 Go (0,80 $/h ; 9,3 Go mesurés @12 refs), A10 en repli
  (1,10 $/h). Offre Starter = 30 $ de crédits/mois. Région par défaut (US) :
  épingler l'UE coûte ×1,5, voir C. Rejeté : RunPod — une clé d'endpoint
  partagée par tous les clients reste extractible, il faudrait une passerelle.
- **Comptes : Supabase, région UE, plan Pro 25 $/mois** (le gratuit se met en
  pause après 7 j sans activité). Aucun mot de passe : code OTP reçu par email,
  tapé dans l'app. Python parle à l'API Auth, tokens rangés dans le trousseau
  OS (`keyring`) — pas de redirection navigateur dans pywebview. SMTP perso
  (Resend) : l'envoi intégré de Supabase est bridé.
  **RLS activé sur toutes les tables** ; la clé `service_role` n'existe que dans
  les secrets Modal. Le client ne porte que la clé publique.
- **Paiement : Stripe.** Checkout hébergé ouvert dans le navigateur système,
  Customer Portal pour résilier et changer de carte, webhooks → Supabase. Le
  serveur ne croit jamais le client sur l'état d'un abonnement.
- **Packaging : PyInstaller `onedir` + pywebview.** Inno Setup (Windows), DMG
  (Mac arm64), non signés jusqu'à B6, GitHub Actions sur tag → GitHub Releases.
- **Pas de CLIP en ONNX.** La sélection des tuiles reste sur le serveur
  (`cobra.py:606`, déjà sur GPU). Les deux raisons de l'ancien plan (ne pas
  envoyer le pool, client sans torch) tombent. **C'est MangaLineExtraction qui
  passe en ONNX** : c'est le dernier torch du client.

### Données (Supabase)

- `subscriptions` : `user_id`, `status`, `plan` (`tester` | `paid`), `period_end`, `stripe_customer_id`
- `usage` : une ligne par `POST /v1/panel` — `user_id`, `page_id`, `generation_id`, `created_at`
- `devices` : `user_id`, `device_id`, `last_seen`
- `jobs` : `user_id`, `started_at`, `ip` — le verrou « un job à la fois »
- `plans` : `plan`, `pages_per_month`, `generations_per_page`, `devices` — une limite changée = une ligne, sans déploiement

Quota compté en `page_id` distincts par mois ; relancer la même page ne
recompte pas, jusqu'à un plafond de générations par page (`generation_id`
distincts : un appui sur l'étape 5) (sinon l'artiste
hésite à corriger, ce qui tue la valeur centrale). Valeurs provisoires :
100 pages/mois, 10 générations/page. Fixées pour de bon en C.

### API serveur v1

Toutes sous `Authorization: Bearer <token Supabase>`, sauf le webhook. Chaque
requête porte `protocol` ; un client trop vieux reçoit un code, l'app le traduit.

- `GET /v1/version` — dernière version client, protocole minimal.
- ~~`GET /v1/me`~~ — remplacé par `my_status` côté Supabase, appelé par l'app
  avec sa session : lire un quota ne réveille pas le GPU.
- `POST /v1/panel` — in : `page_id`, `generation_id`, `device_id` (uuid tous
  les trois), case masquée (PNG), références
  (PNG), indices (masque + couleurs), `steps`, `seed`. Out : raster PNG +
  `model_version`. `label_map` ne quitte jamais le client. Rien n'est écrit sur
  disque côté serveur.
- `POST /v1/checkout` — Checkout Session : `client_reference_id=user_id`,
  `allow_promotion_codes=true`, `payment_method_collection="if_required"`.
- `POST /v1/portal` — URL du Customer Portal.
- `POST /v1/stripe/webhook` — signature vérifiée. `checkout.session.completed`,
  `customer.subscription.updated`, `customer.subscription.deleted`,
  `invoice.payment_failed` → `subscriptions`.

Contrôles à chaque `POST /v1/panel`, dans cet ordre, avant de toucher au GPU :
signature du token · abonnement actif (`tester` ou `paid` non expiré) · quota ·
≤ 2 `device_id` par compte · un seul job en cours (deux IP simultanées = refus
+ log) · entrées PNG uniquement, plafond en px et en Mo · timeout.

### Estimation

Jours de travail concentré, Raph + Claude Code. **Total : 27–42 j, soit 6 à 9
semaines à plein temps**, plus les délais de validation externes (Apple,
Microsoft, Stripe) qui ne sont pas du travail mais du calendrier.

| Phase | Jours | Débloque |
|---|---|---|
| B1 Cobra sur Modal | 3–5 | tests artistes en visio, GPU cloud |
| B2 Comptes et quota | 5–7 | un artiste identifié peut générer |
| B3 Client autonome | 7–12 | l'app tient seule, sans torch, sans perte |
| B4 Installeurs | 5–8 | un artiste installe et lance chez lui |
| B5 Stripe (test) | 3–4 | abonnement, codes testeurs |
| B6 Production | 4–6 | un inconnu paie |

Risques qui font sortir de la fourchette : le fork diffusers de Cobra (versions
torch/CUDA figées) en B1 ; la persistance du projet en B3, qui touche chaque
correction ; les imports cachés PyInstaller et l'absence de Mac pour tester en
B4. B5 peut se faire en parallèle de B3.

**À lancer le jour 1, parce que ça attend** : compte Stripe (ouvert en mode
test, 2026-09-12). Inscription Apple Developer et validation Azure Artifact
Signing reportées en B6 (2026-09-12) — les lancer au **début** de B6, pas à la
fin : ce sont elles qui attendent.

### B1 — Cobra sur Modal (fait, 2026-09-11)

- [x] App Modal : image avec le fork diffusers de Cobra
      (`pip install -e third_party/Cobra/diffusers`), poids HF dans un Volume
      Modal (pas de téléchargement par requête), `CobraProposer` inchangé.
      `cloud/modal_app.py`, Volume `luikki-weights`, `HF_HUB_OFFLINE=1` au
      service, `max_containers=1` tant qu'il n'y a pas de quota.
- [x] Charger `vae` et `scheduler` par sous-dossier et construire
      `CobraPixArtAlphaPipeline` à la main. `from_pretrained(base)`
      (`cobra.py:554`) télécharge le dossier `text_encoder` (T5) pour rien :
      seuls les composants passés en argument sont sautés
      (`pipeline_utils.py:1417` du fork). T5 n'est déjà pas en VRAM — le
      pipeline n'enregistre que vae/transformer/controlnet/scheduler et lit le
      prompt dans `prompt_tensor/*.pt`.
- [x] `POST /v1/panel` derrière un token codé en dur (secret Modal
      `luikki-api`). `cloud/server.py`, erreurs en `{code, params}`.
- [x] `colour/remote.py` : `RemoteProposer` implémente `ColourProposer`.
      `LUIKKI_PROPOSER=remote`, `luikki serve --proposer remote`. 3 essais avec
      backoff, puis erreur. `tests/test_remote.py`.
- [x] `scaledown_window` de quelques minutes : une séance en visio ne paie
      qu'un démarrage à froid. 120 s : à 300 s, `teddy_page` (3 cases) a
      tenu le conteneur 6 min — ~1 min de démarrage à froid + génération,
      5 min à vide — soit ~0,08 $, dont cinq sixièmes d'attente.
- Fait quand : `luikki serve --proposer remote` sort des flats sur la machine
  de dev (1660 Ti). **Premier jalon utile** : tests artistes en visio, app sur
  la machine de Raph, GPU sur Modal.
  Vérifié le 2026-09-11 par `luikki flatten --proposer remote` sur
  `teddy_page` : 3 cases, 438 segments, PSD écrit, couleurs de la référence.
  Puis validé dans l'app par Raph le même jour (`luikki.bat`, qui lance
  désormais `--proposer remote`) : rapide, sans accroc.

### B2 — Comptes et quota (fait, 2026-09-12)

- [x] Compte Supabase (2026-09-12).
- [x] Projet Supabase UE (2026-09-12).
- [x] SMTP Supabase → Resend (2026-09-12) : l'envoi intégré de Supabase
      bride les codes OTP.
- [ ] Tables ci-dessus, RLS sur toutes : `src/luikki/cloud/schema.sql`, collé
      dans l'éditeur SQL. Aucune policy : seul le serveur (`service_role`) lit
      et écrit.
- [x] Un uuid par page dans `page.json` (et un par appui sur l'étape 5) :
      les numéros locaux sont réutilisés après suppression et se répètent
      d'un projet à l'autre, ils ne peuvent pas compter un quota.
      Fait (2026-09-12) : `uid` dans `page.json` (donné à l'ouverture aux
      planches d'avant), les deux ids partent dans `POST /v1/panel` ; le
      serveur les reçoit sans les contrôler encore.
- [x] Écran de connexion dans l'app (email → code), `keyring`, refresh du token.
      Fait (2026-09-12), connexion validée avec un vrai code : `luikki/account.py`,
      entrée **Compte** du rail. Connecté, l'étape 5 part avec la session et
      l'uuid de l'appareil ; sinon avec le token partagé.
- [x] Vérification du token dans la FastAPI Modal, contrôles ci-dessus,
      écriture de `usage`, `devices`, `jobs`. Déployé (2026-09-12) ; la clé
      publique est refusée sur les tables et les deux fonctions (vérifié).
      `cloud/accounts.py`, `start_panel` / `finish_panel` dans
      `schema.sql`. Token vérifié sur place (ES256, clé publique du projet),
      tout le reste en une transaction. Écarts : `usage` écrit seulement si
      la case est peinte ; un appareil absent 30 j libère sa place ; les PNG
      sont décodés avant le quota. Le token partagé est retiré en B4, et le
      plafond des images est en B6. Validé de bout en bout
      (2026-09-12) : étape 5 connectée, `usage` et `devices` écrits,
      `jobs` vidé à la fin.
- [x] Quota affiché dans l'étape 5, **avant** le clic (2026-09-12). Pas par
      `GET /v1/me` : l'app appelle la fonction Supabase `my_status` avec sa
      session, parce que lire un quota sur Modal réveillerait le GPU. Les
      limites vivent dans la table `plans`, lue aussi par `start_panel`.
- [x] Erreurs réseau / quota / abonnement / version en `StepError`
      `{code, params}`, mots dans `locales/en.json` et `fr.json` (2026-09-12) :
      codes `gpu_*`, traduits par `_gpu_refusal` dans `web/app.py`.
- [x] Hors ligne ou sans abonnement : étapes 1–4, 6, 7 marchent ; l'étape 5 dit
      pourquoi elle ne peut pas. Le proposer `distinct` reste un choix explicite
      de l'artiste, jamais un repli silencieux — ses couleurs ne portent aucun
      sens et le snap derrière serait arbitraire.
- [x] Testeurs : `plan='tester'` posé à la main dans Supabase (pas de Stripe).
- Fait quand : un compte testeur génère ; un compte sans plan est refusé avec
  un message traduit.

### B3 — Client autonome (fait, 2026-09-12)

- [x] MangaLineExtraction → ONNX : `torch.onnx.export` une fois, `.onnx`
      versionné, `extract/manga_line.py` sur onnxruntime. Test de parité
      torch/ONNX sur 2 planches réelles (lu sur les rendus).
      Fait (2026-09-12). Parité sur teddy et laurine : écart max 1 niveau de
      gris sur 255, 0,001 % des pixels touchés, aucun pixel ne change de côté
      encre/papier ; rendus dans `reports/onnx_parity/`. ONNX un peu plus
      rapide que torch sur CPU (102 s contre 120 s sur teddy). Écart : le
      `.onnx` n'est **pas** versionné, 173 Mo dépassent la limite de GitHub ;
      `luikki models` l'exporte, et B4 devra le fournir au build (asset de
      release ou export dans la CI).
- [x] Plus de torch dans le client : `_best_device` (`web/session.py`) passe aux
      providers onnxruntime. `CobraProposer` reste utilisable depuis les sources.
      Fait (2026-09-12) : `best_providers` dans `extract/manga_line.py` (CUDA
      avec `onnxruntime-gpu`, DirectML avec `onnxruntime-directml`, sinon CPU).
- [x] Détecteur de bulles embarqué : plus de téléchargement au lancement
      (`segmentation/bubbles.py:109`). Fait (2026-09-12) : `luikki/models.py`
      lit `models/` dans le bundle de l'app installée, ou dans le dépôt ;
      `luikki models` le remplit une fois (détecteur vérifié par sha256, ONNX
      exporté depuis `erika.pth`). Mettre `models/` dans le bundle : B4.
- [x] `platformdirs` : `%LOCALAPPDATA%\Luikki` (local, pas roaming : les
      cartes de zones ne se synchronisent pas), `~/Library/Application
      Support/Luikki`, comme dossier de travail par défaut (2026-09-12).
      Avant : le dossier temp, que le nettoyage de disque vide. Un projet
      resté dans `%TEMP%\luikki` est copié une fois au premier lancement.
- [x] **Persistance du projet** (fait dans A, en fichiers). Fermer la
      fenêtre ne perd plus la page.
- Fait quand : pipeline complet dans un venv sans torch, et une page survit à
  la fermeture de l'app.
  Vérifié le 2026-09-12 dans un venv neuf (`pip install -e ".[web,dev]"`,
  torch absent) : `luikki flatten` sur teddy sort son PSD (3 cases, 438
  segments, comme sur Modal), et la suite passe (321, le seul test sauté est
  la parité, qui a besoin de torch).

### B4 — Installeurs (5–8 j)

- [x] Retirer le token partagé de B1 : serveur Modal, `luikki.bat`, et
      `luikki flatten --proposer remote` passe par `Account`. Gardé jusque-là
      comme filet si Supabase tombe pendant une séance en visio.
      Fait (2026-09-12), déployé : la session est la seule entrée de
      `POST /v1/panel`. Côté client, codes `no_server` (pas d'URL) et
      `not_signed_in` (pas de session) ; `flatten` lit la session que l'app a
      rangée dans le trousseau. L'URL du serveur est écrite dans
      `colour/remote.py` (`REMOTE_URL`, comme celle de Supabase dans
      `account.py`) ; `LUIKKI_REMOTE_URL` ne sert plus qu'à viser un autre
      déploiement.
- [x] Point d'entrée : uvicorn sur `127.0.0.1`, port libre, dans un thread ;
      fenêtre pywebview dessus.
      Fait (2026-09-12) : `luikki app` (`desktop.py`, extra `[desktop]`,
      pywebview 6.2). Le socket est lié avant d'être donné à uvicorn : pas de
      course sur le port. Fenêtre maximisée, WebView2 non privé (la langue
      survit), stockage dans `<données>/Luikki/webview`. L'export PSD passe
      par la boîte « Enregistrer sous » du système (`ALLOW_DOWNLOADS`, sinon
      pywebview annule le téléchargement). Vérifié sur la vraie planche :
      la page rouvre, port 52134, fermer la fenêtre arrête le serveur.
      `--proposer` vaut `remote` par défaut. Pas encore essayés à la main dans
      la fenêtre : la boîte d'export et l'envoi de fichiers (WebView2 les gère
      nativement). Pour PyInstaller : en mode fenêtré `sys.stderr` est `None`,
      la config de logs d'uvicorn devra écrire dans un fichier.
- [x] PyInstaller `onedir` ; imports cachés à régler (scipy, scikit-image,
      opencv, onnxruntime, psd-tools).
      Fait (2026-09-12) : `packaging/luikki.spec`, construit depuis
      `.venv-build` (sans torch). Les hooks de PyInstaller 6.22 et de
      hooks-contrib suffisent pour scipy, scikit-image, opencv 5, onnxruntime,
      psd-tools, pywebview/pythonnet et keyring ; seuls imports ajoutés :
      `linefiller` (dossier vendu, pas un paquet) et les sous-modules
      d'uvicorn. `dist/Luikki` = 638 Mo, dont 340 Mo de modèles. Écarts :
      l'exécutable sans console écrit sa sortie dans
      `%LOCALAPPDATA%\Luikki\Logs\luikki.log` (`desktop.log_to_file`), et
      `Luikki.exe <commande>` lance n'importe quelle commande `luikki`, d'où
      `packaging/smoke.py` : une planche de bout en bout dans l'exécutable,
      sans fenêtre. Vérifié : teddy (3 cases, 438 segments, PSD, 297 s sur
      CPU) et tintin (12 cases, 12 bulles, 659 segments, 15 s) ; la fenêtre
      s'ouvre, lit le compte dans le trousseau, se ferme proprement. Reste
      l'icône : l'exécutable a celle de PyInstaller.
- [ ] Projet d'exemple embarqué : 1 page + character sheet + palette → PSD au
      premier lancement. Planche dessinée par Raph (2026-09-12) : les
      `test_pages` sont sous copyright et ne peuvent pas être distribuées.
- [x] Windows : Inno Setup. Non signé pendant les tests (« Informations
      complémentaires → Exécuter quand même »).
      Fait (2026-09-12) : `packaging/luikki.iss` (Inno Setup 6.7), installeur
      de 385 Mo. Pour l'utilisateur, sans droits admin, dans
      `%LOCALAPPDATA%\Programs\Luikki` ; français et anglais ; icône tirée de
      `favicon.svg` (`packaging/icon.py`) ; une mise à jour remplace tout
      `_internal`. Si WebView2 manque, l'installeur le dit avec le lien (pas
      encore embarqué). Vérifié sur cette machine : installation silencieuse,
      raccourci créé, tintin jusqu'au PSD dans l'app installée (47 s),
      désinstallation qui retire exe et raccourci et laisse le projet de
      `%LOCALAPPDATA%\Luikki` intact. Pas encore fait : une VM Windows vierge.
- [ ] Mac : build sur runner macOS GitHub Actions (PyInstaller ne compile pas
      en croisé). Signature ad hoc seulement (`codesign -s -`, que PyInstaller
      pose par défaut ; vérifier `codesign -dv` sur le `.app`) : sans aucune
      signature, un binaire arm64 ne se lance pas. DMG. arm64. Notarisation : B6.
- [x] Mode d'emploi testeur, une ligne par OS. Fait (2026-09-12) :
      `packaging/TESTEURS.md`, avec la connexion et où trouver `luikki.log`. Windows : « Informations
      complémentaires → Exécuter quand même ». Mac : ouvrir une fois, puis
      Réglages → Confidentialité et sécurité → « Ouvrir quand même » (depuis
      macOS 15, clic droit → Ouvrir ne suffit plus).
- [ ] CI : tag `v*` → build Win + Mac → GitHub Releases (gratuit, dépôt
      public). Secrets de signature : B6.
- [ ] Mise à jour : au lancement, la dernière release GitHub (API publique)
      → bandeau avec le lien. Décidé le 2026-09-12 à la place de
      `GET /v1/version` : sur Modal, la route vit dans le conteneur GPU et
      chaque lancement le réveillerait.
- [ ] Un Mac pour tester : un testeur, ou un Mac loué à l'heure. En attente
      (2026-09-12) : Raph ne peut pas tester sur Mac en direct pour l'instant.
- Fait quand : installation sur une VM Windows vierge et sur un vrai Mac, une
  page va jusqu'au PSD.

### B5 — Stripe, mode test (3–4 j)

- [x] Compte Stripe en mode test (2026-09-12).
- [ ] Produit « Luikki Cloud », prix mensuel.
- [ ] Bouton « S'abonner » → `POST /v1/checkout` → `webbrowser.open(url)`,
      jamais dans pywebview.
- [ ] Customer Portal activé : résiliation, carte, factures.
- [ ] Webhooks → `subscriptions` ; tester résiliation et paiement refusé.
- [ ] Codes testeurs : coupon 100 %, `duration=repeating` (3 mois) ; Promotion
      Codes `TESTEUR-XXXX` avec `max_redemptions` et `expires_at`. Pas de carte
      demandée grâce à `payment_method_collection="if_required"`.
- [ ] Offre fondateur : un autre coupon, même mécanique (remplace les
      « licences fondateur »).
- Fait quand : un testeur s'abonne avec un code sans carte, résilie via le
  portail, et perd l'accès.

### B6 — Production (4–6 j + délais externes)

- [ ] Stripe live sur la micro-entreprise (SIREN, IBAN).
- [ ] TVA : Stripe Managed Payments (Stripe marchand officiel, gère TVA,
      fraude, litiges ; logiciels et SaaS admissibles) **si** la France est dans
      les pays éligibles — la liste ne s'affiche qu'au navigateur, vérifier dans
      le dashboard. Sinon Stripe Tax.
- [x] ~~**[€]** Comptable~~ — pas besoin, vérifié par Raph (2026-09-11) : franchise en base de TVA ; seuil de 10 000 € de
      ventes B2C à des particuliers UE hors France, au-delà duquel la TVA du pays
      client s'applique (guichet OSS) ; activité déclarée qui couvre la vente
      d'abonnements logiciels.
- [ ] CGU/CGV : restrictions d'usage OpenRAIL++-M (Attachment A, héritées de
      PixArt), images supprimées après le job, aucun entraînement. Case à cocher
      à l'inscription.
- [ ] **[€]** Sentry client + serveur, **aucune image** dans les événements.
- [ ] **[€]** Apple Developer Program, 99 $/an, inscription en individuel (une
      micro-entreprise n'est pas une personne morale). Puis `codesign`
      hardened runtime → `xcrun notarytool submit --wait` → `xcrun stapler
      staple` → DMG. Reporté de B4 (2026-09-12).
- [ ] **[€]** Signature Windows : Azure Artifact Signing (~10 $/mois), reportée
      des tests (2026-09-12). Les
      particuliers doivent être aux États-Unis ou au Canada ; les organisations
      UE sont admises — vérifier qu'une micro-entreprise passe la validation.
      Repli : Certum Open Source Code Signing (conditions à vérifier). Même
      signé, SmartScreen avertit tant que la réputation n'est pas construite
      (EV ne la donne plus d'office).
- [ ] Toutes les clés (Stripe live, `service_role`, signature) uniquement dans
      les secrets Modal et GitHub.
- [ ] Plafond des images reçues par `POST /v1/panel` : 10 000 px de côté
      (décidé 2026-09-12), lu dans l'en-tête PNG avant tout décodage. Protège
      le GPU partagé d'une image géante ou d'un PNG qui explose au décodage ;
      l'app n'envoie rien d'aussi grand.
- Fait quand : un inconnu télécharge, s'abonne avec une vraie carte, génère
  une page et reçoit sa facture.

## C — Après les tests : mesurer, durcir

- [ ] Mesurer : s/case, cases/page, pic VRAM, démarrage à froid, coût réel par
      page, relances par page → figer quota et prix.
- [ ] Région UE (Modal ×1,5, ou hébergeur UE) quand de vrais clients paient.
      Jamais d'hôtes tiers (type Community Cloud).
- [ ] Non-rétention vérifiée chez Modal (entrées, sorties, logs) + DPA signé.
- [ ] Références envoyées une fois par hash, plus à chaque case.
- [ ] Cases d'une page en parallèle : latence ÷ N mais N démarrages à froid →
      plafond de workers par page.
- [ ] Annulation : relancer l'étape 5 pendant un job annule les cases restantes
      (sinon elles sont payées).
- [ ] `model_version` gardé dans le projet : une page régénérée après une mise
      à jour du modèle doit pouvoir dire pourquoi elle a changé.
- [ ] Retrieval CLIP côté client (ONNX) seulement si « vos références ne
      quittent pas votre machine » devient un argument de vente.
- [ ] Mise à jour automatique à la place du bandeau.
- [ ] **[€]** Stockage objet (R2 / Scaleway) si GitHub Releases ne suffit plus.

## D — Site + vidéos (parallèle, dès maintenant)

- [ ] Boucle héros 30–60 s, sans voix : trait noir → page couleur.
- [ ] 3 clips courts : coins de case, balayage+fusion de zones, coupe d'une zone qui fuit.
- [ ] Démo longue 5–8 min sur vraie page, avec l'artiste, erreurs comprises.
- [ ] Avant/après sur planche d'album réelle (autorisation écrite).
- [ ] Bloc « vos couleurs, vos références » sur page tarifs : refs de l'artiste uniquement / sortie brute jamais montrée ni exportée / aucun trait dans l'export / aucun entraînement.
- [ ] Page tarifs 2 colonnes (mini gratuit installé / abonnement cloud), même avant le cloud.
- [ ] **[€]** Hébergement vidéo : YouTube non répertorié au début, Bunny/Mux ensuite.
- [x] **[€]** Email transactionnel : Resend, le même compte que le SMTP Supabase (B2). Compte et domaine du site faits (2026-09-12).
- [ ] 3 emails liste d'attente : démo vidéo → codes fondateur → ouverture cloud.

## ~~E — Lignes ouvertes (recherche, transverse)~~ — résolu (2026-09-11)

**Section close.** Raph considère les lignes ouvertes résolues : les cases non
cochées ci-dessous ne sont plus à faire. Gardé pour l'historique.

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
- ~~**Lignes ouvertes** : premier poste, avant tout le reste de A. C'est la seule étape dont l'échec se paie en corrections manuelles à chaque page. Recherche d'abord, code ensuite.~~ Résolu (2026-09-11).
- **Animation** : même moteur, deux retraits (cases, bulles) et un ajout (l'image comme unité). Le risque n'est pas la segmentation, c'est la cohérence d'une zone d'une image à la suivante — à prototyper avant de promettre la variante.
