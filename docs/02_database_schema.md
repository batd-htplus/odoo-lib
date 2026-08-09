# Database Schema — HTPlus APS/MES (Odoo 18 CE)

Mọi model đều có `id`, `create_date`, `write_date`, `create_uid`, `write_uid` do Odoo sinh. Bảng dạng `htplus.<tên>`; bảng đánh dấu **(+)** là mở rộng cột trên model Odoo có sẵn (`_inherit`).

## 1. htplus_planning_base — Master data

**Factory / Plant / Line / Workcenter / Machine** — 4 tầng: Factory → Plant → Line → Workcenter. Machine là thiết bị vật lý gắn workcenter.

```
htplus.factory          name | code | company_id | resource_calendar_id | holiday_ids O2M
htplus.plant            name | code | factory_id | company_id
htplus.line             name | code | plant_id | factory_id(related)
htplus.factory.holiday  name | factory_id | date_from | date_to | active

mrp.workcenter (+)      factory_id | plant_id | line_id | capacity_per_hour | setup_time

htplus.machine          name | code | model | serial_no | workcenter_id | line_id | plant_id
                        | status(operational/standby/maintenance/down/retired)
                        | capacity_per_hour | setup_time | active
```

**Shift & calendar** — ca làm việc; khi cần ảnh hưởng giờ làm của workcenter thì sync sang `resource.calendar.attendance` (ca cắt nửa đêm được tách thành 2 attendance).

```
htplus.shift.template       name | code | shift_type(day/evening/night/overtime)
                            | start_time | end_time | break_minutes | day_of_week_start/end
                            | default_manpower | factory_id | plant_id | line_id
                            | resource_calendar_id | total_hours(computed)
htplus.production.shift     name | shift_template_id | start/end datetime | line_id ...  (lịch ca cụ thể)
```

**Rule & tham số**

```
htplus.planning.rule        name | code | workcenter_ids M2M | capacity_limit_pct | buffer_before/after
                            | batch_size | max_concurrent | objective(min_makespan/min_tardiness/min_cost)
htplus.priority.rule        name | code | sequence | priority_field | weight
htplus.capacity.rule        name | workcenter_id | max_units_per_day | max_hours_per_day
htplus.planning.parameter   name | key(unique) | value | description
```

## 2. htplus_aps_core — Planning & Scheduling

```
htplus.demand.plan          name | state(draft/confirmed/approved/planned/cancelled)
                            | date_start/end | source(manual/import/forecast/ai) | line_ids O2M
htplus.demand.plan.line     plan_id | product_id | date | qty | uom_id | forecast_confidence
htplus.demand.plan.import.wizard   (import Excel)

htplus.production.plan      name | state(draft/confirmed/approved/locked/cancelled)
                            | demand_plan_id | date_start/end | line_ids O2M | production_ids O2M(mrp.production)
htplus.production.plan.line plan_id | demand_line_id | product_id | qty | date_deadline
                            | bom_id | priority | workcenter_ids M2M | material_ok | capacity_ok

htplus.schedule.run         name | version | state(draft/calculated/confirmed/locked)
                            | production_plan_id | scenario_id | algorithm(manual/rule_engine/solver_cpsat)
                            | date_start/end | conflict_count | workorder_ids O2M(mrp.workorder)
htplus.schedule.change      schedule_run_id | workorder_id | field | old_value | new_value  (audit + undo)

htplus.simulation.scenario  name | state(draft/computed/applied/cancelled) | base_schedule_run_id
                            | overtime_hours | capacity_change_pct | manpower_change_pct
                            | include_holiday | line_ids O2M
htplus.simulation.line      scenario_id | workorder_id | original_start/end | simulated_start/end | delay_hours

htplus.dashboard.kpi        (KPI tổng hợp)
```

**MRP extension** — lịch APS **chính là** `mrp.workorder` (xem `04_mrp_integration_decision.md`):

```
mrp.production (+)  htplus_plan_id | htplus_plan_line_id
mrp.workorder (+)   schedule_run_id | line_id | machine_id
                    date_start / date_finished  ← APS viết vào field Odoo (backed bởi resource.calendar.leaves)
                    schedule_state(unscheduled/scheduled/confirmed/locked) | locked | priority
                    schedule_conflict | material_ok | capacity_ok | machine_ok
```

## 3. htplus_mes_shopfloor — MES lite

```
htplus.workorder.actual    workorder_id | date_start/finished | employee_id | machine_id
                           | qty_done | qty_good | qty_ng | state(running/paused/finished)   (lịch sử start/stop/continue)
htplus.downtime.reason     name | code | category(breakdown/setup/wait_material/wait_machine/wait_manpower/power/quality/other)
htplus.downtime            workorder_id | machine_id | reason_id | type(planned/unplanned)
                           | date_start/end | duration_minutes(computed) | cost
htplus.defect              name | code | category                       (mã lỗi NG)
htplus.workorder.ng        workorder_id | defect_id | date | qty | root_cause | countermeasure
htplus.machine.stop        machine_id | date_start/end | reason_id | type | duration_minutes | cost
htplus.issue               workorder_id | type(material/machine/manpower/quality/safety/other)
                           | severity(low/medium/high/critical) | state(open/in_progress/resolved/closed)
htplus.report.production.daily   (báo cáo theo ca/ngày)
```

## 4. htplus_planning_bridge — Planning engine client

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

## Quan hệ chính

```
demand.plan → line → production.plan → line → mrp.production → mrp.workorder
schedule.run → mrp.workorder (O2M, mrp.workorder là dòng lịch)
schedule.run → simulation.scenario → line
workforce.assignment → mrp.workorder / hr.employee / shift
machine → workcenter → line → plant → factory
```

## Ghi chú kỹ thuật

- Số lượng / thời lượng dùng `DECIMAL` (tránh float cộng dồn sai); timestamp lưu UTC.
- `htplus.schedule.change` bắt buộc cho undo/revert trên Gantt.
- Bảng AI dùng `payload JSONB` để linh hoạt, không cứng cột.
- Nên thêm index: `(workorder_id, date_start)` trên actual/downtime; `(date)` trên forecast.line; `(machine_id, date_start)` trên machine.stop.
