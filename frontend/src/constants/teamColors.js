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
// DEUX valeurs par équipe depuis le 2026-09-02 (primaire + secondaire) :
// la secondaire sert UNIQUEMENT de repli pour l'équipe extérieure quand sa
// primaire entre en collision perceptuelle avec la primaire du domicile
// (utils/teamColorCollision.js) -- jamais utilisée par défaut. Valeurs de
// notoriété publique (teinte de marque telle que largement documentée),
// pas extraites d'un actif officiel NBA -- une précision Pantone/RGB exacte
// n'est pas l'objet de cette étape ; à affiner si besoin en étendant aux 24
// équipes restantes.
//
// Périmètre volontairement réduit aux 6 équipes de la base de
// développement (scripts/seed_dev_data.py::create_dashboard_demo_slate) :
// couvre déjà les cas difficiles (teintes très sombres, rouges proches,
// identités bien distinctes) sans étendre une forme pas encore validée à
// l'œil. Une équipe absente de cette table n'affiche simplement aucun
// badge (dégradation silencieuse, voir utils/teamColors.js::resolveTeamBadges)
// -- pas une erreur, le temps que les 24 autres soient ajoutées.
export const TEAM_COLORS = {
  BOS: { primary: '#007A33', secondary: '#BA9653' }, // Celtics -- vert / or
  DET: { primary: '#002D62', secondary: '#C8102E' }, // Pistons -- bleu très sombre / rouge
  CHA: { primary: '#1D1160', secondary: '#00788C' }, // Hornets -- violet très sombre / sarcelle
  CHI: { primary: '#CE1141', secondary: '#000000' }, // Bulls -- rouge / noir
  MIA: { primary: '#98002E', secondary: '#000000' }, // Heat -- rouge sombre / noir
  DEN: { primary: '#0E2240', secondary: '#FEC524' }, // Nuggets -- bleu marine / or
}
