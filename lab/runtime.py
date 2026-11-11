from dataclasses import asdict
from pathlib import Path
import copy, json, threading, uuid
from .core import Classroom, Parking, Sorter, CATEGORIES, finite
from .hal import Store, VirtualClock, VirtualOutput
from .tracking import Tracker


class Runtime:
    def __init__(self, kind, root, database):
        self.kind = kind
        self.root = Path(root)
        self.store = Store(database)
        self.lock = threading.RLock()
        self.clock = VirtualClock()
        self.output = VirtualOutput()
        self.tracker = Tracker()
        self.controller = {"classroom": Classroom, "parking": Parking, "waste": Sorter}[
            kind
        ]()
        config_path = self.root / "models/config.json"
        if kind == "waste" and config_path.exists():
            cfg = json.loads(config_path.read_text())
            self.controller.threshold = cfg["threshold"]
            self.controller.margin = cfg["margin"]
        self.input = {
            "camera_valid": True,
            "motion": False,
            "door": False,
            "obstruction": False,
            "sensor_valid": True,
            "jam": False,
            "actuator_ok": True,
            "distance": [150] * 4,
            "fill": 20,
            "weight": 100,
            "camera_spaces": [False] * 4,
            "person_obstruction": False,
            "count": 0,
            "reliable": True,
        }
        self.result = {}
        self.history = []
        self.threshold = self.controller.threshold if kind == "waste" else 0.25
        self.camera_mode = "fixture"
        self.camera_at = None
        self.frame = ""
        self.source = "Scripted control fixture; no AI inference yet"
        self.manual_ack = False
        self.roi = [0, 0, 1, 1]
        self.depiction_zones = []
        self.sequence = 0
        saved = self.store.load()
        if saved:
            self.tracker.entries = saved.get("entries", 0)
            self.tracker.exits = saved.get("exits", 0)
            self.tracker.next_id = saved.get("next_track_id", 1)
            self.roi = saved.get("roi", [0, 0, 1, 1])
            self.depiction_zones = saved.get("depiction_zones", [])
            self.clock.seconds = saved["time"]
            self.input.update(saved["input"])
            self.history = saved["history"][-300:]
            self.threshold = saved["threshold"]
            self.sequence = saved.get("sequence", 0)
            self.controller = {
                "classroom": Classroom,
                "parking": Parking,
                "waste": Sorter,
            }[kind](**saved["controller"])
            if kind != "waste":
                self.input["camera_valid"] = False
                self.camera_mode = "inference"
                self.camera_at = None
            if kind == "classroom":
                self.controller.observed_at = None
                self.controller.state = "stale"
                self.controller.lights = True
                self.controller.mode = "auto"
                self.controller.next_check = self.clock.now()
            if kind == "parking" and self.controller.gate != "CLOSED":
                self.controller.gate = "FAULT"
                self.controller.reason = (
                    "Restart during gate cycle; inspection required"
                )
            if kind == "waste" and self.controller.state == "MOVING":
                self.controller.state = "FAULT"
                self.controller.reason = (
                    "Restart during sorting; manual reconciliation required"
                )

    def snapshot(self):
        return {
            "kind": self.kind,
            "time": self.clock.now(),
            "controller": asdict(self.controller),
            "input": copy.deepcopy(self.input),
            "history": self.history[-300:],
            "threshold": self.threshold,
            "result": self.result,
            "frame": self.frame,
            "source": self.source,
            "entries": self.tracker.entries,
            "exits": self.tracker.exits,
            "sequence": self.sequence,
            "roi": self.roi,
            "depiction_zones": self.depiction_zones,
            "next_track_id": self.tracker.next_id,
        }

    def reading(self, value):
        return {
            "value": value,
            "valid": self.input["sensor_valid"],
            "at": self.clock.now(),
        }

    def apply(self, action, event_id=None):
        with self.lock:
            key = event_id or str(uuid.uuid4())
            if not isinstance(key, str) or not key or len(key) > 128:
                raise ValueError(
                    "event_id must be a nonempty string of at most 128 characters"
                )
            if self.store.contains(key):
                return self.snapshot()
            before = copy.deepcopy(
                (
                    self.controller,
                    self.input,
                    self.clock.seconds,
                    self.history,
                    self.sequence,
                    self.threshold,
                    self.roi,
                    self.depiction_zones,
                    self.camera_mode,
                    self.source,
                    self.frame,
                    self.result,
                )
            )
            try:
                self._apply(action)
                state = self.snapshot()
                self.store.commit(
                    key,
                    self.clock.now(),
                    {"action": action, "reason": self.controller.reason},
                    state,
                )
                return state
            except Exception:
                (
                    self.controller,
                    self.input,
                    self.clock.seconds,
                    self.history,
                    self.sequence,
                    self.threshold,
                    self.roi,
                    self.depiction_zones,
                    self.camera_mode,
                    self.source,
                    self.frame,
                    self.result,
                ) = before
                raise

    def _apply(self, a):
        if not isinstance(a, dict):
            raise ValueError("action must be an object")
        op = a.get("op")
        if op == "configure":
            if "threshold" in a:
                if not finite(a["threshold"], 0.05, 0.99):
                    raise ValueError("threshold must be .05..99")
                self.threshold = a["threshold"]
                if self.kind == "waste":
                    self.controller.threshold = a["threshold"]
            if self.kind == "classroom":
                for k, lo, hi in [
                    ("interval", 1, 3600),
                    ("grace", 0, 1800),
                    ("stale_after", 1, 7200),
                ]:
                    if k in a:
                        if not finite(a[k], lo, hi):
                            raise ValueError(k + " outside allowed range")
                        setattr(self.controller, k, a[k])
                self.controller.next_check = self.clock.now()
            for k in ["roi", "depiction_zones"]:
                if k in a:
                    boxes = [a[k]] if k == "roi" else a[k]
                    if not isinstance(boxes, list) or len(boxes) > 16:
                        raise ValueError("invalid regions")
                    if any(
                        not isinstance(b, list)
                        or len(b) != 4
                        or not all(finite(v, 0, 1) for v in b)
                        or b[2] <= b[0]
                        or b[3] <= b[1]
                        for b in boxes
                    ):
                        raise ValueError("regions require normalized x1,y1,x2,y2")
                    setattr(self, k, a[k])
        elif op == "sensors":
            if not isinstance(a.get("values", {}), dict):
                raise ValueError("sensor values must be an object")
            if "count" in a.get("values", {}) or "camera_spaces" in a.get("values", {}):
                self.camera_mode = "fixture"
                self.source = "Scripted control fixture; no AI inference"
                self.frame = ""
                self.result = {}
            for k, v in a.get("values", {}).items():
                if k not in self.input:
                    raise ValueError("unknown sensor " + k)
                if isinstance(self.input[k], bool) and not isinstance(v, bool):
                    raise ValueError("boolean required")
                if k in ["fill", "weight", "count"] and not finite(v, 0, 5000):
                    raise ValueError("invalid sensor number")
                if k == "distance" and (
                    not isinstance(v, list)
                    or len(v) != 4
                    or not all(finite(x, 0, 400) for x in v)
                ):
                    raise ValueError("four distances required")
                if k == "camera_spaces" and (
                    not isinstance(v, list)
                    or len(v) != 4
                    or not all(isinstance(x, bool) for x in v)
                ):
                    raise ValueError("four camera states required")
                self.input[k] = v
        elif op == "override" and self.kind == "classroom":
            if a.get("mode") not in ["auto", "on", "off"]:
                raise ValueError("invalid override")
            self.controller.mode = a["mode"]
            self.controller.override_until = self.clock.now() + 300
        elif op == "item" and self.kind == "waste":
            self.sequence += 1
            item = {
                "id": a.get("item_id", f"item-{self.sequence}"),
                "probabilities": a.get(
                    "probabilities", self.result.get("probabilities", {})
                ),
                "mixed": bool(a.get("mixed", False)),
            }
            self.controller.submit(
                self.clock.now(),
                item,
                {c: self.reading(self.input["fill"]) for c in CATEGORIES},
                self.reading(self.input["weight"]),
            )
        elif op not in [
            "step",
            "check",
            "gate",
            "ack",
            "reset_fault",
            "configure",
            "sensors",
        ]:
            raise ValueError("unsupported action")
        dt = a.get("seconds", 0) if op == "step" else 0
        if not finite(dt, 0, 3600):
            raise ValueError("invalid step")
        # One-second integration makes a large accelerated step equivalent to small steps.
        remaining = dt
        if not remaining:
            self.tick(a)
        while remaining > 0:
            d = min(1, remaining)
            self.clock.advance(d)
            remaining -= d
            self.tick(a if remaining == 0 else {"op": "step"})
        value = (
            self.controller.occupancy or 0
            if self.kind == "classroom"
            else (
                self.controller.available
                if self.kind == "parking"
                else sum(self.controller.totals.values())
            )
        )
        self.history.append(
            {
                "time": self.clock.now(),
                "value": value,
                "state": (
                    self.controller.state
                    if self.kind != "parking"
                    else self.controller.gate
                ),
            }
        )
        self.history = self.history[-300:]

    def tick(self, a):
        now = self.clock.now()
        s = self.input
        if self.kind == "classroom":
            if a.get("op") == "check":
                self.controller.next_check = now
            camera_fresh = (
                self.camera_mode == "fixture"
                or self.camera_at is not None
                and now - self.camera_at <= 2
            )
            obs = {
                "count": s["count"],
                "valid": s["camera_valid"] and camera_fresh,
                "reliable": s["reliable"],
            }
            self.controller.update(now, obs, s["motion"], s["door"])
            self.output.write(self.controller.lights)
            s["motion"] = False
            s["door"] = False
        elif self.kind == "parking":
            camera_fresh = (
                self.camera_mode == "fixture"
                or self.camera_at is not None
                and now - self.camera_at <= 2
            )
            camera = (
                s["camera_spaces"] if s["camera_valid"] and camera_fresh else [None] * 4
            )
            obstruction = self.reading(s["obstruction"] or s["person_obstruction"])
            obstruction["valid"] = (
                obstruction["valid"]
                and s["camera_valid"]
                and (
                    self.camera_mode == "fixture"
                    or self.camera_at is not None
                    and now - self.camera_at <= 2
                )
            )
            self.controller.update(
                now,
                camera,
                [self.reading(d) for d in s["distance"]],
                obstruction,
                (
                    a.get("request")
                    if a.get("op") == "gate"
                    else "reset" if a.get("op") == "reset_fault" else None
                ),
                s["actuator_ok"],
            )
            self.output.write(self.controller.gate)
        else:
            # Virtual actuator acknowledges after one second unless manual-ACK testing is enabled.
            auto_ack = (
                not self.manual_ack
                and s["actuator_ok"]
                and now - self.controller.started >= 1
            )
            self.controller.tick(
                now,
                ack=a.get("op") == "ack" or auto_ack,
                jam=s["jam"],
                sensors_ok=s["sensor_valid"] and s["fill"] < 90 and s["weight"] < 2000,
                reset=a.get("op") == "reset_fault",
                actual=a.get("actual"),
            )
            self.output.write(
                self.controller.target if self.controller.state == "MOVING" else None
            )

    def accept_inference(self, result, frame):
        with self.lock:
            before = copy.deepcopy(
                (
                    self.result,
                    self.frame,
                    self.source,
                    self.camera_mode,
                    self.camera_at,
                    self.input,
                    self.tracker,
                )
            )
            try:
                return self._accept_inference(result, frame)
            except Exception:
                (
                    self.result,
                    self.frame,
                    self.source,
                    self.camera_mode,
                    self.camera_at,
                    self.input,
                    self.tracker,
                ) = before
                raise

    def _accept_inference(self, result, frame):
        with self.lock:
            self.result = result
            self.frame = frame
            self.source = result["source"]
            self.camera_mode = "inference"
            self.camera_at = self.clock.now()
            if self.kind != "waste":
                detections = result["detections"]
                target_labels = (
                    ["person"]
                    if self.kind == "classroom"
                    else ["car", "motorcycle", "bus", "truck"]
                )
                tracks = self.tracker.update(
                    [d for d in detections if d["label"] in target_labels],
                    self.clock.now(),
                )
                self.result["tracks"] = tracks
                x1, y1, x2, y2 = self.roi
                inside = lambda d: (
                    x1 <= (d["box"][0] + d["box"][2]) / 2 <= x2
                    and y1 <= (d["box"][1] + d["box"][3]) / 2 <= y2
                )
                people = [d for d in detections if d["label"] == "person" and inside(d)]
                ambiguous = any(
                    any(
                        z[0] <= (d["box"][0] + d["box"][2]) / 2 <= z[2]
                        and z[1] <= (d["box"][1] + d["box"][3]) / 2 <= z[3]
                        for z in self.depiction_zones
                    )
                    for d in people
                )
                self.input.update(
                    camera_valid=True,
                    count=len(people),
                    reliable=result["brightness"] >= 25 and not ambiguous,
                )
                if self.kind == "parking":
                    vehicles = [
                        d
                        for d in detections
                        if d["label"] in ["car", "motorcycle", "bus", "truck"]
                    ]
                    self.input["camera_spaces"] = [
                        any(
                            i / 4 <= (d["box"][0] + d["box"][2]) / 2 < (i + 1) / 4
                            and d["box"][3] > 0.5
                            for d in vehicles
                        )
                        for i in range(4)
                    ]
                    self.input["person_obstruction"] = bool(people)
            return self.apply({"op": "check"})
