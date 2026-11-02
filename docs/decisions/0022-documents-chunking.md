# 0022. Parsers per source; long documents split into 1,200-character chunks

- **Status:** Accepted

## Context

Each export has its own format: WhatsApp on Android and iOS, 12- or 24-hour clocks, day-first or
month-first dates, zips with media; Instagram JSON with broken (mojibake) Unicode; journals with
dated headings; PDFs and Word files. And one embedding of a 30-page PDF can't point to the paragraph
that answers a question.

## Decision

- `dispatch.py` decides what kind of file an upload is and hands it to one parser. Every parser
  returns the same record shape, so everything after parsing is shared.
- Chat messages stay one memory each. Journals are split by their dated headings.
- Long documents are split with LangChain's `RecursiveCharacterTextSplitter`: **1,200 characters
  with 150 characters of overlap**. It prefers breaking at paragraphs, then sentences, then words.
  The overlap keeps a sentence cut at a boundary findable from both chunks.
- Chat exports carry no timezone, so their times are read in `DEFAULT_TIMEZONE` (`Asia/Kolkata`).

## Consequences

- A new source type only needs a parser that returns records.
- Each chunk is cited separately, so evidence points to the right part of a document.
- Users in another timezone must change `DEFAULT_TIMEZONE`, or "first / last" can be off by a day.

## Where in the code

`backend/app/ingestion/dispatch.py`, `ingestion/parsers/` (`whatsapp.py`, `instagram.py`,
`documents.py`), `ingestion/records.py`, `core/timeutils.py`.
