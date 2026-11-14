"""One polite HTTP client: ~1 req/s with jitter, retries on 429/5xx, identifying User-Agent."""
import random
import time

import httpx

USER_AGENT = "bandcamp-scout/0.1 (+https://github.com/druppin/bandcamp-scout)"


class Client:
    def __init__(self, delay=1.0, jitter=0.3, retries=3, timeout=15.0, sleep=time.sleep, transport=None):
        self.delay, self.jitter, self.retries, self.sleep = delay, jitter, retries, sleep
        self._http = httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=timeout,
                                  follow_redirects=True, transport=transport)
        self._last = 0.0

    def request(self, method, url, **kw) -> httpx.Response:
        for attempt in range(self.retries + 1):
            wait = self._last + self.delay + random.uniform(0, self.jitter) - time.monotonic()
            if wait > 0:
                self.sleep(wait)
            try:
                r = self._http.request(method, url, **kw)
            except httpx.TransportError:
                if attempt == self.retries:
                    raise
                self.sleep(2 ** (attempt + 1))
                continue
            finally:
                self._last = time.monotonic()
            if r.status_code == 429 or r.status_code >= 500:
                if attempt == self.retries:
                    r.raise_for_status()
                retry_after = r.headers.get("Retry-After", "")
                self.sleep(float(retry_after) if retry_after.isdigit() else 2 ** (attempt + 1))
                continue
            r.raise_for_status()
            return r
        raise AssertionError("unreachable")

    def get(self, url, **kw):
        return self.request("GET", url, **kw)

    def post(self, url, **kw):
        return self.request("POST", url, **kw)
