"""HTTP flow: register -> upload -> dub -> review/edit -> re-render -> download; tenant isolation; voices."""
import asyncio

import pytest
from fastapi.testclient import TestClient

from apps.api.main import app
from apps.api.routers import pipeline as pipeline_router
from apps.db.session import get_session
from apps.services import providers as prov
from apps.services.dubbing_pipeline import DubbingPipeline


@pytest.fixture
def client(session_factory):
    async def _session():
        async with session_factory() as s:
            yield s

    app.dependency_overrides[get_session] = _session
    app.dependency_overrides[pipeline_router.get_pipeline] = lambda: DubbingPipeline(session_factory)
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def login(c, email):
    r = c.post("/auth/register", json={"email": email, "password": "correct-horse-battery"})
    assert r.status_code == 200, r.text
    r = c.post("/auth/token", data={"username": email, "password": "correct-horse-battery"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def upload(c, h, sample_video):
    with open(sample_video, "rb") as f:
        r = c.post("/uploads", headers=h, files={"file": ("ep1.mp4", f, "video/mp4")})
    assert r.status_code == 201, r.text
    return r.json()["upload_id"]


def test_full_flow(client, sample_video):
    h = login(client, "studio@example.com")
    up = upload(client, h, sample_video)
    r = client.post("/jobs", headers=h, json={"upload_id": up, "rights": True, "title": "Pilot",
                                              "target_language": "de"})
    assert r.status_code == 201, r.text
    job_id = r.json()["id"]
    job = client.get(f"/jobs/{job_id}", headers=h).json()
    assert job["status"] == "completed", job["errors"]
    assert job["qa_report"]["overall_pass"]

    segs = client.get(f"/jobs/{job_id}/segments", headers=h).json()["segments"]
    assert segs and "fitted" not in segs[0]  # internal paths are never exposed

    r = client.get(f"/jobs/{job_id}/output", headers=h)
    assert r.status_code == 200 and r.headers["content-type"] == "video/mp4" and len(r.content) > 1000
    assert "Pilot.de.mp4" in r.headers["content-disposition"]

    # human edit of one line -> re-render only that line
    r = client.patch(f"/jobs/{job_id}/segments/0", headers=h, json={"translation": "Kurz."})
    assert r.status_code == 200
    assert client.get(f"/jobs/{job_id}", headers=h).json()["status"] == "edited"
    r = client.post(f"/jobs/{job_id}/render", headers=h)
    assert r.status_code == 200
    job = client.get(f"/jobs/{job_id}", headers=h).json()
    assert job["status"] == "completed"
    assert client.get(f"/jobs/{job_id}/segments", headers=h).json()["segments"][0]["translation"] == "Kurz."
    assert client.post(f"/jobs/{job_id}/render", headers=h).status_code == 409  # nothing to do

    stats = client.get("/stats", headers=h).json()
    assert stats["completed_jobs"] == 1 and stats["minutes_dubbed"] > 0

    assert client.get("/jobs", headers=h).json()["jobs"][0]["id"] == job_id
    assert client.delete(f"/jobs/{job_id}", headers=h).status_code == 204
    assert client.get(f"/jobs/{job_id}", headers=h).status_code == 404


def test_idempotency(client, sample_video):
    h = login(client, "idem@example.com")
    up = upload(client, h, sample_video)
    body = {"upload_id": up, "rights": True, "idempotency_key": "abc"}
    a = client.post("/jobs", headers=h, json=body).json()["id"]
    b = client.post("/jobs", headers=h, json=body).json()["id"]
    assert a == b


def test_tenant_isolation(client, sample_video):
    a = login(client, "a@example.com")
    b = login(client, "b@example.com")
    up = upload(client, a, sample_video)
    job_id = client.post("/jobs", headers=a, json={"upload_id": up, "rights": True}).json()["id"]
    assert client.post("/jobs", headers=b, json={"upload_id": up, "rights": True}).status_code == 404
    for path in (f"/jobs/{job_id}", f"/jobs/{job_id}/segments", f"/jobs/{job_id}/output", f"/jobs/{job_id}/qa-report"):
        assert client.get(path, headers=b).status_code == 404, path
    assert client.patch(f"/jobs/{job_id}/segments/0", headers=b, json={"translation": "x"}).status_code == 404
    assert client.delete(f"/jobs/{job_id}", headers=b).status_code == 404
    assert client.get("/jobs", headers=b).json()["jobs"] == []
    assert client.get("/stats", headers=b).json()["total_jobs"] == 0


def test_upload_validation(client, tmp_path):
    h = login(client, "up@example.com")
    bad = tmp_path / "x.mp4"
    bad.write_bytes(b"not a video")
    with open(bad, "rb") as f:
        assert client.post("/uploads", headers=h, files={"file": ("x.mp4", f)}).status_code == 422
    with open(bad, "rb") as f:
        assert client.post("/uploads", headers=h, files={"file": ("x.exe", f)}).status_code == 415
    assert client.post("/jobs", headers=h, json={"upload_id": "00000000-0000-0000-0000-000000000000",
                                                 "rights": True}).status_code == 404
    assert client.post("/jobs", headers=h, json={"upload_id": "../../etc", "rights": True}).status_code == 422


def test_requires_auth(client):
    assert client.get("/jobs").status_code == 401
    assert client.get("/jobs", headers={"Authorization": "Bearer nope"}).status_code == 401


def test_voices_clone_use_and_revoke(client, sample_video, tmp_path):
    h = login(client, "voice@example.com")
    sample = tmp_path / "ref.wav"
    asyncio.run(prov.ffmpeg.synth_tone(sample, 12.0))
    with open(sample, "rb") as f:
        r = client.post("/voices/clone", headers=h, data={"speaker_name": "Max", "consent": "false"},
                        files={"sample": ("ref.wav", f)})
    assert r.status_code == 422
    with open(sample, "rb") as f:
        r = client.post("/voices/clone", headers=h, data={"speaker_name": "Max", "consent": "true"},
                        files={"sample": ("ref.wav", f)})
    assert r.status_code == 201, r.text
    voice = r.json()
    assert voice["cloned"] and "reference_audio_url" not in voice

    up = upload(client, h, sample_video)
    job_id = client.post("/jobs", headers=h, json={"upload_id": up, "rights": True,
                                                   "voice_profile_id": voice["id"]}).json()["id"]
    assert client.get(f"/jobs/{job_id}", headers=h).json()["status"] == "completed"

    other = login(client, "other@example.com")
    assert client.get(f"/voices/{voice['id']}", headers=other).status_code == 404
    assert client.delete(f"/voices/{voice['id']}/consent", headers=other).status_code == 404

    r = client.delete(f"/voices/{voice['id']}/consent", headers=h)
    assert r.status_code == 200 and r.json()["jobs_affected"] == 1
    job = client.get(f"/jobs/{job_id}", headers=h).json()
    assert job["status"] == "failed" and job["output_video_url"] is None
    assert client.get(f"/jobs/{job_id}/output", headers=h).status_code == 409
    assert client.get("/voices", headers=h).json()["voices"] == []


def test_stock_voice(client):
    h = login(client, "stock@example.com")
    r = client.post("/voices", headers=h, json={"speaker_name": "Erzähler", "voice_preset": "pNInz6obpgDQGcFmaJgB",
                                                "consent": True})
    assert r.status_code == 201 and not r.json()["cloned"]
    r = client.post("/voices", headers=h, json={"speaker_name": "x", "voice_preset": "../../x", "consent": True})
    assert r.status_code == 422

def test_frontend_serving(client):
    # Root redirects to /app/
    r = client.get("/", follow_redirects=False)
    assert r.status_code == 307
    assert r.headers["location"] == "/app/"
    
    # /api-info returns JSON
    r = client.get("/api-info")
    assert r.status_code == 200
    assert r.json()["service"] == "Series Sync SaaS"
    
    # /app/ serves HTML
    r = client.get("/app/")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    assert "Series Sync" in r.text


def test_multi_line_edit_then_render(client, sample_video):
    h = login(client, "multi@example.com")
    up = upload(client, h, sample_video)
    job_id = client.post("/jobs", headers=h, json={"upload_id": up, "rights": True}).json()["id"]
    assert client.patch(f"/jobs/{job_id}/segments/0", headers=h, json={"translation": "Eins."}).status_code == 200
    assert client.patch(f"/jobs/{job_id}/segments/1", headers=h, json={"translation": ""}).status_code == 200
    assert client.get(f"/jobs/{job_id}", headers=h).json()["status"] == "edited"
    assert client.post(f"/jobs/{job_id}/render", headers=h).status_code == 200
    segs = client.get(f"/jobs/{job_id}/segments", headers=h).json()["segments"]
    assert segs[0]["translation"] == "Eins." and segs[1]["translation"] == ""  # empty edit not re-translated
    assert client.get(f"/jobs/{job_id}", headers=h).json()["status"] in ("completed", "hitl_review")


def test_stock_voice_delete_keeps_dubs(client, sample_video):
    h = login(client, "stockdel@example.com")
    v = client.post("/voices", headers=h, json={"speaker_name": "S", "voice_preset": "pNInz6obpgDQGcFmaJgB",
                                                "consent": True}).json()
    up = upload(client, h, sample_video)
    job_id = client.post("/jobs", headers=h, json={"upload_id": up, "rights": True, "voice_profile_id": v["id"]}).json()["id"]
    assert client.delete(f"/voices/{v['id']}/consent", headers=h).json()["jobs_affected"] == 0
    assert client.get(f"/jobs/{job_id}/output", headers=h).status_code == 200


def test_upload_size_checked_before_parsing(client):
    h = login(client, "big@example.com")
    r = client.post("/uploads", headers={**h, "Content-Length": str(10**13), "Content-Type": "multipart/form-data; boundary=x"},
                    content=b"--x--")
    assert r.status_code == 413
