import time
import base64
import logging
import requests
from urllib.parse import urlparse

_logger = logging.getLogger(__name__)

DEFAULT_PAGE = 100
MAX_RETRIES = 4


class FoodFlowError(Exception):
    pass


class FoodFlowAuthError(FoodFlowError):
    pass


class FoodFlowRateLimit(FoodFlowError):
    pass


class FoodFlowApiError(FoodFlowError):
    def __init__(self, status, body):
        self.status = status
        self.body = body
        super().__init__(f"FoodFlow API {status}: {body}")


class FoodFlowClient:
    """Plain-Python wrapper over the FoodFlow POS API. No Odoo ORM here."""

    def __init__(self, base_url, token, timeout=30):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = timeout
        self._session = requests.Session()

    # ── core request with retry/backoff ──────────────────────────────────
    def _request(self, method, path, params=None, json=None):
        url = f"{self.base_url}{path}"
        headers = {"Authorization": f"Bearer {self.token}",
                   "Content-Type": "application/json"}
        for attempt in range(MAX_RETRIES):
            resp = self._session.request(method, url, params=params, json=json,
                                         headers=headers, timeout=self.timeout)
            if resp.status_code == 429:
                wait = float(resp.headers.get("Retry-After", 2 ** attempt))
                _logger.warning("FoodFlow 429; backoff %ss", wait)
                time.sleep(wait)
                continue
            if resp.status_code in (401, 403):
                raise FoodFlowAuthError(resp.json() if resp.content else {})
            if resp.status_code >= 400:
                raise FoodFlowApiError(resp.status_code,
                                       resp.json() if resp.content else {})
            return resp.json() if resp.content else {}
        raise FoodFlowRateLimit("exhausted retries on 429")

    @staticmethod
    def _extract_list(body):
        """Pull the collection out of a paginated body regardless of its key.

        FoodFlow returns the page under a resource-specific key
        (`items` for menu, `orders` for orders, sometimes `data`)."""
        if isinstance(body, list):
            return body
        for key in ("data", "items", "orders", "categories", "results"):
            val = body.get(key)
            if isinstance(val, list):
                return val
        # Fallback: first list-valued field in the body.
        for val in body.values():
            if isinstance(val, list):
                return val
        return []

    def _paginate(self, path, params=None):
        params = dict(params or {})
        offset, out = 0, []
        while True:
            params.update({"limit": DEFAULT_PAGE, "offset": offset})
            body = self._request("GET", path, params=params)
            batch = self._extract_list(body)
            out.extend(batch)
            if len(batch) < DEFAULT_PAGE:
                return out
            offset += DEFAULT_PAGE

    # ── image download ────────────────────────────────────────────────────
    @property
    def origin(self):
        """Scheme+host of the platform, derived from base_url.

        base_url `http://host:5173/api/pos/v1` → origin `http://host:5173`."""
        p = urlparse(self.base_url)
        return f"{p.scheme}://{p.netloc}"

    def fetch_image_b64(self, image_url):
        """Download an item image and return base64 (or None on any failure).

        Absolute URLs are fetched as-is; relative paths (e.g. `/images/...`)
        are resolved against the platform origin. Image fetches are best-effort
        — a failure must never abort a menu sync."""
        if not image_url:
            return None
        url = image_url if image_url.startswith(("http://", "https://")) \
            else f"{self.origin}{image_url}"
        try:
            resp = self._session.get(url, timeout=self.timeout)
            if resp.status_code != 200 or not resp.content:
                _logger.warning("FoodFlow image %s -> HTTP %s", url, resp.status_code)
                return None
            return base64.b64encode(resp.content).decode()
        except requests.RequestException as e:
            _logger.warning("FoodFlow image %s failed: %s", url, e)
            return None

    # ── public API ───────────────────────────────────────────────────────
    def health(self):
        return self._request("GET", "/health")

    def list_categories(self, include_inactive=False):
        return self._paginate("/menu/categories",
                              {"includeInactive": str(include_inactive).lower()})

    def upsert_category(self, payload, ff_id=None):
        if ff_id:
            return self._request("PATCH", f"/menu/categories/{ff_id}", json=payload)
        return self._request("POST", "/menu/categories", json=payload)

    def list_items(self, include_inactive=False):
        return self._paginate("/menu/items",
                              {"includeInactive": str(include_inactive).lower()})

    def upsert_item(self, payload, ff_id=None):
        if ff_id:
            return self._request("PATCH", f"/menu/items/{ff_id}", json=payload)
        return self._request("POST", "/menu/items", json=payload)

    def set_item_availability(self, ff_id, is_available):
        return self._request("PATCH", f"/menu/items/{ff_id}/availability",
                            json={"isAvailable": is_available})

    def list_combos(self):
        return self._paginate("/menu/combos")

    def list_orders(self, since=None):
        params = {"since": since} if since else {}
        return self._paginate("/orders", params)

    def create_order(self, payload):
        return self._request("POST", "/orders", json=payload)

    def update_order_status(self, ff_id, status, reason=None):
        body = {"status": status}
        if reason:
            body["reason"] = reason
        return self._request("PATCH", f"/orders/{ff_id}/status", json=body)
