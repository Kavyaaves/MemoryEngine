"""Instagram "Download your information" DM parser (messages/inbox/<thread>/message_N.json)."""

import json
from datetime import UTC, datetime

from app.ingestion.records import ParsedRecord, ParseResult, decode_text, sha256_hex


def fix_mojibake(text: str | None) -> str | None:
    """Instagram exports write UTF-8 bytes as if they were Latin-1 characters, so Tamil
    comes out as "Ã Â®Â¨...". Re-encoding as Latin-1 and decoding as UTF-8 undoes that."""
    if not text:
        return text
    try:
        return text.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return text  # it was already correct


def looks_like_instagram(obj: object) -> bool:
    return isinstance(obj, dict) and "participants" in obj and "messages" in obj


def parse_instagram(data: bytes | str | dict, filename: str = "message_1.json") -> ParseResult:
    if isinstance(data, dict):
        thread = data
    else:
        thread = json.loads(data if isinstance(data, str) else decode_text(data))

    participants = [fix_mojibake(p.get("name")) or "unknown" for p in thread.get("participants", [])]
    title = fix_mojibake(thread.get("title")) or ", ".join(participants) or "Instagram chat"
    thread_id = thread.get("thread_path") or thread.get("thread_path_v2") or title

    records: list[ParsedRecord] = []
    # The file lists messages newest-first; reverse so records are chronological.
    for index, message in enumerate(reversed(thread.get("messages", []))):
        text = fix_mojibake(message.get("content")) or ""
        meta: dict = {}
        media_ref = None
        for media_key in ("photos", "videos", "audio_files"):
            if message.get(media_key):
                media_ref = message[media_key][0].get("uri")
                meta["media"] = media_ref
        shared_link = message.get("share", {}).get("link")
        if shared_link:
            meta["share_link"] = shared_link
            text = text or shared_link
        if not text and not media_ref:
            continue

        timestamp = None
        if message.get("timestamp_ms"):
            timestamp = datetime.fromtimestamp(message["timestamp_ms"] / 1000, tz=UTC)
        records.append(ParsedRecord(text=text, timestamp=timestamp, author=fix_mojibake(message.get("sender_name")),
                                    record_id=str(index), media_ref=media_ref, meta=meta))

    return ParseResult(
        source_type="instagram",
        source_name=title,
        fingerprint=sha256_hex("instagram", str(thread_id).lower()),
        records=records,
        conversation_title=title,
        participants=participants,
    )
