#!/bin/bash

LLAMA_DIR="/home/pi/Documents/llama.cpp"
MODEL="/home/pi/models/smolvlm2/SmolVLM2-500M-Video-Instruct-Q8_0.gguf"
MMPROJ="/home/pi/models/smolvlm2/mmproj-SmolVLM2-500M-Video-Instruct-Q8_0.gguf"

HOST="127.0.0.1"
PORT="8080"
# Leave CPU time for camera detection on the four-core Pi.
THREADS="${VLM_THREADS:-3}"

echo "Starting Sofi VLM server..."
echo "Model: SmolVLM2 500M"
echo "Port: $PORT"
echo "Threads: $THREADS"

cd "$LLAMA_DIR" || exit 1

exec nice -n 10 ./build/bin/llama-server \
    -m "$MODEL" \
    --mmproj "$MMPROJ" \
    --host "$HOST" \
    --port "$PORT" \
    -t "$THREADS" \
    --threads-batch "$THREADS" \
    --parallel 1 \
    --poll 0 \
    --poll-batch 0
