/**
 * Poll GET /meetings/{id}/status every 2s while status is UPLOADED or PROCESSING.
 * Stop when COMPLETED or FAILED.
 */

import { useEffect, useState } from "react";
import { getMeetingStatus, isPollingStatus, type MeetingStatusResponse } from "@/lib/api";

const POLL_INTERVAL_MS = 2000;

export function useMeetingStatus(meetingId: string | null) {
  const [data, setData] = useState<MeetingStatusResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!meetingId) {
      setData(null);
      setError(null);
      return;
    }

    let cancelled = false;
    let intervalId: ReturnType<typeof setInterval> | null = null;

    const fetchOnce = async (): Promise<MeetingStatusResponse | null> => {
      try {
        const res = await getMeetingStatus(meetingId);
        if (!cancelled) {
          setData(res);
          setError(null);
        }
        return res;
      } catch (e) {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : "Failed to load status");
        }
        return null;
      }
    };

    void fetchOnce().then((res) => {
      if (cancelled || !res || !isPollingStatus(res.status)) return;
      intervalId = setInterval(() => {
        void fetchOnce().then((next) => {
          if (next && !isPollingStatus(next.status) && intervalId) {
            clearInterval(intervalId);
            intervalId = null;
          }
        });
      }, POLL_INTERVAL_MS);
    });

    return () => {
      cancelled = true;
      if (intervalId) clearInterval(intervalId);
    };
  }, [meetingId]);

  return { data, error };
}
