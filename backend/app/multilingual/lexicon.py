"""Seed lexicon for Tanglish / Manglish handling.

This is only a bootstrap. The personal dictionary (`lexicon_entries` table, PLAN §7)
grows from the user's own corpus and corrections; these seeds are loaded as global
entries (user_id NULL) by `app.multilingual.tanglish.seed_rows()`.
"""

# canonical romanised form -> (surface variants, native script, gloss)
VARIANT_GROUPS: dict[str, tuple[list[str], str | None, str]] = {
    "seri": (["sari", "serii", "sariya", "seriya", "shari"], "சரி", "okay"),
    "illa": (["ila", "illai", "ille", "illey", "illae"], "இல்லை", "no / not"),
    "aama": (["ama", "aamam", "aamaa", "amam"], "ஆமா", "yes"),
    "enna": (["ena", "yenna", "yena", "enaa"], "என்ன", "what"),
    "eppadi": (["epdi", "eppdi", "yepdi", "epudi"], "எப்படி", "how"),
    "eppo": (["epo", "yeppo", "eppothu", "eppodhu"], "எப்போ", "when"),
    "enga": (["yenga", "engey", "engae"], "எங்க", "where"),
    "inga": (["ingey", "ingae", "inge"], "இங்க", "here"),
    "anga": (["angey", "angae", "ange"], "அங்க", "there"),
    "yen": (["en", "yaen", "ean"], "ஏன்", "why"),
    "naan": (["nan", "naa", "na"], "நான்", "I"),
    "nee": (["ni", "nii"], "நீ", "you"),
    "avan": (["avn"], "அவன்", "he"),
    "aval": (["aval", "ava"], "அவள்", "she"),
    "avanga": (["avunga", "avangal"], "அவங்க", "they"),
    "namma": (["nama", "nammal"], "நம்ம", "our"),
    "kooda": (["kuda", "koda", "koodave", "kudave"], "கூட", "with / together"),
    "semma": (["sema", "semmaya", "semaya"], "செம்ம", "awesome"),
    "romba": (["rombha", "roomba", "rmba"], "ரொம்ப", "very"),
    "konjam": (["konjum", "konjom", "kojam"], "கொஞ்சம்", "a little"),
    "venum": (["venu", "vennum", "vendum"], "வேணும்", "want / need"),
    "vendam": (["venam", "vendaam", "vendaa"], "வேண்டாம்", "don't want"),
    "theriyum": (["theriyu", "teriyum", "therium"], "தெரியும்", "know"),
    "theriyala": (["therila", "theriyadhu", "teriyala", "theriyathu"], "தெரியல", "don't know"),
    "nethu": (["netthu", "nethiku", "nethaiku"], "நேத்து", "yesterday"),
    "innaiku": (["inaiku", "innikku", "inniki", "indru"], "இன்னைக்கு", "today"),
    "naalaiku": (["nalaiku", "naalaikku", "naalai", "nalaikku"], "நாளைக்கு", "tomorrow"),
    "ippo": (["ipo", "ippa", "ipa", "ippothu"], "இப்போ", "now"),
    "appo": (["apo", "appodhu"], "அப்போ", "then"),
    "vaa": (["va", "vaada", "vadi"], "வா", "come"),
    "varuviya": (["varuveeya", "varuviyaa", "varriya"], "வருவியா", "will you come"),
    "varen": (["vaaren", "varean", "varein"], "வரேன்", "I'm coming"),
    "poren": (["pooren", "porean"], "போறேன்", "I'm going"),
    "ponen": (["poonen", "ponean"], "போனேன்", "I went"),
    "pona": (["poona", "ponaa"], "போன", "went"),
    "sollu": (["solu", "sollunga", "solunga"], "சொல்லு", "tell"),
    "sonna": (["sona", "sonnan", "sonnaan"], "சொன்ன", "said"),
    "pannu": (["panu", "pannunga"], "பண்ணு", "do"),
    "panna": (["pana", "panni"], "பண்ண", "did"),
    "pannitaan": (["panitan", "pannittan", "pannitan"], "பண்ணிட்டான்", "he did it"),
    "saptiya": (["saapitiya", "sapteeya", "saaptiya", "sapdiya"], "சாப்டியா", "did you eat"),
    "saapadu": (["sapadu", "saappadu"], "சாப்பாடு", "food"),
    "paathen": (["pathen", "paarthen", "partheen"], "பார்த்தேன்", "I saw"),
    "paaru": (["paru", "paarunga"], "பாரு", "look"),
    "kadhal": (["kaadhal", "kathal", "kadal"], "காதல்", "love"),
    "amma": (["ammaa", "ma"], "அம்மா", "mother"),
    "appa": (["appaa", "pa"], "அப்பா", "father"),
    "akka": (["aka", "akkaa"], "அக்கா", "elder sister"),
    "anna": (["annaa", "anne"], "அண்ணா", "elder brother"),
    "thambi": (["tambi", "thambee"], "தம்பி", "younger brother"),
    "machan": (["machaan", "machi", "machaa", "macha"], "மச்சான்", "buddy"),
    "dei": (["dey", "deii", "da", "daa", "di", "dee"], "டேய்", "hey (informal)"),
    "enakku": (["enaku", "yenakku", "enaaku"], "எனக்கு", "to me"),
    "unakku": (["unaku", "unnaku"], "உனக்கு", "to you"),
    "thoongu": (["thungu", "thoonga", "thunga"], "தூங்கு", "sleep"),
    "kalyanam": (["kalyaanam", "kalyana"], "கல்யாணம்", "wedding"),
    "ooru": (["uru", "oor"], "ஊரு", "hometown"),
    "kovil": (["koil", "koyil"], "கோவில்", "temple"),
    "veedu": (["vidu", "veetu", "veettu"], "வீடு", "house"),
    "nalla": (["nala", "nallaa"], "நல்ல", "good"),
}

TANGLISH_MARKERS: set[str] = set()
for canonical, (variants, _native, _gloss) in VARIANT_GROUPS.items():
    TANGLISH_MARKERS.add(canonical)
    TANGLISH_MARKERS.update(v for v in variants if len(v) > 2)  # skip ambiguous 2-letter forms
TANGLISH_MARKERS.update({"da", "di", "pa", "ku", "nu", "thaan", "than", "la", "le", "ah", "va", "na"})
# Common English words that collide with short Tanglish forms — never count them as markers.
TANGLISH_MARKERS -= {"en", "ma", "the", "on", "an"}

# Words people use to *address* someone: pet names, "hey" words, nicknames (used by
# retrieval/address.py for "how do I call Nihal?"). Each entry: (canonical form, regex, gloss).
# The regex must match a whole normalised word (repeats are already collapsed to 2 letters,
# so "kuttaaaa" arrives as "kuttaa"). Longer / more specific words come first: the first match wins.
# Deliberately left out: words that are just as often ordinary words ("panni" = "did", "kannu" = "eye").
ADDRESS_TERMS: list[tuple[str, str, str]] = [
    ("chellakutty", r"chel+a?k+u+t+[iy]+|செல்லக்குட்டி", "sweetheart, little darling"),
    ("chellam", r"chel+a+(m+e*)?|செல்லம்|செல்லமே", "darling"),
    ("kutta", r"kut+a+", "little one"),
    ("kutty", r"kut+[iy]+|குட்டி", "little one"),
    ("dei", r"de+[iy]+|dey|டேய்", "hey! (informal)"),
    ("da", r"da+|டா", "hey (informal)"),
    ("di", r"di+|டி", "hey (informal, to a girl)"),
    ("oii", r"o+[iy]+", "hey!"),
    ("mone", r"mone+|മോനെ|മോനേ", "dear (Malayalam, to a guy)"),
    ("mole", r"mole+|മോളെ|മോളേ", "dear (Malayalam, to a girl)"),
    ("kanna", r"kan+a+|கண்ணா", "dear"),
    ("baby", r"baby+|babe|babu", "baby"),
    ("pookie", r"poo?ki+e?", "pookie"),
    ("loosu", r"lo+su|lusu", "silly (teasing)"),
    ("eruma", r"eru+ma+", "buffalo (teasing)"),
    ("machan", r"macha+n?|machi|மச்சான்", "buddy"),
    ("chetta", r"chet+a+n?", "elder brother (Malayalam)"),
    ("bro", r"bro+", "bro"),
    ("dear", r"dear+", "dear"),
    ("honey", r"honey+", "honey"),
]

MALAYALAM_ROMAN_MARKERS: set[str] = {
    "entha", "enthu", "enthanu", "alle", "aano", "aanu", "cheyyam", "poyi", "vannu", "ningal",
    "njan", "ente", "sheri", "mone", "mole", "chetta", "chettan", "chechi", "kollam", "adipoli",
    "pinne", "ivide", "avide", "evide", "undo", "und", "cheyyu", "parayu", "paranju", "kazhicho",
    "vendi", "onnum", "ithu", "athu", "enikku", "ninakku", "nammal", "varum", "pokam",
}
