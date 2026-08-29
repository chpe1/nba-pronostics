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
| Réussite, série positive, confiance élevée | `#22C55E` | `#166534` |
| Incertitude, fatigue, calendrier resserré | `#FBBF24` | `#8F5E06` |
| Échec, absence majeure, risque | `#F87171` (texte) / `#EF4444` (aplat) | `#B91C1C` |
| Neutre, trop serré | `#9CA3AF` | `#545B6B` |

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

### 9.1 Pronostic non révélé — *état absent du brief, obligatoire ici*

Au-delà de `PREDICTION_REVEAL_THRESHOLD_DAYS` (2 jours) dans le futur par rapport à la vraie date du
jour, l'API renvoie délibérément `None` pour le vainqueur, l'écart, la fiabilité et les notes. Une
vitrine qui met en avant « le match au plus grand écart » n'a donc **rien à afficher**.

Ce n'est pas un cas marginal : le calendrier complet 2026-2027 est déjà en base, donc toute navigation
un peu en avant tombe dedans. Le bandeau annonce le nombre de matchs programmés et indique que les
pronostics seront révélés à l'approche de la date. Traitement neutre, sans accent.

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

**Journée passée** — Score final à la place de l'heure, notes conservées, jauge figée. Le marqueur de
réussite ou d'échec du brief est reporté (§14) : rien ne calcule aujourd'hui si un pronostic s'est
vérifié.

**Pronostic non révélé** — Badge « À venir », notes et jauge absentes. Comportement déjà en place, à
conserver.

### 10.4 Pastilles de contexte

Faits bruts, jamais présentés comme des justifications de la note. Le lecteur fait le lien lui-même ;
c'est plus fort et moins contestable.

- Hauteur ~22 px, coins arrondis, fond légèrement teinté, texte 12 px
- **Trois maximum par équipe**
- Couleurs sémantiques, jamais l'accent

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

Cinq carrés de 8 à 10 px, arrondis, verts ou rouges, du plus ancien au plus récent, sans texte.
Alimenté par le bilan V-D récent déjà exposé (`home_team_recent_record`).

**Accompagné d'un libellé accessible** : cinq carrés colorés sans texte portent l'information par la
seule couleur, ce que la §12 interdit. Un attribut de description lisible par lecteur d'écran suffit.

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
| A | **Le seuil de fiabilité haute doit-il être exposé au frontend public ?** L'échelle de la jauge (§10.1) en dépend. Voir ci-dessous. | à trancher |
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
