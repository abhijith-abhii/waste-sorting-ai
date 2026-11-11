# Reproducible version comparisons

These are named experimental configurations from one development session, not invented historical releases.

| Configuration | Change | Evidence |
|---|---|---|
| Detector baseline | Pretrained YOLO11n, 320 pixels, confidence 0.25 | detection-results.json baseline |
| Resolution only | Same pretrained weights, 640 pixels, confidence 0.25 | detection-results.json resolution_only |
| Validation selection | Compare 0.15, 0.25, 0.40 and 0.55 on validation; 0.25 retained | frozen configuration; same final result as resolution only |
| Classroom baseline | Direct scheduled count to light output | control-results.json baseline |
| Classroom individual safeguards | Grace/confirmation, uncertainty hold, event checks separately | control-results.json ablations |
| Classroom combined | All safeguards | control-results.json combined |
| Parking baseline | Camera-only availability and direct closure requests | control-results.json parking |
| Parking final | Camera/proximity agreement and obstruction interlock | same trace and case set |
| Waste baseline | HSV histogram plus trained linear classifier | classification-results.json color_baseline |
| Waste final | Frozen MobileNet features plus trained linear head | same held-out images |
| Waste control final | Capacity checks, review, acknowledgement and faults | 60 scripted cases, separate from classifier accuracy |

See FAILURES.md for observed software defects and corrections. Initial detector decoder output is retained explicitly and excluded from final comparisons. Baseline models and traces remain reproducible in tools. No Git history was fabricated to suggest earlier independent development.
