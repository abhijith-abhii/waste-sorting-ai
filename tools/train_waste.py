"""Freeze feature extractor; fit train-only classifiers, tune validation, then test once."""

from pathlib import Path
import os, json, hashlib, time, platform

os.environ["OMP_NUM_THREADS"] = "2"
import numpy as np, cv2, onnxruntime as ort
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import (
    accuracy_score,
    f1_score,
    confusion_matrix,
    classification_report,
)

root = Path(__file__).resolve().parents[1]
data = root / "data/dataset-resized"
out = root / "waste-evaluation"
out.mkdir(exist_ok=True)
classes = ["cardboard", "glass", "metal", "paper", "plastic"]
records = []
groups = {}
for p in sorted(data.rglob("*.jpg")):
    if p.parent.name not in classes + ["trash"]:
        continue
    digest = hashlib.sha256(p.read_bytes()).hexdigest()
    groups.setdefault(digest, []).append(p)
# Entire exact-duplicate groups share a split. No final test image used in selection.
for digest, paths in sorted(groups.items()):
    p = paths[0]
    bucket = (
        int(hashlib.sha256(("split-20261111:" + digest).encode()).hexdigest()[:8], 16)
        % 100
    )
    split = "train" if bucket < 60 else "validation" if bucket < 80 else "test"
    if p.parent.name == "trash" and split == "train":
        split = "unused_unknown"
    records.append(
        {
            "path": str(p.relative_to(data)),
            "label": p.parent.name,
            "sha256": digest,
            "split": split,
            "duplicates": [str(q.relative_to(data)) for q in paths[1:]],
        }
    )
(out / "split-manifest.json").write_text(json.dumps(records, indent=2))
options = ort.SessionOptions()
options.intra_op_num_threads = 2
session = ort.InferenceSession(
    str(root / "models/mobilenet_features.onnx"),
    sess_options=options,
    providers=["CPUExecutionProvider"],
)
features = []
colors = []
times = []
start = time.perf_counter()
for i, r in enumerate(records):
    img = cv2.imread(str(data / r["path"]))
    x = cv2.resize(img, (224, 224))[:, :, ::-1].astype(np.float32) / 255
    normalized = (x - np.array([0.485, 0.456, 0.406], np.float32)) / np.array(
        [0.229, 0.224, 0.225], np.float32
    )
    t = time.perf_counter()
    f = session.run(None, {"images": normalized.transpose(2, 0, 1)[None]})[0][0]
    times.append((time.perf_counter() - t) * 1000)
    features.append(f)
    hsv = cv2.cvtColor(cv2.resize(img, (64, 64)), cv2.COLOR_BGR2HSV)
    colors.append(
        np.concatenate(
            [
                cv2.calcHist(
                    [hsv], [c], None, [16], [0, 180 if c == 0 else 256]
                ).flatten()
                / 4096
                for c in range(3)
            ]
        )
    )
    if i % 250 == 0:
        print("Extracted", i, "/", len(records), flush=True)
X = np.asarray(features)
B = np.asarray(colors)
labels = np.array([r["label"] for r in records])
splits = np.array([r["split"] for r in records])
known = labels != "trash"
train = (splits == "train") & known
val = (splits == "validation") & known
test = (splits == "test") & known
np.savez_compressed(
    out / "features.npz", features=X, colors=B, labels=labels, splits=splits
)
fits = {}
tuning = []
training_start = time.perf_counter()
for name, arr in [("color_baseline", B), ("frozen_mobilenet", X)]:
    scaler = StandardScaler().fit(arr[train])
    best = None
    for c in [0.01, 0.1, 1.0]:
        clf = LogisticRegression(
            C=c, max_iter=2000, random_state=42, class_weight="balanced"
        ).fit(scaler.transform(arr[train]), labels[train])
        score = f1_score(
            labels[val], clf.predict(scaler.transform(arr[val])), average="macro"
        )
        tuning.append({"model": name, "C": c, "validation_macro_f1": score})
        if best is None or score > best[0]:
            best = (score, scaler, clf, c)
    fits[name] = best
_, scaler, clf, c = fits["frozen_mobilenet"]
vprobs = clf.predict_proba(scaler.transform(X[splits == "validation"]))
vl = labels[splits == "validation"]
unknown = vl == "trash"
# Choose threshold using known precision and unknown rejection jointly; held-out trash is a proxy, not universal OOD.
choices = []
for threshold in [0.5, 0.6, 0.7, 0.8, 0.9]:
    for margin in [0.0, 0.1, 0.2]:
        top = np.sort(vprobs, axis=1)
        accept = (top[:, -1] >= threshold) & ((top[:, -1] - top[:, -2]) >= margin)
        pred = clf.classes_[vprobs.argmax(1)].astype(object)
        pred[~accept] = "unknown"
        truth = np.where(unknown, "unknown", vl)
        score = f1_score(
            truth, pred, labels=classes + ["unknown"], average="macro", zero_division=0
        )
        choices.append(
            {
                "threshold": threshold,
                "margin": margin,
                "validation_macro_f1_with_unknown": score,
            }
        )
choice = max(choices, key=lambda r: r["validation_macro_f1_with_unknown"])
frozen = {
    "C": c,
    "threshold": choice["threshold"],
    "margin": choice["margin"],
    "seed": 42,
    "training": "L2 multinomial logistic regression, balanced class weights, max_iter 2000; frozen ImageNet backbone",
    "known_classes": classes,
    "split_seed": "split-20261111",
}
(out / "frozen-config.json").write_text(json.dumps(frozen, indent=2))
np.savez_compressed(
    root / "models/waste_head.npz",
    mean=scaler.mean_.astype(np.float32),
    scale=scaler.scale_.astype(np.float32),
    coef=clf.coef_.astype(np.float32),
    intercept=clf.intercept_.astype(np.float32),
    classes=clf.classes_,
)
# Final test labels first used below, after all choices are frozen to disk.
results = {}
for name, arr in [("color_baseline", B), ("frozen_mobilenet", X)]:
    _, s, m, candidate = fits[name]
    pred = m.predict(s.transform(arr[test]))
    results[name] = {
        "accuracy": accuracy_score(labels[test], pred),
        "macro_f1": f1_score(labels[test], pred, average="macro"),
        "confusion_matrix": confusion_matrix(
            labels[test], pred, labels=classes
        ).tolist(),
        "per_class": classification_report(
            labels[test], pred, labels=classes, output_dict=True, zero_division=0
        ),
        "C": candidate,
    }
mask = splits == "test"
probs = clf.predict_proba(scaler.transform(X[mask]))
top = np.sort(probs, axis=1)
accept = (top[:, -1] >= choice["threshold"]) & (
    (top[:, -1] - top[:, -2]) >= choice["margin"]
)
pred = clf.classes_[probs.argmax(1)].astype(object)
pred[~accept] = "unknown"
truth = np.where(labels[mask] == "trash", "unknown", labels[mask])
u = truth == "unknown"
k = ~u
results["rejection"] = {
    "accuracy_including_unknown": accuracy_score(truth, pred),
    "macro_f1_including_unknown": f1_score(truth, pred, average="macro"),
    "unknown_recall": float(np.mean(pred[u] == "unknown")),
    "known_acceptance": float(accept[k].mean()),
    "accepted_known_accuracy": (
        float(np.mean(pred[k & accept] == truth[k & accept]))
        if np.any(k & accept)
        else None
    ),
    "confusion_matrix": confusion_matrix(
        truth, pred, labels=classes + ["unknown"]
    ).tolist(),
    "unknown_count": int(u.sum()),
    "known_count": int(k.sum()),
}
results.update(
    environment=platform.platform(),
    training_seconds=time.perf_counter() - training_start,
    feature_extraction_seconds=training_start - start,
    feature_latency_ms={
        "median": float(np.median(times)),
        "p95": float(np.percentile(times, 95)),
        "count": len(times),
    },
    counts={
        s: {c: int(np.sum((splits == s) & (labels == c))) for c in classes + ["trash"]}
        for s in set(splits)
    },
    tuning=tuning,
    rejection_tuning=choices,
    frozen_config=frozen,
    limitations=[
        "Image-level split with exact-duplicate grouping; physical-object and acquisition-session identities unavailable, so near-duplicate/scene leakage cannot be ruled out.",
        "Trash is an imperfect unknown proxy, not a comprehensive out-of-distribution test.",
        "TrashNet isolated objects differ from dirty mixed waste streams. No field accuracy or Pi latency measured.",
    ],
)
(out / "results.json").write_text(json.dumps(results, indent=2))
(out / "test-predictions.json").write_text(
    json.dumps(
        [
            {
                "path": r["path"],
                "truth": str(t),
                "prediction": str(p),
                "confidence": float(conf),
                "accepted": bool(a),
            }
            for r, t, p, conf, a in zip(
                [r for r in records if r["split"] == "test"],
                truth,
                pred,
                probs.max(1),
                accept,
            )
        ],
        indent=2,
    )
)
print(
    json.dumps(
        {k: results[k] for k in ["color_baseline", "frozen_mobilenet", "rejection"]},
        indent=2,
    ),
    flush=True,
)
