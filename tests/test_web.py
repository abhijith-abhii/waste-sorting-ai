from pathlib import Path
import sys, json, pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lab.web import create_app


@pytest.fixture(params=["classroom", "parking", "waste"])
def client(tmp_path, request):
    for folder in ["static", "samples", "scenarios", "evidence"]:
        (tmp_path / folder).mkdir()
    (tmp_path / "samples/catalog.json").write_text("[]")
    (tmp_path / "static/index.html").write_text("<h1>Lab</h1>")
    app = create_app(request.param, tmp_path)
    app.config["TESTING"] = True
    return app.test_client()


def post(client, body):
    return client.post("/api/action", json=body, headers={"X-Lab-Request": "1"})


def test_api_persistence_and_export(client):
    assert client.get("/").status_code == 200
    a = post(client, {"op": "step", "seconds": 60, "event_id": "one"})
    assert a.status_code == 200 and a.json["time"] == 60
    assert (
        post(client, {"op": "step", "seconds": 60, "event_id": "one"}).json["time"]
        == 60
    )
    assert len(client.get("/api/events").json) == 1
    assert client.get("/api/export").json["state"]["time"] == 60
    assert client.get("/api/samples").json == []


def test_api_rejects_cross_origin_form_and_invalid_json(client):
    assert client.post("/api/action", json={"op": "step"}).status_code == 403
    assert post(client, {"op": "sensors", "values": None}).status_code == 400
    assert post(client, {"op": "step", "seconds": -5}).status_code == 400
    assert (
        post(client, {"op": "configure", "threshold": float("nan")}).status_code == 400
    )
    assert post(client, []).status_code == 400
    assert client.get("/api/state").json["time"] == 0


def test_missing_video_does_not_claim_frames(client):
    assert (
        client.post(
            "/api/video-step", json={}, headers={"X-Lab-Request": "1"}
        ).status_code
        == 400
    )
