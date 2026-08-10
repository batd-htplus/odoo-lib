# Kiến trúc hệ thống — HTPlus APS/MES (Odoo 18 CE)

**Cập nhật 2026-08-10** — sơ đồ tổng quan: deployment, module graph, luồng gọi planning engine.
Chi tiết nghiệp vụ/thiết kế: `01`–`05`.

---

## 1. Deployment — các container

Bốn service chạy trong một bridge network `backend`. Chỉ `nginx` publish port (prod), mọi thứ
khác chỉ gọi nhau qua network nội bộ.

```mermaid
flowchart LR
    USER["Trình duyệt / Client"]

    subgraph NET["backend network (bridge)"]
        NGX["nginx 1.27<br/>TLS · HSTS · rate-limit<br/>X-Accel-Redirect filestore"]
        ODOO["odoo 18 CE<br/>workers + cron threads<br/>http 8069 · longpoll 8072"]
        DB[("postgres 17 · volume db-data")]
        PLN["planning (FastAPI)<br/>uvicorn x2<br/>http :8000"]

        NGX -- "proxy_pass /websocket<br/>→ 8072 (gevent)" --> ODOO
        NGX -- "proxy_pass còn lại → 8069" --> ODOO
        ODOO -- "psycopg :5432" --> DB
        ODOO -- "HTTP /api/v1/* · Bearer key<br/>gọi qua htplus_planning_bridge" --> PLN
        NGX -. "x_sendfile: đọc filestore ro" .-> FS
    end

    USER -- ":80 / :443<br/>(prod)" --> NGX
    USER -.->|":8080 dev · 127.0.0.1"| NGX
    USER -.->|":8069 · :8072 dev direct · 127.0.0.1"| ODOO
```

**Mount/volume:**

```mermaid
flowchart LR
    ODOO["odoo container"]
    ADDONS["./addons → /mnt/extra-addons<br/>(first-party, đọc trước)"]
    VENDOR["./addons_vendor → /mnt/vendor-addons<br/>(read-only mọi môi trường)"]
    CORE["/usr/lib/python3/dist-packages/odoo/addons<br/>(core Odoo)"]
    FS[("volume odoo-data<br/>filestore + sessions")]

    ODOO --> ADDONS
    ODOO --> VENDOR
    ODOO --> CORE
    ODOO --> FS
```

- Thứ tự `addons_path`: `extra-addons` → `vendor-addons` → core: module first-party luôn thắng
  vendor trùng tên.
- `addons_vendor` **read-only ở cả dev lẫn prod**; patch vendor phải làm từ module first-party.
- Dev override mount `./addons` rw (sửa live, `dev_mode = reload`); prod mount `./addons` ro.
- Docker secrets (`*_FILE`) → entrypoint render config 0600 vào `/tmp/odoo.conf`; DB password
  truyền qua CLI args, không bao giờ ghi xuống đĩa.

---

## 2. Module graph — addons Odoo

### 2.1 Tầng nền (standard + vendor)

```mermaid
graph TD
    CORE["Odoo CE core"] --- base & web & mail & mrp & resource & hr & hr_holidays & hr_skills & maintenance
    V["addons_vendor"] --- web_timeline
```

### 2.2 Dependencies giữa module HTPlus

```mermaid
graph TD
    BASE["htplus_base<br/>(framework dùng chung)"]
    FACTORY["htplus_factory<br/>(nhà máy · mrp/resource)"]
    APS["htplus_aps_core<br/>(lập kế hoạch)"]
    MES["htplus_mes_shopfloor<br/>(shop floor)"]
    WF["htplus_workforce<br/>(nhân lực)"]

    FACTORY --> BASE
    APS --> FACTORY
    MES --> FACTORY
    WF --> FACTORY

    MENU["htplus_menu"]
    MENU --> web

    BRIDGE["htplus_planning_bridge<br/>(gọi HTTP planning engine)"]
    BRIDGE --> APS

    TIMELINE["htplus_timeline_spike<br/>(Gantt)"]
    TIMELINE --> APS
    TIMELINE --> web_timeline

    A_MES["htplus_aps_mes"]
    A_MES --> APS
    A_MES --> MES

    A_WF["htplus_aps_workforce"]
    A_WF --> APS
    A_WF --> WF

    M_WF["htplus_mes_workforce"]
    M_WF --> MES
    M_WF --> WF

    F_MT["htplus_factory_maintenance"]
    F_MT --> FACTORY
    F_MT --> maintenance

    WF_H["htplus_workforce_holidays"]
    WF_H --> WF
    WF_H --> hr_holidays

    WF_S["htplus_workforce_skills"]
    WF_S --> WF
    WF_S --> hr_skills
```

---

## 3. Luồng runtime — gọi planning engine

Odoo (qua `htplus_planning_bridge`) gọi FastAPI qua HTTP nội bộ `http://planning:8000`. Engine
xử lý nền (thread + job id), Odoo poll kết quả. Contract trả về là `ScheduleResult`
(xem `03_engine.md` §6); engine **không** đụng ORM Odoo.

```mermaid
sequenceDiagram
    participant U as User (UI Gantt)
    participant O as odoo (htplus_planning_bridge)
    participant P as planning (FastAPI :8000)
    participant D as postgres

    U->>O: click "Tạo kế hoạch AI"
    O->>P: POST /api/v1/schedule/recommend<br/>(Authorization: Bearer, workorders, constraints, objective)
    P-->>O: {success, job_id} (trả về ngay, xử lý nền)
    loop Poll
        O->>P: GET /api/v1/job/{job_id}
        P-->>O: {status: pending|success|failed, data}
    end
    O-->>U: Gantt hiển thị đề xuất (chưa lock)
    O->>D: ghi đề xuất là draft (chờ Approve/Simulate)
```

**Fallback & degraded mode:** forecasting là `moving_average_fallback`, scheduling là
`greedy_fallback` / rule engine, root-cause là `rule_fallback` — response tự gắn nhãn model.
Nếu planning service chết, bridge phải chịu lỗi (retry + degraded mode), không chặn web worker.

---

## 4. Bảng tóm tắt

| Thành phần | Vai trò | Chỉ mở ngoài? |
|---|---|---|
| `nginx` | reverse proxy duy nhất, TLS/HSTS, rate-limit login & RPC, X-Accel-Redirect | Có (80/443, prod) |
| `odoo` | Odoo 18 CE, `proxy_mode=True`, `x_sendfile=True` (prod) | Không (dev: 8069/8072 127.0.0.1) |
| `db` | PostgreSQL 17, volume `db-data` | Không (dev: 5432 127.0.0.1) |
| `planning` | FastAPI sidecar, thread job nền, `/api/v1/*` | Không (dev: 8000 127.0.0.1) |
| `./addons` | module HTPlus first-party | — |
| `./addons_vendor` | module bên thứ ba, ro | — |
| `odoo-data` | filestore + sessions — mất là mất attachments | — |
