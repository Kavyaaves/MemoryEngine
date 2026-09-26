"""Ask a question about your memories (the agent).

    POST /api/ask          → the whole answer as JSON
    POST /api/ask/stream   → Server-Sent Events while the agent works:
                             step (progress) · evidence · token (answer text) · done · error
"""

import asyncio
import json

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.graph import run_agent
from app.agents.tools import MemoryTools
from app.ai.providers.router import get_router
from app.core.ratelimit import rate_limit
from app.db import SessionLocal, get_session
from app.models import User
from app.retrieval.hybrid import HybridRetriever
from app.schemas.api import AskIn, AskOut

router = APIRouter(prefix="/ask", tags=["ask"])
KEEP_ALIVE_SECONDS = 15  # stops proxies from closing a quiet connection


def _history(body: AskIn) -> list[tuple[str, str]]:
    return [(turn.role, turn.content) for turn in body.conversation]


@router.post("", response_model=AskOut)
async def ask(body: AskIn, user: User = Depends(rate_limit("ask", 30)), session: AsyncSession = Depends(get_session)):
    ai_router = get_router()
    tools = MemoryTools(session, user.id, HybridRetriever(ai_router))
    return await run_agent(question=body.question, history=_history(body), tools=tools, router=ai_router)


def _sse(event: str, data) -> bytes:
    """One Server-Sent Event: 'event: <name>\\ndata: <json>\\n\\n'."""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n".encode()


@router.post("/stream")
async def ask_stream(body: AskIn, user: User = Depends(rate_limit("ask", 30))):
    """The agent runs in a background task and pushes events into a queue; the response
    reads from that queue and forwards each event to the browser as it arrives."""
    events: asyncio.Queue = asyncio.Queue()
    user_id = user.id

    async def emit(event: str, data) -> None:
        await events.put((event, data))

    async def run() -> None:
        # Its own database session: the request's session closes when streaming starts.
        async with SessionLocal() as session:
            try:
                ai_router = get_router()
                tools = MemoryTools(session, user_id, HybridRetriever(ai_router))
                result = await run_agent(question=body.question, history=_history(body), tools=tools,
                                         router=ai_router, emit=emit)
                await events.put(("done", AskOut.model_validate(result).model_dump(mode="json")))
            except Exception as exc:
                await events.put(("error", {"message": f"{type(exc).__name__}: {exc}"[:500]}))
            finally:
                await events.put(None)  # end of stream

    async def stream():
        agent_task = asyncio.create_task(run())
        try:
            while True:
                try:
                    item = await asyncio.wait_for(events.get(), timeout=KEEP_ALIVE_SECONDS)
                except TimeoutError:
                    yield b": keep-alive\n\n"  # an SSE comment line; the browser ignores it
                    continue
                if item is None:
                    break
                yield _sse(*item)
        finally:
            if not agent_task.done():
                agent_task.cancel()  # the browser disconnected

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
