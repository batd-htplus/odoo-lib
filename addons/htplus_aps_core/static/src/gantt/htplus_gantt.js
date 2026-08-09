import { Component, onMounted, useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

const DAY_MS = 24 * 60 * 60 * 1000;

export class HtplusGantt extends Component {
    static template = "htplus_aps_core.HtplusGantt";
    static props = {
        workorders: { type: Array, optional: true },
        start: { type: String, optional: true },
        end: { type: String, optional: true },
    };

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.state = useState({
            rows: [],
            start: new Date(),
            end: new Date(Date.now() + 14 * DAY_MS),
            loading: true,
        });
        onMounted(() => this.load());
    }

    async load() {
        this.state.loading = true;
        try {
            const records = await this.orm.call(
                "mrp.workorder",
                "action_open_gantt",
                []
            );
            if (!records.length) {
                this.state.rows = [];
                return;
            }
            const min = new Date(Math.min(...records.map((r) => new Date(r.date_start))));
            const max = new Date(Math.max(...records.map((r) => new Date(r.date_finished))));
            this.state.start = new Date(min.getTime() - DAY_MS);
            this.state.end = new Date(max.getTime() + DAY_MS);
            this.state.rows = records.map((r) => ({
                id: r.id,
                resource_id: r.workcenter_id,
                workorder: r.workorder_ref,
                product: r.product_ref,
                start: new Date(r.date_start),
                end: new Date(r.date_finished),
                locked: r.locked,
                color: r.locked ? "#6b7280" : "#2563eb",
            }));
        } catch (error) {
            this.notification.add(`Không tải được dữ liệu Gantt: ${error.message}`, { type: "danger" });
        } finally {
            this.state.loading = false;
        }
    }

    gridLeft() {
        return this.state.start.toLocaleDateString("vi-VN");
    }
}
