import { registry } from "@web/core/registry";
import { HtplusGantt } from "./htplus_gantt";
import { useService } from "@web/core/utils/hooks";
import { Component } from "@odoo/owl";

registry.category("components").add("HtplusGantt", HtplusGantt);

class HtplusGanttClientAction extends Component {
    static template = "htplus_aps_core.HtplusGanttClientAction";
    static components = { HtplusGantt };
    static props = { workorders: { type: Array, optional: true } };

    setup() {
        this.actionService = useService("action");
    }

    openWorkorder(record) {
        this.actionService.doAction({
            type: "ir.actions.act_window",
            res_model: "mrp.workorder",
            res_id: record.id,
            view_mode: "form",
        });
    }
}

registry.category("actions").add("htplus_aps_core.gantt", HtplusGanttClientAction);
