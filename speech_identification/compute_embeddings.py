"""
Compute speaker embeddings for all audio files in a directory.

Uses the same embedding model as pyannote/speaker-diarization-community-1.
Requires HF_TOKEN or HUGGINGFACE_HUB_TOKEN for model access.
"""

import argparse
import os
from pathlib import Path

import numpy as np
import torch
from pyannote.audio import Audio
from pyannote.audio.pipelines.speaker_verification import PretrainedSpeakerEmbedding


# Same embedding as speaker-diarization-community-1
EMBEDDING_MODEL = {
    "checkpoint": "pyannote/speaker-diarization-community-1",
    "subfolder": "embedding",
}


def compute_embeddings(
    input_dir: str | Path,
    token: str | None = None,
    output_dir: str | Path | None = None,
    output_format: str = "npy",
    pattern: str = "*.wav",
):
    """
    Compute one embedding per audio file in input_dir.

    Parameters
    ----------
    input_dir : directory containing audio files (e.g. merged_output)
    token : Hugging Face token (default: HF_TOKEN / HUGGINGFACE_HUB_TOKEN)
    output_dir : if set, save embeddings here (default: same as input_dir)
    output_format : "npy" (default) or "npz" (single file with all embeddings)
    pattern : glob for audio files (default: *.wav)
    """
    input_dir = Path(input_dir)
    if not input_dir.is_dir():
        raise NotADirectoryError(f"Not a directory: {input_dir}")

    hf_token = token or os.environ.get("HF_TOKEN") or os.environ.get("HUGGINGFACE_HUB_TOKEN")
    if not hf_token:
        raise ValueError(
            "Hugging Face token required. Set HF_TOKEN or HUGGINGFACE_HUB_TOKEN, "
            "or pass --token. Accept conditions at "
            "https://huggingface.co/pyannote/speaker-diarization-community-1"
        )

    audio_paths = sorted(input_dir.glob(pattern))
    if not audio_paths:
        print(f"No files matching '{pattern}' in {input_dir}")
        return {}

    device = torch.device("cuda") if torch.cuda.is_available() else torch.device("cpu")
    print(f"Loading embedding model ({EMBEDDING_MODEL['checkpoint']})...")
    embedding_model = PretrainedSpeakerEmbedding(
        EMBEDDING_MODEL,
        device=device,
        token=hf_token,
    )
    # Audio at embedding model's sample rate (e.g. 16 kHz)
    audio_loader = Audio(sample_rate=embedding_model.sample_rate, mono="downmix")

    results = {}
    out_dir = Path(output_dir) if output_dir else input_dir
    if output_format == "npy":
        out_dir.mkdir(parents=True, exist_ok=True)

    for path in audio_paths:
        if not path.suffix.lower() in (".wav", ".mp3", ".flac", ".m4a", ".ogg"):
            continue
        name = path.stem
        print(f"  {path.name} ...")
        try:
            waveform, sr = audio_loader(path)
            # (channels, samples) -> (1, 1, samples)
            w = waveform.unsqueeze(0)
            emb = embedding_model(w)
            emb = np.squeeze(emb)
            if np.any(np.isnan(emb)):
                print(f"    Warning: NaN in embedding (audio may be too short)")
            results[name] = emb
            if output_format == "npy":
                out_path = out_dir / f"{name}_embedding.npy"
                np.save(out_path, emb, allow_pickle=False)
                print(f"    -> {out_path}")
        except Exception as e:
            print(f"    Error: {e}")
            results[name] = None

    if output_format == "npz":
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / "embeddings.npz"
        np.savez(out_path, **{k: v for k, v in results.items() if v is not None})
        print(f"Saved all embeddings to {out_path}")

    return results


def main():
    parser = argparse.ArgumentParser(
        description="Compute speaker embeddings for audio files in a directory"
    )
    parser.add_argument(
        "input_dir",
        type=Path,
        default=Path("merged_output"),
        nargs="?",
        help="Directory containing audio files (default: merged_output)",
    )
    parser.add_argument(
        "-t", "--token",
        default=None,
        help="Hugging Face token (default: HF_TOKEN / HUGGINGFACE_HUB_TOKEN)",
    )
    parser.add_argument(
        "-o", "--output-dir",
        type=Path,
        default=None,
        help="Where to save embeddings (default: same as input_dir)",
    )
    parser.add_argument(
        "--format",
        choices=("npy", "npz"),
        default="npy",
        help="npy = one .npy per file; npz = single embeddings.npz (default: npy)",
    )
    parser.add_argument(
        "--pattern",
        default="*.wav",
        help="Glob for audio files (default: *.wav)",
    )
    args = parser.parse_args()

    compute_embeddings(
        input_dir=args.input_dir,
        token=args.token,
        output_dir=args.output_dir,
        output_format=args.format,
        pattern=args.pattern,
    )


if __name__ == "__main__":
    main()
