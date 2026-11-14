# Phase 0 findings

Verified by hand on **2026-11-14** with `curl` (User-Agent `bandcamp-scout/0.1 (+https://github.com/druppin/bandcamp-scout)`, ~1 req/s). All of this is undocumented and can change; `src/bandcamp_scout/bandcamp.py` is the only file that depends on it.

## Search — confirmed

`POST https://bandcamp.com/api/bcsearch_public_api/1/autocomplete_elastic`, JSON body:

```json
{"search_text": "burial archangel", "search_filter": "t", "full_page": false}
```

- 200 with `{"auto": {"results": [...]}}`, no auth or cookies needed. `"t"` = tracks.
- Each result: `type` (`"t"`), `id`, `name` (track title), `band_name`, `album_name` (null for singles), `item_url_root`, `item_url_path` (full track URL), `album_id`, `art_id`.
- **No duration in search results.** Duration needs the release page, so the scout ranks hits by name and fetches at most 2 pages per track.
- **No ISRC anywhere** (search or page). Matching is by name + duration only.
- `band_name` is the account the track sits on, often a label (e.g. `newbreed` for Shapeshifta) or a bootlegger. Bootlegs/reuploads title tracks `"Artist - Title (Remix)"`, sometimes `"Artist- Title"` (no space before the dash). `match.candidate_names` treats the part before the dash as an extra artist guess.
- Fixture: `tests/fixtures/search_burial_archangel.json`.

## Release page data — confirmed

Track and album pages embed an HTML-escaped JSON blob in a `data-tralbum="…"` attribute (`html.unescape` then `json.loads`). Fields relied on:

| Field | Example | Meaning |
|---|---|---|
| `item_type` | `"track"` / `"album"` | |
| `url` | `"https://calibre.bandcamp.com/track/even-if"` | canonical URL |
| `artist` | `"Calibre"` | page artist |
| `album_url` | `"/album/even-if"` (relative) or null | null = standalone single |
| `FREE`, `PAID` | `1`, `2` | constants for `current.download_pref` |
| `current.title` | `"Even If"` | |
| `current.download_pref` | `1` / `2` / `null` | 1 free, 2 paid (incl. NYP), null = not sold alone |
| `current.minimum_price` | `1.5` | NYP minimum (0.0 for NYP $0) |
| `current.set_price` | `1.5` | default/suggested price |
| `current.is_set_price` | `null` on every page seen | assumed truthy = fixed price, see below |
| `trackinfo[0].duration` | `454.253` | seconds (float) |
| `trackinfo[0].is_downloadable` | `true` / `false` | false = can't buy the track alone |
| `freeDownloadPage` | URL or null | present for free and *some* NYP $0 tracks; not used for classification |

Currency is **not** in `data-tralbum`. It's in a separate attribute `data-band-currency="GBP"` (also in `data-band` JSON and in ld+json `offers.priceCurrency`).

`<script type="application/ld+json">` exists with `offers` (`price`, `priceCurrency`, `priceSpecification.minPrice`) per release format. It agrees with the tralbum minimums; not used, kept as a cross-check if tralbum ever moves.

## Price types as they appear

| Type | Data | Example (fixture) |
|---|---|---|
| free | `download_pref = 1` | oylumtanis "Burial - Archangel" (`track_free.html`) |
| NYP $0 | `download_pref = 2`, `minimum_price = 0.0`, `is_set_price` null | Noneohone UKG edit (`track_nyp_zero.html`); page says "or more" |
| NYP $X+ | `download_pref = 2`, `minimum_price > 0`, `is_set_price` null | Calibre "Even If", £1.50 (`track_nyp_min.html`) |
| fixed price | **unverified**: no fixed-price page found in ~30 sampled. Assumed `download_pref = 2` + truthy `is_set_price`, and no "or more" on the page | test uses the NYP page with the flag flipped |
| album-only | track page `download_pref = null`, `trackinfo[0].is_downloadable = false`, `album_url` set; the album page is buyable | Xtrica "SubFocus" → album "Fixated" NYP €0 (`track_subscriber_only.html`, `album_subscriber_only.html`) |
| not for sale | as album-only but no `album_url`, or an album page with `download_pref = null` | inferred, no example captured |

Every page sampled (Calibre, Four Tet, New Breed, many bootlegs) was NYP, so expect `nyp_min` to dominate and `paid` to be rare.

## Still open

- [ ] A real fixed-price page, to confirm `is_set_price`.
- [ ] A labeled set of 30–50 of *your* tracks (`tests/fixtures/labeled.json` has an 11-pair seed from this spike).
- [ ] Phase 5 linking key (cratesync): not looked at yet.

## Custom domains (2026-11-14)

Some labels serve Bandcamp from their own domain (e.g. `music.monstercat.com`). For non-browser clients that domain 303s to `<label>.bandcamp.com`, which 301s back, forever; a browser User-Agent gets one redirect and then a "Client Challenge" (bot check) page with no `data-tralbum`. The scout doesn't try to get past it: such candidates are skipped. Tracks only sold through those labels will show as `no_match`.
