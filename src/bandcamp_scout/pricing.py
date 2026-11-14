"""Classify a Candidate's price. Field meanings are in docs/findings.md."""
FREE, PAID = 1, 2  # Bandcamp's own constants, published in every page's tralbum data


def classify(c) -> tuple[str, float | None]:
    """Returns (price_type, price). price_type is one of
    free, nyp_zero, nyp_min, paid, album_only, not_for_sale, unknown."""
    if c.download_pref == FREE:
        return "free", 0.0
    if c.download_pref == PAID:
        if c.is_set_price:
            return ("paid", c.set_price) if c.set_price is not None else ("unknown", None)
        if c.minimum_price is None:
            return "unknown", None
        return ("nyp_zero", 0.0) if c.minimum_price == 0 else ("nyp_min", c.minimum_price)
    if c.download_pref is None and c.item_type == "track" and c.downloadable is False:
        return ("album_only", None) if c.album_url else ("not_for_sale", None)
    if c.download_pref is None and c.item_type == "album":
        return "not_for_sale", None
    return "unknown", None


def label(price_type: str, price: float | None, currency: str | None) -> str:
    cur = f" {currency}" if currency else ""
    return {
        "free": "free",
        "nyp_zero": f"NYP 0{cur}+",
        "nyp_min": f"NYP {price}{cur}+",
        "paid": f"{price}{cur}",
    }.get(price_type, price_type)
