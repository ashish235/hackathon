/**
 * Backend API client. Base URL from VITE_API_BASE (e.g. http://localhost:8000).
 */

const API_BASE = (import.meta.env.VITE_API_BASE as string) || "";

export function getApiBase(): string {
  return API_BASE.replace(/\/$/, "");
}

export interface UploadMeetingResponse {
  id: string;
  status: string;
}

export interface MeetingStatusResponse {
  id: string;
  status: string;
  created_at: string;
  updated_at: string;
  error: string | null;
}

/**
 * GET /meetings/{id}/status. Returns meeting status; 404 if not found.
 */
export async function getMeetingStatus(meetingId: string): Promise<MeetingStatusResponse> {
  const base = getApiBase();
  const url = base ? `${base}/meetings/${encodeURIComponent(meetingId)}/status` : `/meetings/${encodeURIComponent(meetingId)}/status`;
  const res = await fetch(url);
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    const detail = body.detail ?? res.statusText;
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return res.json() as Promise<MeetingStatusResponse>;
}

/**
 * Whether status should keep polling (stop when COMPLETED or FAILED).
 */
export function isPollingStatus(status: string): boolean {
  return status === "UPLOADED" || status === "PROCESSING";
}

export interface MeetingSummary {
  id: string;
  status: string;
  created_at: string;
}

export interface ListMeetingsResponse {
  meetings: MeetingSummary[];
}

/**
 * GET /meetings. Returns last 50 meetings, newest first.
 */
export async function getMeetings(): Promise<ListMeetingsResponse> {
  const base = getApiBase();
  const url = base ? `${base}/meetings` : "/meetings";
  const res = await fetch(url);
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    const detail = body.detail ?? res.statusText;
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return res.json() as Promise<ListMeetingsResponse>;
}

/**
 * POST WAV file to /meetings. Reports upload progress via onProgress(0-100).
 * On 200 returns { id, status }; on 4xx/5xx throws with message.
 */
export function uploadMeeting(
  blob: Blob,
  onProgress?: (percent: number) => void
): Promise<UploadMeetingResponse> {
  return new Promise((resolve, reject) => {
    const base = getApiBase();
    const url = base ? `${base}/meetings` : "/meetings";
    const xhr = new XMLHttpRequest();
    const form = new FormData();
    form.append("file", blob, "recording.wav");

    xhr.upload.addEventListener("progress", (e) => {
      if (e.lengthComputable && onProgress) {
        onProgress(Math.round((e.loaded / e.total) * 100));
      }
    });

    xhr.addEventListener("load", () => {
      if (xhr.status === 200) {
        try {
          const data = JSON.parse(xhr.responseText) as UploadMeetingResponse;
          resolve(data);
        } catch {
          reject(new Error("Invalid response"));
        }
      } else {
        let detail = xhr.statusText;
        try {
          const body = JSON.parse(xhr.responseText);
          if (body.detail) detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
        } catch {
          // ignore
        }
        reject(new Error(detail || `Upload failed (${xhr.status})`));
      }
    });

    xhr.addEventListener("error", () => reject(new Error("Network error")));
    xhr.addEventListener("abort", () => reject(new Error("Upload aborted")));

    xhr.open("POST", url);
    xhr.send(form);
  });
}
