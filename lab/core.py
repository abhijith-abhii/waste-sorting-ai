"""Deterministic control policies. Time is supplied, never read implicitly."""

from dataclasses import dataclass, field
import math


def finite(value, low=0, high=1e9):
    return (
        isinstance(value, (float, int))
        and not isinstance(value, bool)
        and math.isfinite(value)
        and low <= value <= high
    )


def fresh(reading, now, ttl=3):
    return (
        isinstance(reading, dict)
        and reading.get("valid") is True
        and finite(reading.get("at"))
        and 0 <= now - reading["at"] <= ttl
    )


@dataclass
class Classroom:
    interval: float = 600
    grace: float = 120
    stale_after: float = 660
    mode: str = "auto"
    override_until: float = 0
    state: str = "uncertain"
    lights: bool = True
    occupancy: int | None = None
    observed_at: float | None = None
    vacancy_since: float | None = None
    negative_checks: int = 0
    next_check: float = 0
    reason: str = "No reliable observation; lights held on"

    def update(self, now, obs=None, motion=False, door=False):
        due = now >= self.next_check or motion or door
        if due and obs is not None:
            self.next_check = now + self.interval
            reliable = (
                obs.get("valid") is True
                and obs.get("reliable") is True
                and finite(obs.get("count"), 0, 200)
            )
            if not reliable:
                self.state = "uncertain"
                self.vacancy_since = None
                self.negative_checks = 0
                self.occupancy = None
                self.observed_at = now
                self.reason = (
                    "Camera failure, poor light or depiction ambiguity; lights held on"
                )
            else:
                self.observed_at = now
                self.occupancy = int(obs["count"])
                if self.occupancy:
                    self.state = "occupied"
                    self.vacancy_since = None
                    self.negative_checks = 0
                    self.reason = "A visual person candidate is present; stationary people are retained"
                else:
                    self.negative_checks += 1
                    if self.vacancy_since is None:
                        self.vacancy_since = now
                    self.state = "vacant"
                    self.reason = (
                        "Empty observation; vacancy grace and confirmation apply"
                    )
        if motion or door:
            self.vacancy_since = None
            self.negative_checks = 0
            if self.state == "vacant":
                self.state = "uncertain"
            self.reason = "Sensor event requests a camera check; absence of motion never proves vacancy"
        if self.observed_at is None or now - self.observed_at > self.stale_after:
            self.state = "stale"
            self.reason = "Observation is stale; lights held on"
        off = (
            self.state == "vacant"
            and self.negative_checks >= 2
            and self.vacancy_since is not None
            and now - self.vacancy_since >= self.grace
        )
        self.lights = not off
        if self.mode != "auto" and now < self.override_until:
            self.lights = self.mode == "on"
            self.reason = f"Manual {self.mode} override until {self.override_until:g}s"
        elif self.mode != "auto":
            self.mode = "auto"
        return self


@dataclass
class Parking:
    gate: str = "CLOSED"
    started: float = 0
    clear_since: float | None = None
    spaces: list = field(default_factory=lambda: ["unknown"] * 4)
    available: int = 0
    reason: str = "Gate closed; waiting for fresh sensors"
    requested: str | None = None
    fault_latched: bool = False

    def update(
        self, now, camera, distances, obstruction, request=None, actuator_ok=True
    ):
        for i in range(4):
            r = distances[i] if i < len(distances) else None
            visual = camera[i] if i < len(camera) else None
            if (
                not fresh(r, now)
                or not finite(r.get("value"), 2, 400)
                or visual not in [True, False]
            ):
                self.spaces[i] = "unknown"
                continue
            # Separate thresholds retain prior proximity occupancy in the deadband.
            d = r["value"]
            near = True if d < 70 else False if d > 90 else self.spaces[i] == "occupied"
            self.spaces[i] = (
                "occupied"
                if near and visual
                else "free" if not near and not visual else "conflict"
            )
        self.available = self.spaces.count("free")
        reliable = fresh(obstruction, now) and isinstance(
            obstruction.get("value"), bool
        )
        blocked = not reliable or obstruction["value"]
        if blocked:
            self.clear_since = None
        elif self.clear_since is None:
            self.clear_since = now
        if not actuator_ok:
            self.gate = "FAULT"
            self.fault_latched = True
            self.reason = "Actuator failed; motion stopped"
            return self
        if self.gate == "FAULT":
            if (
                request == "reset"
                and not blocked
                and self.clear_since is not None
                and now - self.clear_since >= 2
            ):
                self.fault_latched = False
                self.gate = "OPEN"
                self.started = now
                self.reason = (
                    "Fault acknowledged with fresh clear sensors; gate remains open"
                )
            return self
        if blocked and self.gate in ["CLOSING", "OPEN", "HOLD"]:
            self.gate = "HOLD"
            self.reason = "Obstruction or invalid sensor; closure inhibited"
        if request == "open":
            if self.available == 0:
                self.reason = "No confirmed free space; entry denied"
            elif self.gate == "CLOSED":
                self.gate = "OPENING"
                self.started = now
                self.reason = "Entry requested; opening"
        if self.gate == "OPENING" and now - self.started >= 2:
            self.gate = "OPEN"
            self.started = now
            self.reason = "Opening completed in virtual actuator"
        clear = (
            not blocked and self.clear_since is not None and now - self.clear_since >= 2
        )
        if (
            self.gate in ["OPEN", "HOLD"]
            and clear
            and (request == "close" or now - self.started >= 8)
        ):
            self.gate = "CLOSING"
            self.started = now
            self.reason = "Fresh clear evidence for two seconds; closing"
        if request == "close" and not clear:
            self.reason = "Manual close refused by obstruction interlock"
        if self.gate == "CLOSING" and now - self.started >= 2:
            self.gate = "CLOSED"
            self.reason = "Virtual closure completed"
        return self


CATEGORIES = ["cardboard", "glass", "metal", "paper", "plastic"]


@dataclass
class Sorter:
    threshold: float = 0.7
    margin: float = 0.15
    state: str = "IDLE"
    target: str = "manual"
    started: float = 0
    item_id: str | None = None
    reason: str = "Waiting for an item"
    totals: dict = field(default_factory=lambda: {c: 0 for c in CATEGORIES})
    rejected: int = 0
    contamination: int = 0
    seen: list = field(default_factory=list)

    def submit(self, now, item, fill, weight):
        identity = item.get("id")
        if not isinstance(identity, str) or not identity or len(identity) > 128:
            raise ValueError("invalid item id")
        if identity in self.seen:
            self.reason = "Duplicate item ignored"
            return self
        if self.state not in ["IDLE", "REVIEW"]:
            self.reason = "Sorter busy or faulted; item refused"
            return self
        self.seen = (self.seen + [identity])[-1000:]
        self.item_id = identity
        probs = item.get("probabilities", {})
        valid = (
            set(probs) == set(CATEGORIES)
            and all(finite(v, 0, 1) for v in probs.values())
            and abs(sum(probs.values()) - 1) < 1e-4
        )
        ordered = (
            sorted(probs.items(), key=lambda kv: kv[1], reverse=True) if valid else []
        )
        if (
            not valid
            or ordered[0][1] < self.threshold
            or ordered[0][1] - ordered[1][1] < self.margin
            or item.get("mixed")
        ):
            self.state = "REVIEW"
            self.target = "manual"
            self.rejected += 1
            self.reason = "Uncertain or mixed item; manual review"
            return self
        category = ordered[0][0]
        f = fill.get(category)
        if (
            not fresh(f, now)
            or not fresh(weight, now)
            or not finite(f.get("value"), 0, 100)
            or not finite(weight.get("value"), 0, 5000)
        ):
            self.state = "FAULT"
            self.reason = "Invalid or stale fill/weight sensor"
            return self
        if f["value"] >= 90 or weight["value"] >= 2000:
            self.state = "REVIEW"
            self.target = "manual"
            self.rejected += 1
            self.reason = "Full bin or excessive item weight; manual review"
            return self
        self.state = "MOVING"
        self.target = category
        self.started = now
        self.reason = "Classification accepted; waiting for actuator acknowledgement"
        return self

    def tick(
        self, now, ack=False, jam=False, sensors_ok=True, reset=False, actual=None
    ):
        if self.state == "MOVING":
            if jam or not sensors_ok or now - self.started >= 3:
                self.state = "FAULT"
                self.reason = "Jam, sensor failure or actuator timeout; motion stopped"
            elif ack:
                self.totals[self.target] += 1
                if actual is not None and actual != self.target:
                    self.contamination += 1
                self.state = "IDLE"
                self.reason = "Actuator acknowledged; disposal counted once"
        elif self.state == "FAULT" and reset and sensors_ok and not jam:
            self.state = "REVIEW"
            self.target = "manual"
            self.reason = "Fault cleared; pending item requires manual review"
        return self
