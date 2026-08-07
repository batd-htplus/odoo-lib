# Phản biện & Bổ sung chi tiết — 15 Module Nghiệp vụ APS/MES trên Odoo 18 CE

## 1. Đánh giá tổng quan

Cấu trúc 15 module nghiệp vụ của bạn là một phân tách theo **luồng nghiệp vụ (value stream)** hợp lý. Tuy nhiên khi map xuống Odoo cần đóng gói lại vì:

- Odoo CE 18 **không có Gantt view** (`web_gantt` là Enterprise). APS core + Gantt UI phải tự build (OWL component) hoặc dùng thư viện ngoài (dhtmlxGantt, frappe-gantt).
- **Không có thuật toán scheduling** trong Odoo → phải viết constraint engine, hoặc đẩy sang solver service (ORTools/CP-SAT).
- Một vài khái niệm cần có nhưng chưa xuất hiện trong 15 module: **BOM versioning**, **material check (stock reservation)**, **OEE measurement**, **maintenance**, **traceability (serial/lot)**.
- 15 module nghiệp vụ → **không nên** tạo 15 module Odoo (phình manifest/ACL). Gom thành 4 module code.

### Map module nghiệp vụ → module Odoo

| # | Nghiệp vụ | Module Odoo chịu trách nhiệm | Ghi chú |
|---|---|---|---|
| 1 | Dashboard | `htplus_aps_core` | Form + view tổng hợp; AI KPI từ `htplus_ai_bridge` |
| 2 | Demand Planning | `htplus_aps_core` | `htplus.demand.plan` (+ forecast từ AI) |
| 3 | Production Planning | `htplus_aps_core` | `htplus.production.plan` → `mrp.production` |
| 4 | Scheduling | `htplus_aps_core` | `htplus.schedule.run` + constraint engine |
| 5 | Gantt Scheduler | `htplus_aps_core` (assets OWL) | CE tự build; data model đã đủ |
| 6 | Simulation | `htplus_aps_core` | `htplus.simulation.scenario` |
| 7 | Shift Planning | `htplus_planning_base` | Shift template/pattern/holiday |
| 8 | Workforce Assignment | `htplus_aps_core` | `htplus.workforce.assignment` + skill |
| 9 | Shop Floor (MES lite) | `htplus_mes_shopfloor` | mở rộng `mrp.workorder` |
| 10 | Reports & Analytics | `htplus_aps_core` + `htplus_mes_shopfloor` | Report qweb/BI |
| 11 | AI Assistant | `htplus_ai_bridge` | Client gọi AI Service (FastAPI) |
| 12 | Workflow & Approval | xuyên suốt | `mail.thread` + state + groups |
| 13 | Master Data | `htplus_planning_base` | Factory/Plant/Line/Machine/Shift/Rule/Skill |
| 14 | System Admin | Odoo core | `res.users`, `res.groups`, `ir.config_parameter`, audit |
| 15 | Integration | `htplus_ai_bridge` + controllers | REST/JSON-RPC, import/export, cron |

## 2. Phản biện chi tiết từng module

### 2.1 Dashboard
- OK dùng Odoo dashboard; bổ sung **KPI chuẩn OEE** = Availability × Performance × Quality. Muốn vậy phải đo: `uptime`, `ideal cycle time`, `qty good` → bắt buộc có data từ Shop Floor.
- Thêm **drill-down**: Dashboard → Work Order → Actual (không chỉ hiển thị số).

### 2.2 Demand Planning
- **Phản biện**: "Import Excel" + "Demand Forecast (AI)" dễ lẫn 2 nguồn dữ liệu. Nên tách rõ `source` (manual/import/ai) trên từng line, để AI forecast có thể **overwrite có kiểm soát** (human-in-the-loop).
- Bổ sung: **BOM explosion** khi chuyển Demand → Production Plan (nhu cầu nguyên vật liệu tính từ BOM, không chỉ thành phẩm).
- Bổ sung: **ATP/date promise** (Available-to-Promise) nếu cần cam kết ngày giao.

### 2.3 Production Planning
- **Phản biện**: Odoo `mrp.production` sinh từ plan là đúng hướng, nhưng phải quyết định **Work Order = Operation hay theo lô**. Nên giữ `mrp.production` = lệnh sản xuất, `mrp.workorder` = operation-level; APS scheduling đặt lịch trên **workorder**.
- Bổ sung trường `bom_id` + `routing_id` mặc định từ `product.template` (hoặc field trên product), giảm thao tác tay.
- Bổ sung **capability check trước khi tạo workorder**: material check (stock quants), capacity check (workcenter load).

### 2.4 Scheduling (trái tim APS)
- **Phản biện mạnh nhất**: không thể viết scheduling bằng `@api.onchange` hay CRUD thuần Odoo cho quy mô thực tế. Kiến trúc đề xuất:
  - Lớp **constraint model** trong Odoo (capacity, shift, machine, material, precedence).
  - Lớp **solver** gọi AI Service (CP-SAT) hoặc engine nội bộ, trả về `planned_start/end` cho từng workorder.
  - **Human-in-the-loop**: solver đề xuất → planner duyệt → `lock`.
- Bắt buộc có **version + optimistic lock**: 2 planner chỉnh cùng lúc sẽ hỏng; cần `write_date` conflict check.
- Định nghĩa rõ objective function: Min makespan? Min tardiness? Min cost? (tham số trong `htplus.planning.rule`).

### 2.5 Gantt Scheduler
- CE không có `web_gantt` → chọn: (a) custom OWL Gantt, (b) embed thư viện. Data model dựng sẵn: `mrp.workorder.schedule_start/end`, `machine_id`, `locked`, `schedule_run_id`.
- Drag & drop, resize phải có **undo/revert** → mỗi thao tác tạo 1 `htplus.schedule.change` log (audit + undo).

### 2.6 Simulation
- Đúng là module riêng. Bổ sung: scenario phải **copy snapshot** của schedule gốc (không sửa trực tiếp schedule thật), so sánh KPI `total_delay`, `total_cost`, `utilization`.
- Bổ sung input: **machine down (from maintenance)**, **holiday**, **overtime**, **capacity/manpower change**, **cost multiplier**.

### 2.7 Shift Planning
- Odoo có `resource.calendar` + `resource.calendar.attendance`. Giải pháp: `htplus.shift.template` (Ca 1: 06-14) và `htplus.shift.pattern` (lịch tuần) — không nên tạo attendance thủ công từng ngày.
- Bổ sung **shift boundary**: workorder cắt qua nửa đêm phải chia theo ca (ảnh hưởng báo cáo năng suất).

### 2.8 Workforce Assignment
- Reuse skill từ `hr_skills` nếu có, không thì dựng `htplus.skill` + `htplus.employee.skill`.
- Bổ sung các luật validation: **OT validation** (giới hạn giờ OT theo luật lao động), **shift conflict** (1 employee không trùng 2 ca), **skill validation** (đủ kỹ năng cho operation của workorder).
- AI chỉ **gợi ý**, con người xác nhận — không auto-apply.

### 2.9 Shop Floor Execution (MES lite)
- Kế thừa `mrp.workorder` (đã có `date_start`, `date_finished`, `qty_done`...). Thêm bảng actual để lưu **lịch sử** (start/stop/continue), không ghi đè.
- Bổ sung các bảng: `htplus.downtime` (reason + duration + cost), `htplus.workorder.ng` (defect + qty + root cause + countermeasure), `htplus.machine.stop`, `htplus.issue`, `htplus.shift.completion`.
- **Phản biện**: cần quy tắc "1 workorder chỉ có 1 actual active tại 1 thời điểm" (state machine). Ngăn ghi đè công đoạn.

### 2.10 Reports & Analytics
- Định nghĩa KPI cố định để mọi báo cáo thống nhất: OEE, Utilization, Yield, Downtime %, On-Time Delivery (OTD), Schedule Adherence, Cycle Time.
- Báo cáo **theo shift** phải dựa trên `htplus.shift.completion` (không cộng giờ theo ngày tự nhiên).

### 2.11 AI Assistant
- Đúng — tách service. Các endpoint cần: forecast, schedule recommendation, auto assignment, bottleneck/delay prediction, root cause, chat, explain.
- Bắt buộc: **explainability** (mọi gợi ý kèm lý do), **degraded mode** khi AI down (dùng rule engine nội bộ), **audit** log gợi ý đã áp dụng/chưa.

### 2.12 Workflow & Approval
- Odoo CE không có module Approvals (Enterprise) → tự xây state machine + groups. Bổ sung: submit/approve/reject/confirm/lock, version, history, audit log.

### 2.13 Master Data
- Nhóm 6 nhóm con là đủ. Ghi chú: **Work Center** = năng lực xử lý, **Line** = nhóm workcenter theo dây chuyền, **Machine** = thiết bị vật lý gắn workcenter. Không gộp 3 khái niệm này.
- Bổ sung Planning Rule/Priority Rule/Capacity Rule/AI Parameter như master data (đã có trong bản).

### 2.14 System Administration
- Odoo đảm nhận: users, roles (groups), permissions (ir.model.access + record rules), companies, notifications (mail), settings (ir.config_parameter), backup (db + filestore), log (audit). Không cần module mới.

### 2.15 Integration
- REST API: Odoo 18 có controller sẵn cho JSON-RPC/XML-RPC; thêm controllers cho PLC/MES/WMS nếu cần.
- Import/Export: chuẩn hóa template CSV/Excel (demand import là ưu tiên 1).
- Scheduler: dùng cron Odoo cho sync + AI polling.

## 3. Các điểm xuyên suốt (cross-cutting) cần quyết định sớm

1. **Concurrency**: schedule bị 2 planner sửa cùng lúc → optimistic lock (`write_date` + conflict warning).
2. **Time zone & shift boundary**: quy ước lưu UTC, hiển thị theo TZ công ty; chia công đoạn theo ca.
3. **Versioning**: `schedule.run.version` + `locked`; không cho sửa version đã lock.
4. **Audit**: mọi thay đổi lịch/gợi ý AI phải có log.
5. **Security**: 3 role cơ bản — `APS User` (xem), `APS Planner` (lập lịch/CRUD), `APS Manager` (duyệt/lock), `MES Operator` (shop floor).
6. **Import/Export template chuẩn**: Demand Plan import là tính năng số 1 cần có.
7. **Degraded mode**: AI down → fallback rule engine + cảnh báo rõ ràng trên UI.

## 4. Kiến trúc module Odoo đề xuất (4 module)

```
htplus_planning_base    Master data: factory/plant/line/machine/workcenter,
                        shift template/pattern/holiday, planning/priority/capacity rule,
                        AI parameter, skill, employee skill, groups + menus gốc
        │ depends
        ▼
htplus_aps_core         demand.plan, production.plan, schedule.run (APS),
                        mrp.workorder extension, simulation.scenario, workforce.assignment,
                        gantt data model, dashboard
        │ depends
        ├───────────────────────────┐
        ▼                           ▼
htplus_mes_shopfloor    htplus_ai_bridge
workorder.actual,       ai.config, ai.forecast(.line), ai.chat(.line),
downtime, workorder.ng, ai.recommendation, REST controller,
machine.stop, issue,    client gọi FastAPI AI Service
shift.completion
```

Đây là cơ sở để thiết kế database schema (doc 02) và API AI (doc 03).
