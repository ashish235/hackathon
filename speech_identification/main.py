"""
Speaker diarization using pyannote.audio.

Requires a Hugging Face token with access to pyannote models.
Set HF_TOKEN or HUGGINGFACE_HUB_TOKEN in your environment.

Accept model conditions at:
- https://huggingface.co/pyannote/speaker-diarization-3.1
- https://huggingface.co/pyannote/segmentation

Improving accuracy (speaker-diarization-community-1):
- Use num_speakers (or min_speakers/max_speakers) when known.
- Tune pipeline_params: segmentation.min_duration_off (e.g. 0.05–0.2) reduces
  flicker; clustering.threshold (default 0.6) controls cluster count.
- Use GPU (pipeline.to(torch.device("cuda"))).
- Prefer 16 kHz mono, clean audio; avoid heavy compression.
- For best accuracy, consider pyannote/speaker-diarization-precision-2 (cloud).
"""

import argparse
import os
import warnings
from pathlib import Path

# Suppress noisy pyannote/PyTorch warnings (harmless for diarization)
warnings.filterwarnings(
    "ignore",
    message=".*TensorFloat-32.*TF32.*",
    module="pyannote.audio.utils.reproducibility",
)
warnings.filterwarnings(
    "ignore",
    message=".*degrees of freedom.*",
    category=UserWarning,
)

import torch
from pyannote.audio import Pipeline
from pyannote.core import Annotation

from audio_io import load_audio

TARGET_SAMPLE_RATE = 16000


def get_diarization(prediction):
    """Extract speaker diarization Annotation from pipeline output."""
    if isinstance(prediction, Annotation):
        return prediction
    if hasattr(prediction, "speaker_diarization"):
        return prediction.speaker_diarization
    raise ValueError("Could not find speaker diarization in pipeline output.")


def run_diarization(
    audio_path: str | Path,
    token: str | None = None,
    pipeline_id: str = "pyannote/speaker-diarization-community-1",
    num_speakers: int | None = None,
    min_speakers: int | None = None,
    max_speakers: int | None = None,
    pipeline_params: dict | None = None,
    output_rttm: str | Path | None = None,
):
    """
    Run speaker diarization on an audio file.

    Parameters
    ----------
    audio_path : path to audio file (e.g. .wav, .mp3, .m4a)
    token : Hugging Face token (default: from HF_TOKEN or HUGGINGFACE_HUB_TOKEN)
    pipeline_id : pretrained pipeline (e.g. pyannote/speaker-diarization-community-1)
    num_speakers : fix number of speakers (optional)
    min_speakers, max_speakers : speaker count bounds (optional)
    pipeline_params : optional dict to tune accuracy, e.g.:
        - segmentation.min_duration_off : merge speech segments separated by
          shorter silence (seconds). Slightly higher (e.g. 0.05–0.2) can reduce
          flicker; 0.0 keeps default.
        - clustering.threshold : VBx clustering threshold (default 0.6). Lower
          (e.g. 0.5) = more clusters (risk over-segmentation); higher = fewer.
        - clustering.Fa, clustering.Fb : VBx parameters (defaults 0.07, 0.8).
      Example: {"segmentation": {"min_duration_off": 0.1}, "clustering": {"threshold": 0.55}}
    output_rttm : if set, write RTTM output to this path
    """
    audio_path = Path(audio_path)
    if not audio_path.is_file():
        raise FileNotFoundError(f"Audio file not found: {audio_path}")

    hf_token = token or os.environ.get("HF_TOKEN") or os.environ.get("HUGGINGFACE_HUB_TOKEN")
    if not hf_token:
        raise ValueError(
            "Hugging Face token required. Set HF_TOKEN or HUGGINGFACE_HUB_TOKEN, "
            "or pass token=... . Accept conditions at "
            "https://huggingface.co/pyannote/speaker-diarization-3.1"
        )

    print(f"Loading pipeline: {pipeline_id}")
    pipeline = Pipeline.from_pretrained(pipeline_id, token=hf_token)
    if pipeline is None:
        raise RuntimeError(f"Failed to load pipeline: {pipeline_id}")

    # Optional: tune pipeline for better accuracy (community-1 defaults:
    # segmentation.min_duration_off=0.0, clustering.threshold=0.6, Fa=0.07, Fb=0.8)
    if pipeline_params:
        pipeline.instantiate(pipeline_params)
        print("Applied pipeline params:", pipeline_params)

    # Use CUDA when available, otherwise CPU
    if torch.cuda.is_available():
        device = torch.device("cuda")
        print(f"Using device: {device} ({torch.cuda.get_device_name(0)})")
    else:
        device = torch.device("cpu")
        print(
            "Using device: cpu (CUDA not available). "
            "To use GPU: ensure this machine has an NVIDIA GPU and the NVIDIA driver is installed (run: nvidia-smi)."
        )
    pipeline.to(device)

    print(f"Diarizing: {audio_path}")
    # Load with TorchCodec (recommended); pass waveform dict to avoid deprecated torchaudio path in pyannote
    waveform, sr = load_audio(audio_path, sample_rate=TARGET_SAMPLE_RATE)
    if waveform.shape[0] > 1:
        waveform = waveform.mean(dim=0, keepdim=True)
    audio_input = {"waveform": waveform, "sample_rate": sr}

    kwargs = {}
    if num_speakers is not None:
        kwargs["num_speakers"] = num_speakers
    if min_speakers is not None:
        kwargs["min_speakers"] = min_speakers
    if max_speakers is not None:
        kwargs["max_speakers"] = max_speakers

    diarization = pipeline(audio_input, **kwargs)
    annotation = get_diarization(diarization)

    print("\nSpeaker segments:")
    print("-" * 60)
    for item in annotation.itertracks(yield_label=True):
        segment, speaker = item[0], item[2] if len(item) >= 3 else item[1]
        print(f"  {segment.start:.2f}s - {segment.end:.2f}s  {speaker}")
    print("-" * 60)

    if output_rttm:
        out = Path(output_rttm)
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "w") as f:
            annotation.write_rttm(f)
        print(f"RTTM written to: {out}")

    return annotation


def main():
    parser = argparse.ArgumentParser(description="Speaker diarization with pyannote.audio")
    parser.add_argument(
        "audio",
        type=Path,
        help="Path to audio file (e.g. .wav, .mp3, .m4a)",
    )
    parser.add_argument(
        "-t", "--token",
        default=None,
        help="Hugging Face token (default: HF_TOKEN / HUGGINGFACE_HUB_TOKEN)",
    )
    parser.add_argument(
        "-p", "--pipeline",
        default="pyannote/speaker-diarization-3.1",
        help="Pretrained pipeline ID (default: pyannote/speaker-diarization-3.1)",
    )
    parser.add_argument(
        "--num-speakers",
        type=int,
        default=None,
        help="Fixed number of speakers",
    )
    parser.add_argument(
        "--min-speakers",
        type=int,
        default=None,
        help="Minimum number of speakers",
    )
    parser.add_argument(
        "--max-speakers",
        type=int,
        default=None,
        help="Maximum number of speakers",
    )
    parser.add_argument(
        "-o", "--output-rttm",
        type=Path,
        default=None,
        help="Write RTTM output to this path",
    )
    parser.add_argument(
        "--min-duration-off",
        type=float,
        default=None,
        metavar="SEC",
        help="Merge speech segments separated by shorter silence (e.g. 0.1). Improves stability.",
    )
    parser.add_argument(
        "--clustering-threshold",
        type=float,
        default=None,
        metavar="FLOAT",
        help="VBx clustering threshold (default 0.6). Lower=more speakers, higher=fewer.",
    )
    args = parser.parse_args()

    pipeline_params = None
    if args.min_duration_off is not None or args.clustering_threshold is not None:
        pipeline_params = {}
        if args.min_duration_off is not None:
            pipeline_params.setdefault("segmentation", {})["min_duration_off"] = args.min_duration_off
        if args.clustering_threshold is not None:
            pipeline_params.setdefault("clustering", {})["threshold"] = args.clustering_threshold

    run_diarization(
        audio_path=args.audio,
        token=args.token,
        pipeline_id=args.pipeline,
        num_speakers=args.num_speakers,
        min_speakers=args.min_speakers,
        max_speakers=args.max_speakers,
        pipeline_params=pipeline_params,
        output_rttm=args.output_rttm,
    )


if __name__ == "__main__":
    main()
