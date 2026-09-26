"""Work out what an uploaded file is, and send it to the right parser (PLAN §4.1).

    detect_source_type("chat.txt", bytes)  → "whatsapp"
    parse_upload("chat.txt", bytes, "whatsapp") → ParsedUpload(results=[...], media=[...])
"""

import io
import json
import mimetypes
import zipfile
from dataclasses import dataclass, field
from pathlib import PurePosixPath

from app.ingestion.parsers import documents
from app.ingestion.parsers.instagram import looks_like_instagram, parse_instagram
from app.ingestion.parsers.whatsapp import looks_like_whatsapp, parse_whatsapp
from app.ingestion.records import ParseResult, decode_text, sha256_hex

SOURCE_TYPES = {"auto", "whatsapp", "instagram", "journal", "document", "image", "audio", "video"}

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif", ".gif"}
AUDIO_EXTENSIONS = {".mp3", ".m4a", ".aac", ".wav", ".ogg", ".opus", ".flac", ".amr"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm", ".3gp", ".avi"}
MAX_ZIP_MEMBER_BYTES = 500 * 1024 * 1024


@dataclass
class MediaFile:
    name: str
    data: bytes
    kind: str  # photo | audio | video
    mime_type: str | None


@dataclass
class ParsedUpload:
    results: list[ParseResult] = field(default_factory=list)  # one per chat / document
    media: list[MediaFile] = field(default_factory=list)  # photos etc. found in the upload


def extension(filename: str) -> str:
    return PurePosixPath(filename.lower()).suffix


def media_kind(filename: str) -> str | None:
    ext = extension(filename)
    if ext in IMAGE_EXTENSIONS:
        return "photo"
    if ext in AUDIO_EXTENSIONS:
        return "audio"
    if ext in VIDEO_EXTENSIONS:
        return "video"
    return None


def detect_source_type(filename: str, data: bytes, hint: str = "auto") -> str:
    """The user's choice wins; otherwise guess from the extension and the content."""
    if hint and hint != "auto":
        return hint
    kind = media_kind(filename)
    if kind:
        return {"photo": "image", "audio": "audio", "video": "video"}[kind]

    ext = extension(filename)
    if ext == ".zip":
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            names = archive.namelist()
        is_instagram = any("messages/inbox/" in n and n.endswith(".json") for n in names)
        return "instagram" if is_instagram else "whatsapp"
    if ext == ".json":
        try:
            if looks_like_instagram(json.loads(decode_text(data))):
                return "instagram"
        except ValueError:
            pass
        return "document"
    if ext in {".txt", ".md", ".markdown"}:
        return "whatsapp" if looks_like_whatsapp(decode_text(data[:20000])) else "journal"
    return "document"


def _media_file(name: str, data: bytes) -> MediaFile | None:
    kind = media_kind(name)
    if not kind:
        return None
    return MediaFile(name=PurePosixPath(name).name, data=data, kind=kind, mime_type=mimetypes.guess_type(name)[0])


def _parse_zip(filename: str, data: bytes, source_type: str) -> ParsedUpload:
    """WhatsApp zips hold one chat .txt plus media; Instagram zips hold many message_N.json files."""
    upload = ParsedUpload()
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        for member in archive.infolist():
            if member.is_dir() or member.file_size > MAX_ZIP_MEMBER_BYTES:
                continue
            name = member.filename
            if source_type == "whatsapp" and name.lower().endswith(".txt"):
                # the chat name comes from the zip's name, not the inner "_chat.txt"
                upload.results.append(parse_whatsapp(archive.read(member), filename))
            elif source_type == "instagram" and "messages/inbox/" in name and name.endswith(".json"):
                upload.results.append(parse_instagram(archive.read(member), name))
            elif media := _media_file(name, archive.read(member)):
                upload.media.append(media)
    if source_type == "instagram":
        upload.results = _merge_by_fingerprint(upload.results)
    return upload


def _merge_by_fingerprint(results: list[ParseResult]) -> list[ParseResult]:
    """message_1.json, message_2.json … of one Instagram thread become a single source."""
    merged: dict[str, ParseResult] = {}
    for result in results:
        if result.fingerprint in merged:
            merged[result.fingerprint].records.extend(result.records)
        else:
            merged[result.fingerprint] = result
    for result in merged.values():
        result.records.sort(key=lambda r: r.timestamp.timestamp() if r.timestamp else 0)
    return list(merged.values())


def parse_upload(filename: str, data: bytes, source_type: str) -> ParsedUpload:
    if source_type in ("image", "audio", "video"):
        # A single media file: no text records yet — the pipeline describes it with AI.
        media = _media_file(filename, data) or MediaFile(filename, data, source_type, mimetypes.guess_type(filename)[0])
        result = ParseResult(source_type=source_type, source_name=filename,
                             fingerprint=sha256_hex(source_type, sha256_hex(data)), records=[])
        return ParsedUpload(results=[result], media=[media])

    ext = extension(filename)
    if ext == ".zip":
        return _parse_zip(filename, data, source_type)
    if source_type == "whatsapp":
        return ParsedUpload(results=[parse_whatsapp(data, filename)])
    if source_type == "instagram":
        return ParsedUpload(results=[parse_instagram(data, filename)])

    document_parsers = {
        ".pdf": documents.parse_pdf,
        ".docx": documents.parse_docx,
        ".eml": documents.parse_eml,
        ".json": documents.parse_json,
        ".csv": documents.parse_csv,
    }
    if ext in document_parsers:
        return ParsedUpload(results=[document_parsers[ext](data, filename)])
    text_type = source_type if source_type in ("journal", "document") else "journal"
    return ParsedUpload(results=[documents.parse_text_file(data, filename, text_type)])
