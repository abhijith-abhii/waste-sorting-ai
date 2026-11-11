"""CPU ONNX inference; model files are fetched explicitly by setup tools."""

from pathlib import Path
import time
import numpy as np
import cv2

LABELS = {
    0: "person",
    2: "car",
    3: "motorcycle",
    5: "bus",
    7: "truck",
    56: "chair",
    62: "screen",
}


class Detector:
    def __init__(self, path, size=640):
        import onnxruntime as ort

        options = ort.SessionOptions()
        options.intra_op_num_threads = 2
        options.inter_op_num_threads = 1
        self.session = ort.InferenceSession(
            str(path), sess_options=options, providers=["CPUExecutionProvider"]
        )
        self.size = size

    def predict(self, image, threshold=0.25):
        start = time.perf_counter()
        h, w = image.shape[:2]
        scale = min(self.size / w, self.size / h)
        nw, nh = round(w * scale), round(h * scale)
        left = (self.size - nw) // 2
        top = (self.size - nh) // 2
        canvas = np.full((self.size, self.size, 3), 114, np.uint8)
        canvas[top : top + nh, left : left + nw] = cv2.resize(image, (nw, nh))
        tensor = canvas[:, :, ::-1].transpose(2, 0, 1)[None].astype(np.float32) / 255
        raw = self.session.run(None, {self.session.get_inputs()[0].name: tensor})[0][
            0
        ].T
        detections = []
        for cls, label in LABELS.items():
            rows = raw[
                (raw[:, 4 + cls] >= threshold) & (raw[:, 4:].argmax(axis=1) == cls)
            ]
            if not len(rows):
                continue
            boxes = []
            scores = []
            for r in rows:
                x, y, bw, bh = r[:4]
                boxes.append(
                    [float(x - bw / 2), float(y - bh / 2), float(bw), float(bh)]
                )
                scores.append(float(r[4 + cls]))
            indices = cv2.dnn.NMSBoxes(boxes, scores, threshold, 0.45)
            for i in np.asarray(indices).reshape(-1):
                x, y, bw, bh = boxes[i]
                box = [
                    max(0, (x - left) / scale / w),
                    max(0, (y - top) / scale / h),
                    min(1, (x + bw - left) / scale / w),
                    min(1, (y + bh - top) / scale / h),
                ]
                if box[2] > box[0] and box[3] > box[1]:
                    detections.append({"label": label, "score": scores[i], "box": box})
        return {
            "detections": detections,
            "latency_ms": (time.perf_counter() - start) * 1000,
            "brightness": float(image.mean()),
            "model": "YOLO11n ONNX CPU",
            "source": "real neural-network inference",
        }


class WasteClassifier:
    def __init__(self, model_dir):
        import onnxruntime as ort

        model_dir = Path(model_dir)
        options = ort.SessionOptions()
        options.intra_op_num_threads = 2
        self.session = ort.InferenceSession(
            str(model_dir / "mobilenet_features.onnx"),
            sess_options=options,
            providers=["CPUExecutionProvider"],
        )
        self.head = np.load(model_dir / "waste_head.npz", allow_pickle=False)

    def predict(self, image):
        start = time.perf_counter()
        # Matches training preprocessing exactly: RGB resize 224, ImageNet normalization.
        x = cv2.resize(image, (224, 224))[:, :, ::-1].astype(np.float32) / 255
        x = (x - np.array([0.485, 0.456, 0.406], np.float32)) / np.array(
            [0.229, 0.224, 0.225], np.float32
        )
        features = self.session.run(
            None, {self.session.get_inputs()[0].name: x.transpose(2, 0, 1)[None]}
        )[0]
        standardized = (features - self.head["mean"]) / self.head["scale"]
        logits = (standardized @ self.head["coef"].T + self.head["intercept"])[0]
        logits -= logits.max()
        p = np.exp(logits)
        p /= p.sum()
        return {
            "probabilities": dict(zip(self.head["classes"].tolist(), p.tolist())),
            "latency_ms": (time.perf_counter() - start) * 1000,
            "model": "Frozen ImageNet MobileNetV3 + trained linear head",
            "source": "real neural-network features and trained classifier",
        }


def annotate(image, result):
    out = image.copy()
    h, w = out.shape[:2]
    for d in result.get("detections", []):
        x1, y1, x2, y2 = [int(v * s) for v, s in zip(d["box"], [w, h, w, h])]
        cv2.rectangle(out, (x1, y1), (x2, y2), (75, 220, 125), 2)
        cv2.putText(
            out,
            f"{d['label']} {d['score']:.2f}",
            (x1, max(18, y1 - 6)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            (75, 220, 125),
            1,
        )
    return out
