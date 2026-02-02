/**
 * Recording hook: mic → Float32 PCM via ScriptProcessorNode, then WAV (16 kHz mono).
 * No upload here; blob is for Task 7.
 */

import { useCallback, useRef, useState } from "react";
import { encodeWav } from "@/lib/wavEncoder";

export type RecorderStatus = "idle" | "recording" | "stopped";

export function useRecorder() {
  const [status, setStatus] = useState<RecorderStatus>("idle");
  const [blob, setBlob] = useState<Blob | null>(null);
  const [durationSec, setDurationSec] = useState(0);
  const [error, setError] = useState<string | null>(null);

  const streamRef = useRef<MediaStream | null>(null);
  const contextRef = useRef<AudioContext | null>(null);
  const processorRef = useRef<ScriptProcessorNode | null>(null);
  const sourceRef = useRef<MediaStreamAudioSourceNode | null>(null);
  const chunksRef = useRef<Float32Array[]>([]);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const startTimeRef = useRef<number>(0);

  const startRecording = useCallback(async () => {
    setError(null);
    setBlob(null);
    setDurationSec(0);
    chunksRef.current = [];

    if (typeof navigator === "undefined" || !navigator.mediaDevices?.getUserMedia) {
      setError(
        "Microphone access requires a secure context (HTTPS or localhost). For HTTP: Chrome — chrome://flags/#unsafely-treat-insecure-origin-as-secure, add this origin. Safari — enable Develop menu (Settings → Advanced), then Develop → Allow Media Capture on Insecure Sites."
      );
      return;
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;

      const context = new AudioContext();
      contextRef.current = context;
      const source = context.createMediaStreamSource(stream);
      sourceRef.current = source;

      // ScriptProcessorNode is deprecated but widely supported; captures raw PCM.
      const bufferSize = 4096;
      const processor = context.createScriptProcessor(bufferSize, 1, 1);
      processorRef.current = processor;

      processor.onaudioprocess = (e) => {
        const input = e.inputBuffer.getChannelData(0);
        chunksRef.current.push(new Float32Array(input));
      };

      source.connect(processor);
      processor.connect(context.destination);

      startTimeRef.current = Date.now();
      setStatus("recording");

      timerRef.current = setInterval(() => {
        setDurationSec(Math.floor((Date.now() - startTimeRef.current) / 1000));
      }, 1000);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to start recording");
      setStatus("idle");
    }
  }, []);

  const stopRecording = useCallback(() => {
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }

    const processor = processorRef.current;
    const source = sourceRef.current;
    const context = contextRef.current;
    const stream = streamRef.current;

    if (processor && source && context) {
      source.disconnect(processor);
      processor.disconnect(context.destination);
    }
    if (stream) {
      stream.getTracks().forEach((t) => t.stop());
    }
    processorRef.current = null;
    sourceRef.current = null;
    streamRef.current = null;

    if (contextRef.current && chunksRef.current.length > 0) {
      const sampleRate = contextRef.current.sampleRate;
      const totalLength = chunksRef.current.reduce((acc, c) => acc + c.length, 0);
      const all = new Float32Array(totalLength);
      let offset = 0;
      for (const c of chunksRef.current) {
        all.set(c, offset);
        offset += c.length;
      }
      const wavBlob = encodeWav(all, sampleRate);
      setBlob(wavBlob);
    }
    contextRef.current = null;
    setStatus("stopped");
  }, []);

  const reset = useCallback(() => {
    setBlob(null);
    setDurationSec(0);
    setStatus("idle");
    setError(null);
  }, []);

  return {
    status,
    blob,
    durationSec,
    error,
    startRecording,
    stopRecording,
    reset,
  };
}

/** Format seconds as MM:SS */
export function formatDuration(sec: number): string {
  const m = Math.floor(sec / 60);
  const s = sec % 60;
  return `${m.toString().padStart(2, "0")}:${s.toString().padStart(2, "0")}`;
}
