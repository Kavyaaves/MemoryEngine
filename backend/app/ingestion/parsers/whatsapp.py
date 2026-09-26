"""WhatsApp chat export parser.

Handles both export styles:
    Android:  31/12/2023, 21:15 - Rahul: hi
    iOS:      [31/12/23, 9:15:30 PM] Rahul: hi
with 12h or 24h clocks, and dd/mm vs mm/dd dates (worked out from the whole file).
A line that doesn't start with a date continues the previous message.
"""

import re
from datetime import datetime

from app.ingestion.records import ParsedRecord, ParseResult, decode_text, sha256_hex

# Invisible direction marks that WhatsApp sprinkles into exports.
INVISIBLE_CHARS = "\u200e\u200f\u202a\u202b\u202c\u202d\u202e\ufeff"
# Unusual spaces (e.g. the narrow no-break space before "PM") normalised to a plain space.
ODD_SPACES = "\u202f\u00a0\u2009"

MESSAGE_LINE = re.compile(
    r"^\[?(?P<date>\d{1,4}[./-]\d{1,2}[./-]\d{1,4}),?\s+"  # 31/12/2023,
    r"(?P<time>\d{1,2}[:.]\d{2}(?:[:.]\d{2})?(?:\s?[AaPp]\.?\s?[Mm]\.?)?)\]?"  # 9:15 PM  or  21:15:30
    r"(?:\s+-|\s*:)?\s+(?P<rest>.*)$"  # " - " (Android) or "] " (iOS), then the rest
)
AUTHOR_AND_TEXT = re.compile(r"^(?P<author>[^:]{1,80}?):\s(?P<text>.*)$", re.DOTALL)
ATTACHMENT = re.compile(r"<attached:\s*(?P<file>[^>]+)>|(?P<file2>\S+\.\w{2,4})\s+\(file attached\)", re.I)
MEDIA_OMITTED = re.compile(
    r"^<?(media|image|video|audio|sticker|gif|document|contact card) omitted>?$", re.I)
DELETED = re.compile(r"^(this message was deleted|you deleted this message)$", re.I)
EDITED_MARKER = "<This message was edited>"


def clean_line(line: str) -> str:
    for ch in INVISIBLE_CHARS:
        line = line.replace(ch, "")
    for ch in ODD_SPACES:
        line = line.replace(ch, " ")
    return line.rstrip("\r")


def looks_like_whatsapp(text: str) -> bool:
    """True if at least a third of the first 50 non-empty lines look like chat messages."""
    lines = [clean_line(line) for line in text.splitlines()[:50] if line.strip()]
    if not lines:
        return False
    matches = sum(1 for line in lines if MESSAGE_LINE.match(line))
    return matches >= max(2, len(lines) // 3)


def guess_date_order(dates: list[str]) -> str:
    """'dmy', 'mdy' or 'ymd'. If any first number is > 12 it must be a day (dmy);
    if only the second number ever exceeds 12 it's mdy. Ambiguous files default to dmy
    (the Indian convention)."""
    first_can_be_day = second_can_be_day = False
    for d in dates:
        parts = re.split(r"[./-]", d)
        if len(parts[0]) == 4:
            return "ymd"
        first_can_be_day |= int(parts[0]) > 12
        second_can_be_day |= int(parts[1]) > 12
    if second_can_be_day and not first_can_be_day:
        return "mdy"
    return "dmy"


def parse_timestamp(date_text: str, time_text: str, date_order: str) -> datetime | None:
    numbers = [int(p) for p in re.split(r"[./-]", date_text)]
    if date_order == "ymd":
        year, month, day = numbers
    elif date_order == "mdy":
        month, day, year = numbers
    else:
        day, month, year = numbers
    if year < 100:
        year += 2000

    # Split "9:15 p.m." into the clock part "9:15" and the AM/PM part.
    am_pm = re.search(r"([AaPp])\.?\s?[Mm]\.?$", time_text)
    clock = time_text[: am_pm.start()] if am_pm else time_text
    parts = [int(x) for x in re.split(r"[:.]", clock.strip())]
    hour, minute = parts[0], parts[1]
    second = parts[2] if len(parts) > 2 else 0
    if am_pm:
        is_pm = am_pm.group(1).lower() == "p"
        if is_pm and hour != 12:
            hour += 12  # 9 PM → 21
        elif not is_pm and hour == 12:
            hour = 0  # 12 AM → 00
    try:
        return datetime(year, month, day, hour, minute, second)  # naive local time
    except ValueError:
        return None


def chat_title_from_filename(filename: str) -> str:
    """'WhatsApp Chat with Rahul.txt' → 'Rahul'."""
    name = filename.replace("\\", "/").rsplit("/", 1)[-1]
    name = re.sub(r"\.(txt|zip)$", "", name, flags=re.I)
    name = re.sub(r"^WhatsApp Chat (with|-)\s*", "", name, flags=re.I).strip(" -_")
    return name or "WhatsApp chat"


def split_into_messages(text: str) -> list[tuple[str, str, str]]:
    """[(date, time, rest-of-message)], with continuation lines joined onto their message."""
    messages: list[tuple[str, str, str]] = []
    for line in text.splitlines():
        line = clean_line(line)
        match = MESSAGE_LINE.match(line)
        if match:
            messages.append((match["date"], match["time"], match["rest"]))
        elif messages:  # continuation of a multi-line message
            date_text, time_text, rest = messages[-1]
            messages[-1] = (date_text, time_text, rest + "\n" + line)
    return messages


def parse_whatsapp(data: bytes | str, filename: str = "chat.txt") -> ParseResult:
    text = data if isinstance(data, str) else decode_text(data)
    messages = split_into_messages(text)
    date_order = guess_date_order([m[0] for m in messages])

    records: list[ParsedRecord] = []
    message_counts: dict[str, int] = {}
    for index, (date_text, time_text, rest) in enumerate(messages):
        timestamp = parse_timestamp(date_text, time_text, date_order)
        rest = rest.strip()

        match = AUTHOR_AND_TEXT.match(rest)
        # System lines ("Rahul added Priya") and the encryption notice have no real author.
        if not match or "end-to-end encrypted" in rest.lower():
            records.append(ParsedRecord(text=rest, timestamp=timestamp, is_system=True, record_id=str(index)))
            continue

        author = match["author"].strip()
        body = match["text"].replace(EDITED_MARKER, "").strip()
        meta: dict = {}
        media_ref = None

        attachment = ATTACHMENT.search(body)
        if attachment:
            media_ref = (attachment["file"] or attachment["file2"]).strip()
            meta["media"] = media_ref
            body = ATTACHMENT.sub("", body).strip()
        elif MEDIA_OMITTED.match(body):
            meta["media_omitted"] = body.strip("<>").lower()
            body = ""
        if DELETED.match(body):
            meta["deleted"] = True
            body = ""

        if not body and not media_ref:
            continue  # nothing left worth remembering
        message_counts[author] = message_counts.get(author, 0) + 1
        records.append(ParsedRecord(text=body, timestamp=timestamp, author=author, record_id=str(index),
                                    media_ref=media_ref, meta=meta))

    title = chat_title_from_filename(filename)
    most_active_first = sorted(message_counts, key=lambda name: message_counts[name], reverse=True)
    return ParseResult(
        source_type="whatsapp",
        source_name=title,
        fingerprint=sha256_hex("whatsapp", title.lower()),
        records=records,
        conversation_title=title,
        participants=most_active_first,
        meta={"date_order": date_order},
    )
