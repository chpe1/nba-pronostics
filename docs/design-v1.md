# Design V1 — Moteur de Pronostics NBA

Document de référence pour la direction visuelle du projet. Même statut que
[`docs/calibrage-v1.md`](calibrage-v1.md) : il consigne des décisions et leur raisonnement, pas
seulement des valeurs. Toute valeur ci-dessous est opposable ; toute valeur qu'on décide de changer
se change **ici d'abord**.

Adapté d'un brief de design rédigé indépendamment du projet. Les écarts entre ce brief et l'état
réel du code sont tranchés et justifiés en §2.

---

## 1. Périmètre

**Ce chantier ne modifie aucun comportement fonctionnel.** Il ne touche ni l'algorithme, ni l'API, ni
le schéma de base. Toute idée du brief d'origine qui exigeait une nouvelle donnée, un nouvel endpoint
ou une nouvelle colonne est listée en §14 (« Reporté ») plutôt qu'implémentée en douce.

Le projet reste ce que décrit `CLAUDE.md` : **usage personnel, MVP en local**. Les exigences du brief
d'origine qui ne valent que pour un produit public (crédibilité vis-à-vis d'un visiteur, performance
en 4G, prudence juridique sur les marques) sont conservées uniquement quand elles produisent de toute
façon une meilleure interface. Elles ne sont jamais la justification principale d'une décision.

**Trois décisions cadre, prises le 2026-08-29 :**

| Sujet | Décision |
|---|---|
| Mode clair / sombre | Les deux, complets, avec un bouton de bascule visible. **Sombre par défaut.** |
| Thèmes d'accent alternatifs | Axe présent en variables CSS, **aucun sélecteur visible**. Orange parquet actif. |
| PWA (manifest, service worker) | **Reportée à l'Étape 8**, avec le déploiement. Voir §2. |

---

## 2. Écarts assumés avec le brief d'origine

### 2.1 La PWA est reportée

Le brief la place dans son titre, son format et ses contraintes. Elle est écartée pour deux raisons
concrètes :

- **Le hors ligne n'a pas de sens ici.** Le backend tourne en local. Un service worker servirait une
  coquille d'application sans aucune donnée derrière — moins utile qu'une erreur de connexion franche.
- **La mise en cache saboterait ce chantier précisément.** Un service worker ressert les fichiers
  déjà téléchargés : on déploie une correction visuelle, on recharge, on voit l'ancienne version. Sur
  un travail fait d'allers-retours visuels permanents, c'est une source de faux bugs coûteuse.

Ce qui est utile dans la démarche PWA est conservé sans elle : polices auto-hébergées, `theme-color`
pour teinter la barre du navigateur mobile, balise `viewport` correcte, icône d'écran d'accueil.

L'argument « les polices doivent être auto-hébergées pour le hors ligne » tombe donc, mais la
conclusion tient pour d'autres raisons : pas de dépendance à un CDN externe, et pas de clignotement de
texte au chargement.

### 2.2 Les couleurs sémantiques varient selon le mode

Le brief pose qu'elles sont fixes. C'est juste **vis-à-vis de l'axe d'accent** : le vert ne doit pas
changer parce qu'on passe l'accent au violet, sous peine de rendre les graphiques illisibles. Cette
règle est conservée telle quelle.

Mais elles ne peuvent pas être identiques en clair et en sombre. Mesuré : `#22C55E` sur un fond clair
donne un contraste de **2,09:1**, `#FBBF24` donne **1,53:1**, très loin des 4,5:1 exigés par le brief
lui-même. Chaque couleur sémantique a donc **une valeur par mode**, et une seule par mode quel que
soit l'accent.

### 2.3 Deux valeurs de la palette sombre sont corrigées

Mesures faites sur les valeurs exactes du brief, contre le fond `#0E1015` et la surface de carte
`#1A1D26` :

| Valeur du brief | Contraste sur carte | Verdict |
|---|---|---|
| Texte désactivé `#6B7280` | **3,48:1** | Sous le seuil. Remplacé par `#808896` (4,71:1). |
| Rouge `#EF4444` en texte | **4,47:1** | Sous le seuil. Remplacé par `#F87171` (6,08:1) **pour le texte uniquement**. |

`#EF4444` reste la valeur des aplats et des remplissages non textuels, où le seuil de 4,5:1 ne
s'applique pas. Toutes les autres valeurs du brief passent : texte principal 15,46:1, texte secondaire
6,63:1, accent 6,00:1, vert 7,39:1, ambre 10,08:1.

### 2.4 Le §9 du brief (espace administrateur) est conservé pour sa direction visuelle seulement

Sa liste de six fonctions a été écrite sans connaître le back-office réel. Elle ne recoupe pas les
neuf écrans existants et omet complètement les imports CSV, qui sont la colonne vertébrale de
l'alimentation en données. Voir §11.

---

## 3. Intention

Un instrument de pronostic NBA, lisible en cinq secondes sur téléphone, dont la valeur tient à la
qualité de la donnée affichée plutôt qu'à la persuasion.

**Ce que l'écran doit dire en trois secondes** — « Ces gens mesurent quelque chose. »

**Posture** — L'interface assume de dire quand elle ne sait pas. C'est la principale différence de
registre avec un site de paris, et elle doit être visible : un écart faible n'est pas présenté comme un
pronostic timide, il est présenté comme un non-pronostic.

**Format** — Conception mobile d'abord, à **360–390 px de large**. Adaptation ordinateur en grille.

---

## 4. Direction artistique

**Trois adjectifs** — Précis, contemporain, énergique.

**Registre** — Sombre et chaleureux, jamais austère. La couleur existe et éclaire le fond ; elle n'est
ni décorative ni envahissante.

**Références retenues**

| Source | Ce qu'on en prend |
|---|---|
| Raycast | La peau : fond sombre profond, surfaces surélevées, arrondis généreux, couleurs saturées par touches |
| Opta / Stats Perform | Le cerveau : data-viz rigoureuse, qui fait la signature du produit |
| Arc | Le bandeau : en-tête traité comme un objet identifiable, pas comme une barre de navigation neutre |

**Anti-références** — Monochrome austère façon Linear ou Vercel (sans caractère) ; mise en page
éditoriale façon The Athletic (c'est un instrument, pas un journal) ; esthétique de site de paris
agressif (aplats saturés, urgence, incitation).

---

## 5. Palette

### 5.1 Architecture

Deux axes **indépendants**, tous deux en variables CSS :

1. **Mode** clair / sombre, porté par `data-theme` sur `<html>`. Sombre par défaut. Bascule visible
   dans l'en-tête.
2. **Thème d'accent**, porté par `data-accent` sur `<html>`. **Aucun sélecteur dans l'interface** —
   l'axe existe pour pouvoir tester une identité colorée en changeant un attribut, pas pour être offert
   à l'utilisateur.

### 5.2 Mode sombre — thème « Orange parquet » (défaut)

| Rôle | Valeur | Contraste mesuré sur carte |
|---|---|---|
| Fond | `#0E1015` | — |
| Surface élevée (carte) | `#1A1D26` | — |
| Surface enfoncée (piste de jauge) | `#0E1015` | — |
| Surface **encadré informatif** (sur une carte) | `#232733` | texte principal 13,68:1 / texte secondaire 5,87:1 / texte désactivé 4,17:1 |
| Bordure | `#262A35` | — |
| Accent principal | `#F97316` | 6,00:1 |
| Accent clair | `#FDBA74` | 9,98:1 |
| Accent **on** (texte sur un aplat d'accent) | `#0E1015` | 6,79:1 |
| Texte principal | `#F5F5F7` | 15,46:1 |
| Texte secondaire | `#9CA3AF` | 6,63:1 |
| Texte désactivé | `#808896` | 4,71:1 |

### 5.3 Mode clair

Dérivé, mesuré contre le fond `#F4F5F7` et la surface de carte `#FFFFFF`.

| Rôle | Valeur | Contraste mesuré sur carte |
|---|---|---|
| Fond | `#F4F5F7` | — |
| Surface élevée (carte) | `#FFFFFF` | — |
| Surface enfoncée (piste de jauge) | `#E8EAEF` | — |
| Surface **encadré informatif** (sur une carte) | `#F1F2F6` | texte principal 16,16:1 / texte secondaire 6,08:1 / texte désactivé 4,65:1 |
| Bordure | `#D7DAE2` | — |
| Accent **texte** | `#C2410C` | 5,18:1 |
| Accent **aplat** (jauge, remplissage) | `#F97316` | non textuel |
| Accent **on** (texte sur un aplat d'accent) | `#0E1015` | 6,79:1 |
| Accent clair (fond teinté) | `#FFEDD5` | non textuel |
| Texte principal | `#14161C` | 18,08:1 |
| Texte secondaire | `#545B6B` | 6,81:1 |
| Texte désactivé | `#666D7B` | 5,20:1 |

> **Point d'attention** : en mode clair, l'accent a **deux valeurs distinctes** — une pour le texte,
> une pour les aplats. `#F97316` sur blanc ne donne que 2,80:1 et ne doit jamais porter de texte.
> C'est le piège classique d'une palette sombre transposée telle quelle.

> **Troisième rôle, mesuré après coup (2026-08-29)** : ni l'accent-texte ni l'accent-aplat ne
> conviennent pour du texte porté **par-dessus** un aplat d'accent (ex. un bouton plein) — le blanc
> y donne `2,80:1` (même mesure que ci-dessus, la formule de contraste étant symétrique entre deux
> couleurs), inutilisable. Le texte sombre `#0E1015` y donne `6,79:1`, largement suffisant.
> **Cette valeur est identique dans les deux modes** : l'aplat d'accent lui-même (`#F97316`) ne
> change pas de mode (§5.3 ci-dessus), donc le texte qui doit rester lisible dessus non plus.

> **Surface enfoncée vs encadré informatif — deux besoins opposés, un seul token les confondait
> (2026-08-29).** La "surface enfoncée" (`#0E1015` en sombre) est faite pour un élément **creusé**
> dans le fond — la piste d'une jauge, qui doit visuellement s'enfoncer. Elle vaut exactement
> `--canvas` en mode sombre : posée comme fond d'un encadré informatif **sur une carte**
> (`CsvUploadForm.vue`, `CsvTemplatesCard.vue`), elle se confond entièrement avec le fond de page
> et rend l'encadré invisible — repéré en recette. Ce sont deux rôles différents qui n'auraient
> jamais dû partager la même valeur. La "surface encadré informatif" ci-dessus existe pour ce
> second besoin ; **`--surface-sunken` reste réservé aux éléments creusés sur le fond (piste de
> jauge) et ne doit jamais servir de fond à un encadré posé sur une carte.**
>
> **En sombre, le texte désactivé est interdit sur l'encadré informatif** : `4,17:1`, sous le
> seuil de `4,5:1` (§12). Utiliser le texte secondaire à la place pour toute mention atténuée à
> l'intérieur d'un tel encadré. En clair, les trois niveaux de texte (`4,65:1` au pire) passent
> sans exception.
>
> Ce rôle n'est pas encore appliqué dans le code à ce stade — implémentation prévue au Lot 3
> (§15), en même temps que la correction des encadrés concrets qui l'ont révélé.

### 5.4 Couleurs sémantiques

Fixes vis-à-vis de l'axe d'accent, variables selon le mode (voir §2.2).

| Rôle | Sombre | Clair |
|---|---|---|
| Réussite, série positive | `#22C55E` | `#166534` |
| Incertitude, fatigue, calendrier resserré | `#FBBF24` | `#8F5E06` |
| Échec, absence majeure, risque | `#F87171` (texte) / `#EF4444` (aplat) | `#B91C1C` |
| Neutre, trop serré | `#9CA3AF` | `#545B6B` |

> **Correction (Lot 2, 2026-08-30)** : "confiance élevée" retiré de la ligne "Réussite" ci-dessus —
> contradisait §10.2, qui assigne la fiabilité **forte** à l'**accent**, pas au succès/vert. Les
> deux sections se référaient au même niveau avec deux couleurs différentes ; §10.2 fait autorité
> pour la fiabilité (c'est sa raison d'être), cette ligne ne couvre donc plus que la réussite et la
> série positive au sens propre (aucune des deux n'a de brique de calcul aujourd'hui, voir §14.2).

### 5.5 Thèmes d'accent alternatifs

Présents en variables, non exposés. À activer en changeant `data-accent`.

| Nom | Accent | Accent clair |
|---|---|---|
| Orange parquet *(actif)* | `#F97316` | `#FDBA74` |
| Violet électrique | `#8B5CF6` | `#C4B5FD` |
| Vert menthe | `#00E5A0` | `#7DF5CD` |
| Bleu profond | `#3B82F6` | `#93C5FD` |

> Chaque accent alternatif devra recevoir sa propre valeur « accent texte » (mode clair) **et**
> « accent on » (texte sur aplat, les deux modes), mesurées, avant d'être activé. Ce n'est pas
> nécessaire tant qu'ils dorment. **Vérifié pour le violet électrique** (2026-08-29) : le texte
> sombre `#0E1015` (la valeur "accent on" mesurée pour l'orange) n'y donne que `4,49:1` sur
> `#8B5CF6` — sous le seuil de `4,5:1`. Cette valeur ne se transpose donc pas automatiquement d'un
> accent à l'autre ; chaque accent aura potentiellement besoin d'un texte "on" différent (clair ou
> sombre selon sa propre luminosité), pas nécessairement `#0E1015`.

### 5.6 Règle d'or

**L'accent occupe moins de 10 % de la surface visible.** En aplats généralisés, l'orange évoque le
bookmaker ; en touches sur fond sombre, il évoque l'instrument.

### 5.7 Couleurs d'équipe

Le brief prévoit un marqueur de couleur par équipe. **Cette donnée n'existe pas** dans le modèle
`Team`. Reporté (§14). D'ici là, l'identité d'équipe repose uniquement sur le tricode.

---

## 6. Typographie

| Usage | Police | Réglages |
|---|---|---|
| Titres, tricodes, noms d'équipes | `Archivo` variable | graisse 700, largeur ~118 %, interlettrage −0.01em |
| Interface, texte courant | `Archivo` variable | largeur 100 %, graisses 400 et 500 |
| Chiffres, notes, écarts, scores | `JetBrains Mono` | graisses 500 à 600 |

**Pourquoi ce choix** — Archivo est une police variable : un seul fichier couvre toutes les graisses et
toutes les largeurs. La largeur étendue donne l'énergie sportive aux titres ; la largeur normale reste
sobre pour le corps. JetBrains Mono aligne les chiffres au pixel dans une liste, et permet d'animer une
valeur sans faire tressauter la mise en page.

**Mise en œuvre** — Auto-hébergées en `woff2` dans `frontend/public/fonts/`, préchargées, avec
`font-display: swap`. Pas de CDN externe.

**Hiérarchie** — Par la graisse et la largeur avant tout. Éviter la multiplication des tailles.

**Chiffres tabulaires obligatoires** (`font-variant-numeric: tabular-nums`) sur toute valeur
susceptible de changer : notes, écarts, scores, compteurs du back-office.

---

## 7. Mise en œuvre technique des tokens

Le projet est en **Tailwind CSS v4** (`@tailwindcss/vite` 4.3.x). Il n'y a pas de
`tailwind.config.js` et il ne doit pas en être créé : en v4, les tokens se déclarent dans le CSS.

`frontend/src/style.css` contient aujourd'hui une seule ligne (`@import "tailwindcss"`). Il devient le
seul endroit où une couleur, un rayon ou une graisse est définie.

**Structure attendue :**

1. Les valeurs brutes en variables CSS classiques, déclarées trois fois : sur `:root` (sombre par
   défaut), sur `[data-theme="light"]`, et par thème d'accent sur `[data-accent="..."]`.
2. Les tokens Tailwind déclarés en `@theme inline`, pointant vers ces variables plutôt que vers des
   valeurs en dur — c'est ce qui permet à une classe utilitaire de suivre le changement de mode à
   l'exécution.

> **À vérifier avant d'écrire ce fichier** : la syntaxe exacte de `@theme inline` et le mécanisme de
> variante sombre sur attribut (`@custom-variant`) en Tailwind 4.3. Ces API ont changé entre les
> versions mineures de la v4 ; se référer à la documentation officielle de la version installée plutôt
> qu'à un exemple trouvé ailleurs.

**Règle** — Une fois les tokens en place, **plus aucune couleur en dur** dans un composant. Pas de
`text-gray-600`, pas de `bg-white`. Un écran qui utilise une couleur par défaut de Tailwind est un
écran qui cassera au changement de mode.

**Persistance du mode** — Le choix clair/sombre est stocké côté navigateur (`localStorage`), lu avant
le premier rendu pour éviter un éclair de thème clair au chargement. **Aucune donnée serveur, aucun
appel API, aucune colonne en base** : ce n'est pas un réglage de l'application, c'est une préférence
d'affichage locale.

---

## 8. Structure et mise en page

### 8.1 Coquille d'application

Aujourd'hui, `App.vue` porte une barre de navigation limitée à `max-w-2xl` et pose `<RouterView />`
nu juste en dessous. Chaque vue gère donc sa propre largeur dans son coin.

**À corriger** : un conteneur de mise en page partagé, une balise `<main>` unique, une largeur maximale
définie une seule fois. Les vues ne gèrent plus leur largeur.

### 8.2 Navigation

Il y a aujourd'hui **neuf liens** dans une rangée sans retour à la ligne et sans un seul point de
rupture responsive. Sur un téléphone, connecté en admin, cette barre déborde. C'est la démonstration
que le « Mobile-First » de l'Étape 5 n'a jamais été vérifié en conditions réelles.

Règles pour le regroupement :

- **Visiteur non connecté** : l'en-tête ne porte que le titre, la bascule de thème et « Connexion
  admin ». Il n'y a aucun problème de place dans ce cas — le débordement est un problème strictement
  admin.
- **Admin connecté** : les huit écrans de gestion sont regroupés sous une entrée unique
  **« Administration »**.
- **« Déconnexion » reste en dehors du regroupement.** C'est une action de compte, pas un écran de
  gestion. L'enfouir dans le menu ferait déconnecter en cherchant les réglages.
- Les liens doivent utiliser les **routes nommées** (`:to="{ name: 'admin-imports' }"`), pas les
  chemins en dur comme aujourd'hui. Un futur changement d'URL casserait la navigation en silence.
- **État actif visible.** Il n'existe pas aujourd'hui : `RouterLink` pose bien `router-link-active`,
  mais aucune règle ne la stylise. **Piège** : le lien de titre pointe vers `/`, or `/` est un préfixe
  de toutes les routes — il recevrait `router-link-active` en permanence. C'est
  `router-link-exact-active` qu'il lui faut.
- Cibles tactiles de **44 px minimum**, y compris dans le menu déroulant.

### 8.3 Route attrape-tout

Il n'y en a pas. Une URL inconnue affiche aujourd'hui l'en-tête surmontant une page vide, sans message.
Une route `/:pathMatch(.*)*` est ajoutée, avec un écran qui dit ce qui s'est passé et propose le retour
au tableau de bord. Même fichier, même chantier.

### 8.4 Tableau de bord (`DashboardView`)

Du haut vers le bas :

1. **En-tête** — titre, bascule de thème, navigation
2. **Sélecteur de date** — existant, à retravailler visuellement. Le brief propose une bande de dates à
   défilement horizontal avec accrochage ; c'est compatible avec le comportement actuel (la date choisie
   alimente `GET /api/predictions/today?date=...`) tant qu'on ne change pas ce qui est envoyé à l'API.

   **Deux widgets, deux métiers — décision du 2026-08-30, à ne pas rouvrir en croyant simplifier.**
   Une première version (bande seule, fenêtre de 22 jours) a révélé un problème de fond plutôt
   qu'un simple réglage de largeur : la bande *parcourt* bien les jours proches, mais *saute* mal
   loin dans le calendrier (atteindre J+14 au doigt demande une dizaine de balayages, et un
   libellé de mois n'y change rien). Elle a en outre fait disparaître, sans que ce soit signalé sur
   le moment, une capacité réelle de l'ancien `<input type="date">` : atteindre n'importe quelle
   date du calendrier 2026-2027 (déjà entièrement en base) en deux clics via son calendrier
   mensuel natif.
   - **La bande sert exclusivement à parcourir** les jours proches de la date consultée. Fenêtre
     resserrée à **`-7`/`+3` jours** autour d'elle, calée sur le seuil de révélation
     (`PREDICTION_REVEAL_THRESHOLD_DAYS = 2`, `app/api/predictions.py`) et non sur une valeur
     ronde : `is_upcoming = days_ahead > 2` signifie que **J+2 est encore révélé, J+3 est le
     premier jour masqué** — la fenêtre s'arrête donc juste après cette frontière pour qu'elle
     soit visible dans la bande plutôt qu'implicite.
   - **Un champ de date natif, à côté de la bande, sert exclusivement à sauter** à une date
     quelconque — il repositionne la bande sur la date choisie. Ce n'est pas une fonctionnalité
     nouvelle : c'est la restitution de la capacité déjà perdue.
   - **Les jours de la bande au-delà du seuil de révélation sont marqués**, pour que le masquage
     se voie avant le clic plutôt qu'après (cohérent avec la posture du §3 : dire quand on ne sait
     pas). Deux règles pour ce marquage : il ne doit **jamais** ressembler à un état désactivé
     (contour, pas un assombrissement/`opacity` — ces jours restent pleinement cliquables et
     mènent à un état légitime, pas une impasse) ; et il ne doit **jamais** reposer sur la seule
     couleur (§12) — chaque jour marqué porte une description accessible explicite pour un lecteur
     d'écran, distincte de son simple numéro de jour.
     **Condition supplémentaire, corrigée en recette (2026-08-30)** : ce marquage ne s'affiche que
     lorsque la fenêtre de la bande contient **à la fois** des jours révélés/passés et des jours
     masqués — c'est-à-dire quand la frontière est effectivement présente dans la bande. Avant
     l'ouverture de la saison, tous les jours proposés sont uniformément masqués : marquer les 11
     jours de la même façon n'indique alors rien de plus qu'une bande entièrement neutre ne dirait
     déjà, et deviendrait l'état visuel permanent du produit pendant plusieurs semaines pour aucun
     bénéfice. Quand tous les jours sont du même côté du seuil, aucun jour n'est marqué — c'est le
     bandeau contextuel (§9.1) qui porte déjà cette information dans ce cas.
3. **Bandeau contextuel** — voir §9
4. **Bouton de recalcul admin** — existant, visible uniquement connecté, agit sur la date consultée.
   Absent du brief d'origine : **à conserver impérativement**.
5. **Liste des matchs** — une carte par match

**Mobile** — Colonne unique, cartes empilées, espacement de 12 à 16 px, aucune séparation décorative.

**Ordinateur** — Grille de deux à trois cartes par ligne, hauteur de carte identique pour que les
jauges d'une même ligne s'alignent.

> Le brief propose un tri par écart décroissant sur ordinateur. **Écarté pour l'instant** : l'ordre
> actuel vient de l'API et le changer côté client rendrait la même journée différemment ordonnée selon
> la largeur de l'écran. À reconsidérer si le besoin se confirme à l'usage.

### 8.5 Écrans du back-office

Huit écrans existants, tous en tableaux et formulaires. Ils reçoivent la même palette et la même
typographie, mais une **densité différente** : angles moins arrondis, espacements resserrés, aucune
animation de transition. L'accent y sert uniquement aux actions et aux alertes.

Aucune restructuration fonctionnelle. Voir §11.

### 8.6 Écran de connexion (`LoginView`)

Absent du brief d'origine. Il porte un comportement à ne pas perdre : en cas de verrouillage
anti-bruteforce, il affiche un message spécifique incluant le délai d'attente, distinct du message
d'identifiants invalides. Le traitement visuel doit distinguer ces deux états — le second n'est pas une
erreur de saisie.

---

## 9. Le bandeau contextuel

Même emplacement, même forme, **quatre états** selon la date consultée. Le brief d'origine n'en prévoit
que trois ; le quatrième est imposé par un comportement déjà en place.

### 9.1 Aucun pronostic à mettre en vitrine — *état absent du brief, obligatoire ici*

Une vitrine qui met en avant « le match au plus grand écart » (§9.2) n'a **rien à afficher** dès
que la journée ne compte aucun pronostic révélé. **Deux raisons distinctes** y mènent (voir §10.3,
qui les distingue déjà pour la carte de match) — même traitement visuel neutre, sans accent, mais
un message différent selon le cas :

- **Pronostics jamais calculés** (`prediction === null` pour tous les matchs du jour) — le plus
  souvent parce que l'effectif de la saison courante n'est pas encore importé. **État dominant
  jusqu'à mi-septembre** (§12) : le bandeau doit le dire explicitement plutôt que rester vague —
  ex. "Aucun pronostic calculé — l'effectif de la saison courante doit être importé, puis un
  recalcul lancé". **Piège corrigé en recette (2026-08-30)** : une première formulation ("effectif
  en cours de chargement") évoquait à tort une attente passagère de quelques instants, alors que
  c'est un état stable de plusieurs semaines — dire "en cours de chargement" pour un import qui
  n'aura pas lieu avant mi-septembre est aussi trompeur que de ne rien dire du tout.

  **Seconde phrase ajoutée, secondaire, expliquant QUAND (2026-08-30).** La première phrase dit ce
  qu'il faut faire (importer l'effectif) mais pas quand ce sera possible — sans ce repère, cet
  écran sera ce que l'utilisateur voit à chaque ouverture de l'application jusqu'à mi-septembre, et
  il a l'air cassé alors qu'il est simplement en attente d'un événement extérieur connu et
  prévisible. **Un état d'attente connue doit se distinguer visuellement d'un état d'erreur, sinon
  l'utilisateur cherche une panne qui n'existe pas.** Cette seconde phrase reste dans le bandeau
  uniquement (jamais sur la carte, voir la correction ci-dessus sur la duplication du message), en
  traitement visuel secondaire — un complément d'information, pas une alerte, donc en retrait de la
  première phrase plutôt qu'au même niveau. Elle ne calcule ni ne cite aucune date précise : la
  contrainte vient du calendrier NBA (les rosters ne se stabilisent qu'après les coupes d'effectif
  de présaison), pas du projet, et n'est pas déterminable par le code — seul un repère saisonnier
  ("mi-septembre") est donné, jamais un compte à rebours qui suggérerait une précision inexistante.
- **Pronostics calculés mais masqués** (`prediction.is_upcoming === true`) — au-delà de
  `PREDICTION_REVEAL_THRESHOLD_DAYS` (2 jours) dans le futur par rapport à la vraie date du jour,
  l'API renvoie délibérément `None` pour le vainqueur, l'écart, la fiabilité et les notes. Le
  bandeau annonce ici le nombre de matchs programmés et indique que les pronostics seront révélés
  à l'approche de la date. **Ce n'est pas un cas marginal** : le calendrier complet 2026-2027 est
  déjà en base, donc toute navigation un peu en avant tombe dedans.

Une journée peut mélanger les deux raisons selon les matchs (effectif importé pour l'un, pas pour
l'autre) — dans ce cas, traiter la journée comme "aucun pronostic révélé" au sens large (le bandeau
ne montre rien de toute façon) mais préférer le message "aucun pronostic calculé" dès qu'au moins
un match de la journée en relève, puisque c'est l'information la plus actionnable pour
l'utilisateur à ce stade de la saison.

**Le message explicatif complet n'appartient qu'au bandeau, jamais à la carte — corrigé en recette
(2026-08-30).** Une première version répétait la phrase complète ("l'effectif de la saison
courante doit être importé...") à la fois dans le bandeau et sur *chaque* carte de la journée : sur
un jour de 12 matchs, la même phrase apparaissait 13 fois à l'écran. La cause est **globale** (elle
concerne la journée entière, pas un match en particulier) : elle n'a donc besoin d'être écrite
qu'une fois, dans le bandeau, qui la porte déjà. La carte se contente d'un marqueur court (voir
§10.3) — c'est le bandeau, pas la carte, qui explique *pourquoi*.

### 9.2 À venir / aujourd'hui — vitrine

Met en avant le match au plus grand écart, donc le pronostic le plus fiable. Tricodes, notes, jauge
réduite, mention « Pronostic du jour ». Fond teinté à l'accent, objet plein et arrondi.

### 9.3 Passé — bilan

**Reporté (§14).** Le ratio de pronostics validés suppose une comparaison entre pronostic et résultat
réel, qui n'existe nulle part dans le projet. En attendant, une journée passée affiche le même bandeau
que §9.2, sans mention de bilan.

### 9.4 En cours — provisoire

**Reporté (§14).** Le modèle `Game` ne connaît que `SCHEDULED`, `FINISHED` et `POSTPONED` : il n'y a pas
d'état « en cours ».

---

## 10. Composants signature

### 10.1 La jauge divergente — élément central

L'algorithme attribue une note à chaque équipe. **C'est l'écart entre les deux notes qui porte la
fiabilité du pronostic**, et c'est donc lui que la jauge représente.

- Barre horizontale, curseur ancré au centre, déporté vers l'équipe favorite proportionnellement à
  l'écart
- Un seul objet porte les deux notes et leur différence
- **Version linéaire uniquement** dans cette V1. La version en arc du brief est liée à la vue match
  plein écran, qui n'existe pas (§14).
- Animation d'entrée : remplissage depuis le centre, ~600 ms, courbe douce
- Remplace ou absorbe le `ReliabilityGauge.vue` existant

**Échelle de déport — déport maximal atteint à `reliability_threshold_high` (30.0).**

La distribution simulée du calibrage V1 va de 0 à 58, avec une médiane à 18,5, et le garde-fou de test
garantit seulement un écart inférieur à 100. Caler le déport maximal sur la valeur observée (58) ou sur
la borne théorique (100) donnerait une jauge morte : la moitié des matchs bougeraient à peine.

Le déport atteint donc son maximum à **30,0**, c'est-à-dire au seuil de fiabilité haute, avec écrêtage
au-delà. Ce choix a un sens lisible : la jauge pleine signifie « confiance maximale », et un écart de
40 ne mérite pas plus d'appui visuel qu'un écart de 30 puisque les deux relèvent déjà de la même
décision. L'écart chiffré reste affiché en clair sous la jauge (ligne 5 de la carte), donc l'écrêtage ne
fait perdre aucune information.

**Conséquence importante** : `calibrage-v1.md` annonce que les seuils 7,0 / 30,0 seront recalibrés dès
que de vraies données de saison seront disponibles. L'échelle de la jauge doit suivre ce recalibrage
automatiquement, sans qu'on ait à y penser. Voir la question ouverte §14.1-A.

**« Remplace ou absorbe » appliqué au pied de la lettre (Lot 2, 2026-08-30).** L'écart entre les
deux notes *porte* la fiabilité (première phrase de cette section) : la jauge divergente et
l'ancien `ReliabilityGauge.vue` encodaient donc la même information deux fois dans la même carte —
la redondance déjà écartée pour la forme récente (§10.5), appliquée ici à l'identique. Une carte de
la liste du Dashboard ne porte plus qu'**un seul objet de mesure**, la jauge divergente.

Le niveau de confiance (§10.2) n'est pas perdu pour autant : sa pastille de mention (Ligne 1 de la
carte, §10.3) survit et reste le seul porteur visuel du niveau nommé (couleur + libellé
"Confiance élevée"/"modérée"/"Trop serré"). Ce qui disparaît, c'est uniquement le fichier
`ReliabilityGauge.vue` en tant que **composant séparé** — son rôle (le mapping couleur/libellé,
`constants/reliability.js::RELIABILITY_TREATMENT`) est conservé et directement intégré à
`GameCard.vue`, pas dupliqué dans un second composant nommé "Gauge" à côté du vrai gauge.

**Vérifié avant suppression** : `ReliabilityGauge.vue` n'était consommé que par `GameCard.vue`
(grep exhaustif de `frontend/src`) -- ni la page Diagnostic équipes (`MatchupResultCard.vue` a
toujours eu sa propre pastille "Fiabilité X" inline, jamais ce composant), ni aucun autre écran.
Suppression sans effet de bord ailleurs.

### 10.2 Niveaux de confiance

Les trois niveaux du brief se branchent **exactement** sur les trois niveaux de fiabilité déjà calibrés.
Aucun nouveau seuil n'est introduit.

| Fiabilité existante | Écart | Traitement visuel | Mention affichée |
|---|---|---|---|
| Forte | ≥ 30,0 | Accent coloré plein | Confiance élevée |
| Moyenne | 7,0 – 30,0 | Ambre atténué | Confiance modérée |
| Faible | < 7,0 | **Aucun accent, gris neutre** | Trop serré |

**Ce retrait de couleur est un choix d'affichage, pas un masquage.** L'API continue de renvoyer un
vainqueur et un écart pour un match à fiabilité faible, et l'interface continue de les montrer — elle
retire seulement l'appui visuel qui vaudrait recommandation. Ne jamais transformer ce niveau en
absence de donnée.

**Le design refuse de recommander un match incertain.** Un écart faible n'est pas un pronostic prudent,
c'est une absence de pronostic, et l'interface doit le montrer par le retrait de la couleur.

Le libellé accompagne **toujours** le traitement visuel : l'information n'est jamais portée par la seule
couleur.

Le libellé accompagne toujours le traitement : sur un écran en niveaux de gris, « Trop serré » reste
lisible là où l'absence d'accent, seule, ne dirait rien.

**Confirmé (§14.1-D, résolu)** : `GET /api/predictions/today` renvoie déjà `reliability` comme un
niveau **nommé** (`"faible"`/`"moyenne"`/`"forte"`, pas une valeur numérique brute) — le frontend
n'a donc pas à reclasser lui-même un écart dans l'un de ces trois niveaux, juste à brancher son
traitement visuel sur la valeur reçue. Cela ne répond pas à la question §14.1-A : l'échelle de
déport de la jauge (§10.1) a besoin des **valeurs numériques** des seuils eux-mêmes (`30,0` etc.),
pas seulement du niveau qu'ils produisent — cette question reste ouverte, voir §14.1.

### 10.3 Carte de match — état fermé

Environ 100 px de haut, quatre informations maximum.

- Ligne 1 — heure à gauche, pastille de niveau de confiance à droite
- Ligne 2 — tricodes des deux équipes, en Archivo étendu ; favorite en texte principal, l'autre atténuée
- Ligne 3 — les deux notes en JetBrains Mono ; celle du favori à l'accent, l'autre atténuée
- Ligne 4 — jauge divergente
- Ligne 5 — écart chiffré, en texte secondaire

**Hauteur réservée pour les pastilles, calée sur le maximum réel de la vue courante — pas sur le
plafond théorique de 3 (Lot 2, corrigé le 2026-08-30).** §8.4 exige une hauteur de carte identique
pour que les jauges d'une même ligne (grille ordinateur) s'alignent. Égaliser la hauteur *externe*
des cartes n'y suffit pas : le nombre de pastilles (§10.4) varie d'une équipe à l'autre, et tout ce
qui suit dans la carte (bilan récent, jauge, écart) se décale d'autant si leur zone n'a pas une
hauteur fixe.

Une première version réservait systématiquement la hauteur du cas maximum théorique (trois
pastilles). **Erreur constatée en recette** : tant que l'effectif de la saison courante n'est
importé pour aucune équipe (l'état dominant du produit pendant plusieurs semaines, §12), *aucun*
match n'a jamais de pastille — la carte entière gonflait alors de ~100 px à ~360 px pour réserver
un vide qui ne servait jamais à rien.

**Règle retenue** : la zone de pastilles réserve une hauteur calée sur le nombre maximum de
pastilles **réellement présentes parmi les cartes de la vue courante** (la journée consultée), pas
sur un plafond théorique fixe.
- Si aucune carte de la vue n'a de pastille, la zone disparaît entièrement (pas même un vide
  résiduel).
- Si la carte la plus fournie de la vue en compte deux, **toutes** les zones de pastilles (y
  compris celles des équipes sans aucun fait) réservent la hauteur de deux.
- Le plafond absolu de trois pastilles par équipe (§10.4, avec pastille de reste au-delà) reste
  inchangé : c'est une règle de *contenu*, distincte de cette règle de *hauteur réservée*, qui
  reste elle-même bornée au maximum observé (jamais plus de trois).

L'objectif reste le même qu'à l'origine — l'alignement des jauges d'une même ligne — mais sans
gonfler artificiellement des cartes qui n'ont, dans les faits, jamais de pastille à afficher.

**Journée passée** — Score final à la place de l'heure, notes conservées, jauge figée. Le marqueur de
réussite ou d'échec du brief est reporté (§14) : rien ne calcule aujourd'hui si un pronostic s'est
vérifié.

**Deux états vides distincts, découverts au diagnostic du Lot 2 — ce document les confondait
jusque-là.** `GameWithPredictionRead.prediction` peut être absent de deux façons différentes, qui
n'appellent pas le même traitement :

- **Pronostic jamais calculé** (`prediction === null` tout court) — aucun recalcul n'a encore eu
  lieu pour ce match, le plus souvent parce que l'effectif de la saison courante n'est pas encore
  importé pour l'une des deux équipes. **C'est l'état vide dominant tant que cet import n'a pas eu
  lieu — concrètement jusqu'à mi-septembre** (voir §12, "États vides à traiter explicitement").
- **Pronostic calculé mais masqué** (`prediction.is_upcoming === true`) — un pronostic existe bel
  et bien en base, mais le match est trop loin dans le futur pour être révélé
  (`PREDICTION_REVEAL_THRESHOLD_DAYS`, voir §9.1). **Comportement déjà en place, à conserver tel
  quel** : badge « À venir », notes et jauge absentes.

Le bandeau contextuel (§9) doit lui aussi distinguer ces deux états — §9.1, tel qu'écrit
initialement, ne décrit que le second.

**Marqueur court sur la carte, message complet réservé au bandeau — corrigé en recette
(2026-08-30).** La première formulation demandait à la carte d'expliquer *pourquoi* il n'y a pas de
pronostic (effectif pas encore chargé), reprenant mot pour mot le texte du bandeau (§9.1). Sur une
journée de plusieurs matchs, la même phrase complète apparaissait donc autant de fois que de cartes
en plus du bandeau — une répétition de plusieurs dizaines de mots identiques à l'écran, sans aucune
information supplémentaire apportée par la répétition. La cause étant **globale à la journée**, pas
propre au match de cette carte précise, elle n'a besoin d'être écrite qu'une fois : dans le
bandeau. **La carte porte désormais un marqueur court** ("Pronostic indisponible"), sans réexpliquer
la raison — le bandeau, toujours visible au-dessus de la liste, la porte déjà.

Conséquence sur la hauteur de la carte dans cet état : **les ~100 px du début de cette section
décrivent l'état nominal** (notes + jauge + pastilles), pas cet état sans aucun de ces éléments. Une
carte "jamais calculé" est délibérément plus courte -- il n'y a rien à y montrer de plus qu'un
tricode par équipe et le marqueur court.

### 10.4 Pastilles de contexte

Faits bruts, jamais présentés comme des justifications de la note. Le lecteur fait le lien lui-même ;
c'est plus fort et moins contestable.

- Hauteur ~22 px, coins arrondis, fond légèrement teinté, texte 12 px
- **Trois maximum par équipe**
- Couleurs sémantiques, jamais l'accent

**Correction (Lot 2, 2026-08-30) — le plafond de trois ne doit jamais faire disparaître un fait
sans le signaler.** Une première implémentation tronquait silencieusement au-delà de trois faits
(priorité absent > incertain > calendaire) : une équipe à cinq joueurs absents affichait alors
exactement la même carte qu'une équipe à trois, sans aucune trace des deux manquants — précisément
dans le cas qui compte le plus, un écart important où l'utilisateur veut savoir combien de monde
manque à l'équipe favorite. **Le §3 de ce document pose que l'interface assume de dire quand elle
ne sait pas ; elle ne peut pas, à l'inverse, masquer sans le signaler ce qu'elle sait bel et bien.**

Règle retenue : le plafond visuel de trois pastilles est conservé, mais seules **deux** portent un
fait quand il y en a plus de trois au total — la troisième position devient alors une **pastille de
reste**, neutre (jamais une couleur sémantique, ce n'en est pas une), qui annonce le volume masqué
(ex. « +3 ») plutôt que de le taire. La priorité de sélection des deux faits montrés reste
absent > incertain > calendaire, inchangée. **La pastille de reste porte une description explicite
pour un lecteur d'écran** — « +3 » seul, hors contexte visuel, ne dit rien à l'oreille.

Alimentation réelle, sans aucun développement :

| Pastille | Source | Disponible |
|---|---|---|
| « Tatum absent » (rouge) | `breakdown.absent_players` | oui |
| « Doubtful » / « Questionable » (ambre) | `breakdown.questionable_players` | oui |
| « 3e match en 4 jours » (ambre) | `home_calendar_status` / `away_calendar_status` | oui |

Les trois sont déjà exposées par l'API et affichées de façon rudimentaire dans `GameCard.vue`. Ce
chantier les met en forme, il ne les crée pas.

> « 5 victoires de suite » (vert), prévue par le brief d'origine sur `Team.current_streak`,
> retirée de cette liste — reportée en **§14.2**, voir la raison là-bas.

### 10.5 Forme récente

**Texte seul, pas de carrés** (revu au Lot 2, voir diagnostic `plan-design-lot2.md`). Le brief
d'origine prévoyait cinq carrés colorés, du plus ancien au plus récent — écarté pour trois raisons
qui se renforcent :

1. **Donnée indisponible.** `compute_recent_record` (`app/services/pronostic_calculator.py`) ne
   renvoie qu'un agrégat (`wins`, `losses`, `games_considered`), jamais la séquence chronologique
   des résultats individuels. Des carrés "du plus ancien au plus récent" prétendraient à un ordre
   qu'on ne connaît pas — un affichage qui semble précis sans l'être, exactement ce que le §3
   interdit ("l'interface assume de dire quand elle ne sait pas").
2. **La spécification elle-même était incohérente.** La fenêtre du bilan (`RECENT_RECORD_WINDOW`)
   vaut 7, pas 5 — "5V-2D sur les 7 derniers" est un exemple réel où le nombre de matchs considérés
   dépasse déjà le nombre de carrés prévus. Les cinq carrés étaient faux sur le principe, pas
   seulement irréalisables techniquement.
3. **Redondance visuelle avec l'élément signature.** La carte porte déjà une barre horizontale
   centrale, la jauge divergente (§10.1) — l'élément que ce chantier met le plus en avant. Une
   seconde barre juste à côté (la forme récente) dilue ce qu'on cherche justement à faire ressortir.

Le bilan V-D reste affiché **en texte** ("5V-2D sur les 7 derniers"), déjà exact et déjà présent
dans `GameCard.vue` avant ce lot — aucune perte d'information, seulement le renoncement à une
visualisation qui aurait suggéré une précision inexistante.

> Les cinq carrés ordonnés du brief d'origine sont déplacés en **§14.2** (reporté) : ils
> demanderaient que `compute_recent_record` renvoie la séquence chronologique des résultats, pas
> seulement leurs totaux — une vraie modification backend, hors périmètre de ce chantier visuel.

**La ligne disparaît entièrement quand il n'y a rien à dire — corrigé en recette (2026-08-30).**
Une équipe sans aucun match `FINISHED` dans la fenêtre (`games_considered === 0`, ce qui concerne
les 30 équipes en permanence tant que la saison n'a pas commencé) affichait "Aucun match terminé
récemment" — une phrase sans valeur informative qui, répétée sous chaque tricode de chaque carte,
occupait visuellement autant de place que le nom de l'équipe lui-même. **Quand une équipe n'a
aucun match terminé dans la fenêtre, la ligne ne s'affiche pas du tout** plutôt que d'afficher un
texte qui ne dit rien.

**Distinction à ne pas manquer, du même genre que celle de `is_upcoming` (§10.3)** :
`games_considered === 0` ("aucun match terminé, rien à mesurer") et un bilan `0V-0D sur les N
derniers` avec `games_considered > 0` ("N matchs terminés dans la fenêtre, mais aucun n'a compté
comme victoire ou défaite pour cette équipe") sont deux cas différents. Le second est rare mais
réel et reste une information à part entière — seul `games_considered === 0` doit faire disparaître
la ligne, jamais un bilan à zéro victoire déduit après coup.

### 10.6 Identité d'équipe

**Pas de logos officiels.** Chaque équipe est identifiée par son **tricode en Archivo étendu**. Le
marqueur de couleur prévu par le brief attend la donnée correspondante (§5.7).

---

## 11. Espace administrateur

Direction visuelle : même palette, même typographie, densité supérieure. Tableaux plutôt que cartes,
angles moins arrondis, aucune animation de transition.

**La liste de fonctions du brief d'origine est écartée** : elle décrit un back-office qui n'est pas
celui du projet. Les écrans réels sont :

| Écran | Rôle |
|---|---|
| Imports | Upload CSV, aperçu, historique, modèles téléchargeables |
| Matchs | Correction manuelle date/score, verrou de synchronisation |
| Joueurs | Ajout et correction manuelle |
| Équipes | Correction manuelle, recherche texte |
| Stats N-1 | Correction et suppression des stats de la saison précédente |
| Diagnostic équipes | Décomposition d'un pronostic + simulateur de réglages |
| Base de données | Vue d'ensemble et audit d'intégrité |
| Réglages généraux de l'algorithme | Curseurs et info-bulles |

**Un point d'attention hérité du fonctionnel :**

- **L'écran prioritaire du brief existe déjà à moitié.** Le simulateur de la page Diagnostic équipes
  fait déjà « recalculer avec des réglages modifiés sans rien écrire en base ». Il ne faut **surtout
  pas** construire un second simulateur ailleurs : ce qui lui manque relève de l'agrégation et est
  reporté (§14).

---

## 12. Accessibilité et contraintes

- **Contraste minimum 4,5:1** sur tout texte. Toutes les valeurs de §5 sont mesurées, pas estimées.
- **Cibles tactiles de 44 px minimum**, y compris dans le menu de navigation regroupé.
- **L'information n'est jamais portée par la seule couleur.** Le niveau de confiance est toujours
  accompagné d'un libellé ; la forme récente d'une description accessible.
- **`prefers-reduced-motion` respecté** : transitions réduites à des fondus courts, jauges affichées
  directement à leur valeur finale.
- **Chiffres tabulaires** sur toute valeur susceptible de changer.
- **Focus clavier visible** partout.
- **États vides explicites.** Les états vides réels de ce projet, à traiter en priorité :
  - Effectif de la saison courante pas encore importé → aucune prédiction calculable
  - Journée sans match
  - Date au-delà du seuil de révélation
  - Audit d'intégrité sans anomalie
- **Les contrôles natifs adressables ont besoin d'un fond explicite — l'héritage seul ne suffit
  pas (corrigé au Lot 2, 2026-08-30, validé par essai réel avant d'être écrit ici).** Le preflight
  Tailwind pose `background-color: transparent` sur plusieurs contrôles natifs (`select` compris)
  — correct pour l'élément fermé, qui doit laisser voir la carte derrière lui, mais **`<option>`,
  rendu dans une fenêtre dessinée par le système hors de la page, n'a alors aucun fond à porter**.
  Sa couleur de texte reste claire (héritée de la coquille), d'où un texte clair sur fond resté
  clair en mode sombre — `color-scheme`/`accent-color` (voir plus haut) ne suffisent pas à eux
  seuls quand l'élément est directement adressable en CSS (ce qui est le cas d'`<option>`,
  contrairement au calendrier d'un `<input type="date">`, entièrement opaque à toute règle CSS).
  Corrigé une seule fois, à portée globale (`select, option { background-color: var(--surface);
  color: var(--text); }`, `frontend/src/style.css`), pas classe par classe : un défaut de
  structure du preflight, pas d'un `<select>` en particulier. `<optgroup>` partage exactement la
  même règle de preflight et le même mécanisme de rendu système, mais n'est utilisé nulle part
  dans ce projet à ce jour — non corrigé, volontairement, en attendant un usage réel.

---

## 13. Mouvement

**Philosophie** — L'animation est concentrée sur la jauge. Le reste de l'interface est calme. La
transition liste → match plein écran du brief n'a pas d'objet dans cette V1 (§14).

- **Jauge** — remplissage depuis le centre, ~600 ms, courbe douce ; les notes défilent numériquement
  jusqu'à leur valeur
- **Micro-interactions** — enfoncement de 2 % au contact, retour en 150 ms
- **Entrée de liste** — cascade au premier chargement uniquement : décalage de 30 ms, translation
  verticale de 8 px, opacité
- **Back-office** — aucune animation

**Règles de performance non négociables**

- Animer uniquement `transform` et `opacity` — ces propriétés sont traitées par le processeur
  graphique, sans recalcul de mise en page
- Aucune animation de hauteur, largeur ou ombre portée : c'est la source des saccades

---

## 14. Questions ouvertes et reports

### 14.1 À trancher avant de coder

| # | Question | Statut |
|---|---|---|
| A | **Le seuil de fiabilité haute doit-il être exposé au frontend public ?** L'échelle de la jauge (§10.1) en dépend. Voir ci-dessous. | **résolu (Lot 2)** — oui, voie 2 retenue. Forme exacte ci-dessous. |
| B | `Team.current_streak` est-il réellement alimenté ? `CLAUDE.md` indique qu'il n'entre dans aucun calcul — s'il est vide, la pastille « série en cours » disparaît de la V1. | **résolu** — non, nulle part (grep exhaustif de `app/`, aucune occurrence hors modèle/schéma). Vaut `0` pour les 30 équipes réelles en base. Pastille retirée de la V1, voir §10.4/§14.2. |
| C | `InfoTooltip.vue` se déclenche-t-il au survol seul ? Détermine l'ampleur de la correction tactile (§11). | **résolu** — non, déjà tactile (`@click`/`@blur`, aucun `@mouseenter`/`@mouseleave`). Rien à corriger, retiré de la liste du Lot 3 (§15). |
| D | `GET /api/predictions/today` renvoie-t-il un niveau de fiabilité nommé, ou seulement une valeur numérique ? Détermine si le frontend classe lui-même ou reçoit le niveau. | **résolu** — nommé (`ReliabilityLevel`, enum `str` : `"faible"`/`"moyenne"`/`"forte"`). Le frontend reçoit déjà le niveau, voir §10.2. |

**Sur la question A.** La jauge a besoin de connaître 30,0 pour calculer son déport. Deux voies :

1. **Constante figée côté frontend.** Aucune modification backend, mais la valeur est alors écrite à
   deux endroits — en base dans `Settings`, et en dur dans le code de la jauge. Au premier recalibrage
   avec de vraies données, l'un des deux bougera sans l'autre, et la jauge cessera silencieusement de
   correspondre aux libellés qu'elle affiche. C'est exactement le type de désynchronisation que le
   projet a déjà combattu ailleurs (modèles CSV générés depuis `REQUIRED_COLUMNS`, `previous_season`
   calculée depuis `current_season`).
2. **Exposer les seuils dans la réponse publique.** Ajouter `reliability_threshold_low` et
   `reliability_threshold_high` au schéma de `GET /api/predictions/today`, en lecture seule. Le
   frontend suit alors le calibrage automatiquement. C'est une modification fonctionnelle, minime mais
   réelle : un schéma de réponse élargi.

**Recommandation : la voie 2**, pour rester cohérent avec la règle de source unique appliquée partout
ailleurs dans ce projet. Il n'y a aucun enjeu de confidentialité — ces seuils sont des paramètres
d'affichage, pas un secret, et le niveau de fiabilité qu'ils produisent est déjà public.

**Forme exacte retenue (Lot 2, 2026-08-30).** `GET /api/predictions/today` renvoie une **liste nue**
(`list[GameWithPredictionRead]`), pas un objet enveloppant — l'envelopper pour y loger les deux
seuils une seule fois aurait cassé la dizaine de tests backend existants qui indexent directement
la réponse, ainsi que le contrat déjà consommé par `DashboardView.vue`, pour un lot qui ne devait
changer qu'une seule chose fonctionnellement. Les deux champs
(`reliability_threshold_low`/`reliability_threshold_high`) sont donc **dupliqués sur chaque élément
de la liste**, identiques sur tous les matchs d'une même réponse.

La duplication porte sur le **fil** (la réponse HTTP), jamais sur la **source** : `Settings` reste
l'unique origine des deux valeurs, lue une fois par requête et recopiée sur chaque élément — pas de
risque de désynchronisation, ce qui était tout l'enjeu de cette décision. Pour éviter qu'un lecteur
du JSON ne croie à tort que ces champs varient d'un match à l'autre, ils sont documentés
explicitement dans le schéma Pydantic (`GameWithPredictionRead` docstring/description de champ)
comme des **constantes globales de la réponse**, identiques sur chaque élément, jamais une valeur
propre au match.

**Extension du même principe — `home_score`/`away_score` (Point 5, même journée).** L'état
"journée passée" de la carte de match (§10.3) a besoin du score final, qui existe déjà dans
`Game` et est déjà exposé/modifiable via `AdminGamesView` — mais absent de
`GameWithPredictionRead`. **Ce n'est pas une deuxième modification fonctionnelle** : contrairement
aux seuils de fiabilité (une politique d'affichage nouvelle sur une donnée déjà calculée), il ne
s'agit ici que de mettre à disposition, en lecture seule, une donnée que le système possède,
remplit et affiche déjà ailleurs — aucune capacité nouvelle. Même patron que les seuils : aucune
écriture, aucune migration, aucun calcul. Champs ajoutés directement sur `GameWithPredictionRead`
(pas dupliqués comme les seuils : `home_score`/`away_score` sont déjà propres à chaque match, rien
à recopier). **Détection de l'état "passé" par `status`, jamais par la présence d'un score** : un
match `FINISHED` sans score renseigné (saisie manuelle incomplète) reste théoriquement possible,
la seule présence de `home_score`/`away_score` ne suffit donc pas à conclure qu'un match est
terminé.

### 14.2 Reporté — nécessite du développement fonctionnel

À valider par l'utilisateur avant d'entrer dans une liste de travaux à venir. Rien ici n'est engagé.

| # | Élément | Ce qu'il faudrait |
|---|---|---|
| 1 | Bilan « X pronostics validés sur Y » | Comparer un pronostic à son résultat réel. Brique d'évaluation absente du projet. |
| 2 | Marqueur de réussite/échec sur une carte passée | Même brique que 1. |
| 3 | Fiabilité historique par tranche d'écart | Même brique que 1, plus l'agrégation. |
| 4 | Bandeau « en cours » | Un état de match en direct, absent du modèle `Game`. |
| 5 | Vue match plein écran + transition partagée + gestes | Écran neuf, route neuve. |
| 6 | Prévisualisation d'impact des seuils | Agrégation par-dessus le simulateur existant. |
| 7 | Couleurs d'équipe | Donnée absente du modèle `Team`. |
| 8 | Salle du match | Champ absent du modèle `Game`. |
| 9 | Cotes et confrontations directes | Source de données externe absente. |
| 10 | News par flux RSS | Chantier fonctionnel à part entière. |
| 11 | PWA (manifest, service worker) | Étape 8, avec le déploiement. |
| 12 | Pastille « 5 victoires de suite » (§10.4) | `Team.current_streak` n'est alimenté nulle part (ni import CSV, ni formulaire admin en pratique, ni calcul) et vaut `0` pour les 30 équipes réelles (§14.1-B, résolu le 2026-08-29). Rien à afficher tant que rien ne l'alimente. **À rouvrir en cours de saison**, une fois de vrais matchs joués et une vraie source qui mette à jour cette colonne. |
| 13 | Forme récente en carrés ordonnés (§10.5, brief d'origine) | Retiré au Lot 2 (2026-08-30) au profit du texte seul — voir §10.5 pour le raisonnement complet. Nécessiterait que `compute_recent_record` (`app/services/pronostic_calculator.py`) renvoie la séquence chronologique des résultats individuels, pas seulement `wins`/`losses`/`games_considered` agrégés. Modification backend, hors périmètre d'un chantier visuel. |

---

## 15. Découpage en lots

**Lot 1 — Fondations.** Aucune modification backend. Tokens et deux modes dans `style.css`, bascule
clair/sombre, polices auto-hébergées, coquille de mise en page avec `<main>`, navigation regroupée avec
état actif et routes nommées, route attrape-tout, passage effectif en 360–390 px, `theme-color` et
`viewport`.

**Lot 2 — Tableau de bord.** Carte de match, jauge divergente linéaire, niveaux de confiance, pastilles
de contexte, forme récente, bandeau contextuel à quatre états, sélecteur de date retravaillé.

**Lot 3 — Back-office.** Application de la palette dense aux huit écrans, tableaux lisibles en
360 px. ~~Correction du comportement tactile des info-bulles~~ — retirée : déjà tactile, voir
§14.1-C (résolu).

Les lots sont séquentiels et chacun se termine par une vérification en navigateur **en viewport
mobile**, jamais en desktop seul. Il n'existe aucun test de composant frontend dans ce projet : la
recette manuelle est le seul filet.

### Constats de recette (2026-08-29) à traiter au lot 3

Remontés lors de la recette du Lot 1, à 360 px réels, connecté en admin, dans les deux modes.
Consignés ici pour ne pas se perdre — **rien n'est implémenté à ce stade**, ce sont des constats
chiffrés, pas des décisions de design déjà prises.

**a) Débordement horizontal — `AdminImportsView`, seul débordement du projet.** Le tableau
d'historique fait `653px` de large dans un conteneur de `310px`, et son parent
(`div.rounded-xl.border.bg-surface.p-4`) est en `overflow: visible` — la page entière atteint
`686px` de large à un viewport de `360px`. Correction attendue : `overflow-x-auto` sur le
conteneur du tableau (défilement contenu à lui seul), ou passage en liste de cartes sous un
certain seuil de largeur.

**b) Cibles tactiles sous 44 px (§12), mesurées à 360 px :**

| Écran | Éléments sous 44 px |
|---|---|
| `AdminPreviousSeasonStatsView` | 1166 |
| `AdminPlayersView` | 184 |
| `AdminTeamsView` | 31 |
| `AdminSettingsView` | 12 |

Les trois premiers sont des tableaux éditables avec un bouton par ligne, d'où les volumes. En
cause : boutons d'action à `36–38px`, `<select>` à `34px`, et surtout les déclencheurs
d'info-bulle à `16px` de haut — pointables à la souris, pas au doigt. **C'est le cas le plus
sévère**, à traiter en priorité au Lot 3. Le lien de titre (`24px`) est **hors périmètre** : c'est
une identité de marque, pas une cible d'action (voir Point B, corrigé).

**c) Encadrés d'information indiscernables du fond en mode sombre** (`CsvUploadForm.vue` : encart
"Choisissez un fichier..." ; `CsvTemplatesCard.vue` et similaires). Cause identifiée et token
défini — voir le nouveau rôle "Surface encadré informatif" en §5.2/§5.3. Application au Lot 3.

**d) `AdminGamesView` — le bouton "Enregistrer" n'est pas l'action mise en avant.** Actuellement un
aplat neutre clair (`bg-text`/`text-canvas`, traitement "inversé" générique repris du Lot 1), alors
que c'est l'action principale de l'écran. Maintenant qu'`--accent-on` existe (mesuré, voir
§5.2/§5.3), **les actions principales du back-office devraient passer en aplat d'accent**
(`bg-accent text-accent-on`) plutôt qu'en aplat neutre inversé — à généraliser à tous les boutons
"Enregistrer"/actions principales équivalents des 8 écrans admin, pas seulement celui-ci.

**e) Constat général : l'espace admin manque de couleur.** §11 pose que l'accent y sert "aux
actions et aux alertes", mais dans l'état actuel (Lot 1 seul appliqué) l'accent n'y apparaît
quasiment jamais — la reprise du Lot 1 était mécanique (Point 7), pas un vrai travail de densité
colorée. À retravailler au Lot 3 en même temps que la palette dense du back-office.

**Avant le lot 2**, produire l'inventaire écrit des règles d'affichage conditionnelles de
`GameCard.vue` (badge « À venir », indicateurs calendaires, absents, incertains, bilan V-D) et de
`AdminGamesView.vue` (case de verrou de synchronisation, rechargement après modification). Cet
inventaire sert de liste de recette : sans test automatisé, c'est la seule protection contre la
disparition silencieuse d'une règle pendant la réécriture d'un gabarit.
