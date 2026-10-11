import httpx
import pytest

from app.core.errors import BlockedDestination, LimitExceeded
from app.net.safe_http import API_HOSTS, MEDIA_HOSTS, HostPolicy, SafeHttpClient, is_public_ip
from tests.conftest import mock_client


@pytest.mark.parametrize("ip", [
    "127.0.0.1", "10.1.2.3", "172.16.0.5", "192.168.1.1", "169.254.169.254", "100.64.0.1", "0.0.0.0",
    "224.0.0.1", "255.255.255.255", "::1", "fe80::1", "fc00::1", "fd00:ec2::254", "::ffff:127.0.0.1",
    "::ffff:10.0.0.1", "64:ff9b::a00:1", "2002:7f00:1::", "198.18.0.1", "not-an-ip",
])
def test_private_and_special_ips_blocked(ip):
    assert not is_public_ip(ip)


@pytest.mark.parametrize("ip", ["93.184.216.34", "142.250.72.14", "2606:4700::6810:84e5"])
def test_public_ips_allowed(ip):
    assert is_public_ip(ip)


def test_host_policy():
    assert API_HOSTS.allows("api.x.com")
    assert not API_HOSTS.allows("api.x.com.evil.net")
    assert MEDIA_HOSTS.allows("scontent-iad3-1.cdninstagram.com")
    assert MEDIA_HOSTS.allows("video.twimg.com")
    assert not MEDIA_HOSTS.allows("cdninstagram.com.evil.net")
    assert not MEDIA_HOSTS.allows("evilcdninstagram.com")
    assert not MEDIA_HOSTS.allows("metadata.google.internal")


async def _vet(url, resolver=None, policy=API_HOSTS):
    async def default(host, port):
        return ["93.184.216.34"]
    c = SafeHttpClient(policy, resolver=resolver or default)
    try:
        return await c.vet(url)
    finally:
        await c.aclose()


@pytest.mark.parametrize("url", [
    "http://api.x.com/2/tweets/1",              # not https
    "https://evil.com/",                        # not allowlisted
    "https://127.0.0.1/",                       # IP literal
    "https://[::1]/",                           # IPv6 literal
    "https://api.x.com:8443/",                  # port
    "https://user@api.x.com/",                  # credentials
    "https://metadata.google.internal/",        # metadata host
])
async def test_vet_rejects(url):
    with pytest.raises(BlockedDestination):
        await _vet(url)


async def test_vet_rejects_private_resolution():
    async def rebind(host, port):
        return ["10.0.0.7"]
    with pytest.raises(BlockedDestination):
        await _vet("https://api.x.com/2/tweets/1", rebind)


async def test_vet_rejects_mixed_records():
    async def mixed(host, port):
        return ["93.184.216.34", "169.254.169.254"]
    with pytest.raises(BlockedDestination):
        await _vet("https://api.x.com/", mixed)


async def test_vet_pins_ip_and_keeps_sni():
    t = await _vet("https://api.x.com/2/tweets/1?x=1")
    assert t.url == "https://93.184.216.34/2/tweets/1?x=1"
    assert t.host == "api.x.com"


async def test_request_sends_host_header_and_sni():
    seen = {}

    def handler(req: httpx.Request):
        seen["host"] = req.headers["host"]
        seen["sni"] = req.extensions.get("sni_hostname")
        seen["url_host"] = req.url.host
        return httpx.Response(200, json={"ok": True})

    async with mock_client(API_HOSTS, handler) as c:
        r = await c.get("https://api.x.com/2/tweets/1")
    assert r.json() == {"ok": True}
    assert seen == {"host": "api.x.com", "sni": "api.x.com", "url_host": "93.184.216.34"}


async def test_redirect_to_disallowed_host_blocked():
    def handler(req):
        return httpx.Response(302, headers={"location": "https://evil.example/steal"})

    async with mock_client(API_HOSTS, handler) as c:
        with pytest.raises(BlockedDestination):
            await c.get("https://api.x.com/2/tweets/1")


async def test_redirect_to_metadata_ip_blocked():
    def handler(req):
        return httpx.Response(301, headers={"location": "https://169.254.169.254/latest/meta-data"})

    async with mock_client(API_HOSTS, handler) as c:
        with pytest.raises(BlockedDestination):
            await c.get("https://api.x.com/2/tweets/1")


async def test_redirect_within_allowlist_followed_and_revalidated():
    calls = []

    def handler(req):
        calls.append(req.headers["host"])
        if req.headers["host"] == "api.twitter.com":
            return httpx.Response(301, headers={"location": "https://api.x.com/2/tweets/1"})
        return httpx.Response(200, json={"data": {}})

    async with mock_client(API_HOSTS, handler) as c:
        r = await c.get("https://api.twitter.com/2/tweets/1")
    assert r.status_code == 200
    assert calls == ["api.twitter.com", "api.x.com"]


async def test_too_many_redirects():
    def handler(req):
        return httpx.Response(302, headers={"location": "https://api.x.com/loop"})

    async with mock_client(API_HOSTS, handler) as c:
        with pytest.raises(BlockedDestination):
            await c.get("https://api.x.com/loop")


async def test_stream_size_cap_declared():
    def handler(req):
        return httpx.Response(200, headers={"content-length": "999999"}, content=b"x" * 10)

    async with mock_client(MEDIA_HOSTS, handler) as c:
        with pytest.raises(LimitExceeded):
            async with c.stream("https://video.twimg.com/a.mp4", max_bytes=1000):
                pass


async def test_stream_size_cap_undeclared():
    def handler(req):
        return httpx.Response(200, content=b"x" * 5000)

    async with mock_client(MEDIA_HOSTS, handler) as c:
        with pytest.raises(LimitExceeded):
            async with c.stream("https://video.twimg.com/a.mp4", max_bytes=1000) as (_, body):
                async for _chunk in body:
                    pass


def test_policy_suffix_requires_label():
    p = HostPolicy.of(suffixes=[".fbcdn.net"])
    assert not p.allows("fbcdn.net")
    assert p.allows("video.xx.fbcdn.net")
