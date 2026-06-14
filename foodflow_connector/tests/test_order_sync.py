from unittest.mock import patch
from odoo.tests.common import TransactionCase, tagged
from .common import FakeFoodFlowClient


class _OrderCase(TransactionCase):
    def _pos_config(self):
        pm = self.env["pos.payment.method"].create({"name": "Cash"})
        return self.env["pos.config"].create({
            "name": "FoodFlow POS", "payment_method_ids": [(6, 0, pm.ids)]})

    def _cfg(self, fake, pos_config=None):
        cfg = self.env["foodflow.config"].create({
            "base_url": "https://ff.test/api/pos/v1", "api_token": "ff_live_x",
            "pos_config_id": (pos_config or self._pos_config()).id})
        p = patch.object(type(cfg), "get_client", return_value=fake)
        p.start()
        self.addCleanup(p.stop)
        return cfg

    def _open_session(self, cfg):
        return self.env["foodflow.sync"]._ensure_pos_session(cfg)


@tagged("foodflow_connector", "-at_install", "post_install")
class TestOrderPull(_OrderCase):
    def test_pull_order_records_ff_id_and_status(self):
        fake = FakeFoodFlowClient(orders=[{
            "id": "o1", "external_id": "ext-1", "status": "preparing",
            "updated_at": "2026-06-14T10:00:00Z",
            "customer": {"name": "Sam", "phone": "+200"},
            "items": [], "total": "100.00", "currency": "EGP"}])
        cfg = self._cfg(fake)
        self.env["foodflow.sync"]._pull_orders(cfg)
        order = self.env["pos.order"].search([("foodflow_id", "=", "o1")])
        self.assertTrue(order)
        self.assertEqual(order.foodflow_status, "preparing")


@tagged("foodflow_connector", "-at_install", "post_install")
class TestOrderPush(_OrderCase):
    def test_push_new_order_calls_create(self):
        fake = FakeFoodFlowClient()
        cfg = self._cfg(fake)
        session = self._open_session(cfg)
        order = self.env["pos.order"].create({
            "session_id": session.id,
            "company_id": session.config_id.company_id.id,
            "amount_tax": 0.0, "amount_total": 0.0,
            "amount_paid": 0.0, "amount_return": 0.0,
        })
        self.env["foodflow.sync"]._push_orders(cfg)
        self.assertTrue(fake.created_orders)
        order.invalidate_recordset()
        self.assertTrue(order.foodflow_id)
