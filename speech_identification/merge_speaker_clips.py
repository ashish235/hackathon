"""
Merge all clips in each speaker folder into one audio file per speaker.

Clips are merged in order sorted by filename (001.wav, 002.wav, ...).
"""

import argparse
from pathlib import Path

import torch
import torchaudio


def merge_speaker_clips(
    input_dir: str | Path,
    output_dir: str | Path | None = None,
    output_suffix: str = "_merged",
) -> None:
    """
    Merge all .wav clips in each speaker subfolder into one file per speaker.
    Clips are concatenated in filename order (001.wav, 002.wav, ...).

    Parameters
    ----------
    input_dir : directory containing speaker folders (e.g. my_splits/)
    output_dir : where to write merged files (default: input_dir/merged/)
    output_suffix : suffix for merged filenames (default: _merged -> SPEAKER_00_merged.wav)
    """
    input_dir = Path(input_dir)
    if not input_dir.is_dir():
        raise FileNotFoundError(f"Input directory not found: {input_dir}")

    output_dir = Path(output_dir) if output_dir else input_dir / "merged"
    output_dir.mkdir(parents=True, exist_ok=True)

    # Speaker folders are direct children that contain .wav files
    speaker_dirs = sorted(
        d for d in input_dir.iterdir()
        if d.is_dir() and any(d.glob("*.wav"))
    )

    if not speaker_dirs:
        raise ValueError(f"No speaker folders with .wav files in {input_dir}")

    for speaker_dir in speaker_dirs:
        speaker_name = speaker_dir.name
        clip_paths = sorted(speaker_dir.glob("*.wav"), key=lambda p: p.name)

        waveforms = []
        sample_rate = None

        for path in clip_paths:
            wav, sr = torchaudio.load(str(path))
            if sample_rate is None:
                sample_rate = sr
            elif sr != sample_rate:
                # Resample to match first file
                wav = torchaudio.functional.resample(wav, sr, sample_rate)
            waveforms.append(wav)

        merged = torch.cat(waveforms, dim=-1)  # (channels, time)
        out_path = output_dir / f"{speaker_name}{output_suffix}.wav"
        torchaudio.save(str(out_path), merged, sample_rate)
        print(f"  {speaker_name}: {len(clip_paths)} clips -> {out_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Merge clips in each speaker folder into one file per speaker (sorted by filename)."
    )
    parser.add_argument(
        "input_dir",
        type=Path,
        help="Directory containing speaker folders (e.g. my_splits/)",
    )
    parser.add_argument(
        "-o", "--output-dir",
        type=Path,
        default=None,
        help="Output directory for merged files (default: input_dir/merged/)",
    )
    parser.add_argument(
        "--suffix",
        default="_merged",
        help="Suffix for merged filenames (default: _merged)",
    )
    args = parser.parse_args()

    print(f"Input:  {args.input_dir}")
    print(f"Output: {args.output_dir or args.input_dir / 'merged'}\n")
    merge_speaker_clips(
        args.input_dir,
        output_dir=args.output_dir,
        output_suffix=args.suffix,
    )


if __name__ == "__main__":
    main()
