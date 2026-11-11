# Dashboard guide

| Panel | Meaning |
|---|---|
| Input and detections | Uploaded image/recorded frame with boxes, or a clearly labeled synthetic scene. |
| Observation | Controller state, distinct from detector confidence. |
| Count and actuator | Candidate count/free slots/acknowledged disposals; virtual output only. |
| Last inference | Measured model/preprocessing time on this host; not Pi latency. |
| Latest decision and sensors | Reason, validity and current virtual sensor values. |
| Observation history | Count versus explicit simulation time; duplicate timestamps may overlap. |
| Experiment controls | Fault scenarios, manual requests, threshold and applicable interval controls. |
| Event ledger | Latest 30 rendered events from a 500-event export window; database retains all events. |
| Recorded benchmarks | Frozen historical results and JSON export; not recomputed by dashboard controls. |

Play requests six simulation seconds about every 100 ms; it is approximately 60x when the host keeps up, not a guaranteed clock rate. One video click reads one frame and advances one simulation second, regardless of file FPS. No webcam was used during validation. Changing a dashboard setting does not rewrite the frozen benchmark.
