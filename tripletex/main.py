import base64
import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import List, Optional

load_dotenv()

from agent import build_agent, run_agent
from tools import set_credentials

_agent = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _agent
    _agent = build_agent()
    yield


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
    # Optional API key protection
    api_key = os.environ.get("API_KEY")
    if api_key:
        auth_header = request.headers.get("Authorization", "")
        if auth_header != f"Bearer {api_key}":
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
                file_context += f"\n[File: {f.filename}]\n{content.decode('utf-8', errors='replace')}\n"
            else:
                file_context += f"\n[File: {f.filename} ({f.mime_type}, {len(content)} bytes) — binary file, extract relevant data if needed]\n"
        except Exception:
            file_context += f"\n[File: {f.filename} — could not decode]\n"

    run_agent(_agent, body.prompt, file_context)

    return JSONResponse({"status": "completed"})
