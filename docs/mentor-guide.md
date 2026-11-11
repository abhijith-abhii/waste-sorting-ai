# Code walkthrough and interview guide

Start in app.py: it reads project.json, creates the Flask application and optionally opens a recorded video. lab/web.py defines the request boundary and serializes inference. lab/inference.py converts pixels into boxes or probabilities; it does not decide what a physical actuator should do. lab/tracking.py links boxes by class and overlap, expires tracks and counts line crossings. lab/runtime.py combines inputs, advances the explicit clock and calls the controller. lab/core.py contains deterministic state transitions without a camera or browser dependency. lab/hal.py supplies clocks, sensors, outputs and SQLite persistence. static/app.js displays state and sends explicit user actions.

Read one scenario JSON next. Each object is a command, such as setting sensor values, checking, or advancing time. Run the matching test in tests/test_core.py and change one input. Then inspect evidence/results.json and the raw trace to connect a rule to a measured outcome. The projects share a controller library and regression suite; the repeated 56-test result is the same suite run in each standalone package, not 168 unique tests.

## Decisions and alternatives

Known-class accuracy rose from 62.17% to 90.27%, a 28.10 percentage-point gain (45.20% relative). The feature extractor costs more computation than a color histogram. The selected rejection rule recognized only 4 of 21 unknown-proxy images, or 19.05%. A confident prediction cannot establish purity or suitability for automatic disposal.

Python and ONNX make desktop replay practical. A bare-metal RTOS or emulator would not validate camera models without a target-specific peripheral model. A class-aware IoU tracker is simple to inspect but can switch IDs during occlusion; an appearance tracker could improve association at added cost and still would not establish identity or liveness. SQLite keeps events and state atomic, while physical side effects require a separate acknowledgement design.

## Ten interview questions

### 1 What was actually trained?

The standardization statistics and balanced multinomial linear head were learned from 1457 training images. The ImageNet backbone stayed frozen.

### 2 Why is unknown handling weak?

Known-class softmax can be confident for unfamiliar objects. Only 4/21 held-out trash proxies were rejected. Validation selection optimized a six-label macro F1, not guaranteed unknown rejection.

### 3 Why count only after acknowledgement?

A successful classification does not prove physical disposal. An acknowledgement separates an attempted route from a completed action and makes duplicate events testable.

### 4 Can the model identify mixed waste?

Not reliably. Only 16/60 synthetic mixed composites were rejected. An explicit mixed flag routes to review; actual composition needs new labels and inspection.

### 5 How do you prevent test leakage?

Freeze selection using validation before reading final test scores. Exact duplicates are grouped for TrashNet; COCO images are disjoint. Scene identifiers are missing, so independence is limited. Future video splits must hold out entire recordings and locations.

### 6 How do you distinguish confidence from accuracy?

Confidence is one model score. Accuracy is a frequency measured against held-out labels. The dashboard displays scores while the evidence files report measured performance.

### 7 Why use an explicit simulation clock?

It makes long timeouts deterministic and replayable. A 600-second step integrates one-second controller ticks. This does not emulate Pi scheduling, camera timing or electrical behavior.

### 8 What happens when saving fails?

SQLite commits an event ID and state together. Failed commits restore controller and inference/tracker snapshots. A real actuator cannot be rolled back this way, so physical integration needs an outbox and acknowledgement protocol.

### 9 How is a retry different from a new event?

Reusing an event_id is idempotent. A new event ID is a new command. Waste item IDs prevent repeat counts within a bounded history; a production system needs a durable item ledger across unlimited retention.

### 10 What would you measure on a Raspberry Pi?

End-to-end latency including capture, missed deadlines under CPU load, thermal throttling, process memory, sensor stale time, restart behavior, supply voltage and motor/LED timing. Host measurements cannot be relabeled as Pi results.

## Modifications to implement yourself

1. Compare a higher unknown threshold on validation only and plot rejection against known acceptance before one new held-out evaluation.
2. Add a durable unique item table with an explicit operator reconciliation state after restart.
3. Collect and label real dirty, crushed and mixed objects by acquisition session; compare a fine-tuned model against the frozen-feature baseline.

## Evidence backed resume bullets

- Trained a five-class waste classifier using frozen MobileNetV3 features and a balanced linear head on 1457 training images, with separate validation and test splits.
- Raised held-out known-material accuracy from 62.17% to 90.27% on 452 images against a color-feature baseline; reported unknown rejection separately at 4/21.
- Implemented acknowledged sorting, duplicate-event handling and full-bin, jam and timeout recovery; eliminated 50 unsafe disposals in a 60-case scripted comparison.

Use these after you can explain and reproduce the implementation. Keep simulation and AI assistance clear in the project discussion.
