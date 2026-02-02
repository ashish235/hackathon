# hackathon

Repository for the meeting recorder PWA and backend pipeline, plus the existing speech identification pipeline.

---

## Meeting Recorder (PWA + Backend)

Cross-platform web app that records meetings, uploads WAV to a backend, and shows real-time processing status.

- **Frontend** (PWA): `frontend/` — React, TypeScript, Tailwind, shadcn-style UI. Record → WAV (16 kHz mono) → upload → status view.
- **Backend**: `backend/` — FastAPI, SQLite, `watch_dir/` for ingestion. APIs: `POST /meetings`, `GET /meetings/{id}/status`, `GET /meetings`.
- **Processing script**: `backend/process_watch_dir.py` — Runs automatically when the backend starts (background thread). Monitors `watch_dir/`, runs the pipeline, moves to `processed/`, retries failed.

### Quick start

1. **Backend** (starts the processing loop in a background thread):
   ```bash
   cd backend && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
   export HF_TOKEN=your_token   # if pipeline needs it
   .venv/bin/uvicorn app:app --host 0.0.0.0 --port 8000
   ```

2. **Frontend**:
   ```bash
   cd frontend && npm install && VITE_API_BASE=http://localhost:8000 npm run dev
   ```
   Open the dev URL (e.g. http://localhost:5173), record, upload, and view status. Optional: run `process_watch_dir.py` as a separate process instead of with the backend; see RECORDER_APP_INTEGRATION.md.

See **[RECORDER_APP_INTEGRATION.md](./RECORDER_APP_INTEGRATION.md)** for the full integration test (record → upload → file in watch_dir → status COMPLETED).

- Plan: [RECORDER_APP_PLAN.md](./RECORDER_APP_PLAN.md)  
- Tasks: [RECORDER_APP_SPLIT.md](./RECORDER_APP_SPLIT.md)

---

## Speech identification

`speech_identification/` — Pipeline for diarization, split, merge, embeddings, and speaker matching. See `speech_identification/README.md` or module docstrings for usage.
