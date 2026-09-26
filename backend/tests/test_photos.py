"""Photos use metadata only: EXIF dates, the file name and the file's modified time."""

import io
from datetime import UTC, datetime

from PIL import Image

from app.ingestion.photos import (
    EXIF_DATETIME,
    EXIF_DATETIME_ORIGINAL,
    EXIF_SUB_IFD,
    caption_status,
    photo_metadata,
    photo_text,
    read_exif_dates,
)


def _jpeg(taken: str | None = None, changed: str | None = None) -> bytes:
    exif = Image.Exif()
    if changed:
        exif[EXIF_DATETIME] = changed
    if taken:
        exif.get_ifd(EXIF_SUB_IFD)[EXIF_DATETIME_ORIGINAL] = taken
    out = io.BytesIO()
    Image.new("RGB", (4, 4)).save(out, "JPEG", exif=exif)
    return out.getvalue()


def test_reads_exif_dates():
    taken, changed = read_exif_dates(_jpeg("2023:12:25 09:30:00", "2024:01:02 10:00:00"))
    assert taken == datetime(2023, 12, 25, 9, 30)
    assert changed == datetime(2024, 1, 2, 10, 0)


def test_no_exif_or_not_an_image():
    assert read_exif_dates(_jpeg()) == (None, None)
    assert read_exif_dates(b"not an image at all") == (None, None)


def test_date_priority():
    modified = datetime(2022, 5, 1, tzinfo=UTC)
    timestamp, meta = photo_metadata("a.jpg", _jpeg("2023:12:25 09:30:00"), datetime(2021, 1, 1), modified)
    assert meta["date_source"] == "exif_taken" and timestamp.year == 2023

    timestamp, meta = photo_metadata("IMG-20210101.jpg", _jpeg(), datetime(2021, 1, 1), modified)
    assert meta["date_source"] == "filename" and timestamp.year == 2021

    timestamp, meta = photo_metadata("a.jpg", _jpeg(), None, modified)
    assert meta["date_source"] == "file_modified" and timestamp == modified
    assert meta["filename"] == "a.jpg" and meta["file_modified_at"] == modified.isoformat()

    timestamp, meta = photo_metadata("a.jpg", _jpeg(), None, None)
    assert meta["date_source"] == "uploaded" and timestamp.tzinfo is not None


def test_caption_status_and_text():
    assert caption_status({}) == "none"
    assert caption_status({"caption": "beach"}) == "pending"
    assert caption_status({"caption": "beach", "caption_ingested": "beach"}) == "ingested"
    assert caption_status({"caption": "", "caption_ingested": "beach"}) == "pending"  # cleared: re-ingest
    assert photo_text("a.jpg") == "[photo] a.jpg"
    assert photo_text("a.jpg", "Goa trip") == "Goa trip\n[photo] a.jpg"
