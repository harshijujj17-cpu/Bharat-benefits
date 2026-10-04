"""Helpers for ranking official Indian government web sources."""

from urllib.parse import urlparse

OFFICIAL_HOST_SUFFIXES = (".gov.in", ".nic.in")
PREFERRED_HOSTS = (
    "myscheme.gov.in",
    "www.myscheme.gov.in",
    "india.gov.in",
    "www.india.gov.in",
    "scholarships.gov.in",
    "nsp.gov.in",
    "services.india.gov.in",
)


def hostname(url: str) -> str:
    host = urlparse(url).netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    return host


def normalize_url(url: str) -> str:
    return (url or "").strip().rstrip("/")


def is_official_government_url(url: str) -> bool:
    host = hostname(url)
    if not host:
        return False
    if host in {h.removeprefix("www.") for h in PREFERRED_HOSTS}:
        return True
    return host.endswith(OFFICIAL_HOST_SUFFIXES)


def source_tier(url: str) -> str:
    return "official" if is_official_government_url(url) else "supporting"


def source_verification(url: str) -> dict:
    host = hostname(url)
    official = is_official_government_url(url)
    return {
        "is_official_government_source": official,
        "domain": host,
        "tier": "official" if official else "supporting",
    }
