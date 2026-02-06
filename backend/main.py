from __future__ import annotations

import logging
from typing import Optional

import httpx
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel


OLLAMA_API_URL = "http://localhost:11434/api/generate"
OLLAMA_TAGS_URL = "http://localhost:11434/api/tags"
DEFAULT_MODEL = "codellama:7b"
MAX_FILE_SIZE = 2 * 1024 * 1024
OLLAMA_TIMEOUT = 300.0

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-8s  %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(title="AI Code Doctor", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class AskResponse(BaseModel):
    model: str
    question: str
    filename: str
    answer: str


SYSTEM_PROMPT = (
    "You are an expert programming tutor and code reviewer. "
    "You provide clear, detailed, and actionable answers. "
    "Always reference specific line numbers or code snippets when relevant."
)


def build_prompt(code, question, filename):
    return (
        f"{SYSTEM_PROMPT}\n\n"
        f"--- FILE: {filename} ---\n"
        f"```\n{code}\n```\n\n"
        f"--- TASK ---\n{question}\n"
    )


async def call_ollama(prompt, model=DEFAULT_MODEL):
    payload = {"model": model, "prompt": prompt, "stream": False}

    try:
        async with httpx.AsyncClient(timeout=OLLAMA_TIMEOUT) as client:
            logger.info("Calling Ollama (%s)...", model)
            resp = await client.post(OLLAMA_API_URL, json=payload)
            resp.raise_for_status()
    except httpx.ConnectError:
        raise HTTPException(503, f"Can't reach Ollama at {OLLAMA_API_URL}. Is it running?")
    except httpx.TimeoutException:
        raise HTTPException(504, "Ollama timed out. Try a smaller file or simpler question.")
    except httpx.HTTPStatusError as exc:
        raise HTTPException(502, f"Ollama error: {exc.response.text}")

    answer = resp.json().get("response", "").strip()
    if not answer:
        raise HTTPException(502, "Ollama returned an empty response.")
    return answer


@app.get("/")
async def root():
    return {"status": "ok", "message": "Backend is running.", "usage": "POST /ask"}


@app.get("/models")
async def list_models():
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(OLLAMA_TAGS_URL)
            resp.raise_for_status()
    except httpx.ConnectError:
        raise HTTPException(503, f"Can't reach Ollama at {OLLAMA_TAGS_URL}. Is it running?")
    except httpx.HTTPStatusError as exc:
        raise HTTPException(502, f"Ollama error: {exc.response.text}")

    raw = resp.json().get("models", [])

    models = []
    for m in raw:
        name = m.get("name", "")
        size_gb = round(m.get("size", 0) / (1024 ** 3), 1)
        models.append({"name": name, "size": f"{size_gb} GB", "modified_at": m.get("modified_at", "")})

    # default model goes first, rest alphabetical
    models.sort(key=lambda x: (x["name"] != DEFAULT_MODEL, x["name"]))
    return {"default": DEFAULT_MODEL, "models": models}


@app.post("/ask", response_model=AskResponse)
async def ask(
    file: UploadFile = File(...),
    question: Optional[str] = Form("Explain this code, find bugs, and suggest improvements."),
    model: Optional[str] = Form(DEFAULT_MODEL),
):
    if not file.filename or not file.filename.strip():
        raise HTTPException(400, "No file uploaded.")

    raw = await file.read()
    if len(raw) > MAX_FILE_SIZE:
        raise HTTPException(413, f"File too large ({len(raw)} bytes). Limit is {MAX_FILE_SIZE}.")

    try:
        code = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(400, "File doesn't look like a text file.")

    if not code.strip():
        raise HTTPException(400, "File is empty.")

    question = (question or "").strip() or "Explain this code, find bugs, and suggest improvements."
    model = (model or "").strip() or DEFAULT_MODEL

    logger.info("Got '%s' (%d bytes) — %s", file.filename, len(raw), question[:80])

    prompt = build_prompt(code, question, file.filename)
    answer = await call_ollama(prompt, model)

    return AskResponse(model=model, question=question, filename=file.filename, answer=answer)
