from pathlib import Path
import sys, pytest, json, math

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lab.core import Classroom, Parking, Sorter, CATEGORIES
from lab.tracking import Tracker
from lab.hal import Store, VirtualClock, RecordedSensor
from lab.runtime import Runtime


def reading(value, at=0, valid=True):
    return {"value": value, "at": at, "valid": valid}


def probs(c="paper", score=0.96):
    return {x: score if x == c else (1 - score) / 4 for x in CATEGORIES}


def bins(now=0, fill=20):
    return {c: reading(fill, now) for c in CATEGORIES}


def test_stationary_person_is_not_vacancy():
    c = Classroom()
    c.update(0, {"valid": True, "reliable": True, "count": 1})
    c.update(600, {"valid": True, "reliable": True, "count": 1}, False)
    assert c.lights and c.state == "occupied"


def test_vacancy_needs_two_observations_and_grace():
    c = Classroom(interval=60, grace=120)
    obs = {"valid": True, "reliable": True, "count": 0}
    c.update(0, obs)
    assert c.lights
    c.update(60, obs)
    assert c.lights
    c.update(120, obs)
    assert not c.lights


@pytest.mark.parametrize(
    "obs",
    [
        None,
        {"valid": False},
        {"valid": True, "reliable": False, "count": 0},
        {"valid": True, "reliable": True, "count": float("nan")},
    ],
)
def test_unreliable_holds_on(obs):
    c = Classroom()
    c.update(0, obs)
    assert c.lights


def test_camera_disconnect_after_vacancy():
    c = Classroom(interval=1, grace=0)
    c.update(0, {"valid": True, "reliable": True, "count": 0})
    c.update(1, {"valid": True, "reliable": True, "count": 0})
    assert not c.lights
    c.update(2, {"valid": False})
    assert c.lights and c.state == "uncertain"


def test_stale_distinct_and_override_expiration():
    c = Classroom(stale_after=10)
    c.update(0, {"valid": True, "reliable": True, "count": 1})
    c.mode = "off"
    c.override_until = 5
    c.update(4)
    assert not c.lights
    c.update(11)
    assert c.lights and c.state == "stale" and c.mode == "auto"


def test_door_clears_vacancy_confirmation():
    c = Classroom(interval=1, grace=0)
    obs = {"valid": True, "reliable": True, "count": 0}
    c.update(0, obs)
    c.update(1, obs)
    assert not c.lights
    c.update(2, obs, door=True)
    assert c.lights


def park(
    p,
    t,
    obstruction=False,
    request=None,
    valid=True,
    distances=None,
    camera=None,
    actuator=True,
):
    return p.update(
        t,
        camera or [False] * 4,
        [reading(v, t, valid) for v in (distances or [150] * 4)],
        reading(obstruction, t, valid),
        request,
        actuator,
    )


def test_parking_conflicts_reserve_space():
    p = park(Parking(), 0, distances=[30, 150, 150, 150])
    assert p.spaces[0] == "conflict" and p.available == 3


@pytest.mark.parametrize("blocked,valid", [(True, True), (False, False)])
def test_closing_holds_on_obstruction_or_invalid(blocked, valid):
    p = Parking()
    park(p, 0, request="open")
    park(p, 2)
    park(p, 3, request="close")
    assert p.gate == "CLOSING"
    park(p, 3.5, obstruction=blocked, valid=valid)
    assert p.gate == "HOLD"


def test_manual_close_cannot_bypass():
    p = Parking(gate="OPEN")
    park(p, 0, obstruction=True, request="close")
    assert p.gate == "HOLD"


def test_gate_fault_recovery_requires_stable_clear():
    p = Parking()
    park(p, 0, actuator=False)
    assert p.gate == "FAULT"
    park(p, 1, request="reset")
    assert p.gate == "FAULT"
    park(p, 3, request="reset")
    assert p.gate == "OPEN"


def test_full_parking_denies_open():
    p = park(Parking(), 0, camera=[True] * 4, distances=[20] * 4, request="open")
    assert p.gate == "CLOSED" and p.available == 0


def test_sorter_ack_counts_once():
    s = Sorter()
    s.submit(0, {"id": "a", "probabilities": probs()}, bins(), reading(100))
    assert s.state == "MOVING" and not sum(s.totals.values())
    s.tick(0.5, ack=True, actual="plastic")
    s.tick(1, ack=True)
    assert s.totals["paper"] == 1 and s.contamination == 1


@pytest.mark.parametrize(
    "item",
    [
        {"id": "a", "probabilities": {c: 0.2 for c in CATEGORIES}},
        {"id": "a", "probabilities": probs(), "mixed": True},
        {"id": "a", "probabilities": {"paper": float("nan")}},
    ],
)
def test_unknown_mixed_invalid_reject(item):
    s = Sorter()
    s.submit(0, item, bins(), reading(100))
    assert s.state == "REVIEW" and not sum(s.totals.values())


@pytest.mark.parametrize("fill,weight", [(90, 100), (20, 2000)])
def test_full_or_overweight_review(fill, weight):
    s = Sorter()
    s.submit(0, {"id": "a", "probabilities": probs()}, bins(fill=fill), reading(weight))
    assert s.state == "REVIEW"


def test_stale_sensor_fault():
    s = Sorter()
    s.submit(10, {"id": "a", "probabilities": probs()}, bins(), reading(100))
    assert s.state == "FAULT"


@pytest.mark.parametrize("jam,time", [(True, 1), (False, 3)])
def test_jam_timeout_no_disposal(jam, time):
    s = Sorter()
    s.submit(0, {"id": "a", "probabilities": probs()}, bins(), reading(100))
    s.tick(time, jam=jam)
    assert s.state == "FAULT" and not sum(s.totals.values())
    s.tick(time + 1, reset=True, jam=False)
    assert s.state == "REVIEW"


def test_duplicate_item_rejected():
    s = Sorter()
    item = {"id": "same", "probabilities": probs()}
    s.submit(0, item, bins(), reading(100))
    s.tick(1, ack=True)
    s.submit(2, item, bins(2), reading(100, 2))
    assert s.state == "IDLE" and sum(s.totals.values()) == 1


def test_tracker_crossing_and_stationary():
    t = Tracker()
    ids = []
    for n, x in enumerate(
        [0.25, 0.3, 0.35, 0.4, 0.45, 0.5, 0.55, 0.6, 0.65, 0.65, 0.65]
    ):
        tracked = t.update(
            [{"box": [x - 0.13, 0.2, x + 0.13, 0.8], "label": "person", "score": 0.9}],
            n * 0.1,
        )
        ids.append(tracked[0]["id"])
    assert len(set(ids)) == 1 and t.entries == 1 and t.exits == 0
    t.update([], 10)
    assert not t.tracks
    with pytest.raises(ValueError):
        t.update([], 9)


def test_tracker_one_to_one():
    t = Tracker()
    d = {"box": [0.1, 0.1, 0.4, 0.5], "label": "person", "score": 0.9}
    t.update([d], 0)
    v = t.update([d, d], 1)
    assert len({x["id"] for x in v}) == 2


def test_store_atomic_duplicate_and_reload(tmp_path):
    p = tmp_path / "state.sqlite"
    s = Store(p)
    assert s.commit("id", 0, {"x": 1}, {"a": 1})
    assert not s.commit("id", 1, {"x": 2}, {"a": 2})
    s.close()
    s = Store(p)
    assert s.load() == {"a": 1}
    assert len(s.events()) == 1
    s.close()


@pytest.mark.parametrize("value", [-1, float("nan"), float("inf"), 3601])
def test_clock_invalid(value):
    c = VirtualClock()
    with pytest.raises(ValueError):
        c.advance(value)


@pytest.mark.parametrize("kind", ["classroom", "parking", "waste"])
def test_runtime_duplicate_restore_and_bad_input(tmp_path, kind):
    r = Runtime(kind, tmp_path, tmp_path / "db")
    r.apply({"op": "step", "seconds": 1}, "one")
    r.apply({"op": "step", "seconds": 1}, "one")
    assert r.clock.now() == 1
    before = r.snapshot()
    with pytest.raises(ValueError):
        r.apply({"op": "sensors", "values": {"fill": float("nan")}})
    assert r.snapshot() == before
    r.store.close()
    r = Runtime(kind, tmp_path, tmp_path / "db")
    assert r.clock.now() == 1
    r.store.close()


def test_large_step_equivalent(tmp_path):
    a = Runtime("classroom", tmp_path, tmp_path / "a")
    b = Runtime("classroom", tmp_path, tmp_path / "b")
    a.apply({"op": "step", "seconds": 600})
    for _ in range(600):
        b.apply({"op": "step", "seconds": 1})
    assert a.snapshot()["controller"] == b.snapshot()["controller"]


def test_restart_sorter_does_not_resume_movement(tmp_path):
    a = Runtime("waste", tmp_path, tmp_path / "a")
    a.apply({"op": "item", "probabilities": probs()})
    a.store.close()
    b = Runtime("waste", tmp_path, tmp_path / "a")
    assert b.controller.state == "FAULT"


def test_failed_commit_restores_controller(tmp_path, monkeypatch):
    r = Runtime("classroom", tmp_path, tmp_path / "db")
    before = r.snapshot()

    def fail(*a):
        raise OSError("simulated disk failure")

    monkeypatch.setattr(r.store, "commit", fail)
    with pytest.raises(OSError):
        r.apply({"op": "step", "seconds": 2})
    assert r.snapshot() == before


def test_real_image_is_not_refreshed_without_new_frame(tmp_path):
    r = Runtime("classroom", tmp_path, tmp_path / "db")
    r.accept_inference(
        {"source": "real inference", "detections": [], "brightness": 100}, "image"
    )
    r.apply({"op": "configure", "interval": 1, "grace": 0})
    r.apply({"op": "step", "seconds": 4})
    assert r.controller.lights and r.controller.state == "uncertain"


def test_inference_cannot_clear_physical_obstruction(tmp_path):
    r = Runtime("parking", tmp_path, tmp_path / "db")
    r.apply({"op": "sensors", "values": {"obstruction": True}})
    r.accept_inference(
        {"source": "real inference", "detections": [], "brightness": 100}, "image"
    )
    assert r.input["obstruction"] is True


def test_fill_becoming_full_before_ack_stops_sorter(tmp_path):
    r = Runtime("waste", tmp_path, tmp_path / "db")
    r.apply({"op": "item", "probabilities": probs()})
    r.apply({"op": "sensors", "values": {"fill": 95}})
    assert r.controller.state == "FAULT" and not sum(r.controller.totals.values())


def test_runtime_malformed_event_id(tmp_path):
    r = Runtime("classroom", tmp_path, tmp_path / "db")
    with pytest.raises(ValueError):
        r.apply({"op": "step"}, ["bad"])


def test_stale_parking_image_reserves_all_spaces(tmp_path):
    r = Runtime("parking", tmp_path, tmp_path / "db")
    r.accept_inference(
        {"source": "real inference", "detections": [], "brightness": 100}, "image"
    )
    assert r.controller.available == 4
    r.apply({"op": "step", "seconds": 3})
    assert r.controller.available == 0 and r.controller.spaces == ["unknown"] * 4


def test_tracker_counts_only_target_classes(tmp_path):
    r = Runtime("classroom", tmp_path, tmp_path / "db")
    r.accept_inference(
        {
            "source": "real inference",
            "detections": [
                {"label": "chair", "score": 0.9, "box": [0.1, 0.1, 0.4, 0.4]}
            ],
            "brightness": 100,
        },
        "image",
    )
    assert not r.tracker.tracks


def test_entry_counters_survive_restart(tmp_path):
    r = Runtime("classroom", tmp_path, tmp_path / "db")
    r.tracker.entries = 3
    r.tracker.exits = 2
    r.apply({"op": "check"})
    r.store.close()
    s = Runtime("classroom", tmp_path, tmp_path / "db")
    assert (s.tracker.entries, s.tracker.exits) == (3, 2)


def test_inference_disk_failure_rolls_back_tracking(tmp_path, monkeypatch):
    r = Runtime("classroom", tmp_path, tmp_path / "db")
    before = r.snapshot()

    def fail(*args):
        raise OSError("disk failed")

    monkeypatch.setattr(r.store, "commit", fail)
    with pytest.raises(OSError):
        r.accept_inference(
            {
                "source": "real inference",
                "brightness": 100,
                "detections": [
                    {"label": "person", "score": 0.9, "box": [0.1, 0.1, 0.4, 0.7]}
                ],
            },
            "image",
        )
    assert r.snapshot() == before and not r.tracker.tracks


def test_restart_does_not_promote_old_camera_to_fixture(tmp_path):
    r = Runtime("parking", tmp_path, tmp_path / "db")
    r.accept_inference(
        {"source": "real inference", "brightness": 100, "detections": []}, "image"
    )
    r.store.close()
    s = Runtime("parking", tmp_path, tmp_path / "db")
    s.apply({"op": "check"})
    assert s.controller.available == 0
