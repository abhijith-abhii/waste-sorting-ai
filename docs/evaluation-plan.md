# Raspberry Pi AI implementation and evaluation protocol

Destination corrected by user: abhijith-abhii GitHub profile README and existing Abhijith portfolio. Contact abhijithviswanathan03@gmail.com. No email sending requested.

Projects: classroom-lighting-ai, parking-gate-ai, waste-sorting-ai. Each is a standalone local Python application with an interchangeable hardware layer, Flask dashboard and recorded inputs. No Pi emulator claim; virtual devices exercise control logic without reproducing electrical timing.

Before measurements: keep test scenes untouched during tuning. Detection baseline YOLO11n pretrained on COCO at confidence .25, resolution 320. Compare resolution 640 and validation-selected confidence separately; evaluate target classes with greedy class-specific IoU .5 matching, excluding crowd annotations and recording the limitation. Use a deterministic COCO validation subset partitioned by image; COCO is public benchmark data known to model developers, not an independent unseen deployment set. Classroom physical-presence semantics differ from COCO's visual labels. No identity recognition.

Waste: TrashNet five known material classes, trash withheld as proxy unknown. Exact duplicates grouped; filename/scene provenance limits noted. Train a color-feature baseline and a linear classifier on frozen ImageNet MobileNetV3 features. Fit weights only on training data; select regularization and rejection threshold only on validation; freeze config before test evaluation. Not full neural-network fine-tuning or training from scratch.

Controller acceptance: never automatically turn lights off on stale/uncertain camera; default recheck 600 simulated seconds, event checks, grace, manual overrides with expiry. Gate never closes on invalid/blocked obstruction input; fault recovery requires fresh clear evidence. Sorter never routes low confidence/full/invalid sensor items, and never increments successful disposal before acknowledgement. Persistence, duplicate IDs, invalid numbers, timestamp reversal, timeouts, manual overrides and recovery receive tests.

Comparisons: baseline rules, each relevant safeguard individually, combined policy on identical scenario traces. Measure control errors and availability costs separately. Energy is a stated lighting-load estimate, not measured Pi power. Host latency includes process environment and sample count, no Pi performance claims.

Deliver: actual inference, real classifier training, local interactive demos, raw evaluation records, requirements-to-tests matrix, failure ledger, editable/PDF reports, mentor guides, hardware wiring plans, three source repositories and portfolio index update. Publishing requires destination access; continue all independent work meanwhile.
