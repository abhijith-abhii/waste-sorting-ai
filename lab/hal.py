"""Hardware boundaries: desktop implementations plus opt-in Pi adapters."""

from typing import Protocol
from dataclasses import dataclass
import time, json, sqlite3, threading


class Clock(Protocol):
    def now(self) -> float: ...
class Sensor(Protocol):
    def read(self, now: float) -> dict: ...
class Output(Protocol):
    def write(self, value): ...
class Camera(Protocol):
    def read(self): ...


@dataclass
class VirtualClock:
    seconds: float = 0

    def now(self):
        return self.seconds

    def advance(self, delta):
        if not isinstance(delta, (int, float)) or not 0 <= delta <= 3600:
            raise ValueError("step must be 0..3600 seconds")
        self.seconds += delta
        return self.seconds


class MonotonicClock:
    def now(self):
        return time.monotonic()


@dataclass
class VirtualSensor:
    value: float | bool = 0
    valid: bool = True

    def read(self, now):
        return {"value": self.value, "valid": self.valid, "at": now}


class RecordedSensor:
    def __init__(self, path):
        self.events = json.loads(open(path).read())
        self.index = 0
        if any(
            self.events[i]["at"] > self.events[i + 1]["at"]
            for i in range(len(self.events) - 1)
        ):
            raise ValueError("unordered sensor events")

    def read(self, now):
        while (
            self.index + 1 < len(self.events)
            and self.events[self.index + 1]["at"] <= now
        ):
            self.index += 1
        return (
            self.events[self.index]
            if self.events and self.events[self.index]["at"] <= now
            else {"valid": False, "at": now, "value": None}
        )


class VirtualOutput:
    def __init__(self):
        self.value = None
        self.history = []

    def write(self, value):
        self.value = value
        self.history.append(value)
        self.history = self.history[-1000:]


class OpenCVCamera:
    def __init__(self, source):
        import cv2

        if isinstance(source, int):
            raise ValueError("webcam must be explicitly enabled with AuthorizedWebcam")
        self.cap = cv2.VideoCapture(str(source))

    def read(self):
        return self.cap.read()

    def close(self):
        self.cap.release()


class AuthorizedWebcam(OpenCVCamera):
    def __init__(self, index, authorized=False):
        if not authorized:
            raise ValueError("explicit webcam authorization required")
        import cv2

        self.cap = cv2.VideoCapture(index)


class PiDigitalOutput:
    def __init__(self, pin):
        from gpiozero import OutputDevice

        self.device = OutputDevice(pin, initial_value=False)

    def write(self, value):
        self.device.value = bool(value)

    def close(self):
        self.device.close()


class PiMotionSensor:
    def __init__(self, pin):
        from gpiozero import MotionSensor

        self.device = MotionSensor(pin)

    def read(self, now):
        return {"value": self.device.motion_detected, "valid": True, "at": now}


class PiDistanceSensor:
    def __init__(self, echo, trigger):
        from gpiozero import DistanceSensor

        self.device = DistanceSensor(echo=echo, trigger=trigger, max_distance=4)

    def read(self, now):
        try:
            return {"value": self.device.distance * 100, "valid": True, "at": now}
        except Exception:
            return {"value": None, "valid": False, "at": now}


class PiServo:
    def __init__(self, pin):
        from gpiozero import AngularServo

        self.device = AngularServo(pin, min_angle=0, max_angle=180, initial_angle=None)

    def write(self, value):
        if value is None:
            self.device.detach()
        elif 0 <= value <= 180:
            self.device.angle = value
        else:
            raise ValueError("servo angle outside 0..180")

    # Command completion is not physical acknowledgement; a limit switch is required.


class SerialWeightSensor:
    def __init__(self, port):
        import serial

        self.port = serial.Serial(port, 115200, timeout=0.05)

    def read(self, now):
        try:
            raw = self.port.read_until(b"\n", 64)
            v = float(raw.decode().strip())
            import math

            return {"value": v, "valid": math.isfinite(v) and 0 <= v <= 5000, "at": now}
        except Exception:
            return {"value": None, "valid": False, "at": now}


class Store:
    """One SQLite transaction commits an idempotency key, event and state together."""

    def __init__(self, path):
        self.db = sqlite3.connect(str(path), check_same_thread=False)
        self.lock = threading.RLock()
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.executescript(
            "CREATE TABLE IF NOT EXISTS events(id TEXT PRIMARY KEY, at REAL, payload TEXT); CREATE TABLE IF NOT EXISTS state(id INTEGER PRIMARY KEY CHECK(id=1), payload TEXT);"
        )

    def load(self):
        row = self.db.execute("SELECT payload FROM state WHERE id=1").fetchone()
        return json.loads(row[0]) if row else None

    def contains(self, key):
        return (
            self.db.execute("SELECT 1 FROM events WHERE id=?", (key,)).fetchone()
            is not None
        )

    def commit(self, key, at, event, state):
        with self.lock, self.db:
            cursor = self.db.execute(
                "INSERT OR IGNORE INTO events VALUES(?,?,?)",
                (key, at, json.dumps(event, allow_nan=False)),
            )
            if not cursor.rowcount:
                return False
            self.db.execute(
                "INSERT OR REPLACE INTO state VALUES(1,?)",
                (json.dumps(state, allow_nan=False),),
            )
            return True

    def events(self):
        return [
            dict(id=r[0], at=r[1], **json.loads(r[2]))
            for r in self.db.execute(
                "SELECT * FROM events ORDER BY at DESC,rowid DESC LIMIT 500"
            )
        ]

    def close(self):
        self.db.close()
