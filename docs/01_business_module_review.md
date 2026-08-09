# Kiến trúc module — 15 nghiệp vụ APS/MES trên Odoo 18 CE

Hệ thống gồm 15 nhóm nghiệp vụ, triển khai thành **4 module code** (không tách 15 module — tránh phình manifest/ACL). Lý do gom:

- Odoo CE **không có Gantt** (`web_gantt` là Enterprise) → cần view thay thế (`web_timeline`).
- Odoo **không có thuật toán scheduling** → phải tự viết rule engine hoặc gọi solver (OR-Tools CP-SAT).
- Còn thiếu nếu cần mở rộng: BOM versioning, material check (stock), OEE, maintenance, traceability (serial/lot).

## Map nghiệp vụ → module

| Nghiệp vụ | Module | Ghi chú |
|---|---|---|
| Master data: factory/plant/line/machine, shift, rule, skill | `htplus_planning_base` | Nền tảng, các module khác đều phụ thuộc |
| Demand/Production planning, Scheduling, Simulation, Workforce, Dashboard | `htplus_aps_core` | Trái tim APS |
| Shop floor (MES lite): actual, downtime, NG, machine stop, issue | `htplus_mes_shopfloor` | Kế thừa `mrp.workorder` |
| Planning engine (FastAPI): forecast, recommend, chat | `htplus_planning_bridge` | Client gọi `services/planning` qua HTTP |
| Gantt UI (spike) | `htplus_timeline_spike` | Dùng `web_timeline` (AGPL) — chỉ module view này được phụ thuộc |
| Menu nhanh | `htplus_menu` | Bookmark |

## Cây module

```
htplus_planning_base
      ▼ depends
htplus_aps_core
      ├── htplus_mes_shopfloor
      └── htplus_planning_bridge  ──HTTP──> services/planning (FastAPI)
```

## Quyết định quan trọng

- **Scheduling**: không viết bằng `@api.onchange`/CRUD thuần. Odoo giữ constraint + state; solver (CP-SAT) trả về `date_start/date_finished`; planner duyệt rồi `locked`. Có optimistic lock chống 2 planner sửa cùng lúc.
- **Work Order = dòng lịch**: kế thừa `mrp.workorder` làm lịch APS, hưởng sẵn BOM, routing, stock moves, luồng MES. Chi tiết ở `04_mrp_integration_decision.md`.
- **Shift**: tự định nghĩa `htplus.shift.template`; khi cần ảnh hưởng giờ làm việc workcenter thì nối sang `resource.calendar.attendance`.
- **AI chỉ gợi ý**: mọi gợi ý kèm lý do, con người duyệt. AI down → fallback rule engine + cảnh báo rõ trên UI.
- **MES**: 1 workorder chỉ có 1 actual active tại 1 thời điểm; lưu lịch sử start/stop/continue, không ghi đè.

## Vấn đề xuyên suốt

1. **Concurrency** — optimistic lock (`write_date` + cảnh báo conflict).
2. **Thời gian & ca** — lưu UTC, hiển thị theo TZ công ty; công đoạn cắt nửa đêm chia theo ca.
3. **Versioning** — `schedule.run.version` + `locked`; version đã lock không sửa.
4. **Audit** — mọi thay đổi lịch / gợi ý AI có log.
5. **Phân quyền** — APS User (xem) / APS Planner (lập lịch) / APS Manager (duyệt, lock) / MES Operator (shop floor).
6. **Degraded mode** — AI down → rule engine + cảnh báo UI.

Chi tiết schema DB: `02_database_schema.md`. Nguyên tắc kỹ thuật: `03_engine.md`.
