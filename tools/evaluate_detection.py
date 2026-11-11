from pathlib import Path
import json, time, platform, sys, collections, os
import numpy as np, cv2, psutil

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lab.inference import Detector
from lab.tracking import iou, Tracker

root = Path(__file__).resolve().parents[1]
data = root / "data/coco-sample"
manifest = json.loads((data / "manifest.json").read_text())
out = root / "detection-evaluation"
out.mkdir(exist_ok=True)
classes = {1: "person", 3: "car", 4: "motorcycle", 6: "bus", 8: "truck"}
detectors = {s: Detector(root / f"models/detector-{s}.onnx", s) for s in [320, 640]}
cache = {}


def predict(im, size):
    key = (im["id"], size)
    if key not in cache:
        cache[key] = detectors[size].predict(
            cv2.imread(str(data / im["file_name"])), 0.05
        )
    return cache[key]


def evaluate(images, size, threshold, labels):
    tp = fp = fn = 0
    errors = []
    per = {l: [0, 0, 0] for l in labels}
    crowds = 0
    for im in images:
        pred = [
            d
            for d in predict(im, size)["detections"]
            if d["label"] in labels and d["score"] >= threshold
        ]
        gt = []
        for a in im["annotations"]:
            if classes.get(a["category"]) not in labels:
                continue
            if a["iscrowd"]:
                crowds += 1
                continue
            x, y, w, h = a["bbox"]
            gt.append(
                {
                    "label": classes[a["category"]],
                    "box": [
                        x / im["width"],
                        y / im["height"],
                        (x + w) / im["width"],
                        (y + h) / im["height"],
                    ],
                }
            )
        used = set()
        matched = 0
        for d in sorted(pred, key=lambda x: -x["score"]):
            candidates = [
                (iou(d["box"], g["box"]), j)
                for j, g in enumerate(gt)
                if j not in used and d["label"] == g["label"]
            ]
            best = max(candidates, default=(0, None))
            if best[0] >= 0.5:
                tp += 1
                matched += 1
                used.add(best[1])
                per[d["label"]][0] += 1
            else:
                fp += 1
                per[d["label"]][1] += 1
        fn += len(gt) - matched
        for j, g in enumerate(gt):
            if j not in used:
                per[g["label"]][2] += 1
        errors.append(abs(len(pred) - len(gt)))

    def stats(t, f, n):
        precision = t / (t + f) if t + f else 0
        recall = t / (t + n) if t + n else 0
        return {
            "tp": t,
            "fp": f,
            "fn": n,
            "precision": precision,
            "recall": recall,
            "f1": (
                2 * precision * recall / (precision + recall)
                if precision + recall
                else 0
            ),
        }

    return {
        **stats(tp, fp, fn),
        "count_mae": float(np.mean(errors)),
        "images": len(images),
        "ignored_crowd_annotations": crowds,
        "per_class": {l: stats(*v) for l, v in per.items()},
    }


validation = [i for i in manifest["images"] if i["split"] == "validation"]
test = [i for i in manifest["images"] if i["split"] == "test"]
chosen = {}
tuning = {}
for name, labels in [
    ("classroom", ["person"]),
    ("parking", ["car", "motorcycle", "bus", "truck"]),
]:
    candidates = [
        {"threshold": t, "result": evaluate(validation, 640, t, labels)}
        for t in [0.15, 0.25, 0.4, 0.55]
    ]
    best = max(candidates, key=lambda x: x["result"]["f1"])
    chosen[name] = {"threshold": best["threshold"], "size": 640, "labels": labels}
    tuning[name] = candidates
(out / "frozen-config.json").write_text(json.dumps(chosen, indent=2))
print("Validation choices frozen", chosen, flush=True)
# Final test evaluation starts after all choices are fixed.
results = {
    "environment": platform.platform(),
    "protocol": {
        "matching": "class-aware greedy IoU >= .5; counts include all retained boxes",
        "split": "42 validation and 78 test images, metadata-stratified; image-disjoint",
        "baseline": {"size": 320, "threshold": 0.25},
        "selection": chosen,
        "limitations": [
            "COCO visual labels do not establish physical human presence.",
            "COCO val2017 is known to model developers and not an independent unseen deployment dataset.",
            "Crowd GT ignored, but predictions inside crowds still count as false positives; this is not official COCO AP.",
            "Image-level split; recording or scene IDs are unavailable.",
        ],
    },
    "tuning": tuning,
}
for name, config in chosen.items():
    labels = config["labels"]
    results[name] = {
        "baseline": evaluate(test, 320, 0.25, labels),
        "resolution_only": evaluate(test, 640, 0.25, labels),
        "final": evaluate(test, 640, config["threshold"], labels),
    }
    print(name, results[name], flush=True)
# Controlled image transformations: repeated test images, not extra independent samples.
people = [
    im
    for im in test
    if any(a["category"] == 1 and not a["iscrowd"] for a in im["annotations"])
][:10]
stress = []
for im in people:
    image = cv2.imread(str(data / im["file_name"]))
    h, w = image.shape[:2]
    low = (image.astype(float) * 0.18).astype(np.uint8)
    shadow = image.copy()
    shadow[:, : w // 2] = (shadow[:, : w // 2] * 0.25).astype(np.uint8)
    occluded = image.copy()
    cv2.rectangle(occluded, (w // 3, 0), (w // 2, h), (50, 50, 50), -1)
    poster = np.full((h, w, 3), 210, np.uint8)
    poster[h // 5 : 4 * h // 5, w // 5 : 4 * w // 5] = cv2.resize(
        image, (4 * w // 5 - w // 5, 4 * h // 5 - h // 5)
    )
    for label, img in [
        ("original", image),
        ("low_light", low),
        ("shadow", shadow),
        ("partial_occlusion", occluded),
        ("depiction_composite", poster),
    ]:
        r = detectors[640].predict(img, chosen["classroom"]["threshold"])
        ds = [d for d in r["detections"] if d["label"] == "person"]
        stress.append(
            {
                "image_id": im["id"],
                "transform": label,
                "person_candidates": len(ds),
                "brightness": r["brightness"],
                "physical_person_ground_truth": (
                    0 if label == "depiction_composite" else None
                ),
            }
        )
(out / "stress-tests.json").write_text(json.dumps(stress, indent=2))
results["classroom"]["depiction_stress"] = {
    "composites": 10,
    "images_with_false_physical_person_candidate": sum(
        x["person_candidates"] > 0
        for x in stress
        if x["transform"] == "depiction_composite"
    ),
    "scope": "Entire input is a synthetic framed depiction. COCO source photos transformed; no real classroom posters evaluated. Known depiction zone can mark uncertainty; tracking alone does not solve this.",
}
# Repeated timing on the same 12 images, CPU only, after warmup.
process = psutil.Process()
timing = {}
for size in [320, 640]:
    samples = []
    cpu0 = process.cpu_times()
    t0 = time.perf_counter()
    for repeat in range(3):
        for im in test[:12]:
            samples.append(
                detectors[size].predict(cv2.imread(str(data / im["file_name"])), 0.25)[
                    "latency_ms"
                ]
            )
    wall = time.perf_counter() - t0
    cpu1 = process.cpu_times()
    timing[str(size)] = {
        "count": len(samples),
        "repeats": 3,
        "median_ms": float(np.median(samples)),
        "p95_ms": float(np.percentile(samples, 95)),
        "throughput_images_s": len(samples) / wall,
        "wall_seconds": wall,
        "cpu_seconds": cpu1.user + cpu1.system - cpu0.user - cpu0.system,
        "cpu_core_equivalents": (cpu1.user + cpu1.system - cpu0.user - cpu0.system)
        / wall,
        "rss_bytes": process.memory_info().rss,
        "samples_ms": samples,
    }
results["host_timing"] = timing
(out / "results.json").write_text(json.dumps(results, indent=2))
(out / "predictions.json").write_text(
    json.dumps(
        [{"image_id": key[0], "size": key[1], **value} for key, value in cache.items()],
        indent=2,
    )
)
print("Final detection evaluation saved", flush=True)
