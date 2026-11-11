# Development failures and corrective actions

## D01 Detector label assignment review
The first evaluator retained any class score above threshold, allowing a single YOLO proposal to become both a car and a truck. Per-class suppression did not remove cross-class duplicates. Review replaced this with the highest-scoring class across all 80 outputs, followed by class-aware suppression. Initial results are retained in initial-multilabel-results.json and excluded from headline comparisons. The same test images are rerun after this decoding correction; they were not used for threshold selection. This is an evaluator correction, not model training or an accuracy-tuned test-set optimization.

## D02 Stale image reuse review
The initial runtime reused an old image count at every future camera check. It now timestamps actual inference inputs and refuses to refresh a camera observation without a new frame. Synthetic fixtures are explicitly labeled and remain independent. Regression covers a reused empty image.

## D03 Obstruction fusion review
Camera inference initially overwrote the virtual proximity obstruction flag. Camera and proximity evidence now remain separate and are OR-combined; invalid or stale evidence prevents closure. Regression ensures an empty image cannot clear a physical-obstruction input.

## D04 Full bin during motion review
Fill level initially applied only at classification. The controller now faults if the bin becomes full before acknowledgement, with no disposal increment. A regression covers this transition.

These were code-review findings, not claimed incidents on physical hardware. Initial 38 controller tests passed; added regressions and HTTP tests subsequently passed. No fabricated historical release timeline is implied.

## D05 Stale parking evidence and misleading scenario panel
Browser and source review found that old camera space values could remain available after frame expiry, although the gate interlock already held. The runtime now reserves all spaces on stale images; a regression verifies availability drops from four to zero after three simulated seconds. Scenario playback now clears prior neural-network overlays and probabilities so scripted scores cannot appear to be a new AI result. The history chart now spaces observations by elapsed simulation time. These are observed software findings, not physical incidents.

## D06 Restart freshness and inference rollback
Review found that restored camera readings inherited fixture freshness and that an inference transaction failure could leave new tracker state in memory. Restart now invalidates camera evidence, and inference restores its input and tracker snapshot on storage failure. Regression tests inject a failing SQLite commit and restart after an empty image.

## D07 Scenario replay after restart
Final browser testing found that a stationary preset inherited a disconnected camera and the parking obstruction preset inherited a restart FAULT. Presets now explicitly restore their virtual devices; the parking replay waits three simulated seconds and requests guarded fault reset before replaying closure. The sorter panel now labels a nonmoving actuator STOPPED while retaining its last target. Scenario results and real-inference results are displayed separately.

## G01 Generated stress scene
The mixed pile received an 82.1% cardboard score and passed the selected confidence rule. Explicitly marking the item as mixed routed it to review; the classifier alone did not establish material purity.

Exploratory synthetic input, n=1; no statistical accuracy claim or model improvement is inferred. See generated-tests.md and evidence/generated-image-test.json.
