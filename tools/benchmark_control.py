from pathlib import Path
import sys, json, math, time, platform

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lab.core import Classroom, Parking, Sorter, CATEGORIES
from lab.tracking import Tracker

root = Path(__file__).resolve().parents[1]
out = root / "control-evaluation"
out.mkdir(exist_ok=True)


def reading(v, t, valid=True):
    return {"value": v, "at": t, "valid": valid}


# Classroom: one recorded sensor/camera trace, independent of vision accuracy evaluation.
trace = []
for t in range(3601):
    truth = 1 if t < 1200 or 1500 <= t < 1800 or 2400 <= t < 2700 else 0
    count = truth
    if 600 <= t < 700:
        count = 0  # one missed seated/stationary observation
    if 3000 <= t < 3300:
        count = 1  # known human depiction
    valid = not 2400 <= t < 2600
    reliable = not 3000 <= t < 3300
    event = t in [1200, 1500, 1800, 2400, 2700]
    trace.append(
        {
            "time": t,
            "physical_people": truth,
            "visual_count": count,
            "valid": valid,
            "reliable": reliable,
            "door": event,
        }
    )
variants = {}
for name in [
    "baseline",
    "grace_confirmation",
    "uncertainty_hold",
    "event_checks",
    "combined",
]:
    c = Classroom()
    last = None
    next_check = 0
    vacancy = None
    neg = 0
    lights = True
    rows = []
    for r in trace:
        t = r["time"]
        obs = {
            "count": r["visual_count"],
            "valid": r["valid"],
            "reliable": r["reliable"],
        }
        if name == "combined":
            c.update(t, obs, door=r["door"])
            lights = c.lights
        else:
            due = t >= next_check or name == "event_checks" and r["door"]
            if due:
                next_check = t + 600
                if name == "uncertainty_hold" and (not r["valid"] or not r["reliable"]):
                    lights = True
                else:
                    positive = r["visual_count"] > 0 if r["valid"] else False
                    if name == "grace_confirmation":
                        if positive:
                            neg = 0
                            vacancy = None
                            lights = True
                        else:
                            neg += 1
                            if vacancy is None:
                                vacancy = t
                            lights = not (neg >= 2 and t - vacancy >= 120)
                    else:
                        lights = positive
        rows.append(
            {"time": t, "lights": lights, "physical_people": r["physical_people"]}
        )
    errors = sum(not r["lights"] and r["physical_people"] > 0 for r in rows[:-1])
    empty_on = sum(r["lights"] and r["physical_people"] == 0 for r in rows[:-1])
    on = sum(r["lights"] for r in rows[:-1])
    variants[name] = {
        "occupied_lights_off_seconds": errors,
        "empty_lights_on_seconds": empty_on,
        "lights_on_seconds": on,
        "estimated_energy_Wh": on / 3600 * 120,
        "scope": "3600 simulated seconds; 120 W fixed lighting load assumed; no measured power",
    }
    if name == "combined":
        (out / "classroom-trace.json").write_text(json.dumps(rows))
# Parking: each slot has truth, visual and proximity channels; synthetic per-second faults.
p = Parking()
parking = []
base_falsefree = final_falsefree = correct_base = correct_final = decided = 0
for t in range(120):
    truth = [t < 60, 30 <= t < 90, 50 <= t < 100, 70 <= t < 110]
    camera = truth.copy()
    dist = [30 if v else 150 for v in truth]
    valid = True
    if 15 <= t < 30:
        camera[0] = False  # occluded car
    if 30 <= t < 45:
        camera[3] = True  # reflection false vehicle
    if 75 <= t < 85:
        valid = False
    if 90 <= t < 105:
        dist[2] = 150  # conflicting distance
    obstruction = 42 <= t < 47
    request = (
        "open" if t in [0, 35, 70, 105] else "close" if t in [4, 40, 74, 109] else None
    )
    p.update(
        t,
        camera,
        [reading(x, t, valid) for x in dist],
        reading(obstruction, t, valid),
        request,
    )
    for i in range(4):
        base_falsefree += not camera[i] and truth[i]
        correct_base += camera[i] == truth[i]
        final_falsefree += p.spaces[i] == "free" and truth[i]
        if p.spaces[i] in ["free", "occupied"]:
            decided += 1
            correct_final += (p.spaces[i] == "occupied") == truth[i]
    parking.append(
        {
            "time": t,
            "truth": truth,
            "camera": camera,
            "spaces": p.spaces.copy(),
            "gate": p.gate,
            "obstruction": obstruction,
            "sensor_valid": valid,
        }
    )
# Same closure requests on unsafe cases; direct command baseline ignores interlocks.
closure_cases = [{"blocked": i % 3 == 0, "valid": i % 5 != 0} for i in range(30)]
unsafe_base = unsafe_final = 0
for r in closure_cases:
    unsafe = r["blocked"] or not r["valid"]
    unsafe_base += unsafe
    c = Parking(gate="OPEN", clear_since=0)
    c.update(
        3,
        [False] * 4,
        [reading(150, 3) for _ in range(4)],
        reading(r["blocked"], 3, r["valid"]),
        "close",
    )
    unsafe_final += unsafe and c.gate == "CLOSING"
parking_result = {
    "baseline_false_free_slot_seconds": int(base_falsefree),
    "final_false_free_slot_seconds": int(final_falsefree),
    "baseline_occupancy_accuracy": correct_base / 480,
    "final_accuracy_on_decided_slots": correct_final / decided,
    "final_decision_coverage": decided / 480,
    "total_slot_seconds": 480,
    "unsafe_closure_requests_baseline": int(unsafe_base),
    "unsafe_closure_requests_final": int(unsafe_final),
    "closure_cases": 30,
    "scope": "Synthetic camera/proximity readings, not real parking-space detection accuracy",
}
(out / "parking-trace.json").write_text(json.dumps(parking))
# Waste routes: compare argmax always-route to actual state-machine checks.
waste = []
baseline_bad = final_bad = success = 0
for i in range(60):
    case = ["normal", "unknown", "full", "sensor_fault", "jam", "timeout"][i % 6]
    s = Sorter(threshold=0.5, margin=0.0)
    prob = {c: 0.96 if c == "paper" else 0.01 for c in CATEGORIES}
    if case == "unknown":
        prob = {c: 0.2 for c in CATEGORIES}
    fill = {
        c: reading(98 if case == "full" else 20, 0, case != "sensor_fault")
        for c in CATEGORIES
    }
    item = {"id": str(i), "probabilities": prob}
    s.submit(0, item, fill, reading(100, 0))
    s.tick(
        3 if case == "timeout" else 1,
        ack=case not in ["timeout", "jam"],
        jam=case == "jam",
    )
    unsafe = case != "normal"
    baseline_bad += unsafe
    final_bad += unsafe and sum(s.totals.values()) > 0
    success += sum(s.totals.values())
    waste.append(
        {
            "case": case,
            "final_state": s.state,
            "counted": sum(s.totals.values()),
            "reason": s.reason,
        }
    )
waste_result = {
    "baseline_unsafe_disposals": baseline_bad,
    "final_unsafe_disposals": final_bad,
    "normal_disposals_acknowledged": success,
    "cases": 60,
    "scope": "Scripted classifier scores and fault events; separate from real classifier accuracy",
}
# Deterministic trajectory tracking with annotated crossing, stationary and duplicate-frame workload.
t = Tracker()
rawcount = 0
ids = set()
for n in range(80):
    x = 0.15 + min(n, 55) * 0.012
    d = {"label": "person", "score": 0.9, "box": [x - 0.1, 0.2, x + 0.1, 0.8]}
    rawcount += 1
    for track in t.update([d], n * 0.1):
        ids.add(track["id"])
tracking = {
    "frames": 80,
    "ground_truth_tracks": 1,
    "naive_sum_of_frame_detections": rawcount,
    "tracked_unique_ids": len(ids),
    "expected_entries": 1,
    "counted_entries": t.entries,
    "expected_exits": 0,
    "counted_exits": t.exits,
    "scope": "Synthetic boxes and known trajectory; not real-video tracking validation",
}
results = {
    "environment": platform.platform(),
    "classroom": variants,
    "parking": parking_result,
    "waste": waste_result,
    "tracking": tracking,
}
(out / "results.json").write_text(json.dumps(results, indent=2))
(out / "classroom-input.json").write_text(json.dumps(trace))
(out / "waste-trace.json").write_text(json.dumps(waste, indent=2))
print(json.dumps(results, indent=2))
