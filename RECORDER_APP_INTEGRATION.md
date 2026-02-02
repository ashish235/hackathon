# Meeting Recorder — Integration Test

This document describes how to run the full stack and verify the end-to-end flow: **record → upload → file in watch_dir → processing script → status COMPLETED → UI shows Completed**.

---

## Prerequisites

- **Backend**: Python 3.10+, venv
- **Frontend**: Node 18+, npm
- **Browser**: Microphone permission for recording

---

## 1. Start the backend

```bash
cd backend
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn app:app --host 0.0.0.0 --port 8000
```

Leave this running. Backend serves at `http://localhost:8000` (health: `GET http://localhost:8000/health` → `{"status":"ok"}`).

**The watch_dir processing loop starts automatically** in a background thread when the backend starts. It monitors `watch_dir/`, runs the speech_identification pipeline on new `.wav` files, and retries failed ones from `processed/`. Set `HF_TOKEN` (or `HUGGINGFACE_HUB_TOKEN`) in the environment before starting the backend if the pipeline needs it.

---

## 2. (Optional) Run the processing script standalone

If you prefer to run the processor as a separate process instead of with the backend:

```bash
cd backend
export HF_TOKEN=your_huggingface_token
.venv/bin/python process_watch_dir.py
```

The script runs until Ctrl+C. When the backend is running, this is **not required**—the backend already runs the same loop in a background thread.

---

## 3. Start the frontend

In a **third terminal**:

```bash
cd frontend
npm install
VITE_API_BASE=http://localhost:8000 npm run dev
```

Open the URL shown (e.g. `http://localhost:5173`) in a browser. Grant microphone access when prompted.

**Using the app over HTTP (not localhost):** Browsers only allow microphone access in secure contexts (HTTPS or localhost). For HTTP URLs (e.g. `http://192.168.x.x:5173`):

- **Chrome:** Go to `chrome://flags/#unsafely-treat-insecure-origin-as-secure`, add your origin (e.g. `http://192.168.1.5:5173`), enable the flag, and relaunch Chrome.
- **Safari:** Enable the Develop menu (Safari → Settings → Advanced → “Show Develop menu in menu bar”), then choose **Develop → Allow Media Capture on Insecure Sites**. Use only for local testing.

---

## 4. Run the integration flow

1. **Record**  
   Click **Start recording**. Wait 10–30 seconds. Click **Stop recording**.

2. **Upload**  
   Click **Upload**. Wait for "Uploaded! Meeting ID: …" and progress to 100%.

3. **Confirm file in watch_dir**  
   In a shell:
   ```bash
   ls backend/watch_dir/
   ```
   You should see `{meeting-id}.wav` briefly; within a few seconds the processing script moves it to `processing/` then `processed/`.

4. **Confirm file in processed/**  
   ```bash
   ls backend/processed/
   ```
   You should see `{meeting-id}.wav`.

5. **Confirm status in UI**  
   Click **View status** (or open the meeting from **Recent meetings**).  
   Status should show **UPLOADED** → **PROCESSING** (with "Processing…") → **COMPLETED** within a few seconds. Polling stops when status is COMPLETED.

6. **Confirm WAV is playable**  
   Download the file from `backend/processed/{id}.wav` and play it in a media player, or use **Download WAV** before uploading and play that file. It should be 16 kHz mono WAV.

---

## 5. Optional checks

- **Recent meetings**: On the record view, the "Recent meetings" section lists the last 50 meetings (newest first). Each row has a **View status** button that opens the status view for that meeting.
- **Backend list**: `curl http://localhost:8000/meetings` returns the same meetings.
- **Backend status**: `curl http://localhost:8000/meetings/{id}/status` returns `{"id":"…","status":"COMPLETED",…}`.

---

## Access from public IP / internet

To reach the app at your **public IP** (or from another network), use **one server** (backend serves the built frontend) and then open access:

### 1. Build frontend and run backend (one server)

```bash
cd frontend
npm run build
cd ../backend
.venv/bin/uvicorn app:app --host 0.0.0.0 --port 8000
```

Do **not** set `VITE_API_BASE` when building; the built app uses relative URLs and talks to the same host. Then open **http://&lt;your-ip&gt;:8000** (or your public URL).

### 2. Why it’s not reachable on the public IP

| Situation | What to do |
|-----------|------------|
| **Cloud VM (AWS, GCP, etc.)** | Open **port 8000** in the instance **security group / firewall** (inbound TCP 8000 from 0.0.0.0/0 or your IP). |
| **Home / office (router)** | Your “public IP” is the router; it doesn’t forward to your machine. Use **ngrok**: `ngrok http 8000` and open the `https://…ngrok.io` URL. Or set up **port forwarding** on the router: external 8000 → your machine’s local IP, port 8000. |
| **Local firewall** | On the server: `sudo ufw allow 8000 && sudo ufw reload` (or equivalent). |

### 3. Quick test with ngrok (no router config)

```bash
# Terminal 1: backend (with frontend built)
cd backend && .venv/bin/uvicorn app:app --host 0.0.0.0 --port 8000

# Terminal 2: tunnel
ngrok http 8000
```

Open the **https** URL ngrok prints; the app and API will work there.

---

## Troubleshooting

| Issue | Check |
|-------|--------|
| CORS / network errors in browser | Backend must allow origin (already configured). Ensure `VITE_API_BASE=http://localhost:8000` (or your backend URL) so the frontend calls the correct host. |
| File stays in watch_dir | Processing runs in a background thread when the backend starts. Ensure backend started without errors; set `HF_TOKEN` if the pipeline needs it. |
| Status stuck at UPLOADED | Script may not have picked up the file yet; wait a few seconds (real-time watcher + 2s debounce). If DB row exists and file is in watch_dir, script will process it. |
| 404 on /meetings/{id}/status | Confirm the meeting id from the upload response; ensure backend and DB are the same (single `backend/db.sqlite`). |
| Pipeline / HF token errors | Set `HF_TOKEN` or `HUGGINGFACE_HUB_TOKEN` before running `process_watch_dir.py`. Install `speech_identification/requirements.txt` in the venv used for the script. |

---

**Task 10 complete**: Full flow is documented and can be verified manually as above.
