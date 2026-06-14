from unittest.mock import patch
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install", "foodflow_connector")
class TestConnectorGate(TransactionCase):

    def setUp(self):
        super().setUp()
        self.Config = self.env["foodflow.config"]
        self.Sync = self.env["foodflow.sync"]
        # Remove any seeded active config so searches are deterministic.
        self.Config.search([]).write({"active": False})

    def test_connector_disabled_by_default(self):
        cfg = self.Config.create({"name": "T", "base_url": "http://x/api"})
        self.assertFalse(cfg.connector_enabled)

    def test_cron_skips_when_connector_disabled(self):
        self.Config.create({
            "name": "T", "base_url": "http://x/api",
            "active": True, "sync_enabled": True, "connector_enabled": False,
        })
        with patch.object(type(self.Sync), "_run_for") as run_for:
            self.Sync.cron_run()
        run_for.assert_not_called()

    def test_cron_runs_only_for_connector_enabled(self):
        enabled = self.Config.create({
            "name": "E", "base_url": "http://x/api", "api_token": "t",
            "active": True, "sync_enabled": True, "connector_enabled": True})
        with patch.object(type(self.Sync), "_run_for") as run_for:
            self.Sync.cron_run()
        run_for.assert_called_once()
        # cron_run calls self._run_for(cfg, directions, resources); since the
        # method is patched on the class, the first positional arg is the cfg.
        self.assertEqual(run_for.call_args.args[0], enabled)
