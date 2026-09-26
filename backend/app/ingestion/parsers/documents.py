"""Parsers for journals and documents: TXT, Markdown, JSON, CSV, PDF, DOCX, EML.

Journals are split into one record per dated entry ("# 2024-06-14 ..."). Everything else
is split into overlapping chunks, so each memory is small enough to retrieve on its own.
"""

import csv
import email
import io
import json
import re
from datetime import datetime
from email.utils import parsedate_to_datetime

from app.ingestion.records import ParsedRecord, ParseResult, decode_text, sha256_hex

CHUNK_SIZE = 1200  # characters
CHUNK_OVERLAP = 150
# Where a chunk may end, best first: paragraph, line, sentence, word, anywhere.
CHUNK_SEPARATORS = ["\n\n", "\n", ". ", "? ", "! ", " ", ""]

MONTHS = {name: number for number, name in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], start=1)}
MONTH_NAME = r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?"

ISO_DATE = re.compile(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b")  # 2024-06-14
NUMERIC_DATE = re.compile(r"\b(\d{1,2})[/.](\d{1,2})[/.](\d{4})\b")  # 14/06/2024 (day first)
DAY_MONTH_YEAR = re.compile(rf"\b(\d{{1,2}})\s+{MONTH_NAME},?\s+(\d{{4}})\b", re.I)  # 14 June 2024
MONTH_DAY_YEAR = re.compile(rf"\b{MONTH_NAME}\s+(\d{{1,2}})(?:st|nd|rd|th)?,?\s+(\d{{4}})\b", re.I)  # June 14th, 2024

# A journal heading: a Markdown heading, or a line that starts with a date.
JOURNAL_HEADING = re.compile(r"^(#{1,6}\s+.*|\s*(\d{4}-\d{1,2}-\d{1,2}|\d{1,2}[/.]\d{1,2}[/.]\d{4}).{0,60})$", re.M)


def find_date(text: str) -> datetime | None:
    """First date found in `text`, trying the formats above in order."""
    candidates = []
    if m := ISO_DATE.search(text):
        candidates.append((int(m[1]), int(m[2]), int(m[3])))
    if m := NUMERIC_DATE.search(text):
        candidates.append((int(m[3]), int(m[2]), int(m[1])))
    if m := DAY_MONTH_YEAR.search(text):
        candidates.append((int(m[3]), MONTHS[m[2][:3].lower()], int(m[1])))
    if m := MONTH_DAY_YEAR.search(text):
        candidates.append((int(m[3]), MONTHS[m[1][:3].lower()], int(m[2])))
    for year, month, day in candidates:
        try:
            return datetime(year, month, day)
        except ValueError:  # e.g. 31/02/2024
            continue
    return None


def chunk_text(text: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """Split text into chunks of at most `size` characters, using LangChain's recursive splitter.

    The splitter tries the separators in CHUNK_SEPARATORS in order: it keeps whole paragraphs
    together if they fit, otherwise whole lines, then whole sentences, then words — and cuts
    mid-word only as a last resort. Neighbouring chunks share up to `overlap` characters of
    whole sentences, so a sentence that falls on a boundary can still be found in one piece.
    """
    text = text.strip()
    if len(text) <= size:
        return [text] if text else []
    # Imported here, not at the top: the package also loads sentence-transformers (and torch)
    # whenever those happen to be installed, which takes seconds — only pay that when chunking.
    from langchain_text_splitters import RecursiveCharacterTextSplitter

    splitter = RecursiveCharacterTextSplitter(chunk_size=size, chunk_overlap=overlap, separators=CHUNK_SEPARATORS,
                                              keep_separator="end")  # "end": a sentence keeps its full stop
    return splitter.split_text(text)


def _result(source_type: str, name: str, records: list[ParsedRecord], fingerprint: str | None = None) -> ParseResult:
    return ParseResult(source_type=source_type, source_name=name, records=records,
                       fingerprint=fingerprint or sha256_hex(source_type, name.lower()))


def parse_journal(text: str, filename: str, source_type: str = "journal") -> ParseResult:
    """One record per dated heading; text before the first heading and undated files are chunked."""
    heading_starts = [m.start() for m in JOURNAL_HEADING.finditer(text) if find_date(m.group(0))]
    if not heading_starts:
        date = find_date(filename) or find_date(text[:300])
        records = [ParsedRecord(text=chunk, timestamp=date, record_id=str(i))
                   for i, chunk in enumerate(chunk_text(text))]
        return _result(source_type, filename, records)

    records: list[ParsedRecord] = []
    preamble = text[: heading_starts[0]]
    for i, chunk in enumerate(chunk_text(preamble)):
        records.append(ParsedRecord(text=chunk, record_id=f"pre-{i}"))

    entry_bounds = zip(heading_starts, heading_starts[1:] + [len(text)], strict=True)
    for entry_no, (start, end) in enumerate(entry_bounds):
        entry = text[start:end].strip()
        heading = entry.splitlines()[0]
        date = find_date(heading)
        for i, chunk in enumerate(chunk_text(entry)):
            records.append(ParsedRecord(text=chunk, timestamp=date, record_id=f"{entry_no}-{i}",
                                        meta={"heading": heading.strip("# ")}))
    return _result(source_type, filename, records)


def _parse_json_date(value) -> datetime | None:
    if isinstance(value, (int, float)):
        seconds = value / 1000 if value > 1e11 else value  # milliseconds vs seconds
        return datetime.fromtimestamp(seconds)
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return find_date(value)
    return None


def records_from_rows(rows: list) -> list[ParsedRecord]:
    """Rows (JSON objects / CSV lines) that have a text-like field → one record each."""
    text_fields = ("text", "content", "body", "message", "note", "entry")
    date_fields = ("timestamp", "date", "created_at", "time", "datetime")
    author_fields = ("author", "sender", "from", "user")
    if not rows or not all(isinstance(row, dict) for row in rows[:20]):
        return []

    records = []
    for i, row in enumerate(rows):
        text = next((str(row[f]) for f in text_fields if row.get(f)), None)
        if not text:
            continue
        date = next((d for f in date_fields if (d := _parse_json_date(row.get(f)))), None)
        author = next((str(row[f]) for f in author_fields if row.get(f)), None)
        records.append(ParsedRecord(text=text, timestamp=date, author=author, record_id=str(i)))
    return records


def parse_json(data: bytes, filename: str) -> ParseResult:
    obj = json.loads(decode_text(data))
    # Accept a list of rows, or an object whose first list-valued field holds the rows.
    if isinstance(obj, list):
        rows = obj
    elif isinstance(obj, dict):
        rows = next((v for v in obj.values() if isinstance(v, list)), [])
    else:
        rows = []
    records = records_from_rows(rows)
    if not records:  # unknown shape: index the pretty-printed JSON as text
        pretty = json.dumps(obj, ensure_ascii=False, indent=1)
        records = [ParsedRecord(text=chunk, record_id=str(i)) for i, chunk in enumerate(chunk_text(pretty))]
    return _result("document", filename, records)


def parse_csv(data: bytes, filename: str) -> ParseResult:
    rows = list(csv.DictReader(io.StringIO(decode_text(data))))
    records = records_from_rows(rows)
    if not records:  # no text-like column: each row becomes "column: value" lines
        records = [ParsedRecord(text="\n".join(f"{k}: {v}" for k, v in row.items() if v), record_id=str(i))
                   for i, row in enumerate(rows)]
    return _result("document", filename, records)


def parse_pdf(data: bytes, filename: str) -> ParseResult:
    from pypdf import PdfReader

    date = find_date(filename)
    records = []
    for page_no, page in enumerate(PdfReader(io.BytesIO(data)).pages, start=1):
        for i, chunk in enumerate(chunk_text(page.extract_text() or "")):
            records.append(ParsedRecord(text=chunk, timestamp=date, record_id=f"p{page_no}-{i}",
                                        meta={"page": page_no}))
    return _result("document", filename, records)


def parse_docx(data: bytes, filename: str) -> ParseResult:
    import docx

    document = docx.Document(io.BytesIO(data))
    text = "\n\n".join(p.text for p in document.paragraphs if p.text.strip())
    return parse_journal(text, filename, source_type="document")


def parse_eml(data: bytes, filename: str) -> ParseResult:
    message = email.message_from_bytes(data)
    body = ""
    parts = message.walk() if message.is_multipart() else [message]
    for part in parts:
        if part.get_content_type() == "text/plain" and not part.get_filename():
            body += part.get_payload(decode=True).decode(part.get_content_charset() or "utf-8", "replace")
    try:
        date = parsedate_to_datetime(message["Date"]) if message["Date"] else None
    except (TypeError, ValueError):
        date = None
    subject = str(message["Subject"] or filename)
    sender = str(message["From"] or "") or None
    records = [ParsedRecord(text=chunk, timestamp=date, author=sender, record_id=str(i),
                            meta={"subject": subject, "to": str(message["To"] or "")})
               for i, chunk in enumerate(chunk_text(f"Subject: {subject}\n\n{body}"))]
    result = _result("document", subject, records, fingerprint=sha256_hex("email", str(message["Message-ID"] or filename)))
    result.participants = [sender] if sender else []
    return result


def parse_text_file(data: bytes, filename: str, source_type: str = "journal") -> ParseResult:
    return parse_journal(decode_text(data), filename, source_type=source_type)
