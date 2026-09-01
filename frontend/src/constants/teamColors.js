// Couleurs officielles des équipes NBA (docs/design-v1.md §5.7). Axe
// INDÉPENDANT du mode clair/sombre et de l'accent -- ni l'un ni l'autre ne
// doit les altérer, et elles n'altèrent ni l'un ni l'autre (le filet posé
// dans GameCard.vue est un troisième axe, pas une variante de l'accent).
//
// Décision explicite (2026-08-31) : PAS de logo NBA, sous aucune forme --
// marque déposée, et l'usage sur un produit lié aux paris est le cas le
// plus exposé. La couleur brute + le tricode (déjà affiché partout)
// suffisent à porter une identité d'équipe reconnaissable sans reproduire
// un actif protégé. Voir §5.7 pour le raisonnement complet.
//
// Une SEULE valeur stockée par équipe (la teinte officielle brute, telle
// que couramment publiée) : la règle de contraste
// (utils/teamColorContrast.js) dérive à l'exécution les variantes
// réellement lisibles par mode -- jamais une seconde valeur saisie à la
// main par équipe/par mode.
//
// Valeurs de notoriété publique (teinte de marque telle que largement
// documentée), pas extraites d'un actif officiel NBA -- une précision
// Pantone/RGB exacte n'est pas l'objet de cette étape (valider la FORME du
// traitement, §5.7) ; à affiner si besoin au moment d'étendre aux 24
// équipes restantes.
//
// Périmètre volontairement réduit aux 6 équipes de la base de
// développement (scripts/seed_dev_data.py::create_dashboard_demo_slate) :
// couvre déjà les cas difficiles (teintes très sombres, rouges proches,
// identités bien distinctes) sans étendre une forme pas encore validée à
// l'œil. Une équipe absente de cette table n'affiche simplement aucun
// filet (voir utils/teamColors.js::teamRailColor) -- dégradation
// silencieuse, pas une erreur, le temps que les 24 autres soient ajoutées.
export const TEAM_COLORS = {
  BOS: '#007A33', // Boston Celtics -- vert
  DET: '#002D62', // Detroit Pistons -- bleu très sombre
  CHA: '#1D1160', // Charlotte Hornets -- violet très sombre
  CHI: '#CE1141', // Chicago Bulls -- rouge
  MIA: '#98002E', // Miami Heat -- rouge (proche de CHI, plus sombre)
  DEN: '#0E2240', // Denver Nuggets -- bleu marine
}
