// Couleurs officielles des équipes NBA (docs/design-v1.md §5.7). Axe
// INDÉPENDANT du mode clair/sombre et de l'accent -- ni l'un ni l'autre ne
// doit les altérer, et elles n'altèrent ni l'un ni l'autre.
//
// Décision explicite : PAS de logo NBA, sous aucune forme -- marque
// déposée, et l'usage sur un produit lié aux paris est le cas le plus
// exposé. Le monogramme (`GameCard.vue`, tricode dans un badge teinté) et
// la couleur seule suffisent à porter une identité reconnaissable sans
// reproduire un actif protégé.
//
// DEUX valeurs par équipe (primaire + secondaire) : la secondaire sert
// UNIQUEMENT de repli pour l'équipe extérieure quand sa primaire entre en
// collision perceptuelle avec la primaire du domicile
// (utils/teamColorCollision.js, seuil 0,03 depuis le 2026-09-02) -- jamais
// utilisée par défaut. Valeurs de notoriété publique (teinte de marque
// telle que largement documentée), pas extraites d'un actif officiel NBA --
// une précision Pantone/RGB exacte n'est pas l'objet de ce chantier.
//
// Table étendue aux 30 équipes le 2026-09-02, après validation de la forme
// sur les 6 équipes de la base de développement (BOS/DET/CHA/CHI/MIA/DEN,
// scripts/seed_dev_data.py::create_dashboard_demo_slate) -- extension
// mécanique une fois la règle (OKLCH + collision) arrêtée, voir §5.7 pour
// le contraste texte mesuré sur les 30 badges et la liste des collisions
// recalculée sur la table complète.
//
// San Antonio (SAS) : primaire = ARGENT (`#C4CED4`, pas le noir officiel
// pourtant aussi porté par la franchise) -- décision actée le 2026-09-02
// (§5.7) : le noir pur, chroma nulle par construction, devient un gris sans
// aucun axe de séparation une fois éclairci pour le contraste. L'argent
// est une vraie couleur de la franchise (pas inventée), déjà conforme au
// contraste sans le moindre ajustement.
export const TEAM_COLORS = {
  ATL: { primary: '#E03A3E', secondary: '#26282A' }, // Hawks -- rouge / anthracite
  BOS: { primary: '#007A33', secondary: '#BA9653' }, // Celtics -- vert / or
  BKN: { primary: '#000000', secondary: '#FFFFFF' }, // Nets -- noir / blanc
  CHA: { primary: '#1D1160', secondary: '#00788C' }, // Hornets -- violet très sombre / sarcelle
  CHI: { primary: '#CE1141', secondary: '#000000' }, // Bulls -- rouge / noir
  CLE: { primary: '#860038', secondary: '#FDBB30' }, // Cavaliers -- bordeaux / or
  DAL: { primary: '#00538C', secondary: '#B8C4CA' }, // Mavericks -- bleu / argent
  DEN: { primary: '#0E2240', secondary: '#FEC524' }, // Nuggets -- bleu marine / or
  DET: { primary: '#002D62', secondary: '#C8102E' }, // Pistons -- bleu très sombre / rouge
  GSW: { primary: '#1D428A', secondary: '#FFC72C' }, // Warriors -- bleu / or
  HOU: { primary: '#CE1141', secondary: '#000000' }, // Rockets -- rouge / noir
  IND: { primary: '#002D62', secondary: '#FDBB30' }, // Pacers -- bleu marine / or
  LAC: { primary: '#C8102E', secondary: '#1D428A' }, // Clippers -- rouge / bleu
  LAL: { primary: '#552583', secondary: '#FDB927' }, // Lakers -- violet / or
  MEM: { primary: '#5D76A9', secondary: '#F5B112' }, // Grizzlies -- bleu sourd / or
  MIA: { primary: '#98002E', secondary: '#000000' }, // Heat -- rouge sombre / noir
  MIL: { primary: '#00471B', secondary: '#EEE1C6' }, // Bucks -- vert très sombre / crème
  MIN: { primary: '#0C2340', secondary: '#78BE20' }, // Timberwolves -- bleu marine / vert
  NOP: { primary: '#0C2340', secondary: '#B4975A' }, // Pelicans -- bleu marine / or
  NYK: { primary: '#006BB6', secondary: '#F58426' }, // Knicks -- bleu / orange
  OKC: { primary: '#007AC1', secondary: '#EF3B24' }, // Thunder -- bleu / orange-rouge
  ORL: { primary: '#0077C0', secondary: '#000000' }, // Magic -- bleu / noir
  PHI: { primary: '#006BB6', secondary: '#ED174C' }, // 76ers -- bleu / rouge
  PHX: { primary: '#1D1160', secondary: '#E56020' }, // Suns -- violet très sombre / orange
  POR: { primary: '#E03A3E', secondary: '#000000' }, // Trail Blazers -- rouge / noir
  SAC: { primary: '#5A2D81', secondary: '#63727A' }, // Kings -- violet / gris
  SAS: { primary: '#C4CED4', secondary: '#000000' }, // Spurs -- argent / noir (voir note ci-dessus)
  TOR: { primary: '#CE1141', secondary: '#000000' }, // Raptors -- rouge / noir
  UTA: { primary: '#002B5C', secondary: '#000000' }, // Jazz -- bleu marine très sombre / noir
  WAS: { primary: '#002B5C', secondary: '#E31837' }, // Wizards -- bleu marine très sombre / rouge
}
