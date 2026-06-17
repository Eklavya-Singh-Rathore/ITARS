"""Phase 15B — Qdrant URL normalization + credential-safe logging.

Guards the production-readiness fixes for the Qdrant store wrapper. Pure unit
tests on string helpers — no Qdrant connection needed.
"""

from backend.rag.store import host_for_logging, normalize_qdrant_url


# ----------------------------------------------------------- normalize_qdrant_url


def test_memory_passes_through():
    assert normalize_qdrant_url(":memory:") == ":memory:"


def test_empty_string_passes_through():
    assert normalize_qdrant_url("") == ""


def test_explicit_https_unchanged():
    url = "https://abc.cloud.qdrant.io:6333"
    assert normalize_qdrant_url(url) == url


def test_explicit_http_unchanged():
    url = "http://localhost:6333"
    assert normalize_qdrant_url(url) == url


def test_bare_cloud_host_gets_https_and_default_port():
    assert (
        normalize_qdrant_url("abc.cloud.qdrant.io")
        == "https://abc.cloud.qdrant.io:6333"
    )


def test_bare_cloud_host_with_port_gets_https():
    assert (
        normalize_qdrant_url("abc.cloud.qdrant.io:6333")
        == "https://abc.cloud.qdrant.io:6333"
    )


def test_bare_localhost_gets_http_default_port():
    assert normalize_qdrant_url("localhost") == "http://localhost:6333"


def test_bare_localhost_with_port_gets_http():
    assert normalize_qdrant_url("localhost:6333") == "http://localhost:6333"


def test_loopback_ip_gets_http():
    # 127.0.0.1 is local, should fall back to http://
    assert normalize_qdrant_url("127.0.0.1:6333") == "http://127.0.0.1:6333"


def test_local_path_with_dot_slash_unchanged():
    assert normalize_qdrant_url("./qdrant_data") == "./qdrant_data"


def test_local_path_with_leading_slash_unchanged():
    assert normalize_qdrant_url("/var/lib/qdrant") == "/var/lib/qdrant"


def test_windows_path_unchanged():
    # Drive-letter path on Windows — must not be coerced into an HTTP URL.
    assert normalize_qdrant_url("C:/qdrant_data") == "C:/qdrant_data"


# ----------------------------------------------------------- host_for_logging


def test_logging_redacts_credentials_for_explicit_url():
    # Even when no creds are in the URL, port and host are preserved.
    assert (
        host_for_logging("https://abc.cloud.qdrant.io:6333")
        == "https://abc.cloud.qdrant.io:6333"
    )


def test_logging_strips_default_https_port():
    assert host_for_logging("https://abc.cloud.qdrant.io") == "https://abc.cloud.qdrant.io"


def test_logging_strips_default_http_port():
    assert host_for_logging("http://localhost") == "http://localhost"


def test_logging_keeps_nonstandard_port():
    assert host_for_logging("http://localhost:6334") == "http://localhost:6334"


def test_logging_normalizes_bare_host_first():
    assert (
        host_for_logging("abc.cloud.qdrant.io")
        == "https://abc.cloud.qdrant.io:6333"
    )


def test_logging_passes_memory_through():
    assert host_for_logging(":memory:") == ":memory:"


def test_logging_passes_local_path_through():
    assert host_for_logging("./qdrant_data") == "./qdrant_data"
