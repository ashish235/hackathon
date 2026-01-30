"""
Split an audio file into segments by speaker using an RTTM diarization file.

Consecutive RTTM segments of the same speaker are merged into one chunk before
splitting, so that short back-to-back turns from the same speaker become a
single file instead of many tiny files.

Two outputs:
1. Per-speaker folders (e.g. SPEAKER_00/001.wav, SPEAKER_01/002.wav).
2. An "ordered" folder with segments in chronological order, named by turn
   and speaker (e.g. 0_SPEAKER_00.wav, 1_SPEAKER_02.wav, 2_SPEAKER_01.wav).
"""

import argparse
from pathlib import Path

import torch
import torch.nn.functional as F
from pyannote.core import Segment
from pyannote.database.util import load_rttm

from audio_io import load_audio, save_audio


def split_audio_by_rttm(
    audio_path: str | Path,
    rttm_path: str | Path,
    output_dir: str | Path,
    ordered_output_dir: str | Path | None = None,
) -> None:
    """
    Split audio into segments per speaker. Consecutive same-speaker segments
    in the RTTM are merged into one before splitting. Creates:
    1. One folder per speaker with segments 001.wav, 002.wav, ...
    2. An ordered folder with segments in chronological order named
       {index}_{speaker}.wav (e.g. 0_SPEAKER_00.wav, 1_SPEAKER_02.wav).
       By default this is output_dir/ordered; pass ordered_output_dir to
       use a different path (e.g. work_dir/output).

    Parameters
    ----------
    audio_path : path to the source audio file (e.g. output2.wav)
    rttm_path : path to the RTTM diarization file (e.g. output2.rttm)
    output_dir : base directory for speaker folders
    ordered_output_dir : directory for chronological ordered files (default: output_dir/ordered)
    """
    audio_path = Path(audio_path)
    rttm_path = Path(rttm_path)
    output_dir = Path(output_dir)

    if not audio_path.is_file():
        raise FileNotFoundError(f"Audio file not found: {audio_path}")
    if not rttm_path.is_file():
        raise FileNotFoundError(f"RTTM file not found: {rttm_path}")

    annotations = load_rttm(rttm_path)
    uri = audio_path.stem
    if uri not in annotations:
        if len(annotations) == 1:
            uri = next(iter(annotations))
        else:
            raise ValueError(
                f"RTTM does not contain uri '{uri}'. "
                f"Available uris: {list(annotations.keys())}"
            )
    annotation = annotations[uri]

    # Load full audio with TorchCodec (recommended; avoids deprecated torchaudio path)
    waveform, sample_rate = load_audio(audio_path)
    if waveform.shape[0] > 1:
        waveform = waveform.mean(dim=0, keepdim=True)
    num_samples = waveform.shape[1]

    output_dir.mkdir(parents=True, exist_ok=True)
    ordered_dir = Path(ordered_output_dir) if ordered_output_dir is not None else output_dir / "ordered"
    ordered_dir.mkdir(parents=True, exist_ok=True)

    # Chronological order: sort segments by start time
    segments_with_speaker = []
    for item in annotation.itertracks(yield_label=True):
        segment, speaker = item[0], item[2] if len(item) >= 3 else item[1]
        segments_with_speaker.append((segment, speaker))
    segments_with_speaker.sort(key=lambda x: x[0].start)

    # Merge consecutive segments of the same speaker into one (avoids very small chunks)
    merged: list[tuple[Segment, str]] = []
    for segment, speaker in segments_with_speaker:
        if merged and merged[-1][1] == speaker:
            # Extend previous segment to include this one
            prev_seg, _ = merged[-1]
            merged[-1] = (Segment(prev_seg.start, segment.end), speaker)
        else:
            merged.append((Segment(segment.start, segment.end), speaker))

    speaker_count: dict[str, int] = {}

    for global_index, (segment, speaker) in enumerate(merged):
        speaker_count[speaker] = speaker_count.get(speaker, 0) + 1
        idx = speaker_count[speaker]

        # Crop segment (zero-pad if out of bounds)
        start_s, end_s = float(segment.start), float(segment.end)
        start_sample = int(start_s * sample_rate)
        end_sample = int(end_s * sample_rate)
        pad_start = max(0, -start_sample)
        pad_end = max(0, end_sample - num_samples)
        start_sample = max(0, start_sample)
        end_sample = min(num_samples, end_sample)
        chunk = waveform[:, start_sample:end_sample]
        if pad_start > 0 or pad_end > 0:
            chunk = F.pad(chunk, (pad_start, pad_end))

        # Per-speaker folder: SPEAKER_00/001.wav, ...
        speaker_dir = output_dir / speaker
        speaker_dir.mkdir(parents=True, exist_ok=True)
        out_path = speaker_dir / f"{idx:03d}.wav"
        save_audio(out_path, chunk, sample_rate)

        # Ordered folder: 0_SPEAKER_00.wav, 1_SPEAKER_02.wav, ...
        ordered_path = ordered_dir / f"{global_index}_{speaker}.wav"
        save_audio(ordered_path, chunk, sample_rate)

        print(
            f"  {segment.start:.2f}s - {segment.end:.2f}s  {speaker}  ->  {out_path}  |  {ordered_path.name}"
        )

    total = sum(speaker_count.values())
    print(f"\nSaved {total} segments to {output_dir}/")
    print(f"  Per-speaker: {output_dir}/<SPEAKER_xx>/")
    print(f"  By turn:     {ordered_dir}/ (0_SPEAKER_00.wav, 1_SPEAKER_02.wav, ...)")
    for spk, count in sorted(speaker_count.items()):
        print(f"  {spk}: {count} file(s)")


def main():
    parser = argparse.ArgumentParser(
        description="Split audio into per-speaker segments using an RTTM file."
    )
    parser.add_argument(
        "audio",
        type=Path,
        help="Path to audio file (e.g. output2.wav)",
    )
    parser.add_argument(
        "rttm",
        type=Path,
        help="Path to RTTM diarization file (e.g. output2.rttm)",
    )
    parser.add_argument(
        "-o", "--output-dir",
        type=Path,
        default=None,
        help="Output directory for speaker folders (default: <audio_stem>_splits)",
    )
    args = parser.parse_args()

    output_dir = args.output_dir
    if output_dir is None:
        output_dir = args.audio.parent / f"{args.audio.stem}_splits"

    print(f"Audio: {args.audio}")
    print(f"RTTM:  {args.rttm}")
    print(f"Output: {output_dir}\n")
    split_audio_by_rttm(args.audio, args.rttm, output_dir)


if __name__ == "__main__":
    main()
