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
     {"region": "California", "sub_region": None, "country": "United States", "vintage_year": None,
      "varietal": "Cabernet Sauvignon", "grapes": ["Cabernet Sauvignon"], "abv": 14.5,
      "body": "full"}),
    ("Château du Cauze Saint-Émilion Grand Cru 2019", "",
     {"region": "Bordeaux", "sub_region": "Saint-Émilion", "country": "France",
      "vintage_year": 2019, "varietal": "Merlot", "grapes": ["Merlot", "Cabernet Franc"],
      "abv": None, "body": "full"}),
    ("Les Lunes Rouge 2021", "A fresh, low-tannin red blend from Mendocino.",
     {"region": "Mendocino", "sub_region": None, "country": "United States", "vintage_year": 2021,
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


# ── deterministic normalization (lifts every extractor backend) ──────────────

# Parent region -> country. Keyed by canonical region name (APPELLATIONS keys +
# common broad regions the models emit). Drives country inference when a region
# is known but the country field is missing/inconsistent.
REGION_COUNTRY = {
    # France
    "bordeaux": "France", "burgundy": "France", "rhone": "France", "loire": "France",
    "beaujolais": "France", "languedoc": "France", "provence": "France",
    "southwest france": "France", "champagne": "France", "alsace": "France",
    # Italy
    "tuscany": "Italy", "piedmont": "Italy", "veneto": "Italy", "other italy": "Italy",
    "alto adige": "Italy", "sicily": "Italy", "abruzzo": "Italy", "puglia": "Italy",
    "lombardy": "Italy", "umbria": "Italy", "friuli": "Italy",
    # Spain / Portugal
    "rioja": "Spain", "other spain": "Spain", "ribera del duero": "Spain",
    "priorat": "Spain", "rias baixas": "Spain", "rueda": "Spain",
    "douro": "Portugal", "other portugal": "Portugal",
    # USA
    "napa valley": "United States", "sonoma": "United States",
    "central coast": "United States", "other california": "United States",
    "california": "United States", "willamette valley": "United States",
    "columbia valley": "United States", "oregon": "United States",
    "washington": "United States", "texas": "United States", "paso robles": "United States",
    # Southern hemisphere + Germany + SA
    "mendoza": "Argentina", "other argentina": "Argentina", "argentina": "Argentina",
    "chile": "Chile", "barossa valley": "Australia", "other australia": "Australia",
    "australia": "Australia", "marlborough": "New Zealand",
    "other new zealand": "New Zealand", "new zealand": "New Zealand",
    "germany": "Germany", "mosel": "Germany", "south africa": "South Africa",
}

# Region-name variants (foreign/alt spellings) -> our canonical region name.
REGION_ALIASES = {
    "toscana": "Tuscany", "toskana": "Tuscany",
    "piemonte": "Piedmont", "piedmonte": "Piedmont",
    "rhone valley": "Rhône", "cotes du rhone": "Rhône", "cote du rhone": "Rhône",
    "bourgogne": "Burgundy", "borgogna": "Burgundy",
    "napa": "Napa Valley", "sonoma county": "Sonoma", "sonoma coast": "Sonoma",
    "sud de france": "Languedoc", "south of france": "Languedoc",
    "usa": "California", "u.s.a.": "California",   # only when no finer region given
}

# Grape synonyms -> our canonical varietal spelling.
GRAPE_SYNONYMS = {
    "fume blanc": "Sauvignon Blanc", "fumé blanc": "Sauvignon Blanc",
    "prosecco": "Glera",
    "pinot gris": "Pinot Grigio",
    "shiraz": "Syrah",
    "garnacha": "Grenache",
    "monastrell": "Mourvèdre",
    "primitivo": "Zinfandel",
    "cot": "Malbec", "côt": "Malbec",
    "spatburgunder": "Pinot Noir", "spätburgunder": "Pinot Noir",
    "grauburgunder": "Pinot Grigio",
    "weissburgunder": "Pinot Blanc",
}

# Country-name variants -> canonical.
COUNTRY_ALIASES = {
    "us": "United States", "u.s.": "United States", "usa": "United States",
    "u.s.a.": "United States", "america": "United States", "united states of america": "United States",
    "argentine": "Argentina", "españa": "Spain", "espana": "Spain",
    "italia": "Italy", "deutschland": "Germany",
}


def canonical_region(region: Optional[str]) -> Optional[str]:
    if not region:
        return region
    return REGION_ALIASES.get(_norm(region), region)


def canonical_country(country: Optional[str]) -> Optional[str]:
    if not country:
        return country
    return COUNTRY_ALIASES.get(_norm(country), country)


def canonical_grape(grape: Optional[str]) -> Optional[str]:
    if not grape:
        return grape
    return GRAPE_SYNONYMS.get(_norm(grape), grape)


def country_for_region(region: Optional[str]) -> Optional[str]:
    """Infer country from a (canonicalized) region name, else None."""
    if not region:
        return None
    return REGION_COUNTRY.get(_norm(region))
