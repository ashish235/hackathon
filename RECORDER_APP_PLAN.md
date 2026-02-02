# PLAN: Meeting Recording Web App & Backend Pipeline

**Date**: 2025-01-30  
**Goal**: Cross-platform PWA that records meetings, uploads WAV to backend, places file in a watch directory, and shows real-time processing status.

---

## 1. Goal Restatement

Build a **single codebase** web application (PWA) that:

1. **Records** in-person meetings via device microphone (30–120 min).
2. **Saves** recording as `.wav` (PCM, mono, 16 kHz or higher).
3. **Uploads** the WAV to a Python backend.
4. **Places** the file into a specific folder (`watch_dir/`) for a Python processing script.
5. **Waits** for processing completion.
6. **Shows** real-time processing status (Uploaded → Processing → Completed / Failed).

This app is the **entry point** to the existing meeting intelligence system (e.g. `speech_identification/` pipeline).

---

## 2. Sub-Systems

| Sub-System | Responsibility | Tech |
|------------|----------------|------|
| **Frontend (PWA)** | Record mic → WAV, upload, poll status, show UI | React, TypeScript, Tailwind, shadcn/ui, Web Audio API, MediaRecorder |
| **Backend API** | Receive uploads, save to `watch_dir/`, persist status, serve status API | FastAPI, SQLite, file I/O |
| **Processing Script** | Poll `watch_dir/`, pick up new WAVs, simulate/run processing, move to `processed/` or `failed/`, update DB status | Python 3.10+, file polling |

**Data flow (high level):**

```
[Device Mic] → [PWA: MediaRecorder → WAV] → [POST /meetings] → [Backend: save to watch_dir/, insert DB]
                                                                        ↓
[Processing Script] ← polls watch_dir/ ← new .wav file
        ↓
  move to processing/ → (simulate) process → move to processed/ or failed/
        ↓
  update status in DB (via backend or direct SQLite)
        ↓
[PWA: GET /meetings/{id}/status] ← user sees status
```

---

## 3. APIs and Data Flow

### Backend APIs (FastAPI)

| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | `/meetings` | Upload WAV file (multipart). Create DB row (status=UPLOADED), save file to `watch_dir/{meeting_id}.wav`, return `{ id, status }`. |
| GET | `/meetings/{id}/status` | Return `{ id, status, created_at?, error? }`. Status: `UPLOADED | PROCESSING | COMPLETED | FAILED`. |
| GET | `/meetings` | List recent meetings (e.g. last 50) for "Recent meetings" UI. Return `[{ id, status, created_at }]`. |

### Status Lifecycle

1. **UPLOADED** – File saved to `watch_dir/`, record created in SQLite.
2. **PROCESSING** – Processing script has picked up the file (script sets this when it starts).
3. **COMPLETED** – Script moved file to `processed/`, updated DB.
4. **FAILED** – Script moved file to `failed/`, updated DB (optional: store error message).

### Database (SQLite)

- **Table**: `meetings`  
  - `id` (TEXT PK, e.g. UUID)  
  - `status` (TEXT: UPLOADED | PROCESSING | COMPLETED | FAILED)  
  - `created_at` (ISO timestamp)  
  - `updated_at` (ISO timestamp)  
  - `error` (TEXT, nullable, for FAILED)

Processing script can update `meetings` via SQLite (same DB file as backend) or via a small backend PATCH endpoint. **Decision**: script updates SQLite directly to avoid extra HTTP and keep backend simple; both backend and script use `backend/db.sqlite`.

---

## 4. File Formats, Codecs, Sample Rate

| Decision | Value | Rationale |
|----------|--------|-----------|
| **Container** | WAV | Required; widely supported, lossless. |
| **Encoding** | PCM | Required; no codec in browser needed. |
| **Channels** | Mono | Required; keeps size down, pipeline expects mono. |
| **Sample rate** | 16 kHz | Required minimum; matches `speech_identification` (TARGET_SAMPLE_RATE 16000). |
| **Bit depth** | 16-bit | Standard for PCM WAV, small size, playable everywhere. |

**Frontend recording**: Use MediaRecorder with `audio/webm` or `audio/ogg` for capture, then decode with Web Audio API and resample to 16 kHz mono, then encode to WAV (PCM) in JavaScript, **or** use a library that outputs WAV (e.g. from AudioWorklet/MediaRecorder). Alternative: record at 16 kHz mono via AudioContext + ScriptProcessorNode/MediaRecorder if supported. **Decision**: Record with MediaRecorder; if codec is not PCM, use Web Audio API to decode and a small JS WAV encoder to produce 16 kHz mono PCM WAV (so we don’t depend on backend transcoding).

---

## 5. Polling vs WebSocket

| Choice | Rationale |
|--------|-----------|
| **Polling** | Required: "Wait for processing completion" and "real-time processing status" can be achieved with GET `/meetings/{id}/status` every 2–3 seconds. No WebSocket infra; simpler for backend and PWA; sufficient for 30–120 min recordings where processing takes seconds to minutes. |
| **WebSocket** | Out of scope per instructions; not implemented. |

**Polling interval**: Start with 2 s when status is UPLOADED or PROCESSING; optional: increase to 5 s after 30 s to reduce load. Stop polling when status is COMPLETED or FAILED.

---

## 6. Directory Layout

```
hackathon/
├── backend/
│   ├── watch_dir/          # Backend drops uploaded WAVs here (ingestion)
│   ├── processing/         # Script moves file here while working (optional)
│   ├── processed/          # Script moves here on success
│   ├── failed/             # Script moves here on failure
│   ├── app.py              # FastAPI app, routes, SQLite
│   ├── db.sqlite           # SQLite DB (created at first run)
│   └── requirements.txt
├── frontend/
│   ├── src/
│   ├── public/
│   ├── service-worker.ts   # PWA (or generated from config)
│   ├── package.json
│   └── ...
├── scripts/                # Or backend/scripts/
│   └── process_watch_dir.py   # Polls watch_dir/, processes, updates DB
├── speech_identification/ # Existing pipeline (unchanged for now)
└── RECORDER_APP_PLAN.md   # This file
```

**Note**: `processing/` is optional; script can move file to `processing/` when starting (so status = PROCESSING) and then to `processed/` or `failed/`. Keeps `watch_dir/` clean.

---

## 7. Execution Plan (Order of Implementation)

1. **Backend skeleton** – FastAPI app, SQLite schema, create dirs (`watch_dir/`, `processed/`, `failed/`, `processing/`).
2. **POST /meetings** – Accept multipart WAV, save to `watch_dir/{id}.wav`, insert row (UPLOADED).
3. **GET /meetings/{id}/status** and **GET /meetings** – Implement and test with curl.
4. **Processing script** – Poll `watch_dir/` for `.wav`, move to `processing/`, set PROCESSING, sleep (simulate), move to `processed/` or `failed/`, set COMPLETED/FAILED.
5. **Frontend scaffold** – React + TypeScript, Tailwind, shadcn/ui, PWA (service worker).
6. **Frontend: record** – Start/stop recording, timer, produce WAV (16 kHz mono).
7. **Frontend: upload** – POST WAV to `/meetings`, show upload progress.
8. **Frontend: status** – Poll GET `/meetings/{id}/status`, show status screen (Uploaded / Processing / Completed / Failed).
9. **Frontend: recent meetings** – GET `/meetings`, list recent meetings.
10. **Integration test** – Record → upload → file in `watch_dir/` → status UPLOADED → PROCESSING → COMPLETED, UI reflects.

---

## 8. Decisions Log

| Decision | Choice | Reason |
|----------|--------|--------|
| Status updates | Script writes to SQLite directly | Single DB; no extra PATCH API; backend and script share `backend/db.sqlite`. |
| Meeting ID | UUID v4 | Unique, no collision; safe for filenames. |
| WAV production | Frontend produces 16 kHz mono PCM WAV | Backend stays dumb; pipeline gets correct format; no server-side transcoding in scope. |
| Script location | `scripts/process_watch_dir.py` or `backend/process_watch_dir.py` | Under repo root or backend; TBD in SPLIT. We'll use `backend/process_watch_dir.py` so all backend-related paths are in one place. |

---

## 9. Out of Scope (Reminder)

- Authentication
- Live transcription
- Real Jira / Email / Teams integrations
- Real ML in this app (script may later call `speech_identification` pipeline)
- Streaming audio

---

**Next step**: SPLIT – break this plan into small, testable tasks with clear dependencies.
