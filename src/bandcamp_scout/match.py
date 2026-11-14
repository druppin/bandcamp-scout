"""Normalize titles/artists and score an input track against a Bandcamp candidate (0..1)."""
import re
import unicodedata

from rapidfuzz import fuzz

W_TITLE, W_ARTIST, W_DURATION = 0.45, 0.35, 0.20
VERSION_CAP = 0.5
MATCH, REVIEW = 0.90, 0.75

_VERSION_WORDS = re.compile(r"\b(remix|mix|edit|vip|bootleg|rework|refix|flip|dub|version|versão|versión|remaster(ed)?|"
                            r"mashup|cover|tribute|instrumental|acapella|karaoke|backing track|nightcore|sped up|"
                            r"slowed|live|acoustic|demo|8[ -]?bit)\b", re.I)
_NOT_A_VERSION = re.compile(r"^\s*(original( mix)?|remaster(ed)?( \d{4})?|\d{4} remaster(ed)?)\s*$", re.I)
_FEAT = re.compile(r"\s*[\(\[]?\b(feat\.?|ft\.?|featuring)\s.*?([\)\]]|$)", re.I)
_BRACKETED = re.compile(r"\s*[\(\[]([^\)\]]*)[\)\]]")
_DASH_SUFFIX = re.compile(r"\s+-\s+([^-]*)$")
_ARTIST_DASH = re.compile(r"\s+[-–]\s*|\s*[-–]\s+")
_ARTIST_SEP = re.compile(r"\s*[,&/+]\s*|\s+(?:and|x|vs\.?|feat\.?|ft\.?|featuring|with)\s+", re.I)


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
    return artist_names(artists), normalize(base), version


def artist_names(artists) -> list[str]:
    """['DJ Marky & S.P.Y', 'Lynx'] -> ['dj marky', 's p y', 'lynx']: compare whole names, so 'Zim' != 'Gera Zim Zum'."""
    names = (normalize(n) for a in artists for n in _ARTIST_SEP.split(a or ""))
    return [n.removeprefix("the ") for n in names if n]


def duration_score(a: float | None, b: float | None) -> float:
    if not a or not b:
        return 0.5
    diff = abs(a - b)
    return 1.0 if diff <= 3 else max(0.0, 1 - (diff - 3) / 12)


def score(artists, title, duration_s, bc_artist, bc_title, bc_duration_s) -> float:
    in_title, in_version = split_title(title)
    bc_artists, bc_base, bc_version = candidate_names(bc_artist, bc_title)
    t = fuzz.token_sort_ratio(in_title, bc_base) / 100  # not token_set: "on fire" would fully match "chestnuts roasting on an open fire"
    a = max((fuzz.ratio(x, y) / 100 for x in artist_names(artists) for y in bc_artists), default=0.0)
    a = max(0.0, 2 * a - 1)  # steep: 'rush' vs 'gush' (0.75) is a different artist, not a 75% one
    s = W_TITLE * t + W_ARTIST * a + W_DURATION * duration_score(duration_s, bc_duration_s)
    account = max((fuzz.ratio(x, y) / 100 for x in artist_names(artists) for y in artist_names([bc_artist])), default=0.0)
    if account < 0.95 and not (duration_s and bc_duration_s and abs(duration_s - bc_duration_s) <= 2):
        s = min(s, MATCH - 0.01)  # someone else's upload ('Artist - Title'): only a same-length file is a match
    if (in_version is None) != (bc_version is None) or (
            in_version and bc_version and fuzz.token_set_ratio(in_version, bc_version) < 85):
        s = min(s, VERSION_CAP)
    return round(s, 3)


def status(s: float) -> str:
    return "match" if s >= MATCH else "review" if s >= REVIEW else "no_match"
