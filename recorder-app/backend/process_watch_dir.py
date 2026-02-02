"""
Processing script for meeting recorder (Task 4).

Runs continuously:
- Real-time monitoring of watch_dir/: when a new .wav appears, process it
  (move to processing/, run speech_identification pipeline, then move to processed/
  and set status COMPLETED or FAILED accordingly; all files end up in processed/).
- Periodic retry of failed: every RETRY_INTERVAL seconds, move files in processed/
  whose DB status is FAILED and older than RETRY_AFTER_SECONDS back to watch_dir/
  and set status to UPLOADED so they are processed again.

Requires: speech_identification dependencies (pyannote, etc.). Set HF_TOKEN or
HUGGINGFACE_HUB_TOKEN for the pipeline.

Usage (from repo root or backend/):
  python backend/process_watch_dir.py
  cd backend && python process_watch_dir.py
"""

import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from watchdog.observers import Observer
from watchdog.events import (
    FileSystemEventHandler,
    FileSystemEvent,
    FileCreatedEvent,
    FileMovedEvent,
    DirModifiedEvent,
)

# Same paths as app.py so we use the same DB and dirs
BASE_DIR = Path(__file__).resolve().parent
REPO_ROOT = BASE_DIR.parent
DB_PATH = BASE_DIR / "db.sqlite"
WATCH_DIR = BASE_DIR / "watch_dir"
PROCESSING_DIR = BASE_DIR / "processing"
PROCESSED_DIR = BASE_DIR / "processed"
FAILED_DIR = BASE_DIR / "failed"

# speech_identification pipeline config
PIPELINE_SCRIPT = REPO_ROOT / ".." / "speech_identification" / "pipeline.py"
SAMPLE_EMBEDDINGS_DIR = Path("/home/ubuntu/Aditya/PyannoteAudio/sample_embeddings_dir")

# Retry failed: check every RETRY_INTERVAL seconds; retry if file in processed/ has DB status FAILED and is older than RETRY_AFTER_SECONDS
RETRY_INTERVAL_SECONDS = 60
RETRY_AFTER_SECONDS = 300  # 5 minutes

# Delay (seconds) after a new file appears in watch_dir before processing (allows upload to finish)
WATCH_DIR_DEBOUNCE_SECONDS = 2

# Fallback: poll watch_dir every N seconds for .wav files (in case watchdog events are missed, e.g. copy/paste)
POLL_WATCH_DIR_INTERVAL_SECONDS = 10


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _set_status(meeting_id: str, status: str, error: str | None = None) -> None:
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "UPDATE meetings SET status = ?, updated_at = ?, error = ? WHERE id = ?",
            (status, _iso_now(), error, meeting_id),
        )
        conn.commit()


def _get_status(meeting_id: str) -> str | None:
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute(
            "SELECT status FROM meetings WHERE id = ?", (meeting_id,)
        ).fetchone()
    return row[0] if row else None


def _run_pipeline(meeting_audio_path: Path, work_dir: Path) -> subprocess.CompletedProcess[bytes]:
    """Run speech_identification pipeline; work_dir is temp and will be deleted by caller."""
    cmd = [
        sys.executable,
        str(PIPELINE_SCRIPT),
        str(meeting_audio_path),
        "--sample-embeddings-dir",
        str(SAMPLE_EMBEDDINGS_DIR),
        "-w",
        str(work_dir),
    ]
    token = os.environ.get("HF_TOKEN") or os.environ.get("HUGGINGFACE_HUB_TOKEN")
    if token:
        cmd.extend(["-t", token])
    return subprocess.run(cmd, cwd=str(REPO_ROOT), capture_output=True, check=False)


def process_one(wav_path: Path) -> None:
    """
    Process a single WAV: move to processing/, run speech_identification pipeline
    (temp work dir created and deleted), then move to processed/ and set status
    COMPLETED or FAILED. All files (success and failure) end up in processed/.
    Skips if status is already COMPLETED or PROCESSING.
    """
    meeting_id = wav_path.stem
    if _get_status(meeting_id) in ("COMPLETED", "PROCESSING"):
        return
    if not wav_path.is_file():
        return

    _set_status(meeting_id, "PROCESSING", None)
    processing_path = PROCESSING_DIR / wav_path.name
    try:
        wav_path.rename(processing_path)
    except OSError as e:
        _set_status(meeting_id, "FAILED", str(e))
        return

    work_dir = Path(tempfile.mkdtemp())
    try:
        result = _run_pipeline(processing_path, work_dir)
        if result.returncode != 0:
            stderr = result.stderr.decode("utf-8", errors="replace").strip() if result.stderr else ""
            raise RuntimeError(stderr or f"Pipeline exited with code {result.returncode}")
        processed_path = PROCESSED_DIR / wav_path.name
        processing_path.rename(processed_path)
        _set_status(meeting_id, "COMPLETED", None)
    except Exception as e:
        # Move to processed/ like successful runs; status is FAILED
        processed_path = PROCESSED_DIR / wav_path.name
        try:
            processing_path.rename(processed_path)
        except OSError:
            pass
        _set_status(meeting_id, "FAILED", str(e))
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


def retry_failed() -> None:
    """Move processed/ files with DB status FAILED (older than RETRY_AFTER_SECONDS) back to watch_dir and set status to UPLOADED."""
    if not PROCESSED_DIR.is_dir():
        return
    now = time.time()
    for wav_path in PROCESSED_DIR.glob("*.wav"):
        try:
            if _get_status(wav_path.stem) != "FAILED":
                continue
            if now - wav_path.stat().st_mtime >= RETRY_AFTER_SECONDS:
                meeting_id = wav_path.stem
                dest = WATCH_DIR / wav_path.name
                wav_path.rename(dest)
                _set_status(meeting_id, "UPLOADED", None)
        except OSError:
            pass


class WatchDirHandler(FileSystemEventHandler):
    """On new .wav in watch_dir, wait DEBOUNCE then process."""

    def __init__(self) -> None:
        super().__init__()
        self._pending: dict[str, float] = {}
        self._lock = threading.Lock()

    def _schedule(self, src_path: str, *, immediate: bool = False) -> None:
        path = Path(src_path)
        if path.suffix.lower() != ".wav":
            return
        try:
            if not path.is_file():
                return
        except OSError:
            return
        key = path.resolve().as_posix()
        with self._lock:
            # immediate=True: treat as already debounced (e.g. existing files on startup)
            self._pending[key] = 0.0 if immediate else time.monotonic()

    def _schedule_path_if_in_watch_dir(self, path_str: str | bytes | None) -> None:
        if path_str is None:
            return
        path_str = path_str.decode() if isinstance(path_str, bytes) else path_str
        path = Path(path_str)
        try:
            resolved = path.resolve()
            if WATCH_DIR not in resolved.parents and resolved.parent != WATCH_DIR:
                return
        except (OSError, RuntimeError):
            return
        self._schedule(path_str)

    def _dispatch(self, event: FileSystemEvent) -> None:
        # Handle created, moved-into, and directory-modified (some systems use this for copy/paste)
        src = event.src_path.decode() if isinstance(event.src_path, bytes) else event.src_path
        if isinstance(event, FileCreatedEvent):
            self._schedule_path_if_in_watch_dir(src)
        elif isinstance(event, FileMovedEvent):
            dest = event.dest_path
            if dest is not None:
                self._schedule_path_if_in_watch_dir(dest)
            self._schedule_path_if_in_watch_dir(src)
        elif isinstance(event, DirModifiedEvent):
            # Fallback: directory changed (e.g. file pasted); scan for new .wav
            if Path(src) == WATCH_DIR:
                self.scan_watch_dir(immediate=False)
        super()._dispatch(event)  # type: ignore[misc]

    def scan_watch_dir(self, *, immediate: bool = False) -> None:
        """Add any .wav in watch_dir to pending (for startup and fallback poll). immediate=True: process on next process_pending (for existing files on startup)."""
        if not WATCH_DIR.is_dir():
            return
        for wav_path in WATCH_DIR.glob("*.wav"):
            if wav_path.is_file():
                self._schedule(str(wav_path), immediate=immediate)

    def process_pending(self) -> None:
        """Process files that have been in watch_dir for at least WATCH_DIR_DEBOUNCE_SECONDS."""
        now = time.monotonic()
        with self._lock:
            to_process = [
                k for k, t in self._pending.items()
                if t == 0.0 or now - t >= WATCH_DIR_DEBOUNCE_SECONDS
            ]
            for k in to_process:
                del self._pending[k]
        for src in to_process:
            p = Path(src)
            if p.is_file():
                process_one(p)


def ensure_dirs() -> None:
    for d in (WATCH_DIR, PROCESSING_DIR, PROCESSED_DIR, FAILED_DIR):
        d.mkdir(parents=True, exist_ok=True)


def run_forever() -> None:
    """
    Run the watch_dir loop and retry logic until KeyboardInterrupt or process exit.
    Can be called from a background thread (e.g. when backend starts) or standalone.
    """
    ensure_dirs()
    handler = WatchDirHandler()
    # Process existing .wav files in watch_dir on startup (watchdog does not emit events for them)
    handler.scan_watch_dir(immediate=True)
    observer = Observer()
    observer.schedule(handler, str(WATCH_DIR), recursive=False)
    observer.start()

    last_retry = 0.0
    last_poll = 0.0
    try:
        while True:
            handler.process_pending()
            now = time.monotonic()
            if now - last_retry >= RETRY_INTERVAL_SECONDS:
                retry_failed()
                last_retry = now
            # Fallback poll: some systems don't emit events for move/paste; scan watch_dir periodically
            if now - last_poll >= POLL_WATCH_DIR_INTERVAL_SECONDS:
                handler.scan_watch_dir(immediate=False)
                last_poll = now
            time.sleep(WATCH_DIR_DEBOUNCE_SECONDS)
    except KeyboardInterrupt:
        pass
    finally:
        observer.stop()
        observer.join()


def main() -> None:
    run_forever()


if __name__ == "__main__":
    main()
