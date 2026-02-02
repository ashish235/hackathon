/**
 * Produce 16 kHz mono 16-bit PCM WAV from Float32 samples.
 * Used after recording (context may be 44.1k/48k) by resampling to 16 kHz.
 */

const TARGET_SAMPLE_RATE = 16000;

/**
 * Resample Float32 mono from sourceRate to targetRate using linear interpolation.
 */
export function resample(
  samples: Float32Array,
  sourceRate: number,
  targetRate: number = TARGET_SAMPLE_RATE
): Float32Array {
  if (sourceRate === targetRate) return samples;
  const ratio = sourceRate / targetRate;
  const outLength = Math.floor(samples.length / ratio);
  const out = new Float32Array(outLength);
  for (let i = 0; i < outLength; i++) {
    const srcIndex = i * ratio;
    const i0 = Math.floor(srcIndex);
    const i1 = Math.min(i0 + 1, samples.length - 1);
    const t = srcIndex - i0;
    out[i] = samples[i0] * (1 - t) + samples[i1] * t;
  }
  return out;
}

/**
 * Encode Float32 mono samples (range -1..1) at given sampleRate to WAV Blob.
 * If sampleRate !== 16000, resamples to 16 kHz for pipeline compatibility.
 */
export function encodeWav(
  samples: Float32Array,
  sampleRate: number = TARGET_SAMPLE_RATE
): Blob {
  const rate = sampleRate === TARGET_SAMPLE_RATE ? sampleRate : TARGET_SAMPLE_RATE;
  const data = resample(samples, sampleRate, rate);
  const numSamples = data.length;
  const numBytes = numSamples * 2; // 16-bit = 2 bytes per sample
  const buffer = new ArrayBuffer(44 + numBytes);
  const view = new DataView(buffer);

  const writeStr = (offset: number, str: string) => {
    for (let i = 0; i < str.length; i++) view.setUint8(offset + i, str.charCodeAt(i));
  };

  writeStr(0, "RIFF");
  view.setUint32(4, 36 + numBytes, true);
  writeStr(8, "WAVE");
  writeStr(12, "fmt ");
  view.setUint32(16, 16, true); // chunk size
  view.setUint16(20, 1, true); // PCM
  view.setUint16(22, 1, true); // mono
  view.setUint32(24, rate, true);
  view.setUint32(28, rate * 2, true); // byte rate
  view.setUint16(32, 2, true); // block align
  view.setUint16(34, 16, true); // bits per sample
  writeStr(36, "data");
  view.setUint32(40, numBytes, true);

  for (let i = 0; i < numSamples; i++) {
    const s = Math.max(-1, Math.min(1, data[i]));
    const v = s < 0 ? s * 0x8000 : s * 0x7fff;
    view.setInt16(44 + i * 2, v, true);
  }

  return new Blob([buffer], { type: "audio/wav" });
}

export { TARGET_SAMPLE_RATE };
