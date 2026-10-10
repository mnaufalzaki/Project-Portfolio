#!/bin/bash
# Sets up the free, fully offline transcription engine: whisper.cpp + the large-v3-turbo model.
# Pass --with-ollama to also install Ollama for the optional AI rewriting step.
set -euo pipefail

MODEL_DIR="$HOME/Library/Application Support/Yaping/models"
MODEL="ggml-large-v3-turbo-q5_0.bin"   # ~574 MB, best for Indonesian / mixed speech
URL="https://huggingface.co/ggerganov/whisper.cpp/resolve/main/$MODEL"

echo "→ whisper.cpp"
command -v whisper-server >/dev/null || brew install whisper-cpp

mkdir -p "$MODEL_DIR"
if [ ! -f "$MODEL_DIR/$MODEL" ]; then
    echo "→ Downloading $MODEL (resumable)…"
    curl -L --fail --retry 8 --retry-all-errors --retry-delay 3 -C - \
        -o "$MODEL_DIR/$MODEL.part" "$URL"
    mv "$MODEL_DIR/$MODEL.part" "$MODEL_DIR/$MODEL"
fi
echo "✓ Whisper model: $MODEL_DIR/$MODEL"

if [ "${1:-}" != "--with-ollama" ]; then
    echo "✓ Done. In Yaping › Pengaturan › Mesin AI, choose “Lokal — whisper.cpp”."
    exit 0
fi

echo "→ Ollama"
if ! command -v ollama >/dev/null; then
    brew install ollama
fi
curl -s -m 2 http://127.0.0.1:11434/api/tags >/dev/null || { brew services start ollama; sleep 3; }
if [ "$(curl -s http://127.0.0.1:11434/api/tags | grep -c '"name"')" = "0" ]; then
    echo "→ No Ollama model yet, pulling gemma3:4b (~3 GB)…"
    ollama pull gemma3:4b
fi
echo "✓ Ollama ready"
