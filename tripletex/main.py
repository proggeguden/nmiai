import base64
import os
import sys
import time
import traceback
import uuid
from contextlib import asynccontextmanager
from typing import List, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

load_dotenv()

from logger import get_logger, setup_logging
from agent import build_agent, run_agent
from tools import set_credentials, get_stats

setup_logging()
log = get_logger("tripletex.server")

_agent = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _agent
    log.info("Starting up — building agent...")
    _agent = build_agent()
    log.info("Agent ready.")
    yield
    log.info("Shutting down.")


app = FastAPI(lifespan=lifespan)


class FileAttachment(BaseModel):
    filename: str
    content_base64: str
    mime_type: str


class TripletexCredentials(BaseModel):
    base_url: str
    session_token: str


class SolveRequest(BaseModel):
    prompt: str
    files: Optional[List[FileAttachment]] = []
    tripletex_credentials: TripletexCredentials


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/solve")
async def solve(request: Request, body: SolveRequest):
    request_id = str(uuid.uuid4())[:8]
    t_start = time.monotonic()

    log.info(
        "=== New /solve request ===",
        request_id=request_id,
        prompt=body.prompt,
        files=[f.filename for f in (body.files or [])],
        base_url=body.tripletex_credentials.base_url,
        token_prefix=body.tripletex_credentials.session_token[:8] + "...",
    )
    # Log the full prompt with clear delimiters so it can be copied as a test example
    log.info(
        ">>>PROMPT_START<<<\n"
        f"{body.prompt}\n"
        ">>>PROMPT_END<<<",
        request_id=request_id,
    )

    # Optional API key protection
    api_key = os.environ.get("API_KEY")
    if api_key:
        auth_header = request.headers.get("Authorization", "")
        if auth_header != f"Bearer {api_key}":
            log.warning("Unauthorized request", request_id=request_id)
            raise HTTPException(status_code=401, detail="Unauthorized")

    # Set Tripletex credentials for this request
    set_credentials(
        base_url=body.tripletex_credentials.base_url,
        session_token=body.tripletex_credentials.session_token,
    )

    # Build file context string for the agent
    file_context = ""
    for f in body.files or []:
        try:
            content = base64.b64decode(f.content_base64)
            if f.mime_type.startswith("text/") or f.mime_type == "application/json":
                decoded = content.decode("utf-8", errors="replace")
                log.info(f"File decoded: {f.filename}", mime_type=f.mime_type, size_bytes=len(content), request_id=request_id)
                file_context += f"\n[File: {f.filename}]\n{decoded}\n"
            else:
                log.info(f"File attached (binary): {f.filename}", mime_type=f.mime_type, size_bytes=len(content), request_id=request_id)
                file_context += f"\n[File: {f.filename} ({f.mime_type}, {len(content)} bytes) — binary file, extract relevant data if needed]\n"
        except Exception as e:
            log.warning(f"Could not decode file: {f.filename}", error=str(e), request_id=request_id)
            file_context += f"\n[File: {f.filename} — could not decode]\n"

    if file_context:
        log.info(
            ">>>FILES_START<<<\n"
            f"{file_context}\n"
            ">>>FILES_END<<<",
            request_id=request_id,
        )

    # Run the agent
    try:
        run_agent(_agent, body.prompt, file_context)
    except Exception as e:
        elapsed_ms = round((time.monotonic() - t_start) * 1000)
        log.error(
            "Agent raised an exception",
            request_id=request_id,
            elapsed_ms=elapsed_ms,
            error=str(e),
            traceback=traceback.format_exc(),
        )
        # Still return completed — we don't want to timeout; partial work may have happened
        sys.stdout.flush()
        return JSONResponse({"status": "completed"})

    stats = get_stats()
    elapsed_ms = round((time.monotonic() - t_start) * 1000)
    log.info(
        "=== Request completed ===",
        request_id=request_id,
        elapsed_ms=elapsed_ms,
        api_calls=stats["api_calls"],
        api_errors=stats["api_errors"],
    )

    sys.stdout.flush()
    return JSONResponse({"status": "completed"})
