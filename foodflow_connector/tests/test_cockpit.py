from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install", "foodflow_connector")
class TestCockpit(TransactionCase):

    def test_get_data_shape(self):
        data = self.env["foodflow.cockpit"].get_data()
        for key in ("today_sales", "open_orders", "tables_in_use",
                    "low_stock_count", "connector_enabled",
                    "foodflow_orders_today", "currency_symbol"):
            self.assertIn(key, data)
        self.assertIsInstance(data["today_sales"], float)
        self.assertIsInstance(data["open_orders"], int)
        self.assertIsInstance(data["connector_enabled"], bool)

    def test_get_data_chart_datasets(self):
        data = self.env["foodflow.cockpit"].get_data()
        for key in ("sales_trend", "top_items", "source_mix"):
            self.assertIn(key, data)
            self.assertIn("labels", data[key])
            self.assertIn("values", data[key])
            self.assertEqual(len(data[key]["labels"]), len(data[key]["values"]))
        # The 7-day trend always spans exactly seven day buckets.
        self.assertEqual(len(data["sales_trend"]["labels"]), 7)

    def test_get_data_connector_flag_reflects_config(self):
        self.env["foodflow.config"].search([]).write({"connector_enabled": False})
        self.assertFalse(
            self.env["foodflow.cockpit"].get_data()["connector_enabled"])
        self.env["foodflow.config"].create({
            "name": "C", "base_url": "http://x/api",
            "active": True, "connector_enabled": True})
        self.assertTrue(
            self.env["foodflow.cockpit"].get_data()["connector_enabled"])
