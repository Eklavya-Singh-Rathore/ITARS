"""Deployment-hardening tests (Phase 14): CORS lockdown + optional API-token auth.

Both default to the permissive dev behaviour (CORS '*', no auth) so the rest of
the suite is unaffected; these tests exercise the production-locked-down paths.
"""

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from backend.app import create_app  # noqa: E402


class _Engine:
    index_size = 10
    duplicate_threshold = 0.7


class _Artifacts:
    tag_list = [1, 2, 3]
    dept_prototypes = {"a": 1, "b": 2}


class FakePipeline:
    def __init__(self):
        self.artifacts = _Artifacts()
        self.duplicate_engine = _Engine()
        self.routing_sbert = object()


def test_cors_defaults_to_wildcard():
    client = TestClient(create_app(pipeline=FakePipeline()))
    r = client.get("/health", headers={"Origin": "https://anything.example"})
    assert r.status_code == 200
    assert r.headers.get("access-control-allow-origin") == "*"


def test_cors_pinned_origin_is_echoed():
    client = TestClient(
        create_app(pipeline=FakePipeline(), cors_origins="https://itars.vercel.app")
    )
    r = client.get("/health", headers={"Origin": "https://itars.vercel.app"})
    assert r.headers.get("access-control-allow-origin") == "https://itars.vercel.app"


def test_auth_disabled_by_default(db_factory):
    client = TestClient(create_app(pipeline=FakePipeline(), session_factory=db_factory))
    assert client.get("/tickets/recent").status_code == 200


def test_auth_blocks_protected_without_token(db_factory):
    client = TestClient(
        create_app(pipeline=FakePipeline(), session_factory=db_factory, api_token="s3cret")
    )
    # /health stays public (liveness probes must not need a token).
    assert client.get("/health").status_code == 200
    # A protected endpoint is rejected without the token.
    r = client.get("/tickets/recent")
    assert r.status_code == 401
    assert r.json()["error"] == "unauthorized"


def test_auth_accepts_api_key_and_bearer(db_factory):
    client = TestClient(
        create_app(pipeline=FakePipeline(), session_factory=db_factory, api_token="s3cret")
    )
    assert client.get("/tickets/recent", headers={"X-API-Key": "s3cret"}).status_code == 200
    assert (
        client.get("/tickets/recent", headers={"Authorization": "Bearer s3cret"}).status_code
        == 200
    )
    assert client.get("/tickets/recent", headers={"X-API-Key": "nope"}).status_code == 401


def test_auth_allows_cors_preflight(db_factory):
    client = TestClient(
        create_app(
            pipeline=FakePipeline(),
            session_factory=db_factory,
            api_token="s3cret",
            cors_origins="https://itars.vercel.app",
        )
    )
    r = client.options(
        "/tickets/recent",
        headers={
            "Origin": "https://itars.vercel.app",
            "Access-Control-Request-Method": "GET",
        },
    )
    # Preflight must not be blocked by auth, and CORS answers it.
    assert r.status_code in (200, 204)
    assert r.headers.get("access-control-allow-origin") == "https://itars.vercel.app"
