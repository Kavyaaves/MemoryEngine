import io
import json
import zipfile
from datetime import datetime

from app.ingestion.dispatch import detect_source_type, parse_upload
from app.ingestion.parsers.documents import chunk_text, find_date, parse_journal
from app.ingestion.parsers.instagram import parse_instagram
from app.ingestion.parsers.whatsapp import looks_like_whatsapp, parse_whatsapp
from app.ingestion.records import ParsedRecord, content_hashes

ANDROID = """12/31/23, 9:15 PM - Messages and calls are end-to-end encrypted. No one outside of this chat can read them.
12/31/23, 9:15 PM - Rahul ❤\ufe0f: dei tomorrow office varuviya?
12/31/23, 9:16 PM - Priya: seri da
this is a continuation line
1/13/24, 10:02 AM - Rahul ❤\ufe0f: <Media omitted>
1/13/24, 10:03 AM - Priya: This message was deleted
1/13/24, 10:04 AM - Rahul ❤\ufe0f: நான் அவன் கூட போனேன்
"""

IOS = """[31/12/2023, 21:15:30] Rahul: Happy new year!
[31/12/2023, 21:16:02] Priya: \u200eimage omitted
[01/01/2024, 00:00:01] Priya: same to you
[13/01/2024, 10:00:00] Priya: \u200e<attached: 00000012-PHOTO-2024-01-13-10-00-00.jpg>
"""


def test_android_format_mdy_12h():
    r = parse_whatsapp(ANDROID, "WhatsApp Chat with Rahul.txt")
    assert r.source_name == "Rahul"
    texts = [x.text for x in r.records if not x.is_system]
    assert texts == ["dei tomorrow office varuviya?", "seri da\nthis is a continuation line",
                     "நான் அவன் கூட போனேன்"]
    first = next(x for x in r.records if not x.is_system)
    assert first.timestamp == datetime(2023, 12, 31, 21, 15)
    assert first.author == "Rahul ❤\ufe0f"
    assert r.meta["date_order"] == "mdy"
    assert any(x.is_system for x in r.records)
    assert set(r.participants) == {"Rahul ❤\ufe0f", "Priya"}


def test_ios_format_dmy_24h_with_attachments():
    r = parse_whatsapp(IOS, "_chat.txt")
    assert r.meta["date_order"] == "dmy"
    assert r.records[0].timestamp == datetime(2023, 12, 31, 21, 15, 30)
    photo = r.records[-1]
    assert photo.media_ref == "00000012-PHOTO-2024-01-13-10-00-00.jpg"
    assert [x.text for x in r.records][:2] == ["Happy new year!", "same to you"]


def test_whatsapp_detection():
    assert looks_like_whatsapp(ANDROID)
    assert not looks_like_whatsapp("Dear diary,\ntoday was a good day.\n")
    assert detect_source_type("chat.txt", ANDROID.encode()) == "whatsapp"
    assert detect_source_type("notes.md", b"# 2024-06-14\nWent to Kerala") == "journal"


def test_content_hashes_are_stable_and_keep_identical_messages():
    ts = datetime(2024, 1, 1, 10, 0)
    recs = [ParsedRecord("ok", ts, "A"), ParsedRecord("ok", ts, "A"), ParsedRecord("hi", ts, "B")]
    h1 = content_hashes("fp", recs)
    h2 = content_hashes("fp", list(recs))
    assert h1 == h2
    assert len(set(h1)) == 3
    # re-export with a new message appended: old hashes unchanged → incremental ingestion
    h3 = content_hashes("fp", recs + [ParsedRecord("new", ts, "A")])
    assert h3[:3] == h1


def test_reimport_of_same_chat_has_same_fingerprint():
    a = parse_whatsapp(ANDROID, "WhatsApp Chat with Rahul.txt")
    b = parse_whatsapp(ANDROID + "1/14/24, 9:00 AM - Priya: new msg\n", "WhatsApp Chat with Rahul.txt")
    assert a.fingerprint == b.fingerprint
    ha = set(content_hashes(a.fingerprint, a.records))
    hb = set(content_hashes(b.fingerprint, b.records))
    assert ha < hb and len(hb - ha) == 1


def test_whatsapp_zip_with_media():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("_chat.txt", IOS)
        z.writestr("00000012-PHOTO-2024-01-13-10-00-00.jpg", b"\xff\xd8\xff fake")
    data = buf.getvalue()
    assert detect_source_type("WhatsApp Chat - Priya.zip", data) == "whatsapp"
    up = parse_upload("WhatsApp Chat - Priya.zip", data, "whatsapp")
    assert up.results[0].source_name == "Priya"
    assert [m.name for m in up.media] == ["00000012-PHOTO-2024-01-13-10-00-00.jpg"]
    assert up.media[0].kind == "photo"


def test_instagram_mojibake_is_fixed_and_order_is_chronological():
    raw = {
        "participants": [{"name": "Rahul"}, {"name": "Me"}],
        "title": "Rahul",
        "thread_path": "inbox/rahul_123",
        "messages": [
            {"sender_name": "Rahul", "timestamp_ms": 1718400000000,
             "content": "நான்".encode().decode("latin-1")},
            {"sender_name": "Me", "timestamp_ms": 1718300000000, "content": "hi"},
        ],
    }
    r = parse_instagram(json.dumps(raw))
    assert [x.text for x in r.records] == ["hi", "நான்"]
    assert r.records[0].timestamp < r.records[1].timestamp


def test_journal_split_on_dated_headings():
    text = "# 2024-06-14\nPlanned the Kerala trip.\n\n# 15 June 2024\nPacked bags.\n"
    r = parse_journal(text, "journal.md")
    assert [x.timestamp for x in r.records] == [datetime(2024, 6, 14), datetime(2024, 6, 15)]
    assert "Kerala" in r.records[0].text


def test_find_date_formats():
    assert find_date("Entry 2024-02-14") == datetime(2024, 2, 14)
    assert find_date("14/02/2024 notes") == datetime(2024, 2, 14)
    assert find_date("Feb 14th, 2024") == datetime(2024, 2, 14)
    assert find_date("no date") is None


def test_chunking_respects_size():
    text = "\n\n".join(f"Paragraph {i} " + "word " * 80 for i in range(20))
    chunks = chunk_text(text, size=1000, overlap=100)
    assert len(chunks) > 1
    assert all(len(c) <= 1000 for c in chunks)
    assert chunk_text("  short note  ") == ["short note"] and chunk_text("   ") == []


def test_chunks_end_on_sentences_and_overlap():
    sentences = [f"Sentence number {i} is about the Kerala trip." for i in range(60)]
    chunks = chunk_text(" ".join(sentences), size=300, overlap=100)
    assert all(chunk.endswith(".") for chunk in chunks)  # never cut mid-sentence
    for previous, current in zip(chunks, chunks[1:], strict=False):
        last_sentence = previous.rsplit(". ", 1)[-1]
        assert last_sentence in current  # the boundary sentence appears in both chunks
