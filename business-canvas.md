# Business Model Canvas – Luikki

25 septembre 2026, mis à jour le 1er octobre 2026 (ROADMAP G : découpage pur,
plus de couleur IA, une seule offre à 10 €/an). Le détail et les calculs sont
dans `business-plan.md` (draft 3) ; ses chiffres de revenu supposaient les
trois offres et sont à refaire.

**1. Segments de clientèle**
- **La cible : les studios webtoon** (Corée surtout, puis Chine et Japon).
  Environ 10^3 dans le monde. Ils apportent le volume et le revenu.
- Les utilisateurs : les auteurs couleur qui font leurs aplats eux-mêmes
  (France, marché anglophone). Environ 10^4 professionnels,
  10^5 avec les amateurs sérieux. Ils apportent la réputation, pas le revenu.
- Leur besoin : faire les aplats vite, sans perdre le contrôle.
- Leur obstacle : le flatting est lent et cher. Les outils IA actuels mettent
  des couleurs au hasard.

**2. Proposition de valeur**
- Une appli desktop qui découpe la page en cases, bulles, zones et plans
  (1er plan, 2e plan, fond, personnages), et rend un PSD d'environ cinq
  calques que le pro colore dans son logiciel. Aucune couleur proposée.
- Deux testeurs sur deux ont demandé les plans sans qu'on le leur suggère.
- Pour un auteur qui fait ses aplats lui-même : environ 10 fois plus vite.
  Mesuré par les testeurs : 30 minutes par planche au lieu de 4 à 8 heures
  (8 à 16 fois), mesuré avec la couleur au clic d'avant G : à mesurer de nouveau.
  200 planches par an chez un flatter coûtent 2 000 à 3 000 $ ; la licence
  coûte 10 €.
- Pour un studio : pas encore mesuré. Ses coloristes sont rapides.
  À mesurer sur un épisode avec un coloriste de studio.
- L'artiste garde le contrôle à chaque étape.
- Rien ne quitte l'ordinateur : tout le découpage tourne en local.
- Luikki ne remplace pas le flatter. Un flatter pro va aussi vite (2 planches
  par heure) : Luikki lui évite seulement de détourer à la main. Les flatters
  ne sont pas une cible. Luikki remplace les outils IA sans contrôle.

**3. Canaux**
- Un site web avec le téléchargement de l'appli.
- Le paiement en ligne par carte (Stripe).
- Une vente à distance et individuelle.
- Pour les studios : une démonstration, un devis et une facture. Un site
  coréen à part, qui parle en épisodes.

**4. Relations clients**
- Faire connaître : vidéos avant/après sur les réseaux des artistes. À 10 € et
  50 € par an, aucune publicité n'est rentable : seul le bouche-à-oreille
  amène les particuliers.
- Acquérir : un prix d'entrée bas (10 €/an).
- Développer le CA : à redéfinir, il n'y a plus de ligne au-dessus de 10 €.
- Vendre aux studios : démonstration en visio, comme pour les tests.

**5. Flux de revenus** — une seule offre, pas d'offre gratuite (G4)
- Licence : 10 €/an, tout compris. La racheter ajoute un an.
- Archivées le 2026-10-01 (les achats faits restent valides) : licence IA,
  packs, Studio, pass couleur, licence fondateur.
- CA brut à 1, 2 et 3 ans du draft 3, **avec les trois offres, donc périmé** :

  | Scénario (conversion par an) | An 1 | An 2 | An 3 | An 3 par mois |
  |---|---|---|---|---|
  | 0,1 % : +100 particuliers, +1 studio | 3 000 € | 5 700 € | 7 400 € | 620 € |
  | 1 % : +1 000 particuliers, +10 studios | 30 300 € | 56 800 € | 73 900 € | 6 200 € |
  | 10 % : +10 000 particuliers, +100 studios | 302 500 € | 567 800 € | 739 100 € | 61 600 € |

- À 10 €/an, 20 000 €/mois demanderait 24 000 licences actives : à repenser.

**6. Ressources clés**
- Le code de l'appli (source disponible, licence PolyForm Shield).
- Les modèles locaux : extraction de trait, détecteur de bulles, Depth
  Anything V2 Small (profondeur).
- La marque Luikki.
- Les compétences techniques du fondateur.

**7. Activités clés**
- Vendre aux studios webtoon. C'est l'activité qui fait le revenu.
- Améliorer l'appli avec les retours des artistes.
- Tester les prix pendant l'année.

**8. Partenaires clés**
- Modal (fonction de paiement, sans GPU), Stripe (paiement), Supabase
  (comptes), Resend (e-mails).
- Les auteurs des modèles open source (LineFiller, MangaLineExtraction,
  détecteur de bulles, Depth Anything).
- Attendu d'eux : un service fiable et le droit d'utiliser leurs outils.
- Apporté par Luikki : des clients payants et de la visibilité.

**9. Structure des coûts**
- Investissements : marque INPI (~200 €), Apple Developer (99 $/an).
- Charges fixes : signature Windows (~10 $/mois), hébergement, comptes.
  Supabase Pro à 25 $/mois pour une licence à 10 €/an : à revoir (G1).
- Charges variables : plus de GPU. Stripe : 5 % + 0,25 € par paiement, soit
  7,5 % sur une licence à 10 €.
- Le temps du fondateur : le vrai coût, non chiffré.
