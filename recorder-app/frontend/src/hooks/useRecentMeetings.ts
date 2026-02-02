/**
 * Fetch recent meetings (GET /meetings). Refetch on demand (e.g. after upload).
 */

import { useCallback, useEffect, useState } from "react";
import { getMeetings, type MeetingSummary } from "@/lib/api";

export function useRecentMeetings() {
  const [meetings, setMeetings] = useState<MeetingSummary[]>([]);
  const [error, setError] = useState<string | null>(null);

  const fetchMeetings = useCallback(async () => {
    try {
      const res = await getMeetings();
      setMeetings(res.meetings);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load meetings");
      setMeetings([]);
    }
  }, []);

  useEffect(() => {
    fetchMeetings();
  }, [fetchMeetings]);

  return { meetings, error, refetch: fetchMeetings };
}

/** Format ISO date for display (e.g. "Jan 30, 2026 20:11") */
export function formatCreatedAt(iso: string): string {
  try {
    const d = new Date(iso);
    return d.toLocaleString(undefined, {
      month: "short",
      day: "numeric",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}
