# SmolVLM camera context

`llm_test.py` connects to the concatenated-JPEG TCP relay published by
`camera/hand_detection.py` on `127.0.0.1:8003`. The root-level
`hand_detection.py` is an older standalone camera script and does not provide
this relay. Port 8002 is the camera source owned by the detection process.

Run the following in separate terminals from the project directory:

```bash
bash start_vlm.sh
/home/pi/Documents/ENV/AI/bin/python camera/hand_detection.py
/home/pi/Documents/ENV/AI/bin/python llm_test.py
```

Camera detection provides the relay; start `llm_test.py` manually after camera
initialization finishes. Camera detection does not start a VLM worker.
The llama-server started by `start_vlm.sh` is still required.
If the assistant already runs camera detection or llama-server, reuse those
processes; restart camera detection to load this change.

Use `python llm_test.py --help` for relay host, port, endpoint, and output options.

The receiver continuously drains the relay while one inference runs at a time.
Intermediate frames are replaced, so slow inference does not build a queue.
JPEGs are forwarded directly without decoding and re-encoding. The existing
relay includes detection overlays; the prompt asks the model to ignore them.
This does not reduce the model's underlying image-encoding or generation time.
The worker processes images continuously, with no added pause between
inferences. At seven seconds per image, scene updates arrive roughly seven
seconds apart. An optional `--cooldown 10` adds idle time if needed; the
receiver continues draining frames during any configured pause.

`start_vlm.sh` now defaults to two generation/prompt-processing threads, one
server slot, lower scheduling priority (`nice -n 10`), and disabled CPU polling.
Restart the existing server to apply these settings. This favors camera CPU
time at the cost of potentially slower VLM responses; it does not reserve CPU
cores. To lower concurrency further, launch with `VLM_THREADS=1 bash start_vlm.sh`.
The model still occupies memory while idle.

The model describes visible people, actions, objects, and surroundings. Results
include image receipt time, completion time, latency, and whether the token
limit cut off the response. Receipt time is measured at the relay consumer;
the relay protocol does not provide a camera capture timestamp. Only recent
results (20 seconds from receipt) are available through `get_latest()` and
`get_context()`.

The script atomically writes `camera/scene_context.json`. The existing
`add_camera_context_to_command()` function adds fresh scene observations to
assistant commands, even when no faces are visible. Face identity and servo
state stay in their existing file. Restart an already-running voice assistant
to load this context-reader change. A custom `--output` path is useful for
standalone testing but is not read by the assistant automatically.

The output file contains a description, not an image. It retains the last
result after shutdown, but the assistant ignores expired results. Run one VLM
worker per output path.

Validation:

```bash
python -m unittest discover -s tests -v
```

## One-off image analysis without the server

Use `smolvlm_image.py` to run the local multimodal CLI for an image; no
llama-server or camera relay is needed:

```bash
python smolvlm_image.py photo.jpg
```

The command-line script accepts only an image path. Other Python code can call
`from smolvlm_image import analyze_image` with an image path. Each call loads the
model, analyzes the image, then exits; the default is two CPU threads;
`LLAMA_CLI`, `VLM_MODEL`, and `VLM_MMPROJ` can override the executable and
model paths when needed.
