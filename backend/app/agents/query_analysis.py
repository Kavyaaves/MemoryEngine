"""Understanding the question — without AI first, then (optionally) improved by an LLM.

    heuristic_analysis("What was the first trip with Rahul in 2024? show photos", aliases)
      → intent=temporal, people=["Rahul"], 2024-01-01..2025-01-01, order="first", modality=[image]

The deterministic result always wins for things SQL relies on (dates, first/last);
the LLM only adds what rules can't do well (query rewrites, unusual names).
"""

import re
from datetime import date, timedelta

from app.people.aliases import normalize_alias
from app.retrieval.query import STOPWORDS
from app.schemas.ai import QueryAnalysis

MONTHS = {name: number for number, name in enumerate(
    ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october",
     "november", "december"], start=1)}
MONTHS.update({name[:3]: number for name, number in list(MONTHS.items())})
MONTHS["sept"] = 9

# English + Tanglish + Tamil/Malayalam words for "first" and "last".
FIRST_WORDS = {"first", "earliest", "initially", "firstu", "mudhal", "modhal", "muthal", "முதல்", "ആദ്യം"}
LAST_WORDS = {"last", "latest", "recent", "recently", "kadaisi", "kadasi", "கடைசி", "അവസാനം"}

MODALITY_WORDS = {
    "image": {"photo", "photos", "pic", "pics", "picture", "pictures", "image", "images", "selfie"},
    "audio": {"audio", "voice", "recording", "song"},
    "video": {"video", "videos", "clip", "reel"},
}
COUNT_PATTERN = re.compile(r"\bhow many\b|\bcount\b|\bhow often\b|\bevalo\b|\bethana\b")
SUMMARY_PATTERN = re.compile(r"\bsummar|\boverview\b|\bwhat happened\b")

# "How do I call Nihal?" / "What does Nihal call me?" — questions about nicknames and pet names.
# (Not phone calls: "when did I call Nihal" has no "how/what … call" shape, and "what time" is excluded.)
CALL = r"(call|calls|called|address|addresses|refer to|refers to)"
ADDRESSES_ME = re.compile(rf"\b{CALL}\s+me\b|\bmy (nick ?name|pet ?name)|"
                          r"\b(ennai|ennaya|enna|என்னை)\s+(epdi|eppadi|enna solli)\s+(kup|koop|kooptu|kupdu)")
I_ADDRESS = re.compile(rf"\b(how|what)\b.*\b(do|did|would|should)\s+i\s+(\w+\s+)?{CALL}\b|"
                       rf"\bi\s+(usually\s+|mostly\s+|normally\s+|always\s+)?{CALL}\b|"
                       r"\b(nick ?name|pet ?name)s?\b|"
                       r"\b(epdi|eppadi|enna solli)\s+(kup|koop|kooptu|kupdu)")
NOT_ADDRESS = re.compile(r"\bwhat time\b|\bwhen\b|\bhow long\b")


def address_speaker(question: str) -> str | None:
    """'self' (how I address someone), 'them' (how someone addresses me) or None (not that kind of question)."""
    lowered = question.lower()
    if NOT_ADDRESS.search(lowered):
        return None
    if ADDRESSES_ME.search(lowered):
        return "them"
    if I_ADDRESS.search(lowered):
        return "self"
    return None


def temporal_order(question: str) -> str | None:
    """'first', 'last' or None."""
    lowered = question.lower()
    question_words = set(re.findall(r"[\w\u0B80-\u0BFF\u0D00-\u0D7F]+", lowered))
    if question_words & FIRST_WORDS:
        return "first"
    if question_words & LAST_WORDS or "most recent" in lowered:
        return "last"
    return None


def _month_window(year: int, month: int) -> tuple[date, date]:
    end = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
    return date(year, month, 1), end


def parse_time_window(question: str, today: date | None = None) -> tuple[date | None, date | None]:
    """(start, end) dates implied by the question; `end` is exclusive. (None, None) if no time is mentioned.

    Understands: "between 2021 and 2022", "January 2024", "before/after 2020", "in 2023",
    "yesterday"/"nethu", "today", "last/this week", "last/this month", "last/this year".
    """
    today = today or date.today()
    q = question.lower()

    if m := re.search(r"between\s+(\d{4})\s+(?:and|to|-)\s+(\d{4})", q):
        first, last = sorted((int(m[1]), int(m[2])))
        return date(first, 1, 1), date(last + 1, 1, 1)
    month_names = "|".join(sorted(MONTHS, key=len, reverse=True))
    if m := re.search(rf"\b({month_names})[a-z]*\.?,?\s+(\d{{4}})\b", q):
        return _month_window(int(m[2]), MONTHS[m[1]])
    if m := re.search(r"\b(?:before|until|till)\s+(\d{4})\b", q):
        return None, date(int(m[1]), 1, 1)
    if m := re.search(r"\b(after|since)\s+(\d{4})\b", q):
        year = int(m[2]) + 1 if m[1] == "after" else int(m[2])
        return date(year, 1, 1), None
    if m := re.search(r"\b(19\d{2}|20\d{2})\b", q):
        year = int(m[1])
        return date(year, 1, 1), date(year + 1, 1, 1)

    start_of_week = today - timedelta(days=today.weekday())
    first_of_month = today.replace(day=1)
    relative = [
        (("yesterday", "nethu", "நேத்து"), (today - timedelta(days=1), today)),
        (("today", "innaiku"), (today, today + timedelta(days=1))),
        (("last week",), (start_of_week - timedelta(days=7), start_of_week)),
        (("this week",), (start_of_week, today + timedelta(days=1))),
        (("last month",), ((first_of_month - timedelta(days=1)).replace(day=1), first_of_month)),
        (("this month",), (first_of_month, today + timedelta(days=1))),
        (("last year",), (date(today.year - 1, 1, 1), date(today.year, 1, 1))),
        (("this year",), (date(today.year, 1, 1), today + timedelta(days=1))),
    ]
    for phrases, window in relative:
        if any(phrase in q for phrase in phrases):
            return window
    return None, None


def _people_mentioned(question: str, known_aliases: dict[str, str]) -> list[str]:
    """Known names (normalised alias → display name) that appear as whole words in the question."""
    normalized_question = normalize_alias(question)
    people: list[str] = []
    for alias, display_name in sorted(known_aliases.items(), key=lambda item: -len(item[0])):  # longest first
        if len(alias) >= 2 and display_name not in people and \
                re.search(rf"(?<!\w){re.escape(alias)}(?!\w)", normalized_question):
            people.append(display_name)
    return people


def _intent(question: str, order: str | None, modality: list[str], people: list[str]) -> str:
    lowered = question.lower()
    if COUNT_PATTERN.search(lowered):
        return "count"
    if people and address_speaker(question):
        return "address"
    if order:
        return "temporal"
    if modality != ["text"]:
        return "media"
    if people and len(lowered.split()) <= 6:
        return "person"  # a short question about someone: "what about Rahul?"
    if SUMMARY_PATTERN.search(lowered):
        return "summary"
    return "lookup"


def heuristic_analysis(question: str, known_aliases: dict[str, str], today: date | None = None) -> QueryAnalysis:
    people = _people_mentioned(question, known_aliases)
    start, end = parse_time_window(question, today)
    order = temporal_order(question)
    question_words = set(re.findall(r"\w+", question.lower()))
    modality = [kind for kind, kind_words in MODALITY_WORDS.items() if question_words & kind_words] or ["text"]

    name_words = {word for person in people for word in normalize_alias(person).split()}
    keywords = [word for word in re.findall(r"[\w\u0B80-\u0BFF\u0D00-\u0D7F]+", question.lower())
                if word not in STOPWORDS and word not in name_words and not word.isdigit() and len(word) > 1]
    return QueryAnalysis(
        intent=_intent(question, order, modality, people),
        people=people,
        time_start=start.isoformat() if start else None,
        time_end=end.isoformat() if end else None,
        temporal_order=order,
        address_speaker=address_speaker(question),
        modality=modality,
        rewritten_queries=[" ".join(keywords)] if keywords else [],
        topic_keywords=keywords,
    )


def merge_analysis(rules: QueryAnalysis, llm: QueryAnalysis | None) -> QueryAnalysis:
    """Combine the rule-based and LLM analyses. Rules win for dates and first/last."""
    if llm is None:
        return rules
    # The rules' "address" and "count" intents trigger exact SQL counting, so they win over the LLM's guess.
    intent = rules.intent if rules.intent in ("address", "count") or llm.intent == "lookup" else llm.intent
    people = list(dict.fromkeys(rules.people + llm.people))
    # "How do I call Nihal?": the rules saw the "how do I call" shape but may not have known the
    # name (only full aliases like "nihal manoj" are known) — the LLM found the person, so it's an address question.
    if rules.address_speaker and people and intent != "count":
        intent = "address"
    return QueryAnalysis(
        intent=intent,
        people=people,
        time_start=rules.time_start or llm.time_start,
        time_end=rules.time_end or llm.time_end,
        temporal_order=rules.temporal_order or llm.temporal_order,
        address_speaker=rules.address_speaker or llm.address_speaker,
        modality=sorted(set(rules.modality) | set(llm.modality)),
        rewritten_queries=list(dict.fromkeys(llm.rewritten_queries + rules.rewritten_queries))[:4],
        topic_keywords=list(dict.fromkeys(rules.topic_keywords + llm.topic_keywords)),
    )
