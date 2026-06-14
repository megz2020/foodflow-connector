from unittest.mock import patch
from odoo.tests.common import TransactionCase, tagged
from .common import FakeFoodFlowClient


class _SyncCase(TransactionCase):
    def _cfg(self, fake):
        cfg = self.env["foodflow.config"].create({
            "base_url": "https://ff.test/api/pos/v1", "api_token": "ff_live_x"})
        p = patch.object(type(cfg), "get_client", return_value=fake)
        p.start()
        self.addCleanup(p.stop)
        return cfg


@tagged("foodflow_connector", "-at_install", "post_install")
class TestMenuPull(_SyncCase):
    def test_pull_creates_category_and_item(self):
        fake = FakeFoodFlowClient(
            categories=[{"id": "c1", "name": "Burgers", "display_order": 1,
                         "is_active": True, "updated_at": "2026-06-14T10:00:00Z"}],
            items=[{"id": "i1", "name": "Cheeseburger", "price": "85.00",
                    "category_id": "c1", "is_available": True, "is_active": True,
                    "updated_at": "2026-06-14T10:00:00Z"}])
        cfg = self._cfg(fake)
        self.env["foodflow.sync"]._pull_menu(cfg)
        cat = self.env["pos.category"].search([("foodflow_id", "=", "c1")])
        self.assertEqual(cat.name, "Burgers")
        prod = self.env["product.template"].search([("foodflow_id", "=", "i1")])
        self.assertEqual(prod.name, "Cheeseburger")
        self.assertEqual(prod.list_price, 85.0)
        self.assertTrue(prod.available_in_pos)

    def test_pull_skips_when_remote_not_newer(self):
        # Remote revision equals the one we last applied → no change.
        fake = FakeFoodFlowClient(
            categories=[{"id": "c1", "name": "OldName", "display_order": 1,
                         "is_active": True, "updated_at": "2026-01-01T00:00:00Z"}])
        cfg = self._cfg(fake)
        cat = self.env["pos.category"].create({
            "name": "LocalName", "foodflow_id": "c1",
            "foodflow_updated_at": "2026-01-01 00:00:00"})
        self.env["foodflow.sync"]._pull_menu(cfg)
        self.assertEqual(cat.name, "LocalName")

    def test_pull_applies_when_remote_is_newer(self):
        # A genuinely-newer remote revision must win, even though our own
        # write_date (just-created record) is "now" and far ahead of the
        # remote timestamp — proving we compare against foodflow_updated_at,
        # not write_date.
        fake = FakeFoodFlowClient(
            categories=[{"id": "c1", "name": "NewName", "display_order": 1,
                         "is_active": True, "updated_at": "2026-01-02T00:00:00Z"}])
        cfg = self._cfg(fake)
        cat = self.env["pos.category"].create({
            "name": "LocalName", "foodflow_id": "c1",
            "foodflow_updated_at": "2026-01-01 00:00:00"})
        self.env["foodflow.sync"]._pull_menu(cfg)
        self.assertEqual(cat.name, "NewName")


@tagged("foodflow_connector", "-at_install", "post_install")
class TestMenuPush(_SyncCase):
    def test_push_creates_new_item_on_foodflow(self):
        fake = FakeFoodFlowClient()
        cfg = self._cfg(fake)
        self.env["product.template"].create({
            "name": "Fries", "list_price": 30.0, "available_in_pos": True})
        self.env["foodflow.sync"]._push_menu(cfg)
        self.assertTrue(any(p["name"] == "Fries" for _, p in fake.upserted_items))

    def test_push_sets_external_and_ff_id(self):
        fake = FakeFoodFlowClient()
        cfg = self._cfg(fake)
        prod = self.env["product.template"].create({
            "name": "Cola", "list_price": 20.0, "available_in_pos": True})
        self.env["foodflow.sync"]._push_menu(cfg)
        self.assertTrue(prod.foodflow_id)
        self.assertTrue(prod.foodflow_external_id)
