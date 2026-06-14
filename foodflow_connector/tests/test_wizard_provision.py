from odoo.tests import TransactionCase, tagged
from odoo.exceptions import UserError


@tagged("post_install", "-at_install", "foodflow_connector")
class TestWizardProvision(TransactionCase):

    def setUp(self):
        super().setUp()
        self.Wizard = self.env["foodflow.setup.wizard"]

    def test_wizard_defaults(self):
        wiz = self.Wizard.create({})
        self.assertEqual(wiz.restaurant_name, "My Restaurant")
        self.assertEqual(wiz.table_count, 8)
        self.assertFalse(wiz.connector_enabled)
        self.assertTrue(wiz.create_pos)

    def test_action_test_requires_credentials(self):
        wiz = self.Wizard.create({"connector_enabled": True})
        with self.assertRaises(UserError):
            wiz.action_test()

    def test_provision_pos_restaurant_mode(self):
        wiz = self.Wizard.create({
            "restaurant_name": "Testaurant", "table_count": 5,
            "create_pos": True, "seed_sample": False, "connector_enabled": False})
        config = wiz._provision_pos()
        self.assertEqual(config.name, "Testaurant")
        self.assertTrue(config.module_pos_restaurant)
        names = config.payment_method_ids.mapped("name")
        self.assertIn("Cash", names)
        self.assertIn("Card", names)

    def test_provision_pos_is_idempotent(self):
        wiz = self.Wizard.create({
            "restaurant_name": "Dupe", "create_pos": True,
            "seed_sample": False, "connector_enabled": False})
        first = wiz._provision_pos()
        second = wiz._provision_pos()
        self.assertEqual(first, second)

    def test_provision_payment_methods_idempotent(self):
        wiz = self.Wizard.create({"connector_enabled": False})
        company = self.env.company
        first = wiz._provision_payment_methods(company)
        second = wiz._provision_payment_methods(company)
        self.assertEqual(first, second)
        self.assertEqual(
            set(first.mapped("name")), {"Cash", "Card"})

    def test_provision_floor_and_tables(self):
        wiz = self.Wizard.create({
            "restaurant_name": "Floorplan", "table_count": 6,
            "create_pos": True, "seed_sample": False, "connector_enabled": False})
        config = wiz._provision_pos()
        floor = wiz._provision_floor_tables(config)
        self.assertEqual(floor.name, "Main Floor")
        self.assertIn(config, floor.pos_config_ids)
        self.assertEqual(len(floor.table_ids), 6)

    def test_provision_floor_idempotent(self):
        wiz = self.Wizard.create({
            "restaurant_name": "FloorDupe", "table_count": 3,
            "create_pos": True, "seed_sample": False, "connector_enabled": False})
        config = wiz._provision_pos()
        first = wiz._provision_floor_tables(config)
        second = wiz._provision_floor_tables(config)
        self.assertEqual(first, second)
        self.assertEqual(len(first.table_ids), 3)

    def test_provision_floor_grows_and_numbers_contiguously(self):
        wiz = self.Wizard.create({
            "restaurant_name": "FloorGrow", "table_count": 2,
            "create_pos": True, "seed_sample": False, "connector_enabled": False})
        config = wiz._provision_pos()
        floor = wiz._provision_floor_tables(config)
        self.assertEqual(sorted(floor.table_ids.mapped("table_number")), [1, 2])
        wiz.table_count = 5
        floor = wiz._provision_floor_tables(config)
        self.assertEqual(len(floor.table_ids), 5)
        self.assertEqual(sorted(floor.table_ids.mapped("table_number")), [1, 2, 3, 4, 5])

    def test_mark_products_storable(self):
        prod = self.env["product.template"].create({
            "name": "Storable Burger", "available_in_pos": True,
            "type": "consu"})
        non_pos = self.env["product.template"].create({
            "name": "Backoffice Item", "available_in_pos": False,
            "type": "consu"})
        wiz = self.Wizard.create({"connector_enabled": False})
        result = wiz._mark_products_storable()
        prod.invalidate_recordset(["is_storable"])
        non_pos.invalidate_recordset(["is_storable"])
        self.assertTrue(prod.is_storable)
        self.assertIn(prod, result)
        self.assertNotIn(non_pos, result)
        self.assertFalse(non_pos.is_storable)

    def test_seed_starter_menu_when_empty(self):
        # Hide existing POS products so the catalog looks "empty" to the wizard.
        self.env["product.template"].search(
            [("available_in_pos", "=", True)]).write({"available_in_pos": False})
        wiz = self.Wizard.create({"seed_sample": True, "connector_enabled": False})
        seeded = wiz._seed_starter_menu()
        self.assertTrue(seeded)
        names = self.env["product.template"].search(
            [("available_in_pos", "=", True)]).mapped("name")
        self.assertIn("Classic Burger", names)

    def test_seed_starter_menu_skips_when_catalog_present(self):
        self.env["product.template"].create({
            "name": "Existing Dish", "available_in_pos": True, "type": "consu"})
        wiz = self.Wizard.create({"seed_sample": True, "connector_enabled": False})
        seeded = wiz._seed_starter_menu()
        self.assertFalse(seeded)

    def test_apply_standalone_no_connector(self):
        self.env["product.template"].search(
            [("available_in_pos", "=", True)]).write({"available_in_pos": False})
        # Snapshot pre-existing connector configs so the assertion is robust to
        # any config already present in the database (e.g. from manual setup).
        before = self.env["foodflow.config"].search(
            [("connector_enabled", "=", True)])
        wiz = self.Wizard.create({
            "restaurant_name": "Standalone", "table_count": 4,
            "create_pos": True, "seed_sample": True, "connector_enabled": False})
        result = wiz.action_apply()
        config = self.env["pos.config"].search([("name", "=", "Standalone")], limit=1)
        self.assertTrue(config)
        self.assertTrue(config.module_pos_restaurant)
        floor = self.env["restaurant.floor"].search(
            [("pos_config_ids", "in", config.id)], limit=1)
        self.assertEqual(len(floor.table_ids), 4)
        # The standalone apply must not activate any new connector config.
        after = self.env["foodflow.config"].search(
            [("connector_enabled", "=", True)])
        self.assertEqual(after, before)
        # action_apply returns an action dict (opens the cockpit).
        self.assertIsInstance(result, dict)

    def test_apply_with_connector_sets_flag(self):
        wiz = self.Wizard.create({
            "restaurant_name": "Online Resto", "table_count": 2,
            "create_pos": True, "seed_sample": False,
            "connector_enabled": True, "base_url": "http://x/api",
            "api_token": "tok", "import_menu": False})
        wiz.action_apply()
        cfg = self.env["foodflow.config"].search(
            [("base_url", "=", "http://x/api")], limit=1)
        self.assertTrue(cfg)
        self.assertTrue(cfg.connector_enabled)
