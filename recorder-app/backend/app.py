"""
Meeting recorder backend — FastAPI app.

- GET /health — liveness check
- POST /meetings — upload WAV (Task 2)
- GET /meetings/{id}/status — get meeting status (Task 3)
- GET /meetings — list recent meetings (Task 3)

SQLite: backend/db.sqlite, table meetings.
Dirs (created on startup): watch_dir/, processing/, processed/, failed/.

On startup, the watch_dir processing loop runs in a background thread (process_watch_dir.run_forever).
"""

import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

try:
    from . import process_watch_dir
except ImportError:
    import process_watch_dir  # when run as "uvicorn app:app" from backend/

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

# Base path: directory where app.py lives (backend/)
BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "db.sqlite"
WATCH_DIR = BASE_DIR / "watch_dir"
PROCESSING_DIR = BASE_DIR / "processing"
PROCESSED_DIR = BASE_DIR / "processed"
FAILED_DIR = BASE_DIR / "failed"
FRONTEND_DIST = BASE_DIR.parent / "frontend" / "dist"

app = FastAPI(
    title="Meeting Recorder API",
    description="Upload meeting WAVs and track processing status.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def ensure_dirs() -> None:
    """Create watch_dir, processing, processed, failed if they don't exist."""
    for d in (WATCH_DIR, PROCESSING_DIR, PROCESSED_DIR, FAILED_DIR):
        d.mkdir(parents=True, exist_ok=True)


def init_db() -> None:
    """Create meetings table if it doesn't exist."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS meetings (
                id TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                error TEXT
            )
            """
        )
        conn.commit()


@app.on_event("startup")
def startup() -> None:
    ensure_dirs()
    init_db()
    # Run watch_dir processing loop in background (real-time monitoring + retry failed)
    thread = threading.Thread(target=process_watch_dir.run_forever, daemon=True)
    thread.start()


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness check for Task 1 verification."""
    return {"status": "ok"}


def _iso_now() -> str:
    """Current UTC time as ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat()


@app.post("/meetings")
async def upload_meeting(file: UploadFile = File(..., alias="file")) -> dict[str, str]:
    """
    Upload a WAV file. Saves to watch_dir/{id}.wav and creates a meeting row with status UPLOADED.
    Returns { "id": "<uuid>", "status": "UPLOADED" }.
    """
    if not file.filename or not file.filename.lower().endswith(".wav"):
        raise HTTPException(
            status_code=400,
            detail="Missing or invalid file: must upload a .wav file (key: file)",
        )

    meeting_id = str(uuid.uuid4())
    dest = WATCH_DIR / f"{meeting_id}.wav"
    now = _iso_now()

    try:
        contents = await file.read()
        dest.write_bytes(contents)
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"Failed to save file: {e}") from e

    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute(
                """
                INSERT INTO meetings (id, status, created_at, updated_at, error)
                VALUES (?, ?, ?, ?, NULL)
                """,
                (meeting_id, "UPLOADED", now, now),
            )
            conn.commit()
    except sqlite3.Error as e:
        # Best-effort cleanup: remove file if DB insert fails
        dest.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail=f"Failed to record meeting: {e}") from e

    return {"id": meeting_id, "status": "UPLOADED"}


@app.get("/meetings/{meeting_id}/status")
def get_meeting_status(meeting_id: str) -> dict:
    """
    Return meeting status. Response: { id, status, created_at, updated_at, error }.
    404 if meeting_id not found.
    """
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT id, status, created_at, updated_at, error FROM meetings WHERE id = ?",
            (meeting_id,),
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Meeting not found")
    return {
        "id": row["id"],
        "status": row["status"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "error": row["error"],
    }


@app.get("/meetings")
def list_meetings() -> dict:
    """
    Return recent meetings (last 50, newest first).
    Response: { meetings: [ { id, status, created_at }, ... ] }.
    """
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT id, status, created_at
            FROM meetings
            ORDER BY created_at DESC
            LIMIT 50
            """
        ).fetchall()
    return {
        "meetings": [
            {"id": r["id"], "status": r["status"], "created_at": r["created_at"]}
            for r in rows
        ]
    }


# Serve built frontend (optional: only if frontend/dist exists)
if FRONTEND_DIST.is_dir():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")

    @app.get("/{full_path:path}")
    def serve_spa(full_path: str):
        """Serve index.html for all non-API routes (SPA fallback)."""
        return FileResponse(FRONTEND_DIST / "index.html")
