# Business Model Canvas – Luikki

25 septembre 2026, refait le 2 octobre 2026 : une appli locale et simple,
10 €/an, vendue en ligne, sans travail de vente. Le détail et les calculs sont
dans `business-plan.md` (draft 4).

**1. Segments de clientèle**
- Les auteurs couleur qui font leurs aplats eux-mêmes (France, marché
  anglophone). Environ 10^4 professionnels, 10^5 avec les amateurs sérieux.
- Leur besoin : faire les aplats vite, sans perdre le contrôle.
- Leur obstacle : le flatting est lent et cher. Les outils IA actuels mettent
  des couleurs au hasard.
- Plus une cible : les studios webtoon (démos, devis, site coréen : du
  travail de vente). Ils peuvent acheter des licences comme tout le monde.

**2. Proposition de valeur**
- Une appli desktop qui découpe la page en cases, bulles, zones et plans
  (1er plan, 2e plan, fond, personnages), et rend un PSD d'environ cinq
  calques que le pro colore dans son logiciel. Aucune couleur proposée.
- Deux testeurs sur deux ont demandé les plans sans qu'on le leur suggère.
- Pour un auteur qui fait ses aplats lui-même : environ 10 fois plus vite
  (8 à 16 fois, mesuré avec la couleur au clic d'avant G : à mesurer de
  nouveau). 200 planches par an chez un flatter coûtent 2 000 à 3 000 $ ; la
  licence coûte 10 €.
- L'artiste garde le contrôle à chaque étape.
- Rien ne quitte l'ordinateur : tout tourne en local.

**3. Canaux**
- Un site web avec le téléchargement de l'appli.
- Le paiement en ligne par carte (Stripe).
- Aucune vente individuelle, aucune démo.

**4. Relations clients**
- Faire connaître : vidéos avant/après sur les réseaux des artistes. À
  10 €/an, aucune publicité n'est rentable : seul le bouche-à-oreille amène
  les clients.
- Self-service : télécharger, acheter, se connecter. Pas de support au-delà
  des e-mails.

**5. Flux de revenus**
- Licence : 10 €/an, tout compris, pas d'offre gratuite. La racheter ajoute
  un an. Net : 9,25 € après Stripe.
- Archivées le 2026-10-01 (les achats faits restent valides) : licence IA,
  packs, Studio, pass couleur, licence fondateur.
- CA brut (100 000 personnes, 40 % ne renouvellent pas) :

  | Scénario (conversion par an) | An 1 | An 2 | An 3 | An 3 par mois | Plafond par mois |
  |---|---|---|---|---|---|
  | 0,1 % : +100 licences | 1 000 € | 1 600 € | 1 960 € | 163 € | 208 € |
  | 1 % : +1 000 licences | 10 000 € | 16 000 € | 19 600 € | 1 633 € | 2 083 € |
  | 10 % : +10 000 licences | 100 000 € | 160 000 € | 196 000 € | 16 333 € | 20 833 € |

- 1 000 €/mois = 1 200 licences actives. 20 000 €/mois = 24 000 : hors
  d'atteinte sans vente, et c'est accepté.

**6. Ressources clés**
- Le code de l'appli (source disponible, licence PolyForm Shield).
- Les modèles locaux : extraction de trait, détecteur de bulles, Depth
  Anything V2 Small (profondeur).
- La marque Luikki.
- Les compétences techniques du fondateur.

**7. Activités clés**
- Améliorer l'appli avec les retours des artistes.
- Faire les vidéos et le site.
- Tester les prix pendant l'année.

**8. Partenaires clés**
- Stripe (paiement : un Payment Link), Supabase (comptes, et le webhook de
  Stripe en Edge Function), Resend (e-mails). Tous en offre gratuite sauf
  Stripe. Plus de Modal.
- Les auteurs des modèles open source (LineFiller, MangaLineExtraction,
  détecteur de bulles, Depth Anything).

**9. Structure des coûts**
- Investissement : marque INPI (~200 €, une fois).
- Charges fixes : Apple Developer (99 $/an), signature Windows (~10 $/mois).
  Environ 200 €/an : **22 licences par an les paient.**
- Supabase reste en gratuit (Pro = 25 $/mois = 30 licences). Passer en Pro
  seulement si le projet se met en pause.
- Charges variables : Stripe, 0,75 € par licence. Pas de GPU : un client ne
  coûte rien après la vente.
- Le temps du fondateur : le vrai coût, non chiffré.
