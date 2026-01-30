"""
Match source embeddings to target embeddings.

For each embedding in the source directory, finds which embedding
in the target directory has the highest cosine similarity (best match).
"""

import argparse
from pathlib import Path

import numpy as np


def load_embeddings_dir(dir_path: Path) -> dict[str, np.ndarray]:
    """Load all .npy embedding files from a directory. Returns {name: embedding}."""
    embeddings = {}
    for path in sorted(dir_path.glob("*.npy")):
        name = path.stem.replace("_embedding", "").replace("_merged_embedding", "")
        arr = np.load(path, allow_pickle=False)
        arr = np.asarray(arr).flatten().astype(np.float64)
        if arr.size == 0:
            continue
        embeddings[path.name] = arr
    return embeddings


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Cosine similarity between two 1D vectors."""
    a = np.asarray(a, dtype=np.float64).flatten()
    b = np.asarray(b, dtype=np.float64).flatten()
    if a.shape != b.shape:
        raise ValueError(f"Shape mismatch: {a.shape} vs {b.shape}")
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))


def main():
    parser = argparse.ArgumentParser(
        description="Find which target embedding matches best for each source embedding"
    )
    parser.add_argument(
        "--source",
        type=Path,
        default=Path("sample_embeddings_dir"),
        help="Directory containing source embeddings (default: sample_embeddings_dir)",
    )
    parser.add_argument(
        "--target",
        type=Path,
        default=Path("embeddings_dir"),
        help="Directory containing target embeddings (default: embeddings_dir)",
    )
    args = parser.parse_args()

    if not args.source.is_dir():
        raise SystemExit(f"Source directory not found: {args.source}")
    if not args.target.is_dir():
        raise SystemExit(f"Target directory not found: {args.target}")

    source_embeddings = load_embeddings_dir(args.source)
    target_embeddings = load_embeddings_dir(args.target)

    if not source_embeddings:
        raise SystemExit(f"No .npy embeddings found in {args.source}")
    if not target_embeddings:
        raise SystemExit(f"No .npy embeddings found in {args.target}")

    print(f"Source: {args.source} ({len(source_embeddings)} embedding(s))")
    print(f"Target: {args.target} ({len(target_embeddings)} embedding(s))")
    print("-" * 60)

    for source_name, source_emb in source_embeddings.items():
        best_target = None
        best_score = -2.0

        for target_name, target_emb in target_embeddings.items():
            try:
                score = cosine_similarity(source_emb, target_emb)
            except ValueError as e:
                print(f"  Skip {target_name}: {e}")
                continue
            if score > best_score:
                best_score = score
                best_target = target_name

        if best_target is not None:
            print(f"  {source_name}")
            print(f"    -> best match: {best_target}  (cosine similarity: {best_score:.4f})")
        else:
            print(f"  {source_name} -> no valid target match")
        print()


if __name__ == "__main__":
    main()
