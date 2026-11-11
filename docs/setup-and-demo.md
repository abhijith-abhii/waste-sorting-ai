# Setup and reproducible demonstration

Tested with Python 3.12.14 on macOS arm64. Linux and Raspberry Pi installation are pending validation. Use a recent Python with available pinned wheels; system Python 3.9 is not supported.

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python app.py
# Open http://127.0.0.1:8813
```

Alternatively, after choosing a Python 3.12 environment, run `sh launch.sh`. It creates a local .venv and installs runtime requirements when absent. On Windows use `.venv\Scripts\python.exe` in place of `.venv/bin/python` and launch app.py directly.

The source ZIP excludes pretrained backbones and COCO photos. Control fixtures work without models. For real inference, install conversion dependencies and download/export official weights:

```sh
.venv/bin/python -m pip install -r requirements-training.txt
.venv/bin/python tools/setup_models.py
.venv/bin/python tools/fetch_samples.py
```

The trained waste head and frozen configuration are included; the backbone is fetched by setup. This setup currently exports both detector sizes and the MobileNet backbone, even if the current project uses only one. It can require substantial dependency downloads. Model hashes in evidence describe the original run; export byte hashes may vary with conversion tooling.

For full evaluation, run tools/download_data.py, tools/prepare_detection.py, then tools/evaluate_detection.py or tools/train_waste.py. The data downloader fetches both public source datasets (about 296 MB compressed). Generated outputs go into detection-evaluation, waste-evaluation and control-evaluation; preserve the committed evidence before replacing it. Re-running training evaluates an already-seen test set and is reproduction, not a fresh independent claim. Run tools/benchmark_control.py for controller comparisons.


## Demonstration

Choose paper and Run AI on sample. Sort latest AI result then advance one second to count acknowledgement. Click unknown to route scripted uncertainty to REVIEW; full to inhibit sorting; jam to enter FAULT. Restore devices and Clear fault to return to review; a new item requires a new decision.

To use an authorized recording: `.venv/bin/python app.py --video /absolute/path/recording.mp4`. Each Next video frame click advances one simulated second. Webcam capture requires both `--webcam 0 --authorize-webcam`; it is never opened automatically.

## Regression tests

`.venv/bin/python -m pytest tests -q` runs the shared 56-case suite, including timeouts, malformed inputs, persistence, restart, idempotency and failed commits. It does not require pretrained models. Browser controls and real model inference were checked separately.

## Troubleshooting

- Models unavailable: complete setup_models.py with training requirements installed; control fixtures remain usable.
- Unknown sample: choose an entry first. Missing sample: run fetch_samples.py for COCO or restore the credited waste examples.
- Camera disconnect or old image: acquire a fresh frame; changing clock time cannot refresh a cached image.
- Port occupied: add `--port 8891` and open that port.
- Unexpected prior state: the app persists runtime/state.sqlite. Stop it and move the runtime directory to a backup before starting a clean run.
- Fault does not clear: restore devices and meet the controller recovery guards. A waste fault resets to REVIEW, not automatic disposal.

The Flask development server listens only on loopback. It has no authentication or deployment hardening for remote access. Uploaded images and session logs stay in the local runtime directory and are excluded from source packaging.

## Additional reproduction tools

After full data and model setup, tools/stress_probe.py reproduces synthetic waste and parking stress probes without retuning. tools/measure_requests.py measures 30 warm local requests for this project. Install requirements-docs.txt and run tools/build_report.py to rebuild the editable report from versioned content and charts; PDF conversion requires a Word-compatible renderer. Raw outputs and original environment versions are retained under evidence.
