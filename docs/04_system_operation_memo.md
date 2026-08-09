# Memo: Vận hành hệ thống — Spec/Wireframe → HTPlus đang triển khai

**Ngày:** 2026-08-09  
**Nguồn:** `images/` + catalog nghiệp vụ + code `addons/htplus_*`  
**Chốt sản phẩm:** không UI 1:1 theo mockup; UX Odoo-native + nối đủ vòng nghiệp vụ + giữ `htplus_*` làm core FW clone được (mục 4).

---

## 1. Hình dung vận hành (một vòng khép kín)

Hệ thống **không** là 22 màn rời. Mọi màn “neo” quanh **một kế hoạch sản xuất đang chọn** (ví dụ `PLAN-YYYYMMDD-xxx`) và một **chuỗi trạng thái** xuyên suốt:

```
Draft → AI Generated → Simulated → Pending Approval → Confirmed → Executing → Completed
```

Luồng nghiệp vụ (theo wireframe):

```text
Demand data
  → Demand Plan
  → Production Plan (+ MO / Work Order)
  → AI Plan Result
  → Gantt chỉnh tay
  → Simulation (có thể quay lại AI/Gantt)
  → Phê duyệt (Manager)
  → Shift Calendar / Shift Detail
  → Shift Assignment (skill)
  → Shift / WO Actual (MES)
  → KPI Dashboard / Shift Report
```

**Ai làm gì**

| Vai | Việc chính |
|---|---|
| Planner | Demand, Production Plan, AI/Gantt/Sim, đề xuất ca & phân công |
| Production Manager | Duyệt / lock lịch, xem dashboard & báo cáo |
| Line Leader | Xác nhận phân ca, theo dõi thực tích ca |
| MES Operator | Start / Pause / Finish actual trên shop floor |
| Admin | Master: pattern ca, nghỉ, line, skill, cấu hình |

**Nguyên tắc sản phẩm (wireframe)**

1. Dashboard và hầu hết màn “nặng” đều mang **plan context** (số plan, nhà máy, planner, version, status, next step).
2. AI **chỉ đề xuất**; con người duyệt rồi mới Confirmed.
3. Simulation là cổng “what-if” trước phê duyệt; có vòng quay lại AI/Gantt.
4. Sau Confirmed mới khóa vào Shift → Assignment → Actual.
5. Actual phản hồi KPI/alert — vòng cải tiến kỳ sau.

---

## 2. Áp vào kiến trúc code hiện tại

Cây module (đã có — xem thêm `01_business_module_review.md`):

```text
htplus_planning_base          # factory/plant/line/machine, shift, skill, holiday
      ▼
htplus_aps_core               # demand, production plan, schedule, sim, workforce, dashboard
      ├── htplus_mes_shopfloor      # actual, downtime, NG, issue, shift completion
      └── htplus_planning_bridge    # forecast / recommend / solver → services/planning
```

**Map vòng nghiệp vụ → object Odoo hiện có**

| Bước wireframe | Object / hành động HTPlus hiện tại |
|---|---|
| Demand Plan | `htplus.demand.plan` (+ lines); import Excel; forecast qua bridge |
| Production Plan | `htplus.production.plan` → BOM explode → `mrp.production` |
| Work Order / lịch | `mrp.workorder` (`date_start` / `date_finished`, `schedule_run_id`) |
| AI Planning | `htplus.planning.forecast` / recommendation + `action_run_solver` → FastAPI |
| Gantt | Client action Gantt (`htplus_aps_core`) + spike `htplus_timeline_spike` |
| Simulation | `htplus.simulation.scenario` (run / apply) |
| Phê duyệt | Confirm/Approve/Lock trên Demand / Plan / Schedule (`htplus.security.mixin` + groups) |
| Shift | `htplus.production.shift` + calendar; template → `resource.calendar` |
| Assignment | `htplus.workforce.assignment` (`action_propose_workforce`, skill check) |
| Actual | Confirm assignment → `htplus.workorder.actual` (+ productivity) |
| Shift Actual | `htplus.shift.actual` (+ line) + `htplus.shift.completion` |
| Dashboard | `htplus.dashboard` + Shift Management Dashboard |
| Report | Schedule report + daily production report (MES) + Shift Report (wizard PDF/XLSX) |

**Trạng thái: wireframe vs code (chênh lệch quan trọng)**

Wireframe dùng **một stepper chung** trên plan. Trong code, state **tách theo document**:

| Document | State hiện có (rút gọn) |
|---|---|
| Demand Plan | draft → confirmed → approved → planned / cancelled |
| Production Plan | draft → confirmed → approved → locked / cancelled |
| Schedule Run | draft → calculated → confirmed → locked |
| Simulation | draft → computed → … |
| Shift / Assignment / Actual | draft/confirmed/… riêng từng model |

→ **Áp dụng thực tế:** chưa gộp một field `plan_lifecycle` duy nhất. Muốn UI giống mockup thì cần *tính toán / hiển thị* lifecycle từ các state trên (hoặc bổ sung field tổng hợp trên Production Plan) — đây là gap sản phẩm, không chỉ gap skin.

**Ràng buộc shift hiện tại của module:** 1 shift/workcenter/ngày (`_check_machine_availability`) và 1 leader/ngày (`_check_leader_conflict`) — seed chỉ tạo Day shifts; Eve/Night giữ làm cấu hình template. Nếu cần vận hành 3 ca cùng line thì phải nới các check này (gap cho phiên bản sau).

---

## 3. Map 22 màn → hiện trạng triển khai

Chú thích: **OK** = dùng được cho E2E cơ bản · **Partial** = có model/màn nhưng thiếu UX/luồng mockup · **Gap** = chưa có hoặc lệch mạnh.

| # | Màn (spec) | Module / entry hiện tại | Trạng thái | Ghi chú áp dụng |
|---|---|---|---|---|
| 01 | Dashboard | `htplus.dashboard` | Partial | KPI cards + Refresh + **Working Production Plan** (`action_use_on_dashboard`) + alert thiếu material (`material_ok`); thiếu stepper plan lifecycle |
| 02 | DS Demand | Demand Plans list | Partial | List OK; thiếu search/filter/group/copy như list Odoo “đủ việc” |
| 03 | Tạo/sửa Demand | Demand form + import + forecast | Partial | Header/workflow Odoo đã thống nhất; **thiếu** lưới nhu cầu theo ngày + trend chart như mockup |
| 04 | DS Production Plan | Production Plans list | Partial | Giống 02 |
| 05 | Chi tiết Production Plan | Production Plan form → MO | OK nền | Line/BOM/MO/schedule run; chưa UI “từng công đoạn” kiểu mockup |
| 06 | AI Planning | Bridge forecast/recommend + solver | Partial | Có cầu nối engine; chưa màn “AI kết quả tối ưu” đầy đủ gắn plan |
| 07 | Gantt | Gantt client (`htplus_aps_core.gantt`) | OK | Kéo thả/resize/đổi line persist → `mrp.workorder`; snap 30 phút; conflict + optimistic lock; context plan/run; panel task còn mỏng so mockup |
| 08 | Simulation | Simulation Scenarios | OK nền | Run/Apply có; UX còn mỏng |
| 09 | Shift Calendar | Production Shift calendar | OK | Khớp hướng |
| 10 | Shift Detail | Production Shift form | OK | Đã thống nhất header/button |
| 11 | Tạo ca mới | Shift create (+ template) | OK | Wizard nhiều bước như mockup chưa có |
| 12 | Phân ca | Workforce Assignment | OK | Propose + skill check + conflict; chưa AI phân ca / wizard cân bằng skill |
| 13 | Thực tích phân ca | `htplus.shift.actual` (+ line) + Shift Completion + MES Actual | OK | Assignment confirm → MES actual; Shift Actual generate/confirm/done + header buttons từ Shift |
| 14 | Shift Report | `htplus.shift.report.wizard` → QWeb PDF + export XLSX | OK | Wizard chọn khoảng ngày/line/template; tổng qty_target/done/good/NG/downtime/achievement/yield |
| 15–17 | Cấu hình ca / pattern / nghỉ | Settings, Shift Template, Factory Holidays | Partial / OK | Pattern + holiday OK; màn “Shift Configuration” gom chưa có |
| 18 | Quản lý ca (list) | Shifts list | OK | |
| 19 | Nhân viên phân ca | `htplus.shift.member` (factory/plant/line/is_leader) + skill | OK | Màn/list/form/menu + ACL user/planner/manager/operator |
| 20 | Line | `htplus.line` (+ WC/machine) | OK | |
| 21 | Skill | Skill Matrix HTPlus | OK nền | |
| 22 | Dashboard quản lý ca | Shift Management Dashboard | OK nền | |

Seed demo đầy đủ (`scripts/seed_htplus_full.py`, chạy trên DB sạch): 1 factory/2 plant/4 line/4 WC/4 machine + 3 shift template (Day sync calendar, Eve/Night UI) + 10 employee/5 user (`manager|planner|op1-3@htplus.demo`, pass `htplus123`) + 8 shift member (4 leader) + 6 product BOM đa tầng (FG→SEMI→RM) + stock raw/SEMI → Demand Plan → Production Plan (10 MO) → Schedule Run (18 WO, 0 conflict) → Propose/Confirm Workforce (16 confirmed/0 conflict) → MES actual (16, 4 finished) → Shift Actual/Completion → Working plan Dashboard.

---

## 4. Quyết định sản phẩm (chốt 2026-08-09)

### Không làm gì

- **Không** vẽ UI 1:1 theo `images/` (sidebar tím, card pixel-perfect, chart giống mockup…). Tốn thời gian, khó bảo trì trên Odoo, không cần thiết.
- `images/` chỉ là **tài liệu nghiệp vụ / tham chiếu luồng**, không phải design system bắt buộc.

### Làm gì

1. **UI/UX theo Odoo** — form/list/search/header chuẩn CE (Document / Workflow / Master đã unify). Chỉnh cho *dễ dùng trong Odoo*, không bắt chước Figma.
2. **Liên kết màn hình thành một vòng nghiệp vụ hoàn chỉnh** — mỗi bước có next action rõ (Demand → Plan → Schedule/Gantt/Sim → Approve → Shift → Assignment → Actual → Dashboard/Report). Không để màn rời rạc.
3. **Đáp ứng nghiệp vụ** trong catalog 01–22 (mục đích / vai / dữ liệu vào–ra), dù UI khác mockup.
4. **Core FW tái sử dụng** — `htplus_planning_base` + `htplus_aps_core` (+ MES/bridge mỏng) là **core sản phẩm**. Dự án sau: clone core, chỉ thêm theme/config/master data/extension — **không sửa lõi nghiệp vụ** trừ khi nâng cấp phiên bản core chung.

→ Tóm lại công việc còn lại chủ yếu là: **chỉnh UX Odoo-native + nối mắt xích + cứng hóa core**, không phải redesign giao diện.

---

## 5. Cách áp vào hệ đang triển khai

Giữ quyết định kỹ thuật `01`–`03`: kế thừa `mrp`/`hr`/`resource`; AI sau bridge; WO = dòng lịch.

### Lớp A — Liên kết & IA (ưu tiên)

- Menu theo vòng nghiệp vụ (Dashboard → Demand → Production → Scheduling/Gantt → Simulation → Shift → Workforce → Shop Floor → Assistant → Master).
- Nút / smart button / action “bước tiếp theo” giữa các document (Demand → Plan → Schedule/Gantt → Workforce → Actual).
- Search/filter list cho Demand & Production Plan.
- Plan context: Dashboard có **Working Production Plan**; KPI/alert lọc theo plan; nút Use on Dashboard từ Production Plan.
- Gantt nhận context `htplus_production_plan_id` / `htplus_schedule_run_id`.

*(Slice 1 đã triển khai trên `htplus_aps_core` 18.0.1.6.0 — 2026-08-09.)*

### Lớp B — Đóng gap nghiệp vụ còn hở

1. Dashboard theo plan + alert thật (conflict, material, thiếu người). ✅ *(Slice 1 — đã có Working Plan + alert material; còn alert conflict/thiếu người gắn plan)*  
2. Gantt/timeline: kéo thả persist → `mrp.workorder` + conflict + giữ context plan/run. ✅ *(harden 18.0.1.6.1 — đã đóng, có optimistic lock)*  
3. AI/solver: kết quả gắn plan/schedule (đề xuất → apply có duyệt). ⏳ *(cố ý để sau — phụ thuộc dịch vụ planning)*  
4. Assignment → Actual / Shift Completion / Shift Report cho Leader/Manager. ✅ *(Shift Actual + Completion + wizard report PDF/XLSX)*

### Lớp C — Cứng hóa core (để clone)

| Thuộc core (ít đổi theo dự án) | Ngoài core (đổi theo dự án) |
|---|---|
| Model + state machine + ACL groups | Branding, tên menu JA/local |
| Luồng Demand→…→Actual | Master data mẫu, factory layout |
| Mixin bảo mật, optimistic lock, calendar bridge | Report layout khách |
| Bridge contract → planning service | Endpoint/URL, API key, model AI cụ thể |
| Convention view Document/Workflow/Master | Widget/theme tùy chọn |

Quy ước: project mới **depends** core modules; custom = module `htplus_<customer>_…` inherit, không fork file core.

### Lớp D — Skin (chỉ khi khách yêu cầu)

- Card/chart đẹp hơn mockup = tùy chọn project, không chặn core.

---

## 6. Ranh giới rõ

| Gợi ý từ images | Quyết định |
|---|---|
| UI 1:1 mockup | **Không** — Odoo-native đủ |
| Sidebar / shell riêng | Dùng shell Odoo + menu HTPlus |
| Stepper màu giống Figma | Tuỳ chọn; ưu tiên statusbar + next action |
| AI tự áp lịch | Đề xuất → Planner/Manager confirm/lock |
| WO ngoài MRP | WO = `mrp.workorder` |
| Sửa core theo từng khách | **Không** — inherit bên ngoài |

---

## 7. Kết luận ngắn

- Vận hành = một vòng APS quanh Production Plan (spec đúng).  
- Code đã có xương sống core; việc đúng hướng giờ là **nối màn + UX Odoo + cứng FW**, không vẽ lại giao diện.  
- `images/` = bản đồ nghiệp vụ; UI thật = Odoo; core = clone được cho dự án sau.

**Tài liệu liên quan:** `01_business_module_review.md`, `02_database_schema.md`, `03_engine.md`.  
**Tham chiếu hình (nghiệp vụ only):** `images/`.
