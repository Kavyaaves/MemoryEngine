"""GET /api/media/raw — serves stored media behind a signed, expiring link.

The browser can't read DynamoDB (or the local development folder) itself, so the API hands out
short-lived signed links to this route (see media/storage.py) and sends the file bytes.
"""

import mimetypes

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from app.media.storage import get_storage

router = APIRouter(prefix="/media", tags=["media"])


@router.get("/raw")
async def raw_media(key: str, exp: int, sig: str):
    """No login needed: the HMAC signature *is* the permission, and it expires."""
    storage = get_storage()
    if not storage.links.verify(key, exp, sig):
        raise HTTPException(403, "invalid or expired link")
    try:
        data = await storage.get(key)
    except FileNotFoundError as exc:
        raise HTTPException(404, "file not found") from exc
    content_type = mimetypes.guess_type(key)[0] or "application/octet-stream"
    return Response(data, media_type=content_type, headers={"Cache-Control": "private, max-age=600"})
