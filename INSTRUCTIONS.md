# Developer Instructions

This is a walkthrough of how the whole app works, file by file, so future-me (or anyone else) can pick it up without guessing.

---

## Overview

The app (AI Code Doctor) is a local AI code reviewer. The user uploads a code file through the browser, picks an action (or types a custom question), the frontend sends it to a FastAPI backend, the backend forwards it to Ollama (a local LLM runner), and the response gets displayed back in the UI.

```
Browser (index.html)
    |
    |  POST /ask  (multipart form: file + question + model)
    v
FastAPI (main.py)
    |
    |  POST to Ollama's /api/generate
    v
Ollama (localhost:11434)
    |
    |  LLM processes the prompt
    v
Response flows back up the same chain
```

No database, no auth, no external APIs. It all stays local.

---

## File Breakdown

### `backend/main.py`

This is the entire backend — a single FastAPI app.

**Config at the top:**
- `OLLAMA_API_URL` — where Ollama listens for generation requests (`localhost:11434/api/generate`)
- `OLLAMA_TAGS_URL` — endpoint to list installed models (`localhost:11434/api/tags`)
- `DEFAULT_MODEL` — falls back to `codellama:7b` if no model is specified
- `MAX_FILE_SIZE` — rejects uploads over 2MB
- `OLLAMA_TIMEOUT` — 5 minute timeout since code analysis can be slow

**Routes:**

| Route | Method | What it does |
|-------|--------|-------------|
| `/` | GET | Health check. Returns a JSON "ok" message. |
| `/models` | GET | Calls Ollama's `/api/tags`, reformats the response into a cleaner list with model name, size in GB, and modified date. Sorts them with the default model first. |
| `/ask` | POST | The main endpoint. Accepts a file upload, a question string, and a model name via multipart form data. Reads the file, builds a prompt, sends it to Ollama, returns the answer. |

**How the prompt is built (`build_prompt`):**

It concatenates a system prompt (telling the LLM to act as a code tutor), the file contents inside a code block, and the user's question. Pretty straightforward — the LLM gets the full file plus context about what the user wants.

**Error handling in `call_ollama`:**

- Connection refused → 503 (Ollama probably isn't running)
- Timeout → 504 (file too big or model too slow)
- HTTP error from Ollama → 502 (something went wrong on Ollama's end)
- Empty response → 502 (model returned nothing)

**CORS** is wide open (`allow_origins=["*"]`) since the frontend runs on a different port locally. Would need tightening for any real deployment.

---

### `frontend/index.html`

Everything is in one file — HTML, CSS, and JS. No build step, no framework, no npm.

**Layout (two panels):**

The UI is a split-pane layout inspired by VS Code:
- **Left panel** — shows the uploaded code with line numbers
- **Right panel** — action buttons, custom question input, and the AI response thread

**Top bar** shows the app name, the currently loaded filename (with a green dot when active), and a model selector dropdown that auto-populates from the `/models` endpoint.

**Bottom status bar** shows connection status, current model, and file stats (line count).

**CSS variables** at the top of `<style>` define the dark theme. All colors reference these variables, so if you wanted to change the theme you'd only need to edit the `:root` block.

**Key JS functions:**

| Function | What it does |
|----------|-------------|
| `fetchModels()` | Hits `GET /models` on page load, populates the model dropdown |
| `loadFile(file)` | Reads an uploaded file with FileReader, stores the content |
| `showCode()` | Renders the code in the left panel with line numbers |
| `clearFile()` | Resets everything back to the upload state |
| `sendRequest(question)` | Sends a POST to `/ask` with the file + question, displays the response |
| `addMessage(role, text)` | Appends a chat bubble to the response area |
| `setStatus(text, state)` | Updates the status bar text and indicator color |

**Action buttons** (Explain, Find Bugs, Improve, Refactor, Document, Security) each have a pre-written prompt stored in `ACTION_PROMPTS`. When clicked, they call `sendRequest()` with that prompt. The custom text input lets you write your own question instead.

**File upload** works via click-to-browse or drag-and-drop. The accepted file types are listed in the `accept` attribute on the hidden file input. It reads the file as text — binary files will fail gracefully on the backend.

**Loading state** — while waiting for a response, buttons are disabled, a bouncing dots animation shows, and the status bar pulses orange. When done, the response appears as a chat message.

**Responsive** — on screens under 768px the panels stack vertically instead of side by side.

---

### `requirements.txt`

Just four packages:
- `fastapi` — the web framework
- `uvicorn` — ASGI server to run FastAPI
- `httpx` — async HTTP client for calling Ollama
- `python-multipart` — needed for FastAPI to handle file uploads

---

## Running It

You need three things running:

1. **Ollama** — `ollama serve` (default port 11434)
2. **Backend** — `uvicorn backend.main:app --reload --port 8000`
3. **Frontend** — `cd frontend && python -m http.server 3000`

Then open `http://localhost:3000`.

The `--reload` flag on uvicorn makes it auto-restart when you edit `main.py`, which is nice during development.

---

## How the Request Flow Works (step by step)

1. User drops a `.py` file onto the upload zone
2. JS reads it with `FileReader` and displays it in the left panel
3. User clicks "Find Bugs" (or types a custom question)
4. JS creates a `FormData` with the file blob, the question text, and the selected model name
5. JS sends `POST /ask` to the backend
6. Backend reads the uploaded bytes, decodes as UTF-8, validates it's not empty / too large
7. Backend calls `build_prompt()` to wrap the code + question into a structured prompt
8. Backend sends the prompt to Ollama's `/api/generate` (non-streaming, so it waits for the full response)
9. Ollama runs the LLM and returns the generated text
10. Backend wraps it in `AskResponse` JSON and sends it back
11. JS displays the answer as a chat message in the right panel

---

## Things to Know

- **Model selection** — the dropdown only shows models you've already pulled with `ollama pull`. If you haven't pulled any, it falls back to showing `codellama:7b` (which will fail if you haven't pulled it).

- **File size limit** — 2MB max. This is a backend check. If someone tries uploading a huge file, they get a 413 error. You can change `MAX_FILE_SIZE` in `main.py`.

- **Timeout** — 5 minutes. Ollama can be slow on large files or complex questions, especially on CPU-only machines. Adjust `OLLAMA_TIMEOUT` if needed.

- **No streaming** — the response comes back all at once. The UI just waits with a loading animation. Could be improved to stream token-by-token but it's not implemented.

- **No conversation memory** — each request is independent. The LLM doesn't remember previous questions about the same file. Every request sends the full file again.

- **No syntax highlighting** — the code panel shows plain text with line numbers. No tokenization or coloring. Adding highlight.js would be a straightforward improvement.

---

## If You Want to Change Things

**Add a new action button:**
1. Add a `<button>` in the action bar in `index.html` (copy an existing one, change the `data-action` and class)
2. Add the matching prompt in the `ACTION_PROMPTS` object in the JS

**Change the default model:**
Update `DEFAULT_MODEL` in `main.py`. The frontend will pick it up from the `/models` response.

**Use a different LLM provider:**
Replace `call_ollama()` in `main.py` with calls to whatever API you want. The rest of the app doesn't care where the answer comes from.

**Add syntax highlighting:**
Drop in highlight.js via CDN in `index.html`, call `hljs.highlightElement()` on the code content div after loading a file.

**Deploy it properly:**
- Serve the frontend through FastAPI itself (with `StaticFiles`) instead of a separate HTTP server
- Lock down CORS to specific origins
- Add rate limiting
- Pin package versions in `requirements.txt`
