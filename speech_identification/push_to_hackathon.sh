#!/bin/bash
# Push this project into ashish235/hackathon as speech_identification/
set -e
REPO_URL="https://github.com/ashish235/hackathon.git"
HACKATHON_DIR="../hackathon"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

cd "$SCRIPT_DIR"

echo "Cloning hackathon repo..."
if [ ! -d "$HACKATHON_DIR" ]; then
  git clone "$REPO_URL" "$HACKATHON_DIR"
else
  echo "  (already exists, pulling latest)"
  (cd "$HACKATHON_DIR" && git pull origin main || true)
fi

echo "Copying project into speech_identification/..."
mkdir -p "$HACKATHON_DIR/speech_identification"
rsync -a \
  --exclude='.git' \
  --exclude='venv' \
  --exclude='.venv' \
  --exclude='__pycache__' \
  --exclude='*_pipeline' \
  --exclude='*_run*' \
  --exclude='.vscode' \
  "$SCRIPT_DIR/" "$HACKATHON_DIR/speech_identification/"

cd "$HACKATHON_DIR"
git add speech_identification/
if git diff --staged --quiet; then
  echo "No changes to commit."
else
  git commit -m "Add speech_identification (pyannote diarization pipeline)"
  echo ""
  echo "Committed. Push with:"
  echo "  cd $HACKATHON_DIR && git push origin main"
fi
