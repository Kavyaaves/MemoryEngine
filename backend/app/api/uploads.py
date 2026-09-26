"""Upload files and follow their processing jobs.

    POST /api/uploads                  save files → create one IngestionJob each → queue them
    GET  /api/uploads/jobs             job list (the Upload page polls this)
    GET  /api/uploads/jobs/{id}
    POST /api/uploads/jobs/{id}/retry  re-queue a failed job
"""

import asyncio
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.security import current_user
from app.config import get_settings
from app.core.ratelimit import rate_limit
from app.db import get_session
from app.ingestion.dispatch import SOURCE_TYPES, detect_source_type, extension
from app.ingestion.records import sha256_hex
from app.media.storage import get_storage, object_key
from app.models import AuditLog, IngestionJob, JobStatus, User
from app.schemas.api import JobOut, JobsOut
from app.workers.queue import enqueue_ingestion

router = APIRouter(prefix="/uploads", tags=["uploads"])

ALLOWED_EXTENSIONS = {
    ".txt", ".md", ".markdown", ".json", ".csv", ".pdf", ".docx", ".eml", ".zip",
    ".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif", ".gif",
    ".mp3", ".m4a", ".aac", ".wav", ".ogg", ".opus", ".flac", ".amr",
    ".mp4", ".mov", ".mkv", ".webm", ".3gp", ".avi",
}
# The first bytes of binary formats ("magic numbers"), so a renamed program can't pass as a photo.
EXPECTED_MAGIC = {".pdf": [b"%PDF"], ".zip": [b"PK\x03\x04", b"PK\x05\x06"], ".docx": [b"PK\x03\x04"],
                  ".png": [b"\x89PNG"], ".jpg": [b"\xff\xd8\xff"], ".jpeg": [b"\xff\xd8\xff"], ".gif": [b"GIF8"]}
EXECUTABLE_MAGIC = [b"MZ", b"\x7fELF", b"#!/"]  # Windows .exe, Linux binaries, shell scripts


def validate_file(filename: str, data: bytes) -> None:
    ext = extension(filename)
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, f"unsupported file type: {filename}")
    if any(data.startswith(magic) for magic in EXECUTABLE_MAGIC):
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, f"executable content rejected: {filename}")
    if ext in EXPECTED_MAGIC and not any(data.startswith(magic) for magic in EXPECTED_MAGIC[ext]):
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, f"file content does not match its type: {filename}")


async def _create_job(session: AsyncSession, user: User, upload: UploadFile, source_type: str,
                      self_name: str | None, file_modified_ms: int | None) -> IngestionJob:
    max_bytes = get_settings().max_upload_mb * 1024 * 1024
    name = (upload.filename or "upload").replace("\\", "/")
    if upload.size and upload.size > max_bytes:  # reject before reading a huge file into memory
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, f"{name} is larger than {max_bytes // 2**20} MB")
    data = await upload.read()
    if len(data) > max_bytes:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, f"{name} is larger than {max_bytes // 2**20} MB")
    validate_file(name, data)

    file_hash = sha256_hex(data)
    detected_type = await asyncio.to_thread(detect_source_type, name, data, source_type)
    earlier_import = (await session.execute(select(IngestionJob.id).where(
        IngestionJob.user_id == user.id, IngestionJob.file_hash == file_hash,
        IngestionJob.status == JobStatus.COMPLETED))).first()
    key = object_key(user.id, "uploads", file_hash, name)

    if earlier_import:  # exact same file imported before: nothing to do
        return IngestionJob(user_id=user.id, filename=name[:1000], source_type=detected_type, object_key=key,
                            file_hash=file_hash, mime_type=upload.content_type, status=JobStatus.DUPLICATE,
                            progress=1.0, stats={"duplicate_of": str(earlier_import[0])})
    await get_storage().put(key, data, upload.content_type)
    return IngestionJob(user_id=user.id, filename=name[:1000], source_type=detected_type, object_key=key,
                        file_hash=file_hash, mime_type=upload.content_type,
                        options={"self_name": self_name, "file_modified_ms": file_modified_ms},
                        status=JobStatus.QUEUED)


@router.post("", response_model=JobsOut, status_code=202)
async def upload(files: list[UploadFile] = File(...), source_type: str = Form("auto"),
                 self_name: str | None = Form(None), last_modified: list[int] = Form([]),
                 user: User = Depends(rate_limit("uploads", 60)), session: AsyncSession = Depends(get_session)):
    """`last_modified` (optional): each file's "last modified" time in epoch milliseconds, in the
    same order as `files`. The browser knows it, the uploaded bytes don't — photos use it as a date."""
    if source_type not in SOURCE_TYPES:
        raise HTTPException(422, f"source_type must be one of {sorted(SOURCE_TYPES)}")
    jobs = []
    for index, file in enumerate(files):
        modified_ms = last_modified[index] if index < len(last_modified) and last_modified[index] > 0 else None
        jobs.append(await _create_job(session, user, file, source_type, self_name, modified_ms))
    session.add_all(jobs)
    session.add(AuditLog(user_id=user.id, action="upload", detail={"files": [job.filename for job in jobs]}))
    await session.commit()

    for job in jobs:  # queue only after commit, so the worker can find the job rows
        if job.status == JobStatus.QUEUED:
            await enqueue_ingestion(job.id)
    for job in jobs:
        await session.refresh(job)  # inline processing may already have changed the status
    return JobsOut(jobs=[JobOut.model_validate(job) for job in jobs])


@router.get("/jobs", response_model=list[JobOut])
async def list_jobs(user: User = Depends(current_user), session: AsyncSession = Depends(get_session)):
    rows = await session.execute(select(IngestionJob).where(IngestionJob.user_id == user.id)
                                 .order_by(IngestionJob.created_at.desc()).limit(200))
    return rows.scalars().all()


async def _get_own_job(session: AsyncSession, user: User, job_id: uuid.UUID) -> IngestionJob:
    job = await session.get(IngestionJob, job_id)
    if job is None or job.user_id != user.id:  # someone else's job looks exactly like a missing one
        raise HTTPException(404, "job not found")
    return job


@router.get("/jobs/{job_id}", response_model=JobOut)
async def get_job(job_id: uuid.UUID, user: User = Depends(current_user), session: AsyncSession = Depends(get_session)):
    return await _get_own_job(session, user, job_id)


@router.post("/jobs/{job_id}/retry", response_model=JobOut)
async def retry_job(job_id: uuid.UUID, user: User = Depends(current_user),
                    session: AsyncSession = Depends(get_session)):
    job = await _get_own_job(session, user, job_id)
    if job.status != JobStatus.FAILED:
        raise HTTPException(409, "only failed jobs can be retried")
    job.status, job.progress, job.error = JobStatus.QUEUED, 0.0, None
    await session.commit()
    await enqueue_ingestion(job.id)
    await session.refresh(job)
    return job
