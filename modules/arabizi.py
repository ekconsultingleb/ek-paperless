# ============================================================
# modules/arabizi.py
# Lebanese Arabizi / Arabic → English kitchen dictionary
#
# HOW TO ADD MORE TERMS:
#   Just add a new line inside the relevant section below:
#   "arabizi_word": "english_word",
#
# HOW TO USE IN ANY MODULE:
#   from modules.arabizi import arabizi_translate
#   terms = arabizi_translate("meleh")   # → ["salt"]
#   terms = arabizi_translate("mel")     # → ["salt"]  (prefix match)
# ============================================================

ARABIZI: dict[str, str] = {

    # ── Basics ───────────────────────────────────────────────
    "meleh":        "salt",
    "mileh":        "salt",
    "mel7":         "salt",
    "sukkar":       "sugar",
    "sakkar":       "sugar",
    "s5kar":        "sugar",
    "miyeh":         "water",
    "mai":          "water",
    "zeit":         "oil",
    "zayt":         "oil",
    "zeit zeitoun": "olive oil",
    "zayt zaytoun": "olive oil",
    "khall":        "vinegar",
    "5all":         "vinegar",
    "zibde":        "butter",
    "zebde":        "butter",
    "haleeb":       "milk",
    "halib":        "milk",
    "bayd":         "egg",
    "bed":          "egg",
    "beid":         "egg",

    # ── Proteins ─────────────────────────────────────────────
    "lahme":        "meat",
    "la7me":        "meat",
    "dajaj":        "chicken",
    "djej":         "chicken",
    "jaj":          "chicken",
    "samak":        "fish",
    "samake":       "fish",
    "kreydes":      "shrimp",
    "kraydes":      "shrimp",
    "kreydess":     "shrimp",
    "kafta":        "kafta",
    "kefta":        "kefta",
    "jawaneh":      "wings",
    "jwene":        "wings",
    "sawda":        "liver",
    "kibde":        "liver",
    "kibda":        "liver",
    "makanek":      "makanek",
    "mkanak":       "makanek",
    "sujuk":        "soujouk",
    "soujok":       "soujouk",
    "sojok":        "soujouk",
    "awarma":       "kawarma",

    # ── Vegetables ───────────────────────────────────────────
    "batata":       "potato",
    "bata7a":       "potato",
    "basal":        "onion",
    "bassall":      "onion",
    "toum":         "garlic",
    "toom":         "garlic",
    "thoum":        "garlic",
    "banadoura":    "tomato",
    "banadoure":    "tomato",
    "tomata":       "tomato",
    "khyar":        "cucumber",
    "5yar":         "cucumber",
    "kousa":        "zucchini",
    "kusa":         "zucchini",
    "batenjan":     "eggplant",
    "batinjan":     "eggplant",
    "arnabeet":     "cauliflower",
    "arnabit":      "cauliflower",
    "malfoof":      "cabbage",
    "malfouf":      "cabbage",
    "khodra":       "vegetable",
    "5odra":        "vegetable",
    "foul":         "fava",
    "fool":         "fava",
    "fasoulia":     "bean",
    "fazoulia":     "bean",
    "hummos":       "chickpea",
    "hommos":       "chickpea",
    "7ommos":       "chickpea",
    "adas":         "lentil",
    "warak":        "grape leaves",
    "dawali":       "grape leaves",
    "mloukhieh":    "molokhia",
    "meloukhieh":   "molokhia",

    # ── Dairy & Cheese ────────────────────────────────────────
    "jibne":        "cheese",
    "jibneh":       "cheese",
    "labneh":       "labneh",
    "laban":        "yogurt",
    "kishk":        "kishk",
    "keshek":       "kishk",

    # ── Grains & Carbs ────────────────────────────────────────
    "roz":          "rice",
    "khobz":        "bread",
    "aish":         "bread",
    "makaroni":     "pasta",
    "makarone":     "pasta",
    "burghul":      "bulgur",
    "bourgol":      "bulgur",
    "freike":       "freekeh",
    "frike":        "freekeh",

    # ── Herbs & Spices ────────────────────────────────────────
    "zaatar":       "thyme",
    "za3tar":       "thyme",
    "nanaa":        "mint",
    "naanaa":       "mint",
    "na3na3":       "mint",
    "baqdounis":    "parsley",
    "ba2dounis":    "parsley",
    "kazbara":      "coriander",
    "kozbara":      "coriander",
    "kamoun":       "cumin",
    "kammoun":      "cumin",
    "filfil":       "pepper",
    "felfel":       "pepper",
    "bahar":        "allspice",
    "baharat":      "allspice",
    "darseen":      "cinnamon",
    "qerfeh":       "cinnamon",
    "kurkum":       "turmeric",
    "zaafaran":     "saffron",
    "summak":       "sumac",
    "sommak":       "sumac",
    "hal":          "cardamom",
    "hale":         "cardamom",
    "hail":         "cardamom",
    "qaranfol":     "cloves",

    # ── Sauces & Condiments ───────────────────────────────────
    "tahini":       "tahini",
    "tahine":       "tahini",
    "pomme":        "ketchup",
    "ketchup":      "ketchup",
    "mayo":         "mayonnaise",
    "maward":       "rose water",
    "mazaher":      "orange blossom",

    # ── Beverages ─────────────────────────────────────────────
    "ahwe":         "coffee",
    "ahwa":         "coffee",
    "shai":         "tea",
    "shay":         "tea",
    "bira":         "beer",
    "birra":        "beer",
    "arak":         "arak",
    "sharab":       "syrup",

}


def arabizi_translate(query: str) -> list[str]:
    """Translate an Arabizi/Arabic query to a list of English search terms.

    Supports prefix matching — typing 'mel' will match 'meleh' → 'salt'.
    Returns an empty list if no match is found (caller falls back to direct search).
    """
    q = query.strip().lower()
    if not q:
        return []
    matches: set[str] = set()
    for arb, eng in ARABIZI.items():
        if arb == q or arb.startswith(q) or q.startswith(arb):
            matches.add(eng)
    return list(matches)
