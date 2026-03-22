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

from logger import get_logger, setup_logging, set_request_id
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
    set_request_id(request_id)  # All log lines from this request will include request_id
    t_start = time.monotonic()

    # Truncate log file at start of each request (fresh log per test)
    log_file = os.environ.get("LOG_FILE")
    if log_file:
        import logging
        for handler in logging.getLogger().handlers:
            if isinstance(handler, logging.FileHandler) and handler.baseFilename.endswith(log_file):
                handler.stream.seek(0)
                handler.stream.truncate(0)
                break

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

    # Build file attachments list for the agent (passed as multimodal content to Gemini)
    file_attachments = []
    for f in body.files or []:
        try:
            content_bytes = base64.b64decode(f.content_base64)
            log.info(f"File attached: {f.filename}", mime_type=f.mime_type, size_bytes=len(content_bytes), request_id=request_id)

            if f.mime_type == "application/pdf":
                # PDFs: extract text server-side for reliable data extraction
                # Gemini with thinking_level=low struggles to parse PDF images
                try:
                    import fitz  # pymupdf
                    doc = fitz.open(stream=content_bytes, filetype="pdf")
                    text = "\n".join(page.get_text() for page in doc)
                    doc.close()
                    log.info(f"PDF text extracted: {len(text)} chars from {f.filename}", request_id=request_id)
                    file_attachments.append({"type": "text", "filename": f.filename, "text": f"\n[Contents of {f.filename}]\n{text}"})
                    # Also send binary so Gemini can see layout if needed
                    file_attachments.append({
                        "type": "binary",
                        "filename": f.filename,
                        "content_base64": f.content_base64,
                        "mime_type": f.mime_type,
                    })
                except Exception as pdf_err:
                    log.warning(f"PDF text extraction failed: {pdf_err}, falling back to binary", request_id=request_id)
                    file_attachments.append({
                        "type": "binary",
                        "filename": f.filename,
                        "content_base64": f.content_base64,
                        "mime_type": f.mime_type,
                    })
            elif f.mime_type.startswith("text/") or f.mime_type in ("application/json", "application/csv", "application/octet-stream"):
                # Text/CSV files: decode and pass as text with filename label
                decoded = content_bytes.decode("utf-8", errors="replace")
                attachment = {"type": "text", "filename": f.filename, "text": f"\n[Contents of {f.filename}]\n{decoded}"}
                # Preserve raw bytes for CSV files (needed for bank statement upload)
                if f.filename.lower().endswith(".csv"):
                    attachment["raw_bytes"] = content_bytes
                file_attachments.append(attachment)
            else:
                # Images, etc: pass as base64 for Gemini multimodal
                file_attachments.append({
                    "type": "binary",
                    "filename": f.filename,
                    "content_base64": f.content_base64,
                    "mime_type": f.mime_type,
                })
        except Exception as e:
            log.warning(f"Could not process file: {f.filename}", error=str(e), request_id=request_id)

    if file_attachments:
        log.info(f"Passing {len(file_attachments)} file(s) to agent", filenames=[a['filename'] for a in file_attachments], request_id=request_id)

    # Run the agent
    try:
        run_agent(_agent, body.prompt, file_attachments, request_id=request_id)
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
