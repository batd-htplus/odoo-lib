# Database Schema — HTPlus APS/MES (Odoo 18 CE)

**Cập nhật 2026-08-10** — tách theo module mới (đồng bộ `05_core_framework_design.md`).
Mọi model có `id`, `create_date`, `write_date`, `create_uid`, `write_uid` do Odoo sinh. Bảng đánh
dấu **(+)** là mở rộng cột trên model Odoo có sẵn (`_inherit`).

> **Reservation — câu hỏi chặn (§5.1.1).** Cách ghi `mrp.workorder.date_start/date_finished` bằng
> `resource.calendar.leaves` hay model riêng **chưa chốt** — xem §1.1.1. Không dựng model mới trước
> khi xác minh trên Odoo 18.

---

## 1. htplus_factory — nền nhà máy (05 §2.2 tầng 1)

**Factory / Plant / Line / Workcenter / Machine** — 4 tầng: Factory → Plant → Line → Workcenter. Machine là thiết bị vật lý gắn workcenter.

```
htplus.factory          name | code | company_id | resource_calendar_id | holiday_ids O2M
htplus.plant            name | code | factory_id | company_id(related)
htplus.line             name | code | plant_id | factory_id(related, stored)
htplus.factory.holiday  name | factory_id | date_from | date_to | resource_leave_id

mrp.workcenter (+)      factory_id | plant_id | line_id | capacity | setup_time
                        | resource_calendar_id (mặc định kế thừa factory)
```

**Calendar & unavailability** — factory gắn `resource.calendar` (giờ làm việc). Factory holiday
**sync sang `resource.calendar.leaves`** — leaves là primitive bắt buộc cho unavailability
(nghỉ lễ, workcenter time-off, bảo trì). Không thay thế nó.

### 1.1.1 Reservation — lưu ở đâu? (chưa chốt)

| Kết quả xác minh trên Odoo 18 | Quyết định |
|---|---|
| `mrp.workorder` còn trỏ `resource.calendar.leaves` (`leave_id`), `_plan_workorders()` ghi leaves | APS ghi leaves theo **đúng cơ chế Odoo**, gắn `origin = schedule_run_id` để xoá/ghi lại sạch. Không dựng model mới |
| Odoo 18 không còn dùng leaves cho workorder | Dựng `htplus.capacity.reservation` (`schedule_run_id · version · workorder_id · resource/workcenter/machine · start/end`). Bộ giải tính: `available = working_time − unavailability − reservation` |

Ràng buộc chống chồng lấn: PostgreSQL `EXCLUDE USING gist (resource_id WITH =, tstzrange(start, end) WITH &&)` ở tầng DB khi Apply (§5.2.1).

## 2. htplus_workforce — ca & nhân lực

```
htplus.shift.template       name | code | shift_type(day/evening/night/overtime)
                            | start_time | end_time | break_minutes | day_of_week_start/end
                            | default_manpower | factory_id | plant_id | line_id
                            | resource_calendar_id | total_hours(computed)
htplus.production.shift     name | shift_template_id | start/end datetime | factory_id | plant_id | line_id
                            | workcenter_id | manpower_required | leader_id | state(draft/confirmed/completed/cancelled)
htplus.shift.member         employee_id | factory_id | plant_id | line_id | is_leader | skill_ids
htplus.shift.actual         shift_id | date | line_ids O2M | state(draft/in_progress/done/cancelled)
htplus.shift.actual.line    actual_id | line_id | qty_target/done/good/ng | downtime_minutes | achievement
htplus.shift.completion     shift_id | line_id | qty_done | overtime_minutes   (MES ↔ workforce)
htplus.workforce.assignment shift_id | workorder_id | employee_id | date_start/end | qty
                            | state(draft/confirmed/cancelled) | conflict | skill_match
```

**Quyền sở hữu `assignment` (§2.5.2):** `htplus_workforce` sở hữu assignment + tính đủ điều kiện
(skill/ca/xung đột). APS chỉ phát biểu **nhu cầu**; bridge `htplus_aps_workforce` dịch nhu cầu →
assignment. MES ghi **sự kiện thi hành**, không phải nguồn sự thật của phân công.

## 3. htplus_aps_core — Planning & Scheduling

```
htplus.demand.plan          name | state(draft/confirmed/approved/planned/cancelled)
                            | date_start/end | source(manual/import/forecast/ai) | line_ids O2M
htplus.demand.plan.line     plan_id | product_id | date | qty | uom_id | forecast_confidence
htplus.demand.plan.import.wizard   (import Excel)

htplus.production.plan      name | state(draft/confirmed/approved/locked/cancelled)
                            | demand_plan_id | date_start/end | line_ids O2M | production_ids O2M(mrp.production)
htplus.production.plan.line plan_id | demand_line_id | product_id | qty | date_deadline
                            | bom_id | priority | material_ok | capacity_ok

htplus.schedule.run         name | version | state(draft/calculated/confirmed/locked)
                            | production_plan_id | scenario_id | algorithm(manual/rule_engine/solver_cpsat)
                            | date_start/end | conflict_count | workorder_ids O2M(mrp.workorder)
htplus.schedule.change      schedule_run_id | workorder_id | field | old_value | new_value  (audit + undo field-level)

htplus.simulation.scenario  name | state(draft/computed/applied/cancelled) | base_schedule_run_id
                            | overtime_hours | capacity_change_pct | manpower_change_pct
                            | include_holiday | line_ids O2M
htplus.simulation.line      scenario_id | workorder_id | original_start/end | simulated_start/end | delay_hours

htplus.planning.rule        name | code | workcenter_ids M2M | capacity_limit_pct | buffer_before/after
                            | batch_size | max_concurrent | objective(min_makespan/min_tardiness/min_cost)
htplus.priority.rule        name | code | sequence | priority_field | weight
htplus.capacity.rule        name | workcenter_id | max_units_per_day | max_hours_per_day
htplus.planning.parameter   name | key(unique) | value | description
                            ⚠️ deprecated — trùng ir.config_parameter, sẽ bỏ (05 §3 nợ #1, P2 #19)

htplus.dashboard.kpi        (KPI tổng hợp)
```

**MRP extension** — lịch APS **chính là** `mrp.workorder`:

```
mrp.production (+)  htplus_plan_id | htplus_plan_line_id
mrp.workorder (+)   schedule_run_id | line_id | machine_id
                    date_start / date_finished  ← chỗ APS đặt lịch (xem §1.1.1, chưa chốt)
                    schedule_state(unscheduled/scheduled/confirmed/locked) | locked | priority
                    schedule_conflict | material_ok | capacity_ok | machine_ok
```

`schedule.run` là **ý định**, `mrp.workorder` là **thi hành** — bộ giải không ghi thẳng vào
workorder; tạo/cập nhật schedule run, duyệt rồi mới **Apply** (§5.1). Hoàn tác lịch = restore
version, không revert từng field.

## 4. htplus_mes_shopfloor — MES lite

```
htplus.workorder.actual    workorder_id | date_start/finished | employee_id | machine_id
                           | qty_done | qty_good | qty_ng | state(running/paused/finished)
htplus.downtime.reason     name | code | category(breakdown/setup/wait_material/wait_machine/wait_manpower/power/quality/other)
htplus.downtime            workorder_id | machine_id | reason_id | type(planned/unplanned)
                           | date_start/end | duration_minutes(computed) | cost
htplus.defect              name | code | category
htplus.workorder.ng        workorder_id | defect_id | date | qty | root_cause | countermeasure
htplus.machine.stop        machine_id | date_start/end | reason_id | type | duration_minutes | cost
htplus.issue               workorder_id | type(material/machine/manpower/quality/safety/other)
                           | severity(low/medium/high/critical) | state(open/in_progress/resolved/closed)
htplus.report.production.daily   (báo cáo theo ca/ngày)
```

MES ghi actual/downtime/NG rồi **đẩy vào `mrp.workcenter.productivity` của Odoo** — OEE tính từ
đó (tổng hợp theo factory/plant/line/machine/**ca** là phần HTPlus thêm, không tính lại từ đầu — 05 §7.1.1).
`_sync_productivity` hiện đang duplicate giữa actual và downtime — sẽ gom vào `htplus.mrp.bridge.mixin` (P3 #23).

## 5. Bridge tầng 3 (`auto_install`, chỉ `_inherit`)

| Bridge | Mở rộng |
|---|---|
| `htplus_factory_maintenance` | `htplus.machine.equipment_id` M2O → `maintenance.equipment` (HAS-A, **không** `_inherits` — 05 §4.5). Vòng bảo trì: request mở → hạ status máy → bộ giải tránh máy đang sửa |
| `htplus_workforce_skills` | `htplus.workforce.assignment._htplus_skill_ok_employee_ids()` — matching skill khi phân công |
| `htplus_mes_workforce` | `htplus.shift.completion` từ MES actual · ACL shift completion |
| `htplus_aps_workforce` | đề xuất phân công theo work order của `schedule.run` |
| `htplus_workforce_holidays` | nghỉ phép → khả dụng nhân lực |
| `htplus_aps_mes` | dashboard hợp APS+MES |

## 6. htplus_planning_bridge — engine client

```
htplus.planning.config      name | url | api_key | model | timeout_sec
htplus.planning.forecast    name | config_id | horizon_days | date_start/end | state(draft/computed/applied) | line_ids O2M
htplus.planning.forecast.line  forecast_id | product_id | date | qty | confidence
htplus.planning.chat        name | user_id | line_ids O2M
htplus.planning.chat.line   chat_id | role(user/assistant) | content | payload JSONB
htplus.planning.recommendation  type(schedule/assignment/bottleneck/delay/root_cause/demand)
                               | title | summary | explanation | payload JSONB | state(new/applied/dismissed)
htplus.planning.service     (cấu hình + gọi HTTP services/planning)
```

**Hợp đồng bộ giải (05 §5.3):** engine trả về `ScheduleResult` (assignments · unassigned · conflicts ·
objective · algorithm · explanation · metadata). `unassigned` + `explanation` là **bắt buộc** — bộ
giải trả ít hơn yêu cầu phải giải thích. Kết quả gắn `algorithm` đã dùng để UI hiển thị degraded mode.

## Quan hệ chính

```
demand.plan → line → production.plan → line → mrp.production → mrp.workorder
schedule.run → mrp.workorder (O2M, mrp.workorder là dòng lịch)
schedule.run → simulation.scenario → line
workforce.assignment → mrp.workorder / hr.employee / shift   (chủ sở hữu: htplus_workforce)
machine → equipment_id → maintenance.equipment (bridge)
machine → workcenter → line → plant → factory
```

## Ghi chú kỹ thuật

- Số lượng / thời lượng dùng `DECIMAL` (tránh float cộng dồn sai); timestamp lưu UTC.
- `htplus.schedule.change` phục vụ undo **mức field** + audit; hoàn tác lịch ở mức **version**
  (`schedule.run.version`) là chính (05 §5.1).
- Bảng AI dùng `payload JSONB` để linh hoạt, không cứng cột.
- **Index (05 §7.4 — điểm khởi đầu, phải `EXPLAIN ANALYZE` trên dữ liệu cỡ thật):**
  `(workorder_id, date_start)` trên actual/downtime · `(machine_id, date_start)` trên machine.stop ·
  `(date)` trên forecast.line · `(schedule_run_id, date_start)` và `(workcenter_id, date_start)` trên
  `mrp.workorder` · `factory_id` trên mọi model dùng scope mixin (§6.1).
- **Phân tách nhà máy** — chưa có `ir.rule` nào trong core (P0 #6): kế hoạch là field
  `factory_id` stored-computed (scope mixin) + `ir.rule` fail-closed +
  `group_htplus_all_factories`. Rỗng = không thấy nhà máy nào.
- **Migrations** — chưa module core nào có `migrations/` (P2 #15, bắt buộc từ phiên bản đầu).
