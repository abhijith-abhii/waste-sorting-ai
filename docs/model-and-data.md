# Model and dataset card

Training used 1457 known-class images, 478 known validation images and 452 known test images. Unknown-proxy trash counts are 39 validation and 21 test; 77 train-bucket trash images were unused. SHA256 groups exact duplicates into fixed roughly 60/20/20 buckets. A 576-feature frozen ImageNet MobileNetV3-small backbone feeds StandardScaler and balanced L2 multinomial logistic regression. Only the scaler and linear head were fitted on training data. C in {0.01, 0.1, 1} and rejection settings were selected on validation. Frozen C=0.01, threshold=0.5, margin=0.0. No CNN fine-tuning or training from scratch occurred.

TrashNet contains mostly isolated objects and is not representative of dirty mixed waste streams. Exact duplicates are grouped, but physical-object/session identifiers are unavailable, so near-duplicate leakage cannot be excluded. Trash is a narrow proxy for unfamiliar items. In 60 mixed-image composites, only 16 were rejected. Dirt, resampling and black masks are synthetic stress probes, not physical crushing, dirt or hidden contamination measurements.

## Evaluation boundaries

Model confidence is not accuracy. Detector scores use visual object annotations. Classroom physical presence and waste composition need different labels. A real-video evaluation must hold out complete recordings, sites and acquisition sessions; this project has no labeled video test set. Synthetic trajectories test tracker mechanics only.

The detector dataset contains 120 metadata-selected COCO val2017 images: 40 people, 40 vehicle and 40 negative-stratum images, partitioned into 42 validation and 78 test images. COCO val2017 is familiar to model developers, so this is a reproducible local comparison rather than an independent deployment benchmark. Crowds are excluded from matching and may still produce false positives. See the manifest and per-class JSON.

The waste baseline uses a 48-feature HSV histogram with a trained linear classifier. The final uses 576 pretrained neural features with a newly trained head. Both use the same data split. Threshold selection is rule tuning; tracking and fusion are control changes; neither trains network weights. Float32 inference was used; no quantization was claimed.

## Sources and rights

- YOLO11: https://docs.ultralytics.com/models/yolo11/ and https://github.com/ultralytics/ultralytics (AGPL-3.0).
- Original weights: https://github.com/ultralytics/assets/releases/download/v8.3.0/yolo11n.pt
- COCO: https://cocodataset.org/#download and https://cocodataset.org/#termsofuse . Annotations are CC BY 4.0; individual photos retain their Flickr licenses. This package does not redistribute COCO photographs. Sample manifests retain original source URLs and license IDs.
- TrashNet by Gary Thung and Mindy Yang: https://github.com/garythung/trashnet and author-hosted https://huggingface.co/datasets/garythung/trashnet (MIT). Six small credited examples are included in the waste package.
- MobileNetV3 implementation: https://docs.pytorch.org/vision/stable/models/generated/torchvision.models.mobilenet_v3_small.html . Torchvision code uses BSD-3-Clause; pretrained ImageNet weights have separate dataset provenance. Download through the official setup tool; no backbone weights are redistributed in source packages.

Model hashes and frozen selections are retained under evidence. Original decoder results are retained separately from corrected results; the decoder bug was corrected without changing selected hyperparameters, and the same held-out evaluation was rerun. This test-set reuse is disclosed in FAILURES.md.
