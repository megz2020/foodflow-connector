class FakeFoodFlowClient:
    """In-memory stand-in for FoodFlowClient used in unit tests (no network)."""

    def __init__(self, categories=None, items=None, orders=None):
        self._categories = categories or []
        self._items = items or []
        self._orders = orders or []
        self.created_orders = []
        self.status_updates = []
        self.upserted_items = []
        self.upserted_categories = []

    def health(self):
        return {"status": "ok"}

    def list_categories(self, include_inactive=False):
        return list(self._categories)

    def list_items(self, include_inactive=False):
        return list(self._items)

    def list_orders(self, since=None):
        return list(self._orders)

    def upsert_category(self, payload, ff_id=None):
        self.upserted_categories.append((ff_id, payload))
        return {"id": ff_id or "ff-new-cat", **payload,
                "updated_at": "2026-06-14T12:00:00Z"}

    def upsert_item(self, payload, ff_id=None):
        self.upserted_items.append((ff_id, payload))
        return {"id": ff_id or "ff-new-item", **payload,
                "updated_at": "2026-06-14T12:00:00Z"}

    def create_order(self, payload):
        self.created_orders.append(payload)
        return {"success": True, "order": {
            "id": "ff-order-1", "status": "pending",
            "updated_at": "2026-06-14T12:00:00Z"}}

    def update_order_status(self, ff_id, status, reason=None):
        self.status_updates.append((ff_id, status))
        return {"id": ff_id, "status": status}
