"""Class-aware one-to-one IoU tracking with line-crossing hysteresis."""

from dataclasses import dataclass
import math


def iou(a, b):
    x1, y1 = max(a[0], b[0]), max(a[1], b[1])
    x2, y2 = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0, x2 - x1) * max(0, y2 - y1)
    return inter / max(
        1e-12, (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    )


class Tracker:
    def __init__(self, max_age=5, min_hits=2, line=0.5):
        self.tracks = {}
        self.next_id = 1
        self.max_age = max_age
        self.min_hits = min_hits
        self.line = line
        self.entries = 0
        self.exits = 0
        self.last_time = -1

    def update(self, detections, now):
        if not math.isfinite(now) or now < self.last_time:
            raise ValueError("tracking timestamps must be monotonic")
        self.last_time = now
        self.tracks = {
            k: v for k, v in self.tracks.items() if now - v["at"] <= self.max_age
        }
        candidates = []
        for k, t in self.tracks.items():
            for j, d in enumerate(detections):
                overlap = iou(t["box"], d["box"])
                if d["label"] == t["label"] and overlap >= 0.15:
                    candidates.append((overlap, k, j))
        assigned = {}
        used = set()
        for _, k, j in sorted(candidates, reverse=True):
            if k not in used and j not in assigned:
                assigned[j] = k
                used.add(k)
        current = []
        for j, d in enumerate(detections):
            k = assigned.get(j)
            if k is None:
                k = self.next_id
                self.next_id += 1
                self.tracks[k] = {"hits": 0, "side": None, "crossed": []}
            t = self.tracks[k]
            t.update(d)
            t["at"] = now
            t["hits"] += 1
            t["id"] = k
            center = (d["box"][0] + d["box"][2]) / 2
            side = (
                -1
                if center < self.line - 0.04
                else 1 if center > self.line + 0.04 else None
            )
            previous = t["side"]
            if side is not None:
                if (
                    previous is not None
                    and previous != side
                    and t["hits"] >= self.min_hits
                ):
                    direction = "entry" if side == 1 else "exit"
                    if direction not in t["crossed"]:
                        t["crossed"].append(direction)
                        if direction == "entry":
                            self.entries += 1
                        else:
                            self.exits += 1
                t["side"] = side
            current.append(dict(t, confirmed=t["hits"] >= self.min_hits))
        return current
