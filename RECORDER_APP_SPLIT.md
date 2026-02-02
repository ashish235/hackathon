# SPLIT: Meeting Recording Web App — Task Breakdown

**Date**: 2025-01-30  
**Input**: RECORDER_APP_PLAN.md

Each task is **independently verifiable**. Dependencies are explicit. Execute in order; verify after each task before moving on.

---

## Dependency Overview

```
T1 (Backend skeleton)
  └─→ T2 (POST /meetings)
  └─→ T3 (GET /meetings/{id}/status, GET /meetings)
        └─→ T4 (Processing script)
T1, T2, T3  ────────────────────→ T5 (Frontend scaffold)
T2, T5 ────────────────────────→ T6 (Frontend: record + WAV)
T2, T6 ────────────────────────→ T7 (Frontend: upload)
T3, T7 ────────────────────────→ T8 (Frontend: status screen)
T3, T8 ────────────────────────→ T9 (Frontend: recent meetings)
T2, T3, T4, T5–T9 ─────────────→ T10 (Integration test)
```

---

## Backend

### Task 1: Backend skeleton

**Goal**: FastAPI app runs; SQLite schema exists; directories exist.

**Deliverables**:
- `backend/app.py` – FastAPI app, CORS, health route (e.g. `GET /health` → `{"status": "ok"}`).
- `backend/requirements.txt` – fastapi, uvicorn, python-multipart, aiosqlite or sqlite3 stdlib.
- SQLite: create `backend/db.sqlite` and table `meetings` (id, status, created_at, updated_at, error).
- On startup: ensure `watch_dir/`, `processing/`, `processed/`, `failed/` exist under backend (or configurable base path).

**Verification**:
1. `cd backend && pip install -r requirements.txt && uvicorn app:app --reload`
2. `curl http://localhost:8000/health` → `{"status":"ok"}` or similar.
3. DB exists: `sqlite3 backend/db.sqlite ".schema meetings"` shows table.
4. Dirs exist: `ls backend/watch_dir backend/processing backend/processed backend/failed` (all present).

**Depends on**: none.

---

### Task 2: POST /meetings (upload WAV)

**Goal**: Client can upload a WAV file; server saves it to `watch_dir/{id}.wav` and inserts a row with status UPLOADED.

**Deliverables**:
- `POST /meetings` – body: multipart form with file (e.g. key `file`). Generate UUID v4 as meeting `id`. Save file as `watch_dir/{id}.wav`. Insert row: id, status=UPLOADED, created_at, updated_at, error=NULL. Return JSON: `{ "id": "<uuid>", "status": "UPLOADED" }`.
- Reject non-WAV or missing file with 400.
- If save fails, respond 500; do not insert row (or insert with FAILED and optional error).

**Verification**:
1. Create a small WAV: `ffmpeg -f lavfi -i anullsrc=r=16000:cl=mono -t 1 -acodec pcm_s16le test.wav` (or use existing small .wav).
2. `curl -X POST http://localhost:8000/meetings -F "file=@test.wav"` → JSON with `id` and `status: "UPLOADED"`.
3. File exists: `ls backend/watch_dir/*.wav` shows `{id}.wav`.
4. DB: `sqlite3 backend/db.sqlite "SELECT id, status FROM meetings;"` shows one row, status UPLOADED.

**Depends on**: T1.

---

### Task 3: GET /meetings/{id}/status and GET /meetings

**Goal**: Callers can read status for one meeting and list recent meetings.

**Deliverables**:
- `GET /meetings/{id}/status` – return `{ "id": "<id>", "status": "<UPLOADED|PROCESSING|COMPLETED|FAILED>", "created_at": "<iso>", "updated_at": "<iso>", "error": "<str|null>" }`. 404 if id not found.
- `GET /meetings` – return `{ "meetings": [ { "id", "status", "created_at" }, ... ] }`, last 50, newest first.

**Verification**:
1. After T2 upload: `curl http://localhost:8000/meetings/<id>/status` → status UPLOADED.
2. `curl http://localhost:8000/meetings` → list includes the uploaded meeting.
3. `curl http://localhost:8000/meetings/invalid-id/status` → 404.

**Depends on**: T1.

---

### Task 4: Processing script

**Goal**: Script polls `watch_dir/`, picks up new .wav files, sets status to PROCESSING, simulates work, moves file to processed/ or failed/, updates DB to COMPLETED or FAILED.

**Deliverables**:
- `backend/process_watch_dir.py` – runnable as `python process_watch_dir.py` (or `python -m backend.process_watch_dir` if package). Uses same SQLite path as backend (e.g. `backend/db.sqlite`).
- Logic: list `watch_dir/*.wav`; for each file, `id = stem`; if id exists in `meetings` and status is UPLOADED: set status to PROCESSING, move file to `processing/{id}.wav`, sleep N seconds (e.g. 3), move to `processed/{id}.wav`, set status COMPLETED (and updated_at). On exception: move to `failed/{id}.wav`, set status FAILED and error message.
- Run once and exit (no daemon); can be run in a loop by cron or external scheduler, or document “run in loop” for local dev.

**Verification**:
1. After T2: one file in `watch_dir/`. Run script once.
2. `watch_dir/` is empty; file is in `processed/` (or `processing/` then `processed/`).
3. `curl http://localhost:8000/meetings/<id>/status` → status COMPLETED.
4. Optional: force a failure (e.g. invalid file or mock exception); check file in `failed/`, status FAILED, error set.

**Depends on**: T1, T2, T3.

---

## Frontend

### Task 5: Frontend scaffold

**Goal**: React + TypeScript app with Tailwind and shadcn/ui; PWA with service worker; builds and runs.

**Deliverables**:
- `frontend/` – Vite + React + TypeScript (or CRA if preferred; Vite preferred for PWA).
- Tailwind CSS configured.
- shadcn/ui added and at least one component used (e.g. Button) to confirm setup.
- PWA: service worker registered (e.g. Vite PWA plugin or custom `service-worker.ts` in public); manifest and icons placeholder.
- Dev server runs; single page with “Meeting Recorder” and a button.

**Verification**:
1. `cd frontend && npm install && npm run build` – success.
2. `npm run dev` – open in browser; page loads, Tailwind and shadcn visible.
3. Lighthouse or “Application” tab: service worker registered (or manifest present).

**Depends on**: none (can develop in parallel with backend; API base URL configurable, e.g. env).

---

### Task 6: Frontend — record and WAV

**Goal**: User can start/stop recording; timer shows duration; app produces a WAV file (16 kHz, mono, PCM).

**Deliverables**:
- Start/Stop recording using MediaRecorder and/or Web Audio API.
- Timer display (MM:SS) that updates every second while recording.
- On stop: produce a WAV blob/file (16 kHz, mono, 16-bit PCM). If MediaRecorder outputs non-PCM, decode and resample in JS and encode to WAV (e.g. small encoder in repo or known library).
- No upload yet; e.g. “Download” or in-memory blob for next task.

**Verification**:
1. Start recording, wait a few seconds, stop; timer matched duration.
2. A WAV file is produced (download or via devtools); play in system player; check format (e.g. 16 kHz mono) with `ffprobe` or similar.

**Depends on**: T5.

---

### Task 7: Frontend — upload

**Goal**: After recording, user can upload the WAV to backend; upload progress is shown.

**Deliverables**:
- After stop, show “Upload” (or auto-upload). POST WAV to `POST /meetings` (multipart, key `file`).
- Use `XMLHttpRequest` or `fetch` with progress (e.g. `ReadableStream` + progress or XHR progress events) and show progress (e.g. 0–100% or “Uploading…”).
- On 200: store returned `id`; navigate or show status view (T8). On 4xx/5xx: show error.

**Verification**:
1. Record a short clip, upload; backend returns 200 with id; file appears in `backend/watch_dir/{id}.wav`.
2. Progress indicator updates during upload (manual check).

**Depends on**: T2, T5, T6.

---

### Task 8: Frontend — status screen

**Goal**: After upload, user sees status (Uploaded / Processing / Completed / Failed) that updates in real time via polling.

**Deliverables**:
- Status view: show meeting id and status (Uploaded | Processing | Completed | Failed). If FAILED, show error if returned.
- Poll `GET /meetings/{id}/status` every 2 s while status is UPLOADED or PROCESSING; stop when COMPLETED or FAILED.
- UI reflects each state (labels or badges). Optional: simple animation or message for “Processing…”.

**Verification**:
1. Upload from T7; status view shows UPLOADED.
2. Run processing script (T4); within a few seconds status changes to PROCESSING then COMPLETED (or directly to COMPLETED if script is fast).
3. Confirm polling stops when COMPLETED.

**Depends on**: T3, T5, T7.

---

### Task 9: Frontend — recent meetings

**Goal**: User can see a list of recent meetings (from GET /meetings).

**Deliverables**:
- Call `GET /meetings` and display list (e.g. id, status, created_at). Link or action to open status view for a meeting (reuse T8 or same page with id in state/route).
- Integrate into layout (e.g. home page or sidebar); “Recent meetings” visible.

**Verification**:
1. After several uploads (and optionally running script): list shows multiple meetings with correct status and order (newest first).

**Depends on**: T3, T5, T8 (or at least T3, T5; T8 for navigation to status).

---

## Integration

### Task 10: Integration test (manual)

**Goal**: Full flow works: record → upload → file in watch_dir → processing script → status COMPLETED → UI shows Completed.

**Steps**:
1. Start backend; start processing script in a loop (e.g. `while true; do python backend/process_watch_dir.py; sleep 2; done`) or run periodically.
2. Start frontend; open in browser (or device).
3. Record 10–30 s; stop; upload. Confirm file in `watch_dir/`, then in `processed/`.
4. Confirm status in UI: Uploaded → Processing → Completed.
5. Confirm WAV is playable (e.g. download from processed/ and play).

**Depends on**: T2, T3, T4, T5, T6, T7, T8, T9.

---

## Task Checklist (Execution Order)

| # | Task | Deps | Done |
|---|------|------|------|
| 1 | Backend skeleton | — | ☐ |
| 2 | POST /meetings | 1 | ☐ |
| 3 | GET /meetings/{id}/status, GET /meetings | 1 | ☐ |
| 4 | Processing script | 1, 2, 3 | ☐ |
| 5 | Frontend scaffold | — | ☐ |
| 6 | Frontend: record + WAV | 5 | ☐ |
| 7 | Frontend: upload | 2, 5, 6 | ☐ |
| 8 | Frontend: status screen | 3, 5, 7 | ☐ |
| 9 | Frontend: recent meetings | 3, 5, 8 | ☐ |
| 10 | Integration test | 2–9 | ☐ |

---

**Next step**: EXECUTE Task 1 (Backend skeleton), then TEST per verification above, then REPEAT for Task 2.
