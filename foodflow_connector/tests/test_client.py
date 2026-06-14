from unittest.mock import patch, MagicMock
from odoo.tests.common import TransactionCase, tagged
from odoo.addons.foodflow_connector.lib import client as ffc


def _resp(status=200, json_body=None, headers=None):
    m = MagicMock()
    m.status_code = status
    m.content = b"{}"
    m.json.return_value = json_body or {}
    m.headers = headers or {}
    return m


@tagged("foodflow_connector", "-at_install", "post_install")
class TestFoodFlowClient(TransactionCase):
    def setUp(self):
        super().setUp()
        self.client = ffc.FoodFlowClient("https://ff.test/api/pos/v1", "ff_live_abc")

    def test_auth_header_set(self):
        with patch.object(self.client._session, "request",
                          return_value=_resp(200, {"status": "ok"})) as req:
            self.client.health()
            _, kwargs = req.call_args
            self.assertEqual(kwargs["headers"]["Authorization"], "Bearer ff_live_abc")

    def test_paginate_concatenates_pages(self):
        big = [{"id": str(i)} for i in range(ffc.DEFAULT_PAGE)]
        pages = [_resp(200, {"data": big}), _resp(200, {"data": [{"id": "last"}]})]
        with patch.object(self.client._session, "request", side_effect=pages):
            items = self.client.list_categories()
            self.assertEqual(len(items), ffc.DEFAULT_PAGE + 1)
            self.assertEqual(items[-1]["id"], "last")

    def test_429_then_success_retries(self):
        seq = [_resp(429, {}, {"Retry-After": "0"}), _resp(200, {"status": "ok"})]
        with patch.object(self.client._session, "request", side_effect=seq):
            with patch("time.sleep"):
                self.assertEqual(self.client.health()["status"], "ok")

    def test_auth_error_raises(self):
        with patch.object(self.client._session, "request",
                          return_value=_resp(401, {"error": "bad token"})):
            with self.assertRaises(ffc.FoodFlowAuthError):
                self.client.list_items()
