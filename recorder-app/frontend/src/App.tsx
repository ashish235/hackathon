import { useState } from "react";
import { Button } from "@/components/ui/button";
import { useRecorder, formatDuration } from "@/hooks/useRecorder";
import { useMeetingStatus } from "@/hooks/useMeetingStatus";
import { useRecentMeetings, formatCreatedAt } from "@/hooks/useRecentMeetings";
import { uploadMeeting } from "@/lib/api";

function StatusView({
  meetingId,
  onBack,
}: {
  meetingId: string;
  onBack: () => void;
}) {
  const { data, error: fetchError } = useMeetingStatus(meetingId);
  const status = data?.status ?? "—";
  const isPolling = status === "UPLOADED" || status === "PROCESSING";

  const statusStyles: Record<string, string> = {
    UPLOADED: "bg-slate-600 text-slate-200",
    PROCESSING: "bg-amber-600/80 text-amber-100",
    COMPLETED: "bg-emerald-600 text-emerald-100",
    FAILED: "bg-red-600 text-red-100",
  };
  const statusClass = statusStyles[status] ?? "bg-slate-600 text-slate-200";

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col items-center justify-center p-6">
      <h1 className="text-3xl font-bold mb-4">Meeting status</h1>
      <p className="text-slate-400 mb-4 font-mono text-sm break-all">
        ID: {meetingId}
      </p>

      {fetchError && (
        <p className="text-red-400 mb-4" role="alert">
          {fetchError}
        </p>
      )}

      <div className="flex flex-col items-center gap-3 mb-6">
        <span
          className={`inline-flex items-center gap-2 px-4 py-2 rounded-full text-sm font-medium ${statusClass}`}
          aria-live="polite"
        >
          {status}
          {isPolling && (
            <span className="inline-block w-2 h-2 rounded-full bg-current animate-pulse" />
          )}
        </span>
        {status === "PROCESSING" && (
          <p className="text-slate-500 text-sm">Processing…</p>
        )}
        {data?.status === "FAILED" && data.error && (
          <p className="text-red-400 text-sm max-w-md text-center">
            {data.error}
          </p>
        )}
      </div>

      <Button variant="outline" onClick={onBack}>
        Back to recorder
      </Button>
    </div>
  );
}

function App() {
  const {
    status,
    blob,
    durationSec,
    error,
    startRecording,
    stopRecording,
    reset,
  } = useRecorder();

  const [uploadedMeetingId, setUploadedMeetingId] = useState<string | null>(null);
  const [uploadProgress, setUploadProgress] = useState<number | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [view, setView] = useState<"record" | "status">("record");

  const { meetings, error: meetingsError, refetch: refetchMeetings } = useRecentMeetings();

  const handleDownload = () => {
    if (!blob) return;
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `recording-${Date.now()}.wav`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const handleUpload = async () => {
    if (!blob) return;
    setUploadError(null);
    setUploadProgress(0);
    try {
      const res = await uploadMeeting(blob, (p) => setUploadProgress(p));
      setUploadedMeetingId(res.id);
      setUploadProgress(null);
      refetchMeetings();
    } catch (e) {
      setUploadError(e instanceof Error ? e.message : "Upload failed");
      setUploadProgress(null);
    }
  };

  const handleViewStatus = () => {
    if (uploadedMeetingId) setView("status");
  };

  const handleOpenStatusFor = (id: string) => {
    setUploadedMeetingId(id);
    setView("status");
  };

  const handleBackToRecord = () => {
    setView("record");
    refetchMeetings();
  };

  // Status view: poll every 2s until COMPLETED or FAILED
  if (view === "status" && uploadedMeetingId) {
    return (
      <StatusView
        meetingId={uploadedMeetingId}
        onBack={handleBackToRecord}
      />
    );
  }

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col items-center justify-center p-6">
      <h1 className="text-3xl font-bold mb-4">Meeting Recorder</h1>
      <p className="text-slate-400 mb-6">
        Record in-person meetings and upload for processing.
      </p>

      {error && (
        <p className="text-red-400 mb-4" role="alert">
          {error}
        </p>
      )}

      {uploadError && (
        <p className="text-red-400 mb-4" role="alert">
          {uploadError}
        </p>
      )}

      {status === "idle" && (
        <Button className="px-6 py-3" onClick={startRecording}>
          Start recording
        </Button>
      )}

      {status === "recording" && (
        <div className="flex flex-col items-center gap-4">
          <p className="text-2xl font-mono tabular-nums" aria-live="polite">
            {formatDuration(durationSec)}
          </p>
          <Button
            variant="destructive"
            className="px-6 py-3"
            onClick={stopRecording}
          >
            Stop recording
          </Button>
        </div>
      )}

      {status === "stopped" && blob && (
        <div className="flex flex-col items-center gap-4">
          <p className="text-slate-400">
            Recording: {formatDuration(durationSec)} • 16 kHz mono WAV
          </p>

          {uploadProgress !== null && (
            <p className="text-slate-400" aria-live="polite">
              Uploading… {uploadProgress}%
            </p>
          )}

          {uploadedMeetingId && !uploadProgress && (
            <p className="text-green-400 mb-2">
              Uploaded! Meeting ID: <span className="font-mono text-sm">{uploadedMeetingId}</span>
            </p>
          )}

          <div className="flex flex-wrap gap-3 justify-center">
            <Button
              className="px-6 py-3"
              onClick={handleUpload}
              disabled={uploadProgress !== null}
            >
              {uploadProgress !== null ? "Uploading…" : "Upload"}
            </Button>
            <Button className="px-6 py-3" onClick={handleDownload}>
              Download WAV
            </Button>
            {uploadedMeetingId && (
              <Button variant="outline" className="px-6 py-3" onClick={handleViewStatus}>
                View status
              </Button>
            )}
            <Button
              variant="outline"
              className="px-6 py-3"
              onClick={() => {
                setUploadedMeetingId(null);
                setUploadError(null);
                reset();
              }}
            >
              Record again
            </Button>
          </div>
        </div>
      )}

      {/* Recent meetings */}
      <section className="mt-12 w-full max-w-lg" aria-label="Recent meetings">
        <h2 className="text-lg font-semibold text-slate-300 mb-3">Recent meetings</h2>
        {meetingsError && (
          <p className="text-red-400 text-sm mb-2" role="alert">
            {meetingsError}
          </p>
        )}
        {meetings.length === 0 && !meetingsError && (
          <p className="text-slate-500 text-sm">No meetings yet.</p>
        )}
        {meetings.length > 0 && (
          <ul className="space-y-2">
            {meetings.map((m) => (
              <li
                key={m.id}
                className="flex flex-wrap items-center justify-between gap-2 rounded-lg bg-slate-800/50 px-4 py-3 border border-slate-700/50"
              >
                <div className="flex flex-wrap items-center gap-2 min-w-0">
                  <span className="font-mono text-xs text-slate-400 truncate max-w-[140px]" title={m.id}>
                    {m.id.slice(0, 8)}…
                  </span>
                  <span
                    className={`text-xs font-medium px-2 py-0.5 rounded ${
                      m.status === "COMPLETED"
                        ? "bg-emerald-600/80 text-emerald-100"
                        : m.status === "FAILED"
                          ? "bg-red-600/80 text-red-100"
                          : m.status === "PROCESSING"
                            ? "bg-amber-600/80 text-amber-100"
                            : "bg-slate-600 text-slate-200"
                    }`}
                  >
                    {m.status}
                  </span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-slate-500 text-xs whitespace-nowrap">
                    {formatCreatedAt(m.created_at)}
                  </span>
                  <Button
                    variant="ghost"
                    className="text-slate-400 hover:text-slate-200 hover:bg-slate-800 text-xs h-8 px-2"
                    onClick={() => handleOpenStatusFor(m.id)}
                  >
                    View status
                  </Button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}

export default App;
