"""
tests/test_cameras.py

Integration tests for camera registry endpoints.

Role: QA Engineer
Coverage:
  - GET /cameras → list
  - POST /cameras → register camera (rtsp:// URL must be accepted)
  - Pydantic regression: HttpUrl vs str for rtsp scheme
"""
from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_list_cameras_returns_list(client):
    """GET /cameras must return a JSON list."""
    resp = await client.get("/cameras")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_create_camera_rtsp_url_accepted(client):
    """
    POST /cameras with rtsp:// URL must be accepted.
    Regression: HttpUrl (Pydantic v2) rejects rtsp:// scheme.
    Fixed: changed rtsp_url field to plain str.
    """
    payload = {
        "camera_id": "cam-test-001",
        "camera_name": "Test Camera",
        "rtsp_url": "rtsp://192.168.1.100:554/stream1",
        "location": "Test Zone A",
    }
    resp = await client.post("/cameras", json=payload)
    # 200/201 = created; 500 would indicate the rtsp:// Pydantic bug is back
    assert resp.status_code in {200, 201}, (
        f"rtsp:// URL rejected — possible Pydantic HttpUrl regression: {resp.text}"
    )


@pytest.mark.asyncio
async def test_create_camera_invalid_url_rejected(client):
    """POST /cameras with invalid URL scheme must return 422."""
    payload = {
        "camera_id": "cam-test-bad",
        "camera_name": "Bad Camera",
        "rtsp_url": "ftp://invalid-scheme.com/stream",
        "location": "Nowhere",
    }
    resp = await client.post("/cameras", json=payload)
    assert resp.status_code == 422, (
        f"Invalid URL scheme should be rejected with 422, got {resp.status_code}"
    )


@pytest.mark.asyncio
async def test_create_camera_webcam_index_accepted(client):
    """POST /cameras with webcam index ('0') must be accepted."""
    payload = {
        "camera_id": "cam-test-webcam",
        "camera_name": "Webcam",
        "rtsp_url": "0",
        "location": "Lab",
    }
    resp = await client.post("/cameras", json=payload)
    assert resp.status_code in {200, 201}, (
        f"Webcam index '0' should be accepted, got {resp.status_code}: {resp.text}"
    )
