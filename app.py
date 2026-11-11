from pathlib import Path
import argparse, json
from lab.web import create_app

ROOT = Path(__file__).parent.resolve()
if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--port", type=int)
    p.add_argument("--video")
    p.add_argument("--webcam", type=int)
    p.add_argument("--authorize-webcam", action="store_true")
    args = p.parse_args()
    cfg = json.loads((ROOT / "project.json").read_text())
    app = create_app(cfg["kind"], ROOT)
    if args.video:
        from lab.hal import OpenCVCamera

        app.extensions["camera"] = OpenCVCamera(args.video)
    if args.webcam is not None:
        from lab.hal import AuthorizedWebcam

        app.extensions["camera"] = AuthorizedWebcam(args.webcam, args.authorize_webcam)
    app.run(host="127.0.0.1", port=args.port or cfg["port"], debug=False, threaded=True)
