{
    "name": "FoodFlow Connector",
    "version": "19.0.1.0.0",
    "summary": "One-click restaurant POS setup + two-way menu & order sync with foodflo.app",
    "description": """
FoodFlow Connector — run your whole restaurant from one screen
==============================================================

Turnkey restaurant management for Odoo, with a live dashboard and two-way
synchronisation between Odoo Point of Sale and your foodflo.app online store.

Key features
------------
* **One-click setup wizard** — provisions a POS, dining floor, tables, payment
  methods and a starter menu (idempotent, safe to re-run).
* **Bidirectional sync with foodflo.app** — push your menu to the web and pull
  online orders back into Odoo POS automatically. One menu, one order stream for
  dine-in and online.
* **Real-time Restaurant Cockpit** — today's sales, open orders, tables in use,
  low-stock alerts and online orders, with a 7-day sales trend, top-selling
  items and an in-house vs. online order-source breakdown.
* **Connection testing & sync logs** — validate your API connection and audit
  every sync.
* **Free to install** (resale/redistribution is not permitted — OPL-1).

The POS and cockpit features work standalone; a foodflo.app account is only
required for online synchronisation.
""",
    "category": "Point of Sale",
    "license": "OPL-1",
    "author": "FoodFlow",
    "maintainer": "FoodFlow",
    "website": "https://foodflo.app",
    "support": "support@foodflo.app",
    "price": 0.0,
    "currency": "EUR",
    "depends": ["point_of_sale", "pos_restaurant"],
    "data": [
        "security/foodflow_security.xml",
        "security/ir.model.access.csv",
        "views/foodflow_config_views.xml",
        "views/foodflow_sync_log_views.xml",
        "wizard/foodflow_setup_wizard_views.xml",
        "data/ir_cron.xml",
        "data/starter_menu.xml",
        "views/cockpit_views.xml",
        "views/menu.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "foodflow_connector/static/src/cockpit/cockpit.scss",
            "foodflow_connector/static/src/cockpit/cockpit.js",
            "foodflow_connector/static/src/cockpit/cockpit.xml",
        ],
    },
    "images": [
        "static/description/banner.png",
        "static/description/cockpit_dashboard.png",
        "static/description/setup_wizard.png",
        "static/description/foodflow_platform.png",
    ],
    "application": True,
    "installable": True,
}
