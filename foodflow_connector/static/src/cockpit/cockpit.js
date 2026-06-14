/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { loadJS } from "@web/core/assets";
import {
    Component, onWillStart, onWillUnmount, useEffect, useRef, useState,
} from "@odoo/owl";

const FF_RED = "#e31e24";
const FF_GREEN = "#16a34a";
const FF_AMBER = "#f59e0b";
const FF_GREY = "#cbd5e1";

export class FoodFlowCockpit extends Component {
    static template = "foodflow_connector.Cockpit";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.trendCanvas = useRef("trendCanvas");
        this.itemsCanvas = useRef("itemsCanvas");
        this.sourceCanvas = useRef("sourceCanvas");
        this._charts = [];
        this.state = useState({
            loading: true,
            data: {
                today_sales: 0,
                open_orders: 0,
                tables_in_use: 0,
                low_stock_count: 0,
                connector_enabled: false,
                foodflow_orders_today: 0,
                currency_symbol: "",
                sales_trend: { labels: [], values: [] },
                top_items: { labels: [], values: [] },
                source_mix: { labels: [], values: [] },
            },
        });
        onWillStart(async () => {
            // Chart.js ships with Odoo's web bundle assets.
            await loadJS("/web/static/lib/Chart/Chart.js");
            await this.load();
        });
        // Render charts AFTER the DOM is patched. Keying on loading+data means
        // a Refresh (which briefly toggles loading and swaps in a new data
        // object) re-runs this once the canvases are back in the DOM — so the
        // charts never bind to a detached/missing canvas and disappear.
        useEffect(
            () => {
                this.renderCharts();
            },
            () => [this.state.loading, this.state.data],
        );
        onWillUnmount(() => this.destroyCharts());
    }

    async load() {
        this.state.loading = true;
        try {
            this.state.data = await this.orm.call(
                "foodflow.cockpit", "get_data", []);
        } finally {
            // Always drop the spinner: on error the dashboard renders with its
            // default zero-state rather than failing to mount entirely.
            this.state.loading = false;
        }
    }

    destroyCharts() {
        this._charts.forEach((c) => c.destroy());
        this._charts = [];
    }

    renderCharts() {
        if (typeof Chart === "undefined") {
            return;
        }
        this.destroyCharts();
        const cur = this.state.data.currency_symbol || "";
        const trend = this.state.data.sales_trend || { labels: [], values: [] };
        const items = this.state.data.top_items || { labels: [], values: [] };
        const source = this.state.data.source_mix || { labels: [], values: [] };

        // 7-day sales trend — smooth area line in brand red.
        if (this.trendCanvas.el) {
            const ctx = this.trendCanvas.el.getContext("2d");
            const grad = ctx.createLinearGradient(0, 0, 0, 220);
            grad.addColorStop(0, "rgba(227, 30, 36, 0.28)");
            grad.addColorStop(1, "rgba(227, 30, 36, 0.00)");
            this._charts.push(new Chart(ctx, {
                type: "line",
                data: {
                    labels: trend.labels,
                    datasets: [{
                        data: trend.values,
                        borderColor: FF_RED,
                        backgroundColor: grad,
                        borderWidth: 3,
                        fill: true,
                        tension: 0.4,
                        pointBackgroundColor: FF_RED,
                        pointRadius: 4,
                        pointHoverRadius: 6,
                    }],
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: { display: false },
                        tooltip: {
                            callbacks: {
                                label: (c) => `${cur}${Number(c.parsed.y).toFixed(2)}`,
                            },
                        },
                    },
                    scales: {
                        y: {
                            beginAtZero: true,
                            ticks: { callback: (v) => `${cur}${v}` },
                            grid: { color: "rgba(0,0,0,0.05)" },
                        },
                        x: { grid: { display: false } },
                    },
                },
            }));
        }

        // Top items — horizontal bars.
        if (this.itemsCanvas.el) {
            this._charts.push(new Chart(this.itemsCanvas.el, {
                type: "bar",
                data: {
                    labels: items.labels,
                    datasets: [{
                        data: items.values,
                        backgroundColor: FF_RED,
                        borderRadius: 6,
                        barThickness: 18,
                    }],
                },
                options: {
                    indexAxis: "y",
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: { legend: { display: false } },
                    scales: {
                        x: { beginAtZero: true, grid: { color: "rgba(0,0,0,0.05)" } },
                        y: { grid: { display: false } },
                    },
                },
            }));
        }

        // Order source mix — doughnut (only meaningful when connector is on).
        if (this.sourceCanvas.el) {
            this._charts.push(new Chart(this.sourceCanvas.el, {
                type: "doughnut",
                data: {
                    labels: source.labels,
                    datasets: [{
                        data: source.values,
                        backgroundColor: [FF_GREY, FF_GREEN],
                        borderWidth: 0,
                    }],
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    cutout: "62%",
                    plugins: { legend: { position: "bottom" } },
                },
            }));
        }
    }

    openAction(xmlId) {
        return this.action.doAction(xmlId);
    }

    openRegister() {
        return this.action.doAction("point_of_sale.action_client_pos_menu");
    }

    async refresh() {
        // Charts re-render via the useEffect keyed on state.data/loading once
        // the reloaded data lands and the DOM is patched.
        await this.load();
    }
}

registry.category("actions").add("foodflow_cockpit", FoodFlowCockpit);
