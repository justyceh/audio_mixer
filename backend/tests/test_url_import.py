import pytest

from api.core.exceptions import ImportRejectedError
from api.utils.filenames import sanitize_filename
from api.utils.range_response import RangeNotSatisfiable, parse_range_header
from api.utils.url_safety import is_public_ip, validate_import_url

ALLOWED = ["youtube.com", "youtu.be", "soundcloud.com"]


def public(_host):
    return ["142.250.72.14"]


@pytest.mark.parametrize(
    "url",
    [
        "https://www.youtube.com/watch?v=abc",
        "https://youtu.be/abc",
        "http://soundcloud.com/artist/track",
        "https://m.youtube.com:443/watch?v=abc",
    ],
)
def test_allowed_urls(url):
    assert validate_import_url(url, ALLOWED, resolver=public)


@pytest.mark.parametrize(
    "url,reason",
    [
        ("ftp://youtube.com/x", "http"),
        ("file:///etc/passwd", "http"),
        ("https://user:pw@youtube.com/x", "credentials"),
        ("https://youtube.com:8080/x", "port"),
        ("https://127.0.0.1/x", "IP address"),
        ("https://[::1]/x", "IP address"),
        ("https://evil.com/x", "not a supported"),
        ("https://youtube.com.evil.com/x", "not a supported"),
        ("https://notyoutube.com/x", "not a supported"),
        ("https://", "no host"),
        ("", "empty"),
    ],
)
def test_rejected_urls(url, reason):
    with pytest.raises(ImportRejectedError) as exc:
        validate_import_url(url, ALLOWED, resolver=public)
    assert reason.lower() in exc.value.message.lower()


@pytest.mark.parametrize("address", ["10.0.0.5", "192.168.1.1", "127.0.0.1", "169.254.169.254", "::1", "fd00::1",
                                     "::ffff:127.0.0.1", "0.0.0.0", "100.64.0.1"])
def test_private_resolution_blocked(address):
    assert not is_public_ip(address)
    with pytest.raises(ImportRejectedError, match="private or reserved"):
        validate_import_url("https://www.youtube.com/watch?v=x", ALLOWED, resolver=lambda h: [address])


def test_unresolvable_host():
    def fail(_host):
        raise OSError("nope")

    with pytest.raises(ImportRejectedError, match="resolve"):
        validate_import_url("https://youtube.com/x", ALLOWED, resolver=fail)


def test_import_endpoint_rejects_unsafe_url(client):
    response = client.post("/api/media/import", json={"url": "http://localhost:8000/api/media"})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "import_rejected"
    assert client.post("/api/media/import", json={"url": "not a url"}).status_code == 422


@pytest.mark.parametrize(
    "name,expected",
    [("../../etc/passwd", "passwd"), ("C:\\Windows\\evil.wav", "evil.wav"), ("ok name (1).mp3", "ok name (1).mp3"),
     ("..", "media"), (None, "media"), ("a\x00b.wav", "ab.wav")],
)
def test_sanitize_filename(name, expected):
    assert sanitize_filename(name) == expected


def test_range_parsing():
    assert parse_range_header("bytes=0-9", 100) == (0, 9)
    assert parse_range_header("bytes=90-", 100) == (90, 99)
    assert parse_range_header("bytes=-10", 100) == (90, 99)
    assert parse_range_header("bytes=50-500", 100) == (50, 99)
    assert parse_range_header("items=0-1", 100) is None
    assert parse_range_header("bytes=0-1,5-6", 100) is None
    with pytest.raises(RangeNotSatisfiable):
        parse_range_header("bytes=100-", 100)
