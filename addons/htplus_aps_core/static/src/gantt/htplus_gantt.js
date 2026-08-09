import { Component, onMounted, onWillUnmount, useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";

const DAY_MS = 24 * 60 * 60 * 1000;
const HALF_HOUR_MS = 30 * 60 * 1000;
const PX_PER_DAY = 60;

function parseUtc(iso) {
    if (!iso) return null;
    const [datePart, timePart = "00:00:00"] = iso.split("T");
    const [y, mo, d] = datePart.split("-").map(Number);
    const [h, mi, s] = timePart.split(":").map(Number);
    return new Date(Date.UTC(y, mo - 1, d, h, mi, s || 0));
}

function toUtcIso(date) {
    return date.toISOString().slice(0, 19);
}

function snap(value) {
    return Math.round(value / HALF_HOUR_MS) * HALF_HOUR_MS;
}

export class HtplusGantt extends Component {
    static template = "htplus_aps_core.HtplusGantt";
    static props = {
        workorders: { type: Array, optional: true },
        actionContext: { type: Object, optional: true },
    };

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.strings = {
            hint: _t("Drag to move, resize the edges, or drop on another line"),
            lineHeader: _t("Line / Work order"),
            reload: _t("Reload"),
            loading: _t("Loading…"),
            noData: _t("No dated work orders in this scope. Open from a Production Plan or Schedule Run, or Calculate first."),
            conflict: _t("Conflict"),
            locked: _t("%(product)s (locked)"),
            workorders: _t("%(count)s work order(s)"),
            loadError: _t("Unable to load Gantt data: %(message)s"),
            saved: _t("Schedule updated."),
            savedConflicts: _t("Saved. %(count)s work order conflict(s) remaining."),
            saveError: _t("Unable to save: %(message)s"),
        };
        this.state = useState({
            rows: [],
            start: null,
            end: null,
            loading: true,
        });
        this.drag = null;
        this._onPointerMove = this._onPointerMove.bind(this);
        this._onPointerUp = this._onPointerUp.bind(this);
        onMounted(() => this.load());
        onWillUnmount(() => this._endDrag());
    }

    async load() {
        this.state.loading = true;
        try {
            const context = this.props.actionContext || {};
            const data = await this.orm.call("mrp.workorder", "action_open_gantt", [], {
                context,
            });
            this._apply(data);
        } catch (error) {
            this.notification.add(
                _t(this.strings.loadError, { message: error.message }),
                { type: "danger" },
            );
        } finally {
            this.state.loading = false;
        }
    }

    _apply(data) {
        const start = parseUtc(data.start) || new Date();
        const end = parseUtc(data.end) || new Date(start.getTime() + 14 * DAY_MS);
        this.state.start = new Date(start.getTime() - DAY_MS);
        this.state.end = new Date(end.getTime() + DAY_MS);
        this.state.rows = (data.lines || []).map((line) => ({
            id: line.id,
            name: line.name,
            machine: line.machine,
            items: [],
        }));
        for (const wo of data.workorders || []) {
            const row = this.state.rows.find((r) => r.id === wo.line_id);
            const target = row || this.state.rows[this.state.rows.length - 1];
            if (!target) continue;
            target.items.push({
                id: wo.id,
                line_id: wo.line_id,
                workorder: wo.workorder_ref,
                product: wo.product_ref,
                workcenter: wo.workcenter_id,
                start: parseUtc(wo.date_start),
                end: parseUtc(wo.date_finished),
                locked: wo.locked,
                conflict: wo.conflict,
                write_date: wo.write_date,
            });
        }
    }

    axisWidth() {
        const days = Math.max(Math.round((this.state.end - this.state.start) / DAY_MS), 10);
        return Math.max(days * PX_PER_DAY, 600);
    }

    dayCells() {
        const cells = [];
        const cur = new Date(this.state.start);
        while (cur < this.state.end) {
            cells.push(new Date(cur));
            cur.setUTCDate(cur.getUTCDate() + 1);
        }
        return cells;
    }

    barLeft(item) {
        return ((item.start - this.state.start) / DAY_MS) * PX_PER_DAY;
    }

    barWidth(item) {
        return Math.max(((item.end - item.start) / DAY_MS) * PX_PER_DAY, PX_PER_DAY * 0.5);
    }

    barColor(item) {
        return item.locked ? "#6b7280" : item.conflict ? "#dc2626" : "#2563eb";
    }

    gridLeft() {
        return this.state.start ? this.fmtDay(this.state.start) : "";
    }

    fmtDay(date) {
        return `${date.getUTCDate()}/${date.getUTCMonth() + 1}`;
    }

    itemsLabel(row) {
        return _t(this.strings.workorders, { count: row.items.length });
    }

    barTitle(item) {
        return item.locked
            ? _t(this.strings.locked, { product: item.product })
            : item.product;
    }

    beginMove(ev, item) {
        if (!ev || item.locked) return;
        ev.stopPropagation();
        this._startDrag(ev, item, "move");
    }

    beginResizeLeft(ev, item) {
        if (!ev || item.locked) return;
        ev.stopPropagation();
        this._startDrag(ev, item, "resize-left");
    }

    beginResizeRight(ev, item) {
        if (!ev || item.locked) return;
        ev.stopPropagation();
        this._startDrag(ev, item, "resize-right");
    }

    _startDrag(ev, item, mode) {
        if (!ev || !item) return;
        ev.preventDefault();
        this.drag = {
            item,
            mode,
            startX: ev.clientX,
            origStart: item.start.getTime(),
            origEnd: item.end.getTime(),
            targetLineId: item.line_id,
        };
        document.addEventListener("pointermove", this._onPointerMove);
        document.addEventListener("pointerup", this._onPointerUp);
    }

    _onPointerMove(ev) {
        const drag = this.drag;
        if (!drag) return;
        const dx = Math.round(((ev.clientX - drag.startX) / PX_PER_DAY) * DAY_MS / HALF_HOUR_MS) * HALF_HOUR_MS;
        if (drag.mode === "move") {
            const newStart = snap(drag.origStart + dx);
            drag.item.start = new Date(newStart);
            drag.item.end = new Date(drag.origEnd + (newStart - drag.origStart));
            const el = document.elementFromPoint(ev.clientX, ev.clientY);
            const rowEl = el && el.closest(".o_htplus_gantt_row");
            const lineId = rowEl ? Number(rowEl.dataset.lineId) : drag.targetLineId;
            if (lineId !== drag.targetLineId) {
                this._moveItemToLine(drag.item, lineId);
                drag.targetLineId = lineId;
            }
        } else if (drag.mode === "resize-left") {
            drag.item.start = new Date(Math.min(snap(drag.origStart + dx), drag.origEnd - HALF_HOUR_MS));
        } else if (drag.mode === "resize-right") {
            drag.item.end = new Date(Math.max(snap(drag.origEnd + dx), drag.origStart + HALF_HOUR_MS));
        }
    }

    _moveItemToLine(item, lineId) {
        for (const row of this.state.rows) {
            const idx = row.items.findIndex((i) => i.id === item.id);
            if (idx >= 0) row.items.splice(idx, 1);
        }
        const target = this.state.rows.find((r) => r.id === lineId);
        if (target) {
            target.items.push(item);
            target.items.sort((a, b) => a.start - b.start);
        }
    }

    _onPointerUp() {
        const drag = this.drag;
        if (!drag) return;
        const moved = drag.item.start.getTime() !== drag.origStart || drag.item.end.getTime() !== drag.origEnd;
        const relined = drag.targetLineId !== drag.item.line_id;
        const item = drag.item;
        const targetLineId = drag.targetLineId;
        this._endDrag();
        if (moved || relined) {
            item.line_id = targetLineId;
            this._saveMove(item, targetLineId);
        }
    }

    _endDrag() {
        if (this.drag) {
            document.removeEventListener("pointermove", this._onPointerMove);
            document.removeEventListener("pointerup", this._onPointerUp);
            this.drag = null;
        }
    }

    async _saveMove(item, lineId) {
        const move = {
            id: item.id,
            date_start: toUtcIso(item.start),
            date_finished: toUtcIso(item.end),
            write_date: item.write_date,
            line_id: lineId || item.line_id || 0,
        };
        try {
            const context = this.props.actionContext || {};
            // RPC args: first positional arg must be a *list* of moves.
            const data = await this.orm.call(
                "mrp.workorder",
                "action_save_gantt_move",
                [[move]],
                { context },
            );
            const conflicted = data.conflicted || 0;
            this.notification.add(
                conflicted
                    ? _t(this.strings.savedConflicts, { count: conflicted })
                    : this.strings.saved,
                { type: conflicted ? "warning" : "success" },
            );
            this._apply(data);
        } catch (error) {
            this.notification.add(
                _t(this.strings.saveError, { message: error.message }),
                { type: "danger" },
            );
            this.load();
        }
    }
}
