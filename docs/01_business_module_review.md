# Kiến trúc module — khung MRP bán riêng cho nhiều nhà máy (Odoo 18 CE)

**Cập nhật 2026-08-10** — đồng bộ với `05_core_framework_design.md`.

Khác bản cũ ("clone core cho từng dự án"): mục tiêu mới là **bán riêng từng năng lực cho
hàng trăm nhà máy** — mỗi nhà máy mới là **cấu hình**, không phải module mới; ranh giới module
đi theo **thứ bán riêng được** (§1.3, §2.5 của 05).

## Bốn nguyên tắc (05 §1)

1. **Core không cài đặt lại primitive của Odoo.** Dùng `resource.calendar`, `mrp.workcenter.productivity`,
   `maintenance.equipment`, `ir.rule`, `ir.config_parameter`… — mỗi lần định viết cơ chế mới phải
   hỏi "Odoo có primitive nào chưa?" (§3).
2. **Cái gì biến thiên theo nhà máy phải là DATA, không phải CODE.** Ca/giờ nghỉ →
   `htplus.shift.template` → `resource.calendar`; quy tắc công suất/ưu tiên/buffer → rule model;
   ngưỡng KPI → config (§1.2). Nhà máy mới = thêm bản ghi.
3. **Ranh giới module đi theo thứ BÁN RIÊNG ĐƯỢC.** Khách mua được MES không cần APS, mua
   Workforce không cần MES (§1.3).
4. **Phụ thuộc một chiều và tối thiểu.** Module năng lực ⊥ module năng lực; keo tích hợp nằm ở
   bridge `auto_install` (§2.1).

## Map nghiệp vụ → module (tên hiện tại)

| Tầng | Module | Sở hữu |
|---|---|---|
| 0 — hạ tầng | `htplus_base` | workflow mixin · concurrency mixin · security mixin · README hợp đồng mở rộng |
| 1 — nền nhà máy | `htplus_factory` | factory/plant/line/machine · factory holiday · calendar bridge · security groups |
| 2 — năng lực | `htplus_aps_core` | demand/production plan · schedule run · simulation · rule · dashboard · Gantt |
| | `htplus_mes_shopfloor` | workorder actual · downtime · NG · issue · báo cáo ngày |
| | `htplus_workforce` | shift template · production shift · shift member/actual/completion · assignment |
| 3 — cầu nối (`auto_install`) | `htplus_aps_workforce` | đề xuất phân công theo work order của schedule run |
| | `htplus_mes_workforce` | actual gắn ca · shift completion từ actual |
| | `htplus_factory_maintenance` | machine ↔ `maintenance.equipment` (M2O) |
| | `htplus_workforce_skills` | skill matching khi phân công |
| | `htplus_workforce_holidays` | nghỉ phép → khả dụng nhân lực |
| | `htplus_aps_mes` | dashboard hợp APS+MES |
| 4 — mở rộng | `htplus_planning_bridge` | adapter → `services/planning` (FastAPI): forecast/recommend/chat |
| | `htplus_menu` | launcher + bookmark |
| | `htplus_timeline_spike` | spike `web_timeline` trên `mrp.workorder` |

**Bản đồ tên (05 §2.2 target ↔ hiện tại):** `htplus_aps` ↔ `htplus_aps_core`, `htplus_mes` ↔
`htplus_mes_shopfloor`, `htplus_engine_bridge` ↔ `htplus_planning_bridge`, `htplus_api` —
chưa có (P3 #24). `htplus_planning_base` đã bị xoá (shell migration chỉ dùng cho DB cũ).

## Cây module

```
htplus_base ──→ htplus_factory ──→ htplus_aps_core · htplus_mes_shopfloor · htplus_workforce   (⊥ nhau)
                                        │  (bridge auto_install tầng 3 nối các năng lực)
htplus_aps_core ──→ htplus_planning_bridge ──HTTP──> services/planning (FastAPI)
```

Mọi mũi tên đi xuống. Không module tầng 2 nào biết module tầng 2 khác tồn tại. Bridge chỉ
`_inherit`, không sở hữu model/menu/vòng đời riêng (luật 4, §2.1).

## Gói bán (05 §2.5)

| Gói | Module | Bán cho |
|---|---|---|
| Shop Floor | base · factory · mes | theo dõi thực tích/downtime/OEE trước |
| Workforce | base · factory · workforce | quản lý ca & phân công |
| APS | base · factory · aps | lập kế hoạch & lịch |
| Full | tất cả + bridge tự bật | trọn vòng Demand→Actual |
| + AI | + engine bridge | forecast/solver/recommendation |
| + Tích hợp | + API + connector | nối ERP/MES/IoT sẵn có (P3) |

Khách mua thêm gói = cài thêm module, **bridge tự bật** — không thao tác tay.

## Quyết định quan trọng

- **Scheduling**: Odoo giữ constraint + state; solver (CP-SAT) trả về `date_start/date_finished`;
  kết quả nằm trong `schedule.run` (ý định), planner duyệt rồi **Apply** mới ghi vào `mrp.workorder`
  (thi hành). Apply theo **batch số bản ghi**, idempotency `(run, version, sequence)`, mỗi batch
  một transaction (§5.2).
- **Work Order = dòng lịch**: kế thừa `mrp.workorder`, hưởng sẵn BOM/routing/stock/MES.
- **Reservation — câu hỏi chặn (§5.1.1)**: chỗ APS chiếm lưu vào `resource.calendar.leaves`
  (nếu Odoo 18 còn dùng leaves cho workorder) hay model riêng `htplus.capacity.reservation` —
  **phải xác minh trên 18 trước khi code APS**.
- **Workflow khai báo**: `htplus.workflow.mixin` — mọi chuyển state qua
  `_htplus_apply_transition()` (role → state nguồn → guard → ghi state → after → event). Không gán
  `.state` trực tiếp (§4.1). Đã áp cho demand/production plan; schedule.run, shift… chưa di trú (P1 #12).
- **Phân quyền theo nhà máy (§6)**: `factory.scope.mixin` + `ir.rule` fail-closed +
  `group_htplus_all_factories` — **P0 #6, chưa làm**. Hiện không `ir.rule` nào trong core.
- **AI chỉ gợi ý**: mọi gợi ý kèm `explanation` + payload, con người duyệt; AI down → fallback rule
  engine + cảnh báo rõ trên UI (§8.3).
- **MES**: 1 workorder chỉ 1 actual active tại 1 thời điểm; lịch sử start/stop/continue, không ghi đè.

## Vấn đề xuyên suốt

1. **Workflow** — chuyển state qua mixin; thêm thuật toán bằng registry/hook, không Selection cứng (§5.3).
2. **Concurrency** — optimistic lock (mixin, giữ context key `htplus_expected_write_date`); xung đột
   khoảng thời gian giải ở tầng DB (`EXCLUDE ... tstzrange`) khi Apply (§5.2.1).
3. **Thời gian & ca** — lưu UTC, hiển thị theo TZ; cam kết dùng `resource.calendar` (bỏ
   hasattr/except fallback — P1 #7).
4. **Versioning** — `schedule.run.version` + `locked`; undo lịch = restore version, không revert
   từng field (§5.1).
5. **Phân quyền** — group ở `htplus_factory` (user/planner/manager/operator); ir.rule theo factory
   fail-closed đang làm (P0 #6).
6. **Degraded mode** — solver chạy nền qua job layer (`htplus.job`, P2 #13); adapter retry/circuit
   breaker/idempotency (§8.2–8.3).
7. **Retention dữ liệu lớn** — chính sách theo khách (§2.5.1): job/event log xoá theo tuổi, MES
   actual/downtime archive sang bảng tổng hợp, partition khi vượt ngưỡng.

Chi tiết schema: `02_database_schema.md` · nguyên tắc kỹ thuật: `03_engine.md` · vận hành:
`04_system_operation_memo.md`.
