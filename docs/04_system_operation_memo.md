# Memo: Vận hành hệ thống — Spec/Wireframe → HTPlus đang triển khai

**Ngày:** 2026-08-09 · **cập nhật:** 2026-08-10 (đồng bộ `05_core_framework_design.md`)
**Nguồn:** `images/` + catalog nghiệp vụ + code `addons/htplus_*`
**Chốt sản phẩm:** không UI 1:1 theo mockup; UX Odoo-native + nối đủ vòng nghiệp vụ + giữ
`htplus_*` là **framework bán riêng cho nhiều nhà máy** — nhà máy mới = cấu hình, không module
mới (§1.2 05).

---

## 1. Hình dung vận hành (một vòng khép kín)

Hệ thống **không** là 22 màn rời. Mọi màn “neo” quanh **một kế hoạch sản xuất đang chọn**
(ví dụ `PLAN-YYYYMMDD-xxx`) và một **chuỗi trạng thái** xuyên suốt:

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
5. Actual phản hồi KPI/downtime/NG; Machine down → maintenance request tự động.
6. Quy trình bắt buộc: View lịch → **Simulate** → **Approve** → **Lock** → Executing.

---

## 2. Màn hình chính

| # | Màn hình | Mô tả | Trạng thái |
|----|------------------------|-----------------------------------------|------------|
| 1 | Factory | CRUD factory/plant/line/machine | ✓ P0 |
| 2 | Shift Template | Pattern ca | ✓ P0 |
| 3 | Production Shift Calendar | Lịch ca tháng (PhpSpreadsheet) | ✓ P0 |
| 4 | Demand Plan | Demand/forecast, import/export Excel | ✓ P0 |
| 5 | Production Plan | MO/WO plan | ✓ P0 |
| 6 | AI Plan Result | Kết quả AI đề xuất | ⏳ P1 |
| 7 | Gantt (timeline) | Sắp lịch công việc | ✓ P0 |
| 8 | Simulation | What-if | ✓ P0 |
| 9 | Schedule Run | Nhiều run, version | ✓ P0 |
| 10 | Shift Assignment | Phân công nhân lực | ✓ P0 |
| 11 | Shift Actual | Thực tích ca | ✓ P0 |
| 12 | WO Actual | Thực tích WO | ✓ P0 |
| 13 | Dashboard | KPI tổng quan | ✓ P0 |
| 14 | DOWN (Maintenance) | Bấm down máy | ⏳ P1 |
| 15 | Machine card | Card máy + báo cáo | ✓ P0 |
| 16 | NG register | Đăng ký NG | ✓ P0 |
| 17 | Issue | Vấn đề sản xuất | ✓ P0 |
| 18 | Data import | Nhập liệu (Excel) | ✓ P0 |
| 19 | Shift Report | Báo cáo ca | ✓ P0 |
| 20 | Daily Production Report | Báo cáo ngày | ✓ P0 |
| 21 | OEE | TBD | ✗ P2+ |
| 22 | Maintenance request | TBD | ✗ P2+ |
| 23 | Planning assistant (chat) | Chat AI | ⏳ P1 |
| 24 | API/external UI | API | ✗ P3 |
| 25 | Login/Layout | Layout Enterprise-like | ✓ P0 |
| 26-31 | Benchmarking · Capacity simulation · Long term forecast · Line balance · Machine classification · Capacity planning vs actual | TBD | ✗ P2+ |
| 32-36 | Workforce planning · Scheduling + simulation · Monitoring + simulation · Shift Report (nâng cao) · Shift Actual (OEE) | TBD | ✗ P2+ |
| 37-56 | NG (nâng cao) · Cost · Warehouse · Inventory · Purchase & Inbound · BOM · Inspection · Inspection material · Manufacturing · Warehouse operation · Stock & Inventory · Planning system · Planning engine · Schedule Control · Execution Control · Shipment · Payment · HR · Accounting | TBD | ✗ P2+ |

---

## 3. Detailing & Phân tích

### 3.1 Lịch (Scheduling) — màn 5, 6, 7, 8, 9

**Quyết định:** `mrp.workorder` là dòng lịch (không tạo `htplus.schedule.line`). Giữ nguyên state
của Odoo, thêm `schedule_state`.

**Chọn thuật toán:** rule engine (heuristic, nhanh) + solver (OR-Tools CP-SAT, tốt hơn).

Chạy scheduler:
1. Planner tạo `schedule.run` (chọn plan, date range, algorithm, objective).
2. Solver chạy **nền** (job layer, không chặn worker) → trả về `ScheduleResult[]` theo hợp đồng
   §5.3 05 (`assignments`, `unassigned` + `explanation` bắt buộc, `objective`, `algorithm`).
3. Planner duyệt trên lịch gợi ý → lan truyền thay đổi.
4. Confirmed → **Lock**.

**Idempotency:** batch apply theo số bản ghi, key `(run, version, sequence)`, mỗi batch một
transaction (§5.2 05). Bộ giải không ghi thẳng vào `mrp.workorder` — schedule run là **ý định**,
duyệt rồi mới Apply (**thi hành**). Hoàn tác lịch = restore version.

**Reservation — câu hỏi chặn (§5.1.1 05):** chỗ APS chiếm lịch ghi `resource.calendar.leaves`
(đúng cơ chế Odoo, gắn `origin = schedule_run_id`) hay model riêng `htplus.capacity.reservation` —
**phải xác minh trên Odoo 18 trước khi code APS**. Chưa dựng model mới.

**MES ↔ Schedule:** MO confirm → sinh WO → workorder thay đổi content → schedule.run
`_htplus_attach_workorders` → conflict detect.

**Concurrency (2 planner):** optimistic lock — client trả về bản ghi; server so sánh `write_date`
(mixin `htplus.concurrency.mixin`, context key `htplus_expected_write_date(s)`). Áp cho
`mrp.workorder` — chưa xong (P1 #11 05).

**Concurrency (solver vs manual edit):** Apply theo batch → version bump → rebuild. Xung đột khoảng
thời gian giải ở tầng DB (`EXCLUDE ... tstzrange`) khi Apply (§5.2.1 05).

**Lịch chống trùng:** `htplus.schedule.change` (audit + undo field-level).

**UI gợi ý heuristic:** hiện “tại sao nên đặt tại đây” + xung đột. Tooltip nếu trái ràng buộc:
solver suggestions. **Degraded mode:** engine down → fallback rule engine + cảnh báo rõ.

### 3.2 Shift & Workforce — màn 10, 11

**Quyết định:** `htplus.workforce` sở hữu `shift` + `workforce.assignment` (§2.5.2 05). Shift có
state; assignment tính đủ điều kiện (skill/ca/xung đột). APS chỉ phát biểu **nhu cầu**; bridge
`htplus_aps_workforce` dịch nhu cầu → assignment. MES ghi **sự kiện thi hành**, không phải nguồn sự
thật của phân công.

**Ai làm gì:** Planner đề xuất assignment (skill matching); Line Leader confirm; MES Operator thao
tác actual. **Phân công AI có vòng:** AI đề xuất theo skill → Line Leader confirm; MES actual phản
hồi KPI; AI học từ lịch sử (feedback loop). **Maintenance → workforce:** machine down → auto-detect
→ gợi ý chuyển ca.

### 3.3 MES — màn 12, 14, 16, 17

**Quyết định:** actual/downtime/NG/issue là MES lite (`htplus_mes_shopfloor`). 1 workorder chỉ 1
actual active tại 1 thời điểm; lịch sử start/stop/continue, không ghi đè. Downtime có reason &
type (planned/unplanned) → nền cho OEE. Actual/downtime đẩy vào `mrp.workcenter.productivity`.

**MES ↔ Planning:** actual (sự thật) **không sửa ngược** production plan; planning trả lời bằng
reschedule suggestion (§2.5 05).

### 3.4 Báo cáo — màn 19, 20

**Quyết định:** báo cáo ca/ngày. Năm hiện tại. Tổng hợp theo factory/plant/line/machine/ca từ
`mrp.workcenter.productivity` (không tính lại từ đầu — §7.1.1 05).

### 3.5 Dashboard — màn 13

**Quyết định:** dashboard có plan context. Không chọn factory thì tính cả nhà máy. Dashboard hợp
APS+MES ở bridge `htplus_aps_mes`.

### 3.6 Machine & Maintenance — màn 14, 15, 22

**Quyết định:** `htplus.machine.equipment_id` M2O → `maintenance.equipment` (bridge
`htplus_factory_maintenance`, **HAS-A không `_inherits`** — §4.5 05). Machine down → auto-create
`maintenance.request`; card máy hiển thị open requests; máy không có equipment vẫn set trạng thái
tay. Vòng bảo trì: request mở → hạ status máy → bộ giải tránh máy đang sửa.

### 3.7 Root cause & AI assistant — màn 23

**Quyết định:** dùng API engine: `/api/v1/root-cause`, `/api/v1/chat` — adapter chịu lỗi (degraded
mode). Mọi gợi ý kèm `explanation` + payload.

### 3.8 API/External UI — màn 24

**Quyết định:** chờ nhu cầu thật — API + event dispatcher + REST cho connector (P3, §9 05).

---

## 4. Kiến trúc lớp (architecture layers)

**Lớp A — Odoo core:** mrp, stock, resource, mail, hr, maintenance.

**Lớp B — Module HTPlus (nghiệp vụ):**

```
htplus_base → htplus_factory → htplus_aps_core ⊥ htplus_mes_shopfloor ⊥ htplus_workforce
                          ↳ bridge auto_install tầng 3 (keo tích hợp)
```

**Lớp C — Core Framework** (`htplus_base` + quy ước, §2.3 05):
- workflow mọi document → `htplus.workflow.mixin` (đã có) — mọi chuyển state qua `_htplus_apply_transition()`
- concurrency → `htplus.concurrency.mixin` (đã có)
- hook `_htplus_*` là API công khai, ghi trong `htplus_base/README.md` (đang nợ — P2 #9)
- framework không được import app cụ thể (luật 2) · data nghiệp vụ không hardcode trong core (§11.3 05)
- Đổi so với bản cũ: **không còn tư duy "clone core cho từng dự án"** — bán riêng nhiều nhà máy trên
  một DB, phân tách bằng `ir.rule` theo factory.

**Lớp D — Bridge / Glue (tầng 3):** `auto_install`, chỉ `_inherit`, không sở hữu model/menu/vòng
đời riêng (luật 4). Danh sách: `htplus_aps_mes` · `htplus_aps_workforce` · `htplus_mes_workforce` ·
`htplus_factory_maintenance` · `htplus_workforce_skills` · `htplus_workforce_holidays`.

---

## 5. Map màn hình → module

| Màn | Module | Ghi chú |
|----|---|---|
| 1 | `htplus_factory` | Factory/plant/line/machine |
| 2 | `htplus_workforce` | Shift template |
| 3 | `htplus_workforce` | Production shift calendar |
| 4 | `htplus_aps_core` | Demand plan |
| 5 | `htplus_aps_core` | Production plan |
| 6 | `htplus_planning_bridge` | AI plan result |
| 7 | `htplus_aps_core` | Gantt |
| 8 | `htplus_aps_core` | Simulation |
| 9 | `htplus_aps_core` | Schedule run |
| 10 | `htplus_workforce` (+`htplus_aps_workforce`) | Shift assignment |
| 11 | `htplus_workforce` | Shift actual |
| 12 | `htplus_mes_shopfloor` | WO actual |
| 13 | `htplus_aps_core` (+`htplus_aps_mes`, `htplus_aps_workforce`) | Dashboard KPI |
| 14 | `htplus_factory_maintenance` | DOWN maintenance |
| 15 | `htplus_factory_maintenance` | Machine card |
| 16 | `htplus_mes_shopfloor` | NG register |
| 17 | `htplus_mes_shopfloor` | Issue |
| 18 | `htplus_aps_core` | Data import |
| 19 | `htplus_mes_shopfloor` | Shift report |
| 20 | `htplus_mes_shopfloor` | Daily production report |
| 21 | `htplus_aps_core` | OEE (TBD) |
| 22 | `htplus_factory_maintenance` | Maintenance request |
| 23 | `htplus_planning_bridge` | Planning assistant (chat) |
| 24 | (API) | External UI (P3) |
| 25 | `htplus_menu` | Login/Layout |
| 26+ | — | Out of scope P2+ |

---

## 6. Ưu tiên triển khai

- **P−1:** trả lời câu hỏi chặn **reservation §5.1.1** (verify trên Odoo 18) — đang bỏ ngỏ.
- **P0:** hạ tầng + 4 module nghiệp vụ + 6 bridge ✅ cấu trúc · workflow mixin ✅ áp cho
  demand/production plan (schedule.run, shift chưa di trú — P1 #12) · **#6 security theo factory
  (scope.mixin + ir.rule fail-closed + group quyền) ❌ chưa làm** — không `ir.rule` nào trong core.
- **P1:** solver nền (job layer, bỏ chờ đồng bộ) · Gantt chuẩn (per-drag undo) · concurrency mixin
  gắn `mrp.workorder` · di trú workflow schedule.run/shift · database index (`EXPLAIN ANALYZE` cỡ
  thật) · migration đầu tiên · README hợp đồng mở rộng.
- **P2:** OEE (từ `mrp.workcenter.productivity`, không tính lại) · maintenance request thủ công ·
  shift-completion & cấp bậc kỹ năng · retention data lớn · automation rule chains · bỏ
  `htplus.planning.parameter` (#19) · migrations bắt buộc (#15).
- **P3:** API/event cho bên thứ ba · đổi tên module theo target (`htplus_aps`, `htplus_mes`,
  `htplus_engine_bridge`) · undo theo version restore.

---

## 7. Kết luận

1. Hệ thống là **một vòng nghiệp vụ khép kín**, không phải tập màn rời — mọi thứ gắn plan context.
2. **MES ↔ Planning một chiều** (Plan → MES); actual không sửa ngược kế hoạch.
3. **AI chỉ đề xuất**, không tự ghi; có degraded mode.
4. **Framework bán riêng nhiều nhà máy**: module tách theo khả năng bán, nhà máy mới = cấu hình.
5. Trạng thái: hướng module **APPROVED**; triển khai **CHƯA** — còn điều kiện chặn §5.1.1 và
   **P0 #6 (ir.rule theo factory) chưa làm**.

---

*Chi tiết: `05_core_framework_design.md` · module: `01_business_module_review.md` · schema:
`02_database_schema.md` · nguyên tắc: `03_engine.md`.*
