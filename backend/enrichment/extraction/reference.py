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
                 "Canon-Fronsac", "Sauternes", "Barsac", "Entre-Deux-Mers", "Listrac",
                 "Côtes de Francs", "Francs Côtes de Bordeaux",
                 "Castillon Côtes de Bordeaux", "Côtes de Castillon",
                 "Blaye Côtes de Bordeaux", "Côtes de Blaye", "Côtes de Bourg",
                 "Cadillac", "Loupiac", "Sainte-Croix-du-Mont",
                 "Lussac-Saint-Émilion", "Montagne-Saint-Émilion",
                 "Puisseguin-Saint-Émilion"],
    "Burgundy": ["Chablis", "Gevrey-Chambertin", "Morey-Saint-Denis", "Chambolle-Musigny",
                 "Vougeot", "Vosne-Romanée", "Nuits-Saint-Georges", "Aloxe-Corton",
                 "Pommard", "Volnay", "Meursault", "Puligny-Montrachet",
                 "Chassagne-Montrachet", "Beaune", "Pouilly-Fuissé", "Mâcon",
                 "Santenay", "Marsannay", "Fixin", "Savigny-lès-Beaune",
                 "Pernand-Vergelesses", "Ladoix", "Auxey-Duresses", "Monthelie",
                 "Saint-Aubin", "Saint-Romain", "Rully", "Mercurey", "Givry",
                 "Montagny", "Corton", "Corton-Charlemagne", "Montrachet",
                 "Côte de Nuits-Villages", "Côte de Beaune-Villages",
                 "Mâcon-Villages", "Saint-Véran", "Viré-Clessé"],
    "Rhône": ["Côte-Rôtie", "Condrieu", "Hermitage", "Crozes-Hermitage", "Saint-Joseph",
              "Cornas", "Châteauneuf-du-Pape", "Gigondas", "Vacqueyras", "Côtes du Rhône",
              "Côtes du Rhône Villages", "Tavel", "Lirac", "Ventoux", "Luberon",
              "Cairanne", "Rasteau", "Séguret", "Sablet", "Visan", "Valréas",
              "Plan de Dieu", "Beaumes-de-Venise", "Costières de Nîmes",
              "Saint-Péray", "Grignan-les-Adhémar", "Vinsobres"],
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
                      "Santa Rita Hills",
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
    s = s.replace("-", " ")   # hyphen/space spelling variants resolve identically
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
    "rhone": "Rhône", "rhone valley": "Rhône", "cotes du rhone": "Rhône", "cote du rhone": "Rhône",
    "southern rhone": "Rhône", "northern rhone": "Rhône",
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


# ── Château / producer gazetteer ─────────────────────────────────────────────
# Producer names carry the place signal a 7B model can't reliably use — and
# hallucinates around (Merlot → "Bordeaux"). Matched DETERMINISTICALLY against
# the wine's name+description; a hit overrides the model. Curated: classified
# growths + crus bourgeois + brands common in TX/TN/NC retail. The prompt gets
# only the famous subset (_CHATEAUX_PROMPT_LIMIT) to keep token cost sane.

CHATEAUX = {
    "Pauillac": ["Lafite Rothschild", "Mouton Rothschild", "Latour",
                 "Pichon Baron", "Pichon Longueville", "Pichon Lalande",
                 "Lynch-Bages", "Pontet-Canet", "Duhart-Milon", "Clerc Milon",
                 "d'Armailhac", "Grand-Puy-Lacoste", "Haut-Batailley", "Batailley",
                 "Croizet-Bages", "Haut-Bages Libéral"],
    "Margaux": ["Palmer", "Brane-Cantenac", "Rauzan-Ségla", "Rauzan-Gassies",
                "Giscours", "Malescot St. Exupéry", "Cantenac Brown", "Kirwan",
                "d'Issan", "Lascombes", "Prieuré-Lichine", "du Tertre",
                "Marquis de Terme", "Labégorce", "Siran", "Angludet"],
    "Saint-Julien": ["Léoville Las Cases", "Léoville Barton", "Léoville Poyferré",
                     "Ducru-Beaucaillou", "Beychevelle", "Talbot", "Gruaud Larose",
                     "Branaire-Ducru", "Lagrange", "Langoa Barton", "Gloria",
                     "Saint-Pierre"],
    "Saint-Estèphe": ["Cos d'Estournel", "Montrose", "Calon-Ségur", "Lafon-Rochet",
                      "Cos Labory", "Phélan Ségur", "Ormes de Pez", "de Pez",
                      "Meyney", "Le Crock", "Capbern"],
    "Haut-Médoc": ["La Lagune", "Cantemerle", "La Tour Carnet", "Belgrave",
                   "Camensac", "Sociando-Mallet", "Citran", "Coufran",
                   "Larose-Trintaudon", "Cambon la Pelouse", "Beaumont"],
    "Médoc": ["Greysac", "Potensac", "La Cardonne", "Rollan de By", "Tour Haut-Caussan",
              "Loudenne", "Patache d'Aux", "Goulée"],
    "Moulis-en-Médoc": ["Chasse-Spleen", "Poujeaux", "Maucaillou"],
    "Pessac-Léognan": ["Haut-Brion", "La Mission Haut-Brion", "Pape Clément",
                       "Smith Haut Lafitte", "Haut-Bailly", "Domaine de Chevalier",
                       "Carbonnieux", "de Fieuzal", "Malartic-Lagravière",
                       "Latour-Martillac", "Larrivet Haut-Brion", "Les Carmes Haut-Brion"],
    "Saint-Émilion": ["Cheval Blanc", "Ausone", "Angélus", "Pavie", "Figeac",
                      "Canon la Gaffelière", "Troplong Mondot", "Valandraud",
                      "Beau-Séjour Bécot", "Beauséjour", "La Gaffelière",
                      "Larcis Ducasse", "Monbousquet", "Fombrauge", "Simard",
                      "Quinault l'Enclos", "Grand Mayne", "La Dominique"],
    "Pomerol": ["Pétrus", "Le Pin", "La Conseillante", "L'Évangile", "L'Eglise-Clinet",
                "Trotanoy", "Vieux Château Certan", "Clinet", "Gazin", "La Pointe",
                "Beauregard", "Bonalgue", "Petit-Village", "Nénin", "de Sales"],
    "Sauternes": ["d'Yquem", "Climens", "Coutet", "Suduiraut", "Guiraud",
                  "Rieussec", "La Tour Blanche", "Doisy-Védrines", "Doisy-Daëne",
                  "Lafaurie-Peyraguey", "Rayne Vigneau"],
}

# Producer/brand -> (region, country). For names that place a wine without any
# appellation word — the exact class that produced the Requingua/"Bordeaux" bug.
PRODUCERS = {
    # Bordeaux négociant brands (region only, no appellation)
    "Mouton Cadet": ("Bordeaux", "France"),
    "Michel Lynch": ("Bordeaux", "France"),
    "Dourthe": ("Bordeaux", "France"),
    # Rhône houses
    "Guigal": ("Rhône", "France"),
    "Chapoutier": ("Rhône", "France"),
    "Jaboulet": ("Rhône", "France"),
    "Vidal-Fleury": ("Rhône", "France"),
    "La Vieille Ferme": ("Rhône", "France"),
    "Famille Perrin": ("Rhône", "France"),
    "Beaucastel": ("Rhône", "France"),
    "Saint Cosme": ("Rhône", "France"),
    "Ferraton": ("Rhône", "France"),
    "Delas": ("Rhône", "France"),
    "Pegau": ("Rhône", "France"),
    "Montmirail": ("Rhône", "France"),
    # Chile
    "Viña Requingua": ("Curicó Valley", "Chile"),
    "Vina Requingua": ("Curicó Valley", "Chile"),
    "Puerto Viejo": ("Curicó Valley", "Chile"),
    "Concha y Toro": ("Central Valley", "Chile"),
    "Casillero del Diablo": ("Central Valley", "Chile"),
    "Santa Rita": ("Maipo Valley", "Chile"),
    "Cousiño-Macul": ("Maipo Valley", "Chile"),
    "Los Vascos": ("Colchagua Valley", "Chile"),
    "Montes": ("Colchagua Valley", "Chile"),
    # Producers whose names contain a Bordeaux château word —
    # longest-match-first makes these win over the château entry
    # ("Latour", "Gloria").
    "Louis Latour": ("Burgundy", "France"),
    "Beaulieu Vineyard": ("Napa Valley", "United States"),
    "Georges de Latour": ("Napa Valley", "United States"),
    "Gloria Ferrer": ("Sonoma", "United States"),
    # Argentina / Spain
    "Trapiche": ("Mendoza", "Argentina"),
    "Campo Viejo": ("Rioja", "Spain"),
    "Marqués de Cáceres": ("Rioja", "Spain"),
    "Marques de Caceres": ("Rioja", "Spain"),
}

# Appellation law → default blend when the model returned no grapes.
# Order matters: first grape becomes the varietal. Each rule carries the
# colors the blend is valid for; it fires when the caller's wine_type is in
# them, or when wine_type is unknown (None) AND the appellation is
# single-color (requires_type=False). Multi-color appellations (Graves,
# Pessac-Léognan, …) never fire on an unknown type.
_BDX_LEFT   = ("Cabernet Sauvignon", "Merlot", "Cabernet Franc")
_BDX_RIGHT  = ("Merlot", "Cabernet Franc", "Cabernet Sauvignon")
_BDX_WHITE  = ("Sauvignon Blanc", "Sémillon")
_GSM_BLEND  = ("Grenache", "Syrah", "Mourvèdre")
_SAUT_WHITE = ("Sémillon", "Sauvignon Blanc")

# (appellations, grapes, wine_types the blend may fill, requires_type)
_DEFAULT_RULES = [
    (("Médoc", "Haut-Médoc", "Margaux", "Pauillac", "Saint-Julien",
      "Saint-Estèphe", "Listrac-Médoc", "Listrac", "Moulis-en-Médoc"),
     _BDX_LEFT, ("red",), False),
    (("Pessac-Léognan", "Graves"), _BDX_LEFT, ("red",), True),
    (("Pessac-Léognan", "Graves"), _BDX_WHITE, ("white",), True),
    (("Saint-Émilion", "Pomerol", "Lalande-de-Pomerol", "Fronsac",
      "Canon-Fronsac"), _BDX_RIGHT, ("red",), False),
    (("Châteauneuf-du-Pape", "Gigondas", "Vacqueyras", "Côtes du Rhône"),
     _GSM_BLEND, ("red",), False),
    (("Sauternes", "Barsac"), _SAUT_WHITE, ("white", "dessert"), False),
    # right-bank satellites, Grand Cru label, Castillon/Francs/Blaye/Bourg
    (("Saint-Émilion Grand Cru", "Lussac-Saint-Émilion",
      "Montagne-Saint-Émilion", "Puisseguin-Saint-Émilion",
      "Castillon", "Castillon Côtes de Bordeaux", "Côtes de Castillon",
      "Côtes de Francs", "Francs Côtes de Bordeaux",
      "Blaye Côtes de Bordeaux", "Côtes de Blaye", "Côtes de Bourg",
      "Bordeaux Supérieur"), _BDX_RIGHT, ("red",), False),
    # umbrella Côtes de Bordeaux bottles whites too — explicit type only
    (("Côtes de Bordeaux",), _BDX_RIGHT, ("red",), True),
    # Bordeaux whites
    (("Entre-Deux-Mers",), _BDX_WHITE, ("white",), False),
    (("Cadillac", "Loupiac", "Sainte-Croix-du-Mont"),
     _SAUT_WHITE, ("white", "dessert"), False),
    # northern Rhône: red-only crus vs dual-color crus
    (("Côte-Rôtie", "Cornas"), ("Syrah",), ("red",), False),
    (("Hermitage", "Crozes-Hermitage", "Saint-Joseph"),
     ("Syrah",), ("red",), True),
    (("Hermitage", "Crozes-Hermitage", "Saint-Joseph"),
     ("Marsanne", "Roussanne"), ("white",), True),
    (("Condrieu",), ("Viognier",), ("white",), False),
    (("Tavel",), ("Grenache",), ("rose",), False),
    # southern-Rhône satellites + the singular 'Côte du Rhône' prod variant
    (("Côtes du Rhône Villages", "Côte du Rhône", "Ventoux", "Cairanne",
      "Rasteau", "Vinsobres"), _GSM_BLEND, ("red",), False),
]

_APPELLATION_DEFAULTS = {}
for _apps, _grapes, _colors, _req in _DEFAULT_RULES:
    for _a in _apps:
        _APPELLATION_DEFAULTS.setdefault(_norm(_a), []).append((_grapes, _colors, _req))


def default_grapes_for(appellation, wine_type=None) -> Optional[list]:
    """Appellation-law default blend, gated by wine color ('rosé' folds to
    'rose' via _norm). Unknown wine_type fires only single-color appellations;
    a known wine_type must be among the rule's colors."""
    if not appellation:
        return None
    rules = _APPELLATION_DEFAULTS.get(_norm(appellation))
    if not rules:
        return None
    wt = _norm(wine_type) if wine_type else None
    for grapes, colors, requires_type in rules:
        if (wt in colors) or (wt is None and not requires_type):
            return list(grapes)
    return None


# Longest-match-first index over château + producer names, normalized.
# The third element marks château entries — single-word château needles
# ("Latour", "Gloria", "Beauregard") collide with unrelated producers and
# only fire when preceded by a Chateau word.
_GAZETTEER_INDEX = []
for _app, _names in CHATEAUX.items():
    for _n in _names:
        _GAZETTEER_INDEX.append((_norm(_n), {"sub_region": _app, "region": "Bordeaux",
                                             "country": "France"}, True))
for _name, (_region, _country) in PRODUCERS.items():
    _GAZETTEER_INDEX.append((_norm(_name), {"sub_region": None, "region": _region,
                                            "country": _country}, False))
_GAZETTEER_INDEX.sort(key=lambda t: len(t[0]), reverse=True)   # longest match wins


def _fold(s: str) -> str:
    """Normalize for matching: accents stripped, lowercased, punctuation →
    space, retail 'St.'/'Ste.' abbreviations → 'saint'/'sainte' (applied to
    both needles and haystacks, so matching stays symmetric)."""
    out = re.sub(r"[^a-z0-9]+", " ", _norm(s)).strip()
    out = re.sub(r"\bst\b", "saint", out)
    return re.sub(r"\bste\b", "sainte", out)


# Flat appellation index for the conflict guard: fold(appellation) → parent region.
_APPELLATION_PARENT = []
for _reg, _apps in APPELLATIONS.items():
    for _app in _apps:
        _APPELLATION_PARENT.append((re.sub(r"[^a-z0-9]+", " ", _norm(_app)).strip(), _app, _reg))

# Region names + aliases as conflict evidence: fold(name) → canonical region
# (normalized). Umbrella terms (countries-as-regions, state-wide) are excluded —
# 'Chile' in the text must not conflict with a narrower Chilean valley hit.
_UMBRELLA_REGIONS = {"california", "oregon", "washington", "texas",
                     "chile", "argentina", "australia", "new zealand",
                     "germany", "south africa"}
_REGION_EVIDENCE = []
for _r in REGION_COUNTRY:
    if _r not in _UMBRELLA_REGIONS and not _r.startswith("other "):
        _REGION_EVIDENCE.append((re.sub(r"[^a-z0-9]+", " ", _r).strip(), _r))
for _alias, _canon in REGION_ALIASES.items():
    _REGION_EVIDENCE.append(
        (re.sub(r"[^a-z0-9]+", " ", _norm(_alias)).strip(), _norm(_canon)))


def gazetteer_hit(source_text: Optional[str]) -> Optional[dict]:
    """Deterministic place fix from a producer/château name in the wine's
    name+description. Longest match wins ('Latour-Martillac' before 'Latour').

    Conflict guard: an appellation explicitly named in the text beats the
    needle — several châteaux share names across appellations ('Chateau Saint
    Pierre Pomerol' is not the Saint-Julien one) and producer brands hide
    inside place names ('Santa Rita' inside 'Santa Rita Hills'). When any
    explicit appellation disagrees with the hit, return None and let the
    evidence gate keep the text-supported place."""
    if not source_text:
        return None
    hay = f" {_fold(source_text)} "
    for needle, place, is_chateau in _GAZETTEER_INDEX:
        nf = _fold(needle)
        if is_chateau and " " not in nf:
            matched = any(f" {p} {nf} " in hay for p in ("chateau", "ch", "chat"))
        else:
            matched = f" {nf} " in hay
        if matched:
            hit_sub = place.get("sub_region")
            for app_fold, _app, parent in _APPELLATION_PARENT:
                if f" {app_fold} " not in hay:
                    continue
                consistent = (
                    (hit_sub and app_fold == _fold(hit_sub))
                    or (not hit_sub and parent == place.get("region"))
                )
                if not consistent:
                    return None
            hit_region_norm = _norm(place.get("region") or "")
            for reg_fold, canon_norm in _REGION_EVIDENCE:
                if f" {reg_fold} " in hay and canon_norm != hit_region_norm:
                    return None
            return dict(place)
    return None


def region_evidenced(region: Optional[str], source_text: str) -> bool:
    """Does the source text actually support this region? True when the region
    name, one of its appellations, an alias, or a distinctive token of the
    region name appears. A grape name alone NEVER evidences a region."""
    if not region:
        return False
    hay = f" {_fold(source_text)} "
    reg_fold = _fold(region)
    if f" {reg_fold} " in hay:
        return True
    # retail shorthand: 'CdR' / 'CdR Villages' = Côtes du Rhône; 'Bdx' = Bordeaux
    if region == "Rhône" and " cdr " in hay:
        return True
    if region == "Bordeaux" and " bdx " in hay:
        return True
    # aliases that canonicalize to this region ("Rhone Valley" → Rhône)
    for alias, canon in REGION_ALIASES.items():
        if canon == region and f" {_fold(alias)} " in hay:
            return True
    # any of the region's appellations
    for app in APPELLATIONS.get(region, []):
        if f" {_fold(app)} " in hay:
            return True
    # distinctive token of a multiword region ("Willamette" for Willamette Valley)
    _GENERIC = {"valley", "coast", "hills", "hill", "mountains", "mountain",
                "county", "central", "other", "southern", "northern", "new",
                "creek", "river"}
    for tok in reg_fold.split():
        if len(tok) >= 4 and tok not in _GENERIC and (
            f" {tok} " in hay or f" {tok}s " in hay   # 'Cotes du Rhones' plural typo
        ):
            return True
    return False


def country_evidenced(country: Optional[str], source_text: str) -> bool:
    if not country:
        return False
    hay = f" {_fold(source_text)} "
    if f" {_fold(country)} " in hay:
        return True
    # adjectival forms common on labels ("Portuguese", "Chilean", "French"…)
    _ADJ = {"France": "french", "Italy": "italian", "Spain": "spanish",
            "Portugal": "portuguese", "Chile": "chilean", "Argentina": "argentine",
            "Germany": "german", "Australia": "australian",
            "New Zealand": "new zealand", "United States": "american",
            "South Africa": "south african"}
    adj = _ADJ.get(country)
    return bool(adj and f" {adj} " in hay)
