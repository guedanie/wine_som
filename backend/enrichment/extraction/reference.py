"""
Cheat sheets for wine-fact extraction. Used both in the Haiku prompt and for
deterministic post-processing (appellation -> parent region).
"""
import re
import unicodedata
from typing import Optional

# Appellation / sub-region -> grouped under its parent region (what we store in wines.region).
APPELLATIONS = {
    "Bordeaux": ["Médoc", "Haut-Médoc", "Margaux", "Pauillac", "Saint-Julien",
                 "Saint-Estèphe", "Listrac-Médoc", "Moulis-en-Médoc", "Pessac-Léognan",
                 "Graves", "Saint-Émilion", "Pomerol", "Lalande-de-Pomerol", "Fronsac",
                 "Canon-Fronsac", "Sauternes", "Barsac", "Entre-Deux-Mers"],
    "Burgundy": ["Chablis", "Gevrey-Chambertin", "Morey-Saint-Denis", "Chambolle-Musigny",
                 "Vougeot", "Vosne-Romanée", "Nuits-Saint-Georges", "Aloxe-Corton",
                 "Pommard", "Volnay", "Meursault", "Puligny-Montrachet",
                 "Chassagne-Montrachet", "Beaune", "Pouilly-Fuissé", "Mâcon"],
    "Rhône": ["Côte-Rôtie", "Condrieu", "Hermitage", "Crozes-Hermitage", "Saint-Joseph",
              "Cornas", "Châteauneuf-du-Pape", "Gigondas", "Vacqueyras", "Côtes du Rhône",
              "Tavel", "Lirac"],
    "Loire": ["Sancerre", "Pouilly-Fumé", "Vouvray", "Chinon", "Bourgueil", "Saumur",
              "Saumur-Champigny", "Muscadet", "Savennières", "Anjou"],
    "Beaujolais": ["Morgon", "Fleurie", "Moulin-à-Vent", "Brouilly", "Côte de Brouilly",
                   "Juliénas", "Chénas", "Chiroubles", "Régnié", "Saint-Amour"],
    "Languedoc": ["Minervois", "Corbières", "Fitou", "Faugères", "Pic Saint-Loup",
                  "Saint-Chinian", "Picpoul de Pinet"],
    "Provence": ["Bandol", "Côtes de Provence", "Cassis", "Bellet"],
    "Southwest France": ["Cahors", "Madiran", "Bergerac", "Jurançon"],
    "Tuscany": ["Chianti", "Chianti Classico", "Brunello di Montalcino",
                "Rosso di Montalcino", "Vino Nobile di Montepulciano", "Bolgheri",
                "Carmignano", "Morellino di Scansano"],
    "Piedmont": ["Barolo", "Barbaresco", "Barbera d'Alba", "Barbera d'Asti",
                 "Dolcetto d'Alba", "Langhe", "Gavi", "Roero", "Nebbiolo d'Alba"],
    "Veneto": ["Valpolicella", "Amarone della Valpolicella", "Soave", "Bardolino",
               "Prosecco", "Ripasso"],
    "Other Italy": ["Franciacorta", "Etna", "Taurasi", "Montepulciano d'Abruzzo",
                    "Primitivo di Manduria", "Vermentino di Sardegna"],
    "Rioja": ["Rioja Alta", "Rioja Alavesa", "Rioja Oriental", "Rioja Baja"],
    "Other Spain": ["Ribera del Duero", "Priorat", "Rías Baixas", "Rueda", "Toro",
                    "Jumilla", "Penedès", "Cava", "Montsant"],
    "Douro": ["Douro", "Port"],
    "Other Portugal": ["Dão", "Alentejo", "Vinho Verde", "Bairrada"],
    "Napa Valley": ["Oakville", "Rutherford", "Stags Leap District", "Howell Mountain",
                    "Mount Veeder", "Spring Mountain", "Diamond Mountain", "Calistoga",
                    "St. Helena", "Carneros", "Atlas Peak", "Coombsville", "Yountville",
                    "Oak Knoll"],
    "Sonoma": ["Russian River Valley", "Alexander Valley", "Dry Creek Valley",
               "Sonoma Coast", "Knights Valley", "Chalk Hill", "Bennett Valley",
               "Sonoma Valley", "Fountaingrove", "Rockpile"],
    "Central Coast": ["Paso Robles", "Santa Maria Valley", "Sta. Rita Hills",
                      "Ballard Canyon", "Edna Valley", "Arroyo Grande", "Monterey",
                      "Santa Lucia Highlands"],
    "Other California": ["Lodi", "Mendocino", "Sierra Foothills", "Livermore Valley",
                         "Santa Cruz Mountains", "Anderson Valley", "Clarksburg"],
    "Willamette Valley": ["Dundee Hills", "Eola-Amity Hills", "Ribbon Ridge",
                          "Yamhill-Carlton", "Chehalem Mountains", "McMinnville"],
    "Columbia Valley": ["Walla Walla Valley", "Yakima Valley", "Red Mountain",
                        "Horse Heaven Hills", "Wahluke Slope"],
    "Texas": ["Texas Hill Country", "Texas High Plains"],
    "Mendoza": ["Uco Valley", "Luján de Cuyo", "Maipú"],
    "Other Argentina": ["Cafayate", "Salta", "Patagonia"],
    "Chile": ["Maipo Valley", "Colchagua Valley", "Casablanca Valley", "Aconcagua",
              "Maule Valley", "Limarí Valley"],
    "Barossa Valley": ["Eden Valley"],
    "Other Australia": ["McLaren Vale", "Coonawarra", "Clare Valley", "Margaret River",
                        "Yarra Valley", "Hunter Valley"],
    "Marlborough": [],
    "Other New Zealand": ["Central Otago", "Hawke's Bay", "Martinborough"],
    "Germany": ["Mosel", "Rheingau", "Pfalz", "Rheinhessen", "Nahe"],
    "South Africa": ["Stellenbosch", "Swartland", "Franschhoek", "Paarl", "Constantia"],
}

CORE_GRAPES = {
    "red": ["Cabernet Sauvignon", "Merlot", "Pinot Noir", "Syrah", "Shiraz", "Malbec",
            "Grenache", "Garnacha", "Tempranillo", "Sangiovese", "Nebbiolo", "Zinfandel",
            "Primitivo", "Cabernet Franc", "Petit Verdot", "Petite Sirah", "Mourvèdre",
            "Monastrell", "Carmenère", "Gamay", "Barbera", "Dolcetto", "Montepulciano",
            "Nero d'Avola", "Touriga Nacional", "Tannat", "Cinsault", "Carignan",
            "Aglianico", "Corvina", "Pinotage"],
    "white": ["Chardonnay", "Sauvignon Blanc", "Riesling", "Pinot Grigio", "Pinot Gris",
              "Chenin Blanc", "Viognier", "Gewürztraminer", "Albariño", "Grüner Veltliner",
              "Sémillon", "Vermentino", "Torrontés", "Moscato", "Muscat", "Marsanne",
              "Roussanne", "Verdejo", "Garganega", "Trebbiano", "Cortese",
              "Melon de Bourgogne", "Fiano", "Greco", "Assyrtiko", "Furmint"],
    "rose": ["Grenache", "Cinsault", "Mourvèdre", "Pinot Noir", "Syrah", "Tempranillo",
             "Sangiovese"],
}

# (name, description) -> expected extracted dict. Seeds the prompt's few-shot section.
FEW_SHOT = [
    ("Decoy Cabernet Sauvignon California Red Wine",
     "Rich Californian red with dark cherry and supple tannins. ABV: 14.5%",
     {"region": "California", "sub_region": None, "country": "US", "vintage_year": None,
      "varietal": "Cabernet Sauvignon", "grapes": ["Cabernet Sauvignon"], "abv": 14.5,
      "body": "full"}),
    ("Château du Cauze Saint-Émilion Grand Cru 2019", "",
     {"region": "Bordeaux", "sub_region": "Saint-Émilion", "country": "France",
      "vintage_year": 2019, "varietal": "Merlot", "grapes": ["Merlot", "Cabernet Franc"],
      "abv": None, "body": "full"}),
    ("Les Lunes Rouge 2021", "A fresh, low-tannin red blend from Mendocino.",
     {"region": "Mendocino", "sub_region": None, "country": "US", "vintage_year": 2021,
      "varietal": "Red Blend", "grapes": [], "abv": None, "body": "medium"}),
    ("Whitehaven Sauvignon Blanc New Zealand White Wine",
     "Zesty Marlborough white, grapefruit and passionfruit.",
     {"region": "Marlborough", "sub_region": None, "country": "New Zealand",
      "vintage_year": None, "varietal": "Sauvignon Blanc", "grapes": ["Sauvignon Blanc"],
      "abv": None, "body": "light"}),
]


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(ch for ch in s if not unicodedata.combining(ch))  # strip accents
    return re.sub(r"\s+", " ", s).strip().lower()


# Inverted index: normalized appellation -> parent region
_APPELLATION_INDEX = {}
for _region, _apps in APPELLATIONS.items():
    for _app in _apps:
        _APPELLATION_INDEX[_norm(_app)] = _region


def parent_region_for(appellation: Optional[str]) -> Optional[str]:
    """Return the parent region for an appellation (case/accent-insensitive), else None."""
    if not appellation:
        return None
    return _APPELLATION_INDEX.get(_norm(appellation))
