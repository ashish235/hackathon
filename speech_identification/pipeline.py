"""
End-to-end pipeline: meeting recording → diarization → split → merge → embeddings → speaker match.

Steps:
1. Take meeting recording as input
2. Perform speech diarization (pyannote)
3. Split main audio by speaker segments (from RTTM)
4. Merge all clips per speaker into one file per speaker
5. Compute embeddings for merged clips
6. Match each speaker's embedding to sample_embeddings_dir and output the best match

Requires HF_TOKEN or HUGGINGFACE_HUB_TOKEN for pyannote models.
"""

import argparse
import shutil
import subprocess
import sys
import warnings
from pathlib import Path
from typing import Mapping

# Suppress noisy pyannote/PyTorch warnings (harmless for our pipeline)
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

# Import from existing modules
from main import run_diarization
from split_audio import split_audio_by_rttm
from merge_speaker_clips import merge_speaker_clips
from compute_embeddings import compute_embeddings
from match_embeddings import (
    load_embeddings_dir,
    cosine_similarity,
)


def run_pipeline(
    meeting_audio: str | Path,
    sample_embeddings_dir: str | Path,
    work_dir: str | Path | None = None,
    token: str | None = None,
    num_speakers: int | None = None,
    min_speakers: int | None = None,
    max_speakers: int | None = None,
    pipeline_id: str = "pyannote/speaker-diarization-community-1",
    pipeline_params: dict | None = None,
    transcribe_with_vexa: bool = True,
    vexa_dir: str | Path = "/home/ubuntu/vexa",
) -> dict[str, tuple[str, float]]:
    """
    Run the full pipeline and return best sample match per speaker.

    If transcribe_with_vexa is True and vexa_dir is set, runs
    ``make transcribe-local FOLDER=<output_dir> OUTPUT=<work_dir>/transcript.txt``
    from vexa_dir as a final step (output_dir = work_dir/output with speaker-named WAVs).

    Returns
    -------
    dict mapping speaker_id (e.g. "SPEAKER_00") -> (best_sample_name, cosine_similarity)
    """
    meeting_audio = Path(meeting_audio)
    sample_embeddings_dir = Path(sample_embeddings_dir)

    if not meeting_audio.is_file():
        raise FileNotFoundError(f"Meeting audio not found: {meeting_audio}")
    if not sample_embeddings_dir.is_dir():
        raise NotADirectoryError(f"Sample embeddings dir not found: {sample_embeddings_dir}")

    if work_dir is None:
        work_dir = meeting_audio.parent / f"{meeting_audio.stem}_pipeline"
    work_dir = Path(work_dir)
    if work_dir.exists():
        shutil.rmtree(work_dir)
        print(f"Cleaned work directory: {work_dir}")
    work_dir.mkdir(parents=True, exist_ok=True)

    rttm_path = work_dir / "diarization.rttm"
    splits_dir = work_dir / "splits"
    output_dir = work_dir / "output"
    merged_dir = work_dir / "merged"
    embeddings_dir = work_dir / "embeddings"

    # --- 1 & 2: Diarization ---
    print("=" * 60)
    print("Step 1-2: Diarization")
    print("=" * 60)
    annotation = run_diarization(
        audio_path=meeting_audio,
        token=token,
        pipeline_id=pipeline_id,
        num_speakers=num_speakers,
        min_speakers=min_speakers,
        max_speakers=max_speakers,
        pipeline_params=pipeline_params,
        output_rttm=rttm_path,
    )
    # Ensure RTTM uri matches audio stem for split_audio lookup
    if hasattr(annotation, "uri") and annotation.uri != meeting_audio.stem:
        annotation.uri = meeting_audio.stem
        with open(rttm_path, "w") as f:
            annotation.write_rttm(f)

    # --- 3: Split by speaker ---
    print("\n" + "=" * 60)
    print("Step 3: Split audio by speaker")
    print("=" * 60)
    split_audio_by_rttm(
        audio_path=meeting_audio,
        rttm_path=rttm_path,
        output_dir=splits_dir,
        ordered_output_dir=output_dir,
    )

    # --- 4: Merge clips per speaker ---
    print("\n" + "=" * 60)
    print("Step 4: Merge clips per speaker")
    print("=" * 60)
    merge_speaker_clips(
        input_dir=splits_dir,
        output_dir=merged_dir,
    )

    # --- 5: Compute embeddings for merged clips ---
    print("\n" + "=" * 60)
    print("Step 5: Compute embeddings for merged clips")
    print("=" * 60)
    compute_embeddings(
        input_dir=merged_dir,
        token=token,
        output_dir=embeddings_dir,
        output_format="npy",
        pattern="*.wav",
    )

    # --- 6: Match to sample_embeddings_dir ---
    print("\n" + "=" * 60)
    print("Step 6: Match speakers to sample embeddings")
    print("=" * 60)

    meeting_embeddings = load_embeddings_dir(embeddings_dir)
    sample_embeddings = load_embeddings_dir(sample_embeddings_dir)

    if not meeting_embeddings:
        raise RuntimeError(f"No embeddings found in {embeddings_dir}")
    if not sample_embeddings:
        raise RuntimeError(f"No embeddings found in {sample_embeddings_dir}")

    # Build all (meeting_speaker, sample, score) triples
    candidates: list[tuple[str, str, float]] = []
    for target_name, target_emb in meeting_embeddings.items():
        for source_name, source_emb in sample_embeddings.items():
            try:
                score = cosine_similarity(source_emb, target_emb)
                candidates.append((target_name, source_name, score))
            except ValueError as e:
                print(f"  Skip {target_name} vs {source_name}: {e}")

    # Sort by score descending so higher-scoring pairs are assigned first
    candidates.sort(key=lambda x: x[2], reverse=True)

    # Greedy 1:1 assignment: each meeting speaker and each sample used at most once.
    # If two meeting speakers both want the same sample, the one with higher score gets it;
    # the other will get its next-best available sample when we process later entries.
    assigned_meeting: set[str] = set()
    assigned_sample: set[str] = set()
    results: dict[str, tuple[str, float]] = {}

    for target_name, source_name, score in candidates:
        if target_name in assigned_meeting or source_name in assigned_sample:
            continue
        assigned_meeting.add(target_name)
        assigned_sample.add(source_name)
        results[target_name] = (source_name, score)

    # Report: one line per meeting speaker
    for target_name in sorted(meeting_embeddings.keys()):
        if target_name in results:
            sample_name, score = results[target_name]
            print(f"  {target_name} -> {sample_name}  (cosine similarity: {score:.4f})")
        else:
            print(f"  {target_name} -> no sample assigned (all samples taken)")

    # --- 7: Rename ordered splits with speaker names ---
    ordered_dir = output_dir
    if ordered_dir.is_dir() and results:
        print("\n" + "=" * 60)
        print("Step 7: Rename ordered splits with speaker names")
        print("=" * 60)
        _rename_ordered_with_speaker_names(ordered_dir, results, meeting_embeddings)

    # --- 8: Optional Vexa transcription of output folder ---
    if transcribe_with_vexa and vexa_dir is not None:
        vexa_path = Path(vexa_dir)
        if not vexa_path.is_dir():
            raise NotADirectoryError(f"vexa_dir not found: {vexa_path}")
        transcript_path = work_dir / "transcript.txt"
        print("\n" + "=" * 60)
        print("Step 8: Transcribe output folder (make transcribe-local)")
        print("=" * 60)
        print(f"  FOLDER={ordered_dir}  OUTPUT={transcript_path}")
        subprocess.run(
            ["make", "transcribe-local", f"FOLDER={ordered_dir}", f"OUTPUT={transcript_path}"],
            cwd=vexa_path,
            check=True,
        )
        print(f"  Transcript written to: {transcript_path}")

    return results


def _speaker_id_from_embedding_key(key: str) -> str:
    """Extract speaker id from embedding filename, e.g. SPEAKER_00_merged_embedding.npy -> SPEAKER_00."""
    if "_merged_embedding" in key:
        return key.split("_merged_embedding")[0]
    return key


def _person_name_from_sample_key(sample_key: str) -> str:
    """Extract short display name from sample embedding filename, e.g. Aditya-Sample_embedding.npy -> Aditya."""
    stem = Path(sample_key).stem
    name = stem.replace("_embedding", "").replace("_merged_embedding", "")
    return name.split("-")[0] if "-" in name else name


def _rename_ordered_with_speaker_names(
    ordered_dir: Path,
    results: dict[str, tuple[str, float]],
    meeting_embeddings: Mapping[str, object],
) -> None:
    """Rename files in ordered/ from {index}_{SPEAKER_xx}.wav to {index}-{person_name}.wav (e.g. 0-Aditya.wav)."""
    # Build speaker_id (SPEAKER_00) -> short name (Aditya)
    speaker_to_name: dict[str, str] = {}
    for emb_key, (sample_key, _) in results.items():
        speaker_id = _speaker_id_from_embedding_key(emb_key)
        speaker_to_name[speaker_id] = _person_name_from_sample_key(sample_key)

    renamed = 0
    for path in sorted(ordered_dir.iterdir()):
        if path.suffix.lower() != ".wav" or not path.is_file():
            continue
        stem = path.stem
        parts = stem.split("_", 1)
        if len(parts) != 2:
            continue
        idx, speaker_id = parts
        if speaker_id not in speaker_to_name:
            continue
        new_name = f"{idx}-{speaker_to_name[speaker_id]}.wav"
        new_path = path.parent / new_name
        if new_path == path:
            continue
        if new_path.exists():
            new_path.unlink()
        path.rename(new_path)
        renamed += 1
        print(f"  {path.name} -> {new_name}")

    if renamed:
        print(f"\nRenamed {renamed} file(s) in {ordered_dir}/ to use speaker names.")


def main():
    parser = argparse.ArgumentParser(
        description="Full pipeline: meeting → diarization → split → merge → embeddings → speaker match",
    )
    parser.add_argument(
        "meeting_audio",
        type=Path,
        help="Path to meeting recording (e.g. .wav, .m4a)",
    )
    parser.add_argument(
        "--sample-embeddings-dir",
        type=Path,
        default=Path("sample_embeddings_dir"),
        help="Directory with sample embeddings to match against (default: sample_embeddings_dir)",
    )
    parser.add_argument(
        "-w", "--work-dir",
        type=Path,
        default=None,
        help="Working directory for RTTM, splits, merged, embeddings (default: <audio_stem>_pipeline)",
    )
    parser.add_argument(
        "-t", "--token",
        default=None,
        help="Hugging Face token (default: HF_TOKEN / HUGGINGFACE_HUB_TOKEN)",
    )
    parser.add_argument(
        "--num-speakers",
        type=int,
        default=None,
        help="Fixed number of speakers for diarization",
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
        "-p", "--pipeline",
        default="pyannote/speaker-diarization-community-1",
        help="Diarization pipeline ID",
    )
    parser.add_argument(
        "--min-duration-off",
        type=float,
        default=None,
        metavar="SEC",
        help="Diarization: merge short silences (e.g. 0.1)",
    )
    parser.add_argument(
        "--clustering-threshold",
        type=float,
        default=None,
        metavar="FLOAT",
        help="Diarization: VBx clustering threshold",
    )
    parser.add_argument(
        "--transcribe",
        action="store_true",
        default=True,
        help="Run Vexa transcription on output folder (requires --vexa-dir)",
    )
    parser.add_argument(
        "--vexa-dir",
        type=Path,
        default="/home/ubuntu/vexa",
        help="Path to Vexa repo for make transcribe-local (required if --transcribe)",
    )
    args = parser.parse_args()

    if args.transcribe and args.vexa_dir is None:
        parser.error("--transcribe requires --vexa-dir")

    pipeline_params = None
    if args.min_duration_off is not None or args.clustering_threshold is not None:
        pipeline_params = {}
        if args.min_duration_off is not None:
            pipeline_params.setdefault("segmentation", {})["min_duration_off"] = args.min_duration_off
        if args.clustering_threshold is not None:
            pipeline_params.setdefault("clustering", {})["threshold"] = args.clustering_threshold

    try:
        run_pipeline(
            meeting_audio=args.meeting_audio,
            sample_embeddings_dir=args.sample_embeddings_dir,
            work_dir=args.work_dir,
            token=args.token,
            num_speakers=args.num_speakers,
            min_speakers=args.min_speakers,
            max_speakers=args.max_speakers,
            pipeline_id=args.pipeline,
            pipeline_params=pipeline_params,
            transcribe_with_vexa=args.transcribe,
            vexa_dir=args.vexa_dir,
        )
    except Exception as e:
        print(f"Pipeline failed: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
