"""Normalize titles/artists and score an input track against a Bandcamp candidate (0..1)."""
import re
import unicodedata

from rapidfuzz import fuzz

W_TITLE, W_ARTIST, W_DURATION = 0.45, 0.35, 0.20
VERSION_CAP = 0.5
MATCH, REVIEW = 0.90, 0.75

_VERSION_WORDS = re.compile(r"\b(remix|mix|edit|vip|bootleg|rework|refix|flip|dub|version|remaster(ed)?|mashup|cover|instrumental|acapella)\b", re.I)
_NOT_A_VERSION = re.compile(r"^\s*(original( mix)?|remaster(ed)?( \d{4})?|\d{4} remaster(ed)?)\s*$", re.I)
_FEAT = re.compile(r"\s*[\(\[]?\b(feat\.?|ft\.?|featuring)\s.*?([\)\]]|$)", re.I)
_BRACKETED = re.compile(r"\s*[\(\[]([^\)\]]*)[\)\]]")
_DASH_SUFFIX = re.compile(r"\s+-\s+([^-]*)$")
_ARTIST_DASH = re.compile(r"\s+[-–]\s*|\s*[-–]\s+")


def normalize(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(ch for ch in s if not unicodedata.combining(ch)).lower().replace("&", " and ")
    s = re.sub(r"[^\w\s]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _strip(title: str) -> tuple[str, str | None]:
    """Remove feat./brackets/' - X Mix' from a raw title; return (raw base, normalized version or None)."""
    version = None
    t = _FEAT.sub("", title or "")

    def take(m):
        nonlocal version
        inner = m.group(1)
        if _VERSION_WORDS.search(inner) and not _NOT_A_VERSION.match(inner):
            version = version or normalize(inner)
        return ""  # other bracketed bits ([Label], (2019)) are noise

    t = _BRACKETED.sub(take, t)
    m = _DASH_SUFFIX.search(t)
    if m and _VERSION_WORDS.search(m.group(1)):
        if not _NOT_A_VERSION.match(m.group(1)):
            version = version or normalize(m.group(1))
        t = t[: m.start()]
    return t, version


def split_title(title: str) -> tuple[str, str | None]:
    """'Glue (Skrillex Remix) [Ninja Tune]' -> ('glue', 'skrillex remix'). Version None if original."""
    base, version = _strip(title)
    return normalize(base), version


def candidate_names(bc_artist: str, bc_title: str) -> tuple[list[str], str, str | None]:
    """Bandcamp bootlegs/labels title tracks 'Artist - Title': the left part is another artist guess."""
    base, version = _strip(bc_title)
    artists = [bc_artist]
    parts = _ARTIST_DASH.split(base, maxsplit=1)  # also 'Burial- Archangel'; not 'Hip-Hop'
    if len(parts) == 2:
        artists.append(parts[0])
        base = parts[1]
    return [normalize(a) for a in artists if a], normalize(base), version


def duration_score(a: float | None, b: float | None) -> float:
    if not a or not b:
        return 0.5
    diff = abs(a - b)
    return 1.0 if diff <= 3 else max(0.0, 1 - (diff - 3) / 12)


def score(artists, title, duration_s, bc_artist, bc_title, bc_duration_s) -> float:
    in_title, in_version = split_title(title)
    bc_artists, bc_base, bc_version = candidate_names(bc_artist, bc_title)
    t = fuzz.token_set_ratio(in_title, bc_base) / 100
    a = max((fuzz.token_set_ratio(normalize(x), y) / 100 for x in artists for y in bc_artists), default=0.0)
    s = W_TITLE * t + W_ARTIST * a + W_DURATION * duration_score(duration_s, bc_duration_s)
    if (in_version is None) != (bc_version is None) or (
            in_version and bc_version and fuzz.token_set_ratio(in_version, bc_version) < 85):
        s = min(s, VERSION_CAP)
    return round(s, 3)


def status(s: float) -> str:
    return "match" if s >= MATCH else "review" if s >= REVIEW else "no_match"
