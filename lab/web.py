"""Loopback dashboard with a serialized controller, bounded uploads and explicit actions."""

from pathlib import Path
import json, uuid, time, threading
from flask import Flask, request, jsonify, send_from_directory, Response
from .runtime import Runtime


def create_app(kind, root, database=None):
    root = Path(root).resolve()
    runtime_dir = root / "runtime"
    runtime_dir.mkdir(exist_ok=True)
    app = Flask(__name__, static_folder=str(root / "static"))
    app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024
    rt = Runtime(kind, root, database or runtime_dir / "state.sqlite")
    app.extensions["runtime"] = rt
    models = {}
    infer_lock = threading.Lock()

    @app.before_request
    def local_boundary():
        # Prevent arbitrary web pages from issuing state-changing browser requests.
        if request.method == "POST" and request.headers.get("X-Lab-Request") != "1":
            return jsonify(error="Local dashboard request header required"), 403

    @app.errorhandler(ValueError)
    def invalid(e):
        return jsonify(error=str(e)), 400

    @app.errorhandler(413)
    def too_large(e):
        return jsonify(error="Upload limit is 8 MiB"), 413

    @app.get("/")
    def home():
        return send_from_directory(root / "static", "index.html")

    @app.get("/api/state")
    def state():
        return jsonify(rt.snapshot())

    @app.post("/api/action")
    def action():
        body = request.get_json(force=True)
        if not isinstance(body, dict):
            raise ValueError("JSON object required")
        return jsonify(rt.apply(body, body.get("event_id")))

    @app.get("/api/events")
    def events():
        return jsonify(rt.store.events())

    @app.get("/api/export")
    def export():
        return Response(
            json.dumps({"state": rt.snapshot(), "events": rt.store.events()}, indent=2),
            mimetype="application/json",
            headers={"Content-Disposition": "attachment; filename=experiment-log.json"},
        )

    @app.get("/api/benchmarks")
    def benchmarks():
        p = root / "evidence/results.json"
        return jsonify(
            json.loads(p.read_text())
            if p.exists()
            else {"status": "Benchmarks have not run yet"}
        )

    @app.get("/api/samples")
    def samples():
        p = root / "samples/catalog.json"
        return jsonify(json.loads(p.read_text()) if p.exists() else [])

    @app.get("/frame/<name>")
    def frame(name):
        return send_from_directory(runtime_dir, name)

    def infer(image):
        import cv2
        from .inference import Detector, WasteClassifier, annotate

        with infer_lock:
            if kind not in models:
                path = root / "models"
                try:
                    models[kind] = (
                        WasteClassifier(path)
                        if kind == "waste"
                        else Detector(path / "detector-640.onnx")
                    )
                except Exception as e:
                    raise ValueError(
                        "Models unavailable. Run the documented model setup first: "
                        + str(e)
                    )
            started = time.perf_counter()
            result = (
                models[kind].predict(image)
                if kind == "waste"
                else models[kind].predict(image, rt.threshold)
            )
            name = "latest.jpg"
            cv2.imwrite(str(runtime_dir / name), annotate(image, result))
            state = rt.accept_inference(
                result, "/frame/" + name + "?v=" + str(uuid.uuid4())
            )
            state["request_latency_ms"] = (time.perf_counter() - started) * 1000
            return jsonify(state)

    @app.post("/api/infer")
    def upload():
        import cv2, numpy as np

        file = request.files.get("image")
        if file is None:
            raise ValueError("image file required")
        image = cv2.imdecode(np.frombuffer(file.read(), np.uint8), cv2.IMREAD_COLOR)
        if image is None or image.size > 30_000_000:
            raise ValueError("Invalid image or more than 10 megapixels")
        return infer(image)

    @app.post("/api/sample")
    def sample():
        import cv2

        name = request.get_json(force=True).get("name", "")
        catalog = json.loads((root / "samples/catalog.json").read_text())
        item = next((s for s in catalog if s["id"] == name), None)
        if item is None:
            raise ValueError("unknown sample")
        p = (root / "samples" / item["file"]).resolve()
        if not p.is_relative_to(root / "samples"):
            raise ValueError("invalid sample path")
        image = cv2.imread(str(p))
        if image is None:
            raise ValueError("Sample missing; run data download instructions")
        return infer(image)

    @app.post("/api/scenario")
    def scenario():
        name = request.get_json(force=True).get("name")
        p = root / "scenarios" / f"{name}.json"
        if name not in [
            "stationary",
            "poster",
            "camera_disconnect",
            "conflict",
            "obstruction",
            "unknown",
            "full",
            "jam",
        ]:
            raise ValueError("unknown scenario")
        if not p.exists():
            raise ValueError("Scenario belongs to another project")
        actions = json.loads(p.read_text())
        with rt.lock:
            rt.source = (
                "Scripted control fixture; detections supplied by scenario, not AI"
            )
            rt.result = {}
            rt.frame = ""
            rt.camera_mode = "fixture"
            rt.camera_at = None
        for a in actions:
            rt.apply(a)
        return jsonify(rt.snapshot())

    @app.post("/api/video-step")
    def video_step():
        camera = app.extensions.get("camera")
        if camera is None:
            raise ValueError("Start with --video PATH to enable recorded video")
        ok, image = camera.read()
        if not ok:
            rt.apply({"op": "sensors", "values": {"camera_valid": False}})
            return jsonify(error="Recorded video ended or camera disconnected"), 409
        rt.apply({"op": "step", "seconds": 1})
        return infer(image)

    return app
