# Database Schema — HTPlus APS/MES (Odoo 18 CE)

Quy ước: mọi model đều có `id` (PK), `create_date`, `write_date`, `create_uid`, `write_uid` do Odoo sinh.
Bảng đầy đủ dạng `htplus.<tên>`; bảng extend (đánh dấu `+`) bổ sung cột vào bảng Odoo có sẵn.

## 1. htplus_planning_base — Master Data

### factory / plant / line / workcenter / machine
```
htplus.factory
  id PK | name | code | company_id FK

htplus.plant
  id PK | name | code | factory_id FK | company_id FK

htplus.line
  id PK | name | code | plant_id FK | factory_id FK(related) | shift_pattern_id FK
  | active

mrp.workcenter  (+)
  factory_id FK | plant_id FK | line_id FK(htplus.line)
  | capacity_per_hour DECIMAL | setup_time DECIMAL(giờ)

htplus.machine
  id PK | name | code | model | serial_no
  | workcenter_id FK(mrp.workcenter) | line_id FK(htplus.line) | plant_id FK
  | status ENUM(operational,standby,maintenance,down,retired)
  | capacity_per_hour DECIMAL | setup_time DECIMAL
  | active
```

### shift & calendar
```
htplus.shift.template         -- Ca làm việc (vd Ca1 06:00-14:00)
  id PK | name | code | start_time DECIMAL | end_time DECIMAL
  | total_hours DECIMAL(computed) | is_overtime BOOL | active

htplus.shift.pattern          -- Bộ ca cho 1 tuần (vd 3 ca)
  id PK | name | code | company_id FK | line_ids O2M | active

htplus.shift.pattern.line
  id PK | pattern_id FK | sequence INT | weekday ENUM(0..6)
  | template_id FK(htplus.shift.template)

htplus.holiday.calendar
  id PK | name | year INT | line_ids O2M | active

htplus.holiday.line
  id PK | calendar_id FK | date DATE | name | active
```

### planning / priority / capacity rule & AI parameter
```
htplus.planning.rule
  id PK | name | code | active
  | workcenter_ids M2M(mrp.workcenter)
  | capacity_limit_pct DECIMAL | buffer_before DECIMAL(giờ) | buffer_after DECIMAL(giờ)
  | batch_size INT | max_concurrent INT
  | objective ENUM(min_makespan,min_tardiness,min_cost)

htplus.priority.rule
  id PK | name | code | sequence INT | active
  | priority_field ENUM(date_deadline,customer_priority,order_priority,due_date)
  | weight DECIMAL

htplus.capacity.rule
  id PK | name | workcenter_id FK | max_units_per_day DECIMAL
  | max_hours_per_day DECIMAL | active

htplus.ai.parameter
  id PK | name | key UNIQUE | value | description | active
```

### skill
```
htplus.skill
  id PK | name | code | description | active

htplus.employee.skill
  id PK | employee_id FK(hr.employee) | skill_id FK(htplus.skill)
  | level ENUM(basic,intermediate,advanced,expert) | certified BOOL
  | last_assessed DATE | active
  | UK(employee_id, skill_id)
```

## 2. htplus_aps_core — Planning & Scheduling

### demand plan
```
htplus.demand.plan
  id PK | name | state ENUM(draft,confirmed,approved,planned,cancelled)
  | date_start DATE | date_end DATE | company_id FK | user_id FK
  | source ENUM(manual,import,forecast,ai)
  | ai_forecast_id FK(htplus.ai.forecast) | line_ids O2M
  | message_ids O2M(mail.message) | active

htplus.demand.plan.line
  id PK | plan_id FK | sequence INT | product_id FK(product.product)
  | date DATE | qty DECIMAL | uom_id FK(uom.uom)
  | forecast_confidence DECIMAL | remark | state
```

### production plan
```
htplus.production.plan
  id PK | name | state ENUM(draft,confirmed,approved,locked,cancelled)
  | demand_plan_id FK | date_start DATE | date_end DATE
  | line_ids O2M | production_ids O2M(mrp.production) | user_id FK

htplus.production.plan.line
  id PK | plan_id FK | demand_line_id FK | product_id FK
  | qty DECIMAL | uom_id FK | date_deadline DATE | bom_id FK(mrp.bom)
  | routing_id FK(mrp.routing) | priority INT | workcenter_ids M2M
  | material_ok BOOL | capacity_ok BOOL | state
```

### workorder (APS extension) — bảng mrp_workorder (+)
```
mrp.workorder  (+)
  schedule_run_id FK(htplus.schedule.run)
  line_id FK(htplus.line) | machine_id FK(htplus.machine)
  schedule_start TIMESTAMP | schedule_end TIMESTAMP
  schedule_state ENUM(unscheduled,scheduled,confirmed,locked)
  locked BOOL | priority INT | schedule_conflict BOOL
  material_ok BOOL | capacity_ok BOOL | machine_ok BOOL
```

### schedule run (APS version) + change log
```
htplus.schedule.run
  id PK | name | version INT | state ENUM(draft,calculated,confirmed,locked)
  | production_plan_id FK | scenario_id FK(htplus.simulation.scenario)
  | algorithm ENUM(manual,solver_cpsat,rule_engine)
  | date_start DATE | date_end DATE | conflict_count INT
  | workorder_ids O2M(mrp.workorder) | message_ids O2M | active

htplus.schedule.change           -- undo/revert + audit
  id PK | schedule_run_id FK | workorder_id FK | user_id FK
  | field ENUM(schedule_start,schedule_end,machine_id,line_id,priority)
  | old_value | new_value | date_change TIMESTAMP
```

### simulation
```
htplus.simulation.scenario
  id PK | name | state ENUM(draft,computed,applied,cancelled)
  | base_schedule_run_id FK | scenario_date DATE
  | overtime_hours DECIMAL | capacity_change_pct DECIMAL
  | manpower_change_pct DECIMAL | cost_multiplier DECIMAL
  | include_holiday BOOL | line_ids O2M
  | total_delay_hours DECIMAL | total_cost DECIMAL

htplus.simulation.line
  id PK | scenario_id FK | workorder_id FK | machine_id FK
  | original_start TIMESTAMP | original_end TIMESTAMP
  | simulated_start TIMESTAMP | simulated_end TIMESTAMP
  | delay_hours DECIMAL(computed) | cost DECIMAL
```

### workforce assignment
```
htplus.workforce.assignment
  id PK | name | workorder_id FK | employee_id FK(hr.employee)
  | shift_template_id FK | date_start TIMESTAMP | date_end TIMESTAMP
  | state ENUM(draft,confirmed,cancelled)
  | skill_ok BOOL | ot_ok BOOL | conflict BOOL
```

## 3. htplus_mes_shopfloor — MES lite

```
htplus.workorder.actual         -- history start/stop/continue
  id PK | workorder_id FK | date_start TIMESTAMP | date_finished TIMESTAMP
  | employee_id FK | machine_id FK | qty_done DECIMAL | qty_good DECIMAL | qty_ng DECIMAL
  | state ENUM(running,paused,finished)

htplus.downtime.reason
  id PK | name | code | category ENUM(breakdown,setup,wait_material,wait_machine,
    wait_manpower,power,quality,other) | active

htplus.downtime
  id PK | workorder_id FK | machine_id FK | reason_id FK(htplus.downtime.reason)
  | type ENUM(planned,unplanned) | date_start TIMESTAMP | date_end TIMESTAMP
  | duration_minutes DECIMAL(computed) | cost DECIMAL | employee_id FK

htplus.defect                         -- master mã lỗi NG
  id PK | name | code | category | active

htplus.workorder.ng
  id PK | workorder_id FK | defect_id FK(htplus.defect) | date TIMESTAMP
  | qty DECIMAL | root_cause | countermeasure | employee_id FK

htplus.machine.stop
  id PK | machine_id FK | date_start TIMESTAMP | date_end TIMESTAMP
  | reason_id FK(htplus.downtime.reason) | type ENUM(planned,unplanned)
  | duration_minutes DECIMAL(computed) | cost DECIMAL

htplus.issue
  id PK | name | workorder_id FK | type ENUM(material,machine,manpower,quality,safety,other)
  | severity ENUM(low,medium,high,critical) | state ENUM(open,in_progress,resolved,closed)
  | root_cause | countermeasure | employee_id FK | date TIMESTAMP

htplus.shift.completion
  id PK | workorder_id FK | shift_template_id FK | date DATE
  | qty_target DECIMAL | qty_done DECIMAL | qty_good DECIMAL | qty_ng DECIMAL
  | downtime_minutes DECIMAL | remarks
```

## 4. htplus_ai_bridge — AI Service

```
htplus.ai.config
  id PK | name | url | api_key | model | timeout_sec INT | active

htplus.ai.forecast
  id PK | name | config_id FK | model | horizon_days INT
  | date_start DATE | date_end DATE | product_ids M2M(product.product)
  | state ENUM(draft,computed,applied) | line_ids O2M

htplus.ai.forecast.line
  id PK | forecast_id FK | product_id FK | date DATE | qty DECIMAL
  | confidence DECIMAL | model

htplus.ai.chat
  id PK | name | user_id FK | config_id FK | line_ids O2M

htplus.ai.chat.line
  id PK | chat_id FK | role ENUM(user,assistant) | content TEXT
  | payload JSONB | created_at TIMESTAMP

htplus.ai.recommendation
  id PK | name | type ENUM(schedule,assignment,bottleneck,delay,root_cause,demand)
  | title | summary | explanation | payload JSONB | model
  | state ENUM(new,applied,dismissed) | source_workorder_id FK | source_plan_id FK
  | user_id FK
```

## 5. ERD tóm tắt

```
demand.plan ──O2M──> demand.plan.line ──O2M?──> production.plan
production.plan ──O2M──> production.plan.line ──O2M──> mrp.production ──O2M──> mrp.workorder(+)
schedule.run ──1──> O2M ── mrp.workorder(+)
schedule.run ──1──> base schedule ──O2M──> simulation.scenario ──O2M──> simulation.line
workforce.assignment ──> workorder / hr.employee / shift.template
workorder.actual ──> workorder / hr.employee / machine
downtime ──> workorder / machine / downtime.reason
workorder.ng ──> workorder / defect
machine.stop ──> machine / downtime.reason
issue ──> workorder
shift.completion ──> workorder / shift.template
ai.forecast ──O2M──> ai.forecast.line ──> product
ai.chat ──O2M──> ai.chat.line
ai.recommendation ──> workorder / plan
machine ──> workcenter ──> line ──> plant ──> factory
shift.pattern ──O2M──> pattern.line ──> shift.template
```

## 6. Ghi chú kỹ thuật

- Mọi `DECIMAL` về qty/duration: tránh float để cộng dồn đúng.
- Timestamp lưu UTC; shift boundary xử lý theo TZ company.
- `htplus.schedule.change` bắt buộc cho Gantt undo/revert.
- AI bảng dùng `payload JSONB` để linh hoạt, không cứng cột.
- Index nên thêm: `(workorder_id, date_start)` trên actual/downtime; `(date)` trên forecast.line; `(machine_id, date_start)` trên machine.stop.
