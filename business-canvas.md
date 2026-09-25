# Business Model Canvas – Luikki

25 septembre 2026. Le détail et les calculs sont dans `business-plan.md`
(draft 3).

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
- Une appli desktop qui découpe la page en zones et colore au clic.
- Une option IA qui colore les cases à partir des fiches personnages.
- Pour un auteur qui fait ses aplats lui-même : environ 10 fois plus vite.
  Mesuré par les testeurs : 30 minutes par planche au lieu de 4 à 8 heures
  (8 à 16 fois). 200 planches par an chez un flatter coûtent 2 000 à 3 000 $ ;
  la licence IA coûte 50 €.
- Pour un studio : pas encore mesuré. Ses coloristes sont rapides.
  L'argument est la couleur IA à partir des fiches et le coût par épisode,
  pas la vitesse. À mesurer sur un épisode avec un coloriste de studio.
- L'artiste garde le contrôle à chaque étape.
- Rien ne quitte l'ordinateur, sauf les cases envoyées à la génération IA.
  Luikki n'en garde aucune et ne s'entraîne sur aucune.
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
- Fidéliser : les cases achetées n'expirent jamais.
- Développer le CA : passer de 10 € à 50 €, puis aux packs, puis au Studio.
- Vendre aux studios : démonstration en visio, comme pour les tests.

**5. Flux de revenus** — trois offres, pas d'offre gratuite
- Licence de base : 10 €/an. Segmentation et click-to-color illimités.
- Licence IA : 50 €/an. 1 000 cases de génération par an incluses.
- Packs IA, réservés à la licence IA : 100 cases à 5 €, 500 à 10 €, 1 000 à
  20 €. Pour recharger vite.
- Studio : 150 €/mois. 5 000 cases par mois, 3 postes.
- CA brut à 1, 2 et 3 ans (méthode Jason Cohen, `business-plan.md` §5) :

  | Scénario (conversion par an) | An 1 | An 2 | An 3 | An 3 par mois |
  |---|---|---|---|---|
  | 0,1 % : +100 particuliers, +1 studio | 3 000 € | 5 700 € | 7 400 € | 620 € |
  | 1 % : +1 000 particuliers, +10 studios | 30 300 € | 56 800 € | 73 900 € | 6 200 € |
  | 10 % : +10 000 particuliers, +100 studios | 302 500 € | 567 800 € | 739 100 € | 61 600 € |

- 20 000 €/mois demande environ 133 studios, soit 4 nouveaux studios par mois
  pour compenser les départs.

**6. Ressources clés**
- Le code de l'appli (source disponible, licence PolyForm Shield).
- Le modèle IA Cobra et le serveur GPU.
- La marque Luikki.
- Les compétences techniques du fondateur.

**7. Activités clés**
- Vendre aux studios webtoon. C'est l'activité qui fait le revenu.
- Améliorer l'appli avec les retours des artistes.
- Faire fonctionner le serveur GPU et surveiller son coût.
- Tester les prix pendant l'année.

**8. Partenaires clés**
- Modal (GPU), Stripe (paiement), Supabase (comptes), Resend (e-mails).
- Les auteurs des modèles open source (Cobra, LineFiller, détecteur de bulles).
- Attendu d'eux : un service fiable et le droit d'utiliser leurs outils.
- Apporté par Luikki : des clients payants et de la visibilité.

**9. Structure des coûts**
- Investissements : marque INPI (~200 €), Apple Developer (99 $/an).
- Charges fixes : signature Windows (~10 $/mois), hébergement, comptes.
- Charges variables :
  - GPU : ~0,0025 € par case, plus ~0,04 € par séance (démarrage et attente).
    Tant que le volume est faible, les séances coûtent plus que les cases.
  - Stripe : 5 % + 0,25 € par paiement, soit 10 % sur un pack à 5 €.
- Le temps du fondateur : le vrai coût, non chiffré.
