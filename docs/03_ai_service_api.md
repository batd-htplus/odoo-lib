# AI Service — Kiến trúc, API & Database (FastAPI)

## 1. Vị trí trong hệ thống

```
Odoo 18 CE (htplus_ai_bridge)  ◄──JSON-RPC/REST──►  AI Service (FastAPI)  ◄──►  PostgreSQL (AI DB)
        ▲                                                      │
        └── poll kết quả / nhận webhook ────────────────────────┘
```

- AI Service chạy riêng (container riêng), **không phụ thuộc Odoo** để forecast/schedule.
- Odoo gọi qua REST, kèm `X-API-Key` + `X-Company-Id`.
- AI Service đọc dữ liệu đầu vào qua **API của Odoo** (pull) hoặc nhận **payload đóng gói** (push) — khuyến nghị push để AI service không cần biết mô hình Odoo.
- Khi AI down → Odoo fallback rule engine + đánh dấu `degraded` trên UI.

## 2. Nguồn dữ liệu cho AI

AI Service có DB riêng và được **sync** từ Odoo (queue-based, qua cron Odoo 15 phút / lần):
- Demand history (sales + demand plan line đã xác nhận).
- Work order lịch sử: start/end thực tế, machine, workcenter, qty.
- Downtime/NG/Issue lịch sử.
- Holiday calendar, shift pattern, capacity rule.

## 3. Database (PostgreSQL riêng) — `ai`

```
ai.job
  id BIGSERIAL PK | job_type ENUM(forecast,schedule,assign,bottleneck,delay,root_cause,chat)
  | status ENUM(pending,running,success,failed) | params JSONB | result JSONB
  | error TEXT | created_at TIMESTAMPTZ | finished_at TIMESTAMPTZ | company_id BIGINT

ai.forecast_result
  id PK | product_id BIGINT | forecast_date DATE | qty NUMERIC | confidence NUMERIC
  | model TEXT | horizon_days INT | job_id FK | created_at TIMESTAMPTZ

ai.schedule_result
  id PK | job_id FK | workorder_id BIGINT | workcenter_id BIGINT | machine_id BIGINT
  | schedule_start TIMESTAMPTZ | schedule_end TIMESTAMPTZ | priority INT
  | conflict BOOL | delay_hours NUMERIC | score NUMERIC

ai.assignment_result
  id PK | job_id FK | workorder_id BIGINT | employee_id BIGINT | score NUMERIC
  | skill_ok BOOL | ot_ok BOOL | shift_conflict BOOL | reason TEXT

ai.bottleneck_result
  id PK | job_id FK | workcenter_id BIGINT | machine_id BIGINT | score NUMERIC
  | factor_type TEXT | period DATE | detail JSONB

ai.chat_history
  id PK | session_id TEXT | role ENUM(user,assistant) | content TEXT
  | payload JSONB | created_at TIMESTAMPTZ

ai.audit_log
  id PK | job_id FK | user_id BIGINT | action TEXT | applied BOOL | created_at TIMESTAMPTZ
```

## 4. API Endpoints (REST, prefix `/api/v1`)

Auth: `Authorization: Bearer <api_key>` (config trong `htplus.ai.config`). Mọi response dùng schema thống nhất:

```
{ "success": true, "data": {...}, "error": null }
```

### 4.1 Forecast — Demand Forecast
`POST /api/v1/forecast`
```json
{
  "company_id": 1,
  "product_ids": [10, 11],
  "horizon_days": 90,
  "granularity": "day",
  "history": {"date": "2026-08-01", "product_id": 10, "qty": 120}
}
```
`200` → `{ "forecast_id": "job-uuid", "lines": [{"product_id":10,"date":"2026-09-01","qty":118.4,"confidence":0.87}] }`

### 4.2 Schedule Recommendation
`POST /api/v1/schedule/recommend`
```json
{
  "workorders": [{"workorder_id":100,"product_id":10,"qty":500,"routing":[10,11],"due":"2026-09-05T18:00:00Z"}],
  "constraints": {"workcenters":[...],"machines":[...],"shifts":[...],"holidays":[...],"rules":{...}},
  "objective": "min_tardiness",
  "lock_workorder_ids": [101]
}
```
`200` → `{ "schedule_result": [{... ai.schedule_result ...}], "kpi": {"makespan":120,"tardiness":5.2,"utilization":0.83} }`

### 4.3 Auto Assignment (Workforce)
`POST /api/v1/assignment/recommend` → đầu vào workorders + employees + skill matrix + shift; trả `assignment_result` kèm `reason` (explain).

### 4.4 Bottleneck & Delay Prediction
`POST /api/v1/bottleneck/predict` → trả `bottleneck_result` (workcenter/machine, score, factor_type).
`POST /api/v1/delay/predict` → trả dự báo delay của từng workorder + lý do.

### 4.5 Root Cause Analysis
`POST /api/v1/root-cause` → đầu vào: workorder + downtime/NG history → trả `{ "causes": [{"factor":"machine_setup","weight":0.62,"evidence":[...]}] }`.

### 4.6 AI Chat
`POST /api/v1/chat`
```json
{"session_id":"abc","message":"Tại sao ca 1 hôm nay chậm?", "context": {"workcenter_id": 5}}
```
`200` → `{ "reply": "...", "recommendations": [...], "payload": {...} }`

### 4.7 Explain Recommendation
`GET /api/v1/recommendation/{job_id}/explain` → lý do mô hình đề xuất (feature attribution).

### 4.8 Health & Sync
- `GET /healthz` → uptime + model version.
- `POST /api/v1/sync/{entity}` → nhận dữ liệu batch từ Odoo (demand, workorder history, downtime).
- `POST /api/v1/webhook/{job_id}` → AI gọi lại Odoo khi xong (hoặc Odoo poll `GET /api/v1/job/{job_id}`).

## 5. Mô hình khuyến nghị

| Bài toán | Mô hình | Ghi chú |
|---|---|---|
| Demand forecast | Prophet / LightGBM | xử lý mùa vụ, ngày lễ |
| Schedule | CP-SAT (ORTools) | constraint-based, min tardiness/makespan |
| Auto assignment | CP-SAT + score heuristic | skill/OT/conflict constraint |
| Bottleneck/delay | Gradient Boosting | trên historical feature |
| Root cause | Rule + ML explainer | SHAP |
| Chat | LLM (RAG trên SOP/issue) | giữ đơn giản trước |

## 6. Luồng tích hợp Odoo ↔ AI

1. Planner bấm **"Run AI Forecast"** → `htplus.ai.forecast` tạo → Odoo push payload → AI Service tạo `ai.job` (pending) → trả `job_id`.
2. Odoo cron poll `GET /job/{id}`; khi success → ghi `htplus.ai.forecast.line` + `ai.forecast_result`.
3. Recommendation → `htplus.ai.recommendation` (state new) → planner review → apply/dismiss → ghi `ai.audit_log`.
4. Degraded mode: timeout (config `timeout_sec`) → dùng rule engine nội bộ + flag.

## 7. Bảo mật

- API key riêng per company/environment, lưu `htplus.ai.config` (secret type).
- Giới hạn rate per key (nginx/middleware).
- Audit mọi job (`ai.audit_log`).
- Không đưa dữ liệu sản xuất thật ra ngoài khi chưa bật cấu hình (privacy flag).
