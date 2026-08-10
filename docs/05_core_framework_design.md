# Core Framework — khung MRP bán được cho nhiều nhà máy

**Ngày thiết kế:** 2026-08-10 · **cập nhật as-built:** 2026-08-10 (đối chiếu code `addons/htplus_*`)
**Mục tiêu:** khung trên Odoo CE `mrp` để **bán và triển khai cho hàng trăm nhà máy**:
mỗi nhà máy mới là **cấu hình**, không phải module mới; mở rộng và tích hợp bên thứ ba
không cần sửa lõi; phụ thuộc tối thiểu và có trật tự; chi phí vận hành thấp.

Tiếp nối `04_system_operation_memo.md` mục 4 (Lớp C). Sơ đồ deployment + module graph hiện
trạng: `00_system_architecture.md`.

> **Trạng thái (2026-08-10, đối chiếu code thực tế):**
>
> | | |
> |---|---|
> | **Hướng kiến trúc module** | ✅ đã triển khai — `factory → {aps_core ⊥ mes_shopfloor ⊥ workforce} → bridge` (§2.2) |
> | **Phân quyền nhiều nhà máy** | ✅ `factory.scope.mixin` + `ir.rule` fail-closed + `group_htplus_all_factories` (§6) |
> | **Workflow khai báo** | ✅ `htplus.workflow.mixin` — demand.plan & production.plan; schedule.run/shift chưa (§4.1) |
> | **Machine ↔ maintenance** | ✅ chốt `Many2one equipment_id` (§4.5), đã triển khai ở bridge |
> | **Reservation** | ✅ chốt: dùng `leave_id` của Odoo (§5.1.1) — **chưa** triển khai ghi leaves |
> | **Apply batching / idempotency** | ❌ chưa triển khai — confirm/lock vẫn đồng bộ (§5.2) |
> | **Job layer trong Odoo** | ❌ chưa (`htplus.job`); planning service tự chạy job nền (§8.2) |
> | **Test** | ❌ hoãn có chủ ý (chỉ `htplus_menu/tests`) (§12) |
>
> Tài liệu này là **thiết kế gốc kèm chú thích as-built** ở từng mục: mục nào đã triển khai
> đúng thiết kế, mục nào chốt khác đi khi code, mục nào còn nợ (không phải kế hoạch tương lai).

---

## 0. Vì sao tự dựng thay vì mua Enterprise

| Enterprise **có** | Enterprise **không có** |
|---|---|
| `web_gantt` (widget Gantt) | **Bộ tối ưu lập lịch (APS)** — EE vẫn greedy tuần tự, không hàm mục tiêu |
| `mrp_mps` (Master Production Schedule) | Phân cấp Factory→Plant→Line (EE cũng dừng ở workcenter) |
| `quality` (control point / check) | Simulation what-if, phiên bản lịch, undo |
| `mrp_plm` (ECO, BOM versioning) | Lifecycle duyệt trên một *kế hoạch sản xuất* |
| Shop Floor tablet view | Gợi ý AI kèm lý do + degraded mode |
| `planning` (xếp ca nhân sự), Barcode, IoT | |

CE đã có: `maintenance`, OEE trên `mrp.workcenter`, `resource.calendar` đầy đủ,
`mrp.workcenter.productivity`.

Enterprise bán **widget UI và app lân cận**, không bán **bộ não lập lịch** — phần đó không
có ở cả hai bản. Mất khi bỏ EE: `web_gantt` (đã thay `web_timeline` AGPL) và `mrp_mps`.
Đổi lại: sửa sâu được, giao nhiều khách không buộc từng khách mua license.

> Cần xác nhận lại bảng này theo phiên bản/báo giá thực tế trước khi dùng để ra quyết định thương mại.

## 1. Bốn nguyên tắc

**1.1 Core không cài đặt lại primitive của Odoo.**
Core = (a) lớp *khai báo* đặt trên primitive Odoo, (b) đúng phần Odoo không có.
Mỗi lần định viết cơ chế mới phải trả lời được "Odoo có primitive nào chưa?" — §3 là câu
trả lời sẵn.

**1.2 Cái gì biến thiên theo nhà máy phải là DATA, không phải CODE.**

| Biến thiên theo khách | Nằm ở |
|---|---|
| Độ sâu phân cấp, số line, workcenter | master data |
| Mẫu ca, giờ nghỉ, ngày nghỉ | `htplus.shift.template` → `resource.calendar` |
| Quy tắc công suất, ưu tiên, buffer | `htplus.planning.rule` / `capacity.rule` / `priority.rule` |
| Ngưỡng KPI, mục tiêu OEE | `ir.config_parameter` + `mrp.workcenter.oee_target` |
| Bước duyệt | `_htplus_transitions` (khai báo, override được) |
| Thuật toán lập lịch | registry + `selection_add` |

Nhà máy mới = thêm bản ghi. Chỉ khi *nghiệp vụ* khác mới sinh `htplus_<customer>_*`.

**1.3 Ranh giới module đi theo cái BÁN RIÊNG ĐƯỢC.**
Với sản phẩm, tiêu chí tách không còn là "có dự án nào lấy bên này bỏ bên kia" mà chặt hơn:
**"khách có mua được cái này mà không mua cái kia không?"** Bán MES trước rồi bán APS sau
là đường vào nhà máy rẻ nhất — kiến trúc phải cho phép.

**1.4 Phụ thuộc phải một chiều và tối thiểu.** Xem §2.1.

## 2. Kiến trúc module

### 2.1 Bốn luật phụ thuộc

| # | Luật | Kiểm bằng |
|---|---|---|
| 1 | **Module năng lực không depends module năng lực khác** (`aps` ⊥ `mes` ⊥ `workforce`). Tích hợp liên năng lực **chỉ** làm bằng bridge tuỳ chọn ở tầng 3 — bridge được phép depends cả hai, đó là lý do nó tồn tại | đọc `depends` |
| 2 | **Core không bao giờ depends app tuỳ chọn** (`hr_skills`, `maintenance`, `quality`…). Keo đi vào **bridge `auto_install`** | đọc `depends` |
| 3 | **Phụ thuộc chỉ đi xuống tầng** — không ngang, không lên | đồ thị không chu trình |
| 4 | **Bridge không sở hữu một capability domain độc lập.** Được phép chứa hành vi tích hợp liên năng lực; **không** được sở hữu aggregate riêng, menu ứng dụng riêng, hay vòng đời nghiệp vụ riêng | xem model/menu mới |

Luật 4 đã sửa 2026-08-10. Bản trước ghi "bridge chỉ chứa keo, không business logic" — mâu
thuẫn với chính §2.4, nơi `htplus_aps_workforce` làm "đề xuất phân công theo work order".
Đó **là** business behavior, và nó đúng chỗ: nó chỉ tồn tại khi có cả hai năng lực. Ranh giới
đúng không phải "có logic hay không" mà là "**có sở hữu một domain độc lập hay không**".

Luật 2 là pattern Odoo tự dùng (`sale_stock`, `mrp_account`, `hr_holidays_attendance`):
bridge `auto_install = True` **tự xuất hiện khi cả hai phía cùng có mặt**. Người vận hành
không bao giờ phải cài tay → tách bạch tối đa mà **không thêm gánh nặng vận hành**.

### 2.2 Bản đồ

**As-built (tên module thật trong `addons/`):** tầng 2 dùng tên `htplus_aps_core` /
`htplus_mes_shopfloor` (thay `htplus_aps` / `htplus_mes` trong bản thiết kế); bridge gọi engine
tên `htplus_planning_bridge` (thay `htplus_engine_bridge`).

```
Tầng 0 — hạ tầng, không biết "nhà máy" là gì
  htplus_base                base, mail

Tầng 1 — nền nhà máy
  htplus_factory             htplus_base, resource, mrp

Tầng 2 — NĂNG LỰC: bán riêng được, ngang hàng, KHÔNG phụ thuộc nhau
  htplus_aps_core            htplus_factory              lập kế hoạch & lịch
  htplus_mes_shopfloor       htplus_factory              thực thi xưởng
  htplus_workforce           htplus_factory, hr          ca & nhân lực

Tầng 3 — CẦU NỐI: auto_install, chỉ chứa keo
  htplus_aps_workforce       htplus_aps_core + htplus_workforce
  htplus_aps_mes             htplus_aps_core + htplus_mes_shopfloor
  htplus_mes_workforce       htplus_mes_shopfloor + htplus_workforce
  htplus_factory_maintenance htplus_factory + maintenance
  htplus_workforce_skills    htplus_workforce + hr_skills
  htplus_workforce_holidays  htplus_workforce + hr_holidays

Tầng 4 — mở rộng (THIẾT KẾ — chưa có code)
  htplus_api                 htplus_base                 REST có version + event bus (§9)
  htplus_connector_<x>       htplus_api                  bên thứ ba
  htplus_demo_data           htplus_aps_core            seed skill/layout [thay bằng scripts/seed_htplus_*.py]

Tuỳ chọn (đã có)
  htplus_menu · htplus_timeline_spike (web_timeline) · htplus_planning_bridge (auto_install=False)
```

**Đọc đồ thị:** mọi mũi tên đi xuống. Không module tầng 2 nào biết module tầng 2 khác tồn
tại. Muốn nối chúng → tầng 3.

### 2.3 Vì sao khác bản trước (6 module)

Bản trước tối ưu cho "clone core cho dự án của chính mình". Mục tiêu mới là **bán riêng cho
hàng trăm khách với phạm vi khác nhau** — tiêu chí đổi (§1.3) thì kết quả đổi. Hai chỗ hỏng
lộ ra khi áp tiêu chí mới:

1. `htplus_mes_shopfloor` **depends `htplus_aps_core`** → không bán được MES riêng. Kỹ thuật
   thì MES chỉ cần factory + mrp. Ranh giới này chặn đường bán mà không đổi lại được gì.
   **As-built: đã sửa** — `htplus_mes_shopfloor` chỉ depends `htplus_factory`; tích hợp APS↔MES
   chuyển sang bridge `htplus_aps_mes` (`auto_install`).
2. `hr`, `hr_skills`, `hr_holidays`, `maintenance` bị kéo vào `planning_base` → mọi khách đều
   phải nuốt, kể cả nhà máy không quản lý skill. Thực tế `hr.*` chỉ được dùng ở
   shift/workforce/shift_member/shift_actual — tức **năng lực workforce**, không phải nền.
   **As-built: đã sửa** — `htplus_factory` chỉ depends `base/mrp/resource`; mỗi bổ sung đi qua
   bridge riêng.

**Số module tăng nhưng trọng lượng không tăng:** 6 bridge tầng 3 mỗi cái vài chục dòng keo,
`auto_install` nên không ai phải cài. Đây là chi phí đúng chỗ — đổi lấy quyền bán từng phần.
**As-built: cả 6 bridge đều `auto_install = True`**, đúng như thiết kế.

### 2.4 Từng module làm gì (as-built)

| Module | depends | Sở hữu | Trạng thái |
|---|---|---|---|
| `htplus_base` | `base`, `mail` | `htplus.workflow.mixin` · `htplus.concurrency.mixin` · README hợp đồng mở rộng | ✅ làm đúng thiết kế (trừ `htplus.job`, undo, event dispatcher — chưa có, xem §4/§8/§9) |
| `htplus_factory` | `htplus_base`, `resource`, `mrp` | factory/plant/line · machine · workcenter ext · `htplus.factory.scope.mixin` · `htplus.security.mixin` · `_htplus_group_map` · group + `ir.rule` fail-closed | ✅ làm đúng thiết kế (`mrp.bridge.mixin` chưa tách — còn nợ §4.4) |
| `htplus_aps_core` | `htplus_factory`, `mail` | demand plan · production plan · planning/capacity/priority rule · schedule run · simulation scenario · dashboard · Gantt client · report · `htplus.schedule.change` | ✅ (apply batch §5.2 và hook `_htplus_resolve_scheduler` §5.3 chưa) |
| `htplus_mes_shopfloor` | `htplus_factory` | workorder actual · downtime · NG/defect · issue · báo cáo ngày | ✅ |
| `htplus_workforce` | `htplus_factory`, `hr` | shift template · production shift · shift member · shift actual/completion · **`htplus.workforce.assignment`** | ✅ đúng §2.5.2 (workforce sở hữu assignment) |
| `htplus_aps_workforce` | `aps_core` + `workforce` | đề xuất phân công theo work order của schedule run (`action_propose_workforce`) | ✅ |
| `htplus_aps_mes` | `aps_core` + `mes_shopfloor` | dashboard tổng hợp APS↔MES | ✅ (bridge mới, thêm khi tách mes) |
| `htplus_mes_workforce` | `mes_shopfloor` + `workforce` | actual gắn ca · shift completion từ actual | ✅ |
| `htplus_factory_maintenance` | `factory` + `maintenance` | machine `equipment_id` (Many2one) · request mở → hạ trạng thái máy (§4.5) | ✅ chốt **Many2one**, không `_inherits` |
| `htplus_workforce_skills` | `workforce` + `hr_skills` | skill matching khi phân công + seed `hr.skill.type` | ✅ |
| `htplus_workforce_holidays` | `workforce` + `hr_holidays` | nghỉ phép → khả dụng nhân lực | ✅ |
| `htplus_menu` | `web` | menu ứng dụng, bookmark | ✅ |
| `htplus_timeline_spike` | `aps_core` + `web_timeline` | Gantt (`web_timeline` AGPL thay `web_gantt`) | ✅ |
| `htplus_planning_bridge` | `aps_core` | adapter HTTP → `services/planning` (`htplus.planning.service`) · forecast/recommend/assignment/chat · poll job | ✅ (chịu lỗi §8.3 chưa đủ) |
| `htplus_api` | — | REST có version · event bus · subscription (§9) | ❌ chưa có — controller legacy `/htplus/api/*` còn |
| `htplus_demo_data` | — | skill seed · factory layout mẫu · seed script | ❌ chưa có — thay bằng `scripts/seed_htplus_*.py` |

**As-built: 4 module bán được** (`factory`, `aps_core`, `mes_shopfloor`, `workforce`)
+ 1 hạ tầng + 6 bridge mỏng + 3 mở rộng/menu/Gantt/bridge engine + 2 mở rộng thiết kế chưa code.

### 2.5 Gói bán

| Gói | Module | Bán cho |
|---|---|---|
| **Shop Floor** | base · factory · mes_shopfloor | nhà máy muốn theo dõi thực tích/downtime/OEE trước |
| **Workforce** | base · factory · workforce | quản lý ca & phân công |
| **APS** | base · factory · aps_core | lập kế hoạch & lịch |
| **Full** | tất cả + bridge tự bật | trọn vòng Demand→Actual |
| **+ AI** | + planning_bridge | forecast/solver/recommendation |
| **+ Tích hợp** | + api + connector | nối ERP/MES/IoT sẵn có — chưa có code (§9) |

Khách mua thêm gói = cài thêm module, **bridge tự bật** — không phải thao tác cài đặt thủ công.

**Nhưng không được nói "không cần migration" (sửa 2026-08-10).** Câu đó mâu thuẫn trực tiếp
với chính §4.5: bridge nào có backfill dữ liệu thì đó **là** migration. Phát biểu đúng:

> Bridge **chỉ bổ sung hành vi** → không cần migration nghiệp vụ.
> Bridge **thêm cột hoặc cần backfill dữ liệu sẵn có** → **bắt buộc** có script migration
> idempotent, chạy lại nhiều lần cho cùng kết quả.

Tương tự, `auto_install` **giảm thao tác vận hành, không xoá được độ phức tạp vận hành**: mỗi
bridge vẫn là một module có version, có đường nâng cấp, cần QA và kiểm tương thích phụ thuộc.

### 2.5.1 Chính sách lưu trữ dài hạn — bắt buộc từ đầu

Một khách 50 nhà máy × 10k work order/ngày làm các bảng sau phình rất nhanh:
`mail.message` · `mail.tracking.value` · `mrp.workcenter.productivity` · MES actual ·
downtime · job log · event log.

Không có chính sách retention thì sau 18–24 tháng: backup chậm, `autovacuum` không theo kịp,
truy vấn dashboard xuống dốc, và chi phí hạ tầng tăng theo tuyến tính với thời gian chứ không
theo quy mô nhà máy.

| Nhóm dữ liệu | Chính sách |
|---|---|
| Job log, event log | xoá theo tuổi (cron), giữ N ngày |
| MES actual, downtime | archive/summary sang bảng tổng hợp; giữ chi tiết theo yêu cầu kiểm toán của khách |
| `mail.message` / tracking | giới hạn model được tracking; dọn định kỳ |
| Bảng lớn theo thời gian | cân nhắc partition theo tháng khi vượt ngưỡng |

Ngưỡng và thời hạn là **cấu hình theo khách** (§1.2), không hardcode.

### 2.5.2 Ai sở hữu `assignment`

Chưa chốt thì sau vài tháng sẽ có ba nguồn sự thật (APS assignment / Workforce assignment /
MES actual employee). Chốt:

| Bên | Vai trò | As-built |
|---|---|---|
| `htplus_workforce` | **sở hữu** `assignment` và tính đủ điều kiện của nhân sự (skill, ca, xung đột) | ✅ model `htplus.workforce.assignment` ở đây |
| `htplus_aps_core` | phát biểu **nhu cầu**: work order này cần bao nhiêu người, kỹ năng gì — **không** tạo assignment | ✅ |
| `htplus_aps_workforce` (bridge) | dịch nhu cầu APS → assignment của Workforce | ✅ `action_propose_workforce` tạo draft assignment |
| `htplus_mes_shopfloor` | ghi **sự kiện thi hành**: ai thực sự đã làm — không phải nguồn sự thật của phân công | ✅ |

### 2.6 Luật từng tầng

| Tầng | Được có | Cấm |
|---|---|---|
| `htplus_base` | AbstractModel, model hạ tầng, menu **Technical**, README | model nghiệp vụ, menu ứng dụng, `depends` mrp/hr, data nghiệp vụ |
| `htplus_factory` | master data, view, menu, `ir.rule` | quy trình, master data của khách |
| Năng lực (tầng 2) | process nghiệp vụ của đúng năng lực đó | depends năng lực khác, fork logic base |
| Bridge (tầng 3) | field bổ sung, hook nối, view kế thừa | model mới, menu mới |
| `htplus_demo_data` | mọi thứ hình dạng khách hàng | bị core depends |

`htplus_base` mà có một menu **ứng dụng** là hết trung lập. Menu dưới Settings › Technical
thì được, đúng như Odoo làm với `ir.cron`.

**Security group ở lại `htplus_factory`.** Dời sang module khác sẽ đổi xmlid
`htplus_planning_base.group_aps_planner`, phá `ir.model.access.csv` và mọi `has_group()`.
Base chỉ định nghĩa cơ chế; `factory` nạp xmlid vào `_htplus_group_map` bằng cách `_inherit`
chính mixin.

### 2.7 Vì sao không nhiều module như OCA/manufacture

`OCA/manufacture` có **54 module**:

| Nhóm | Số | Nội dung điển hình |
|---|---|---|
| `mrp_bom_*` | ~16 | thêm **một** thứ vào BOM: note, image, location, version, UoM rounding… |
| `mrp_production_*` | ~14 | **một** hành vi: note, tag, back-to-draft, auto-validate, putaway… |
| Keo tích hợp | ~10 | `mrp_sale_info`, `account_move_line_mrp_info`, `mrp_subcontracting_*` |
| Đáng kể | ~4 | `mrp_multi_level`, `quality_control_oca`, `mrp_warehouse_calendar`, `mrp_bom_version` |

Đại đa số là **một field / một nút / một report** — 54 miếng vá lên `mrp`, không phải framework.

OCA phục vụ hàng nghìn người dùng xa lạ, mỗi người muốn một 5% khác nhau: **độ hạt mịn chính
là sản phẩm của họ**. HTPlus bán **gói năng lực trọn vòng** — chia tới mức field thì ta trả
giá, không ai mua. Cùng tiêu chí, khác đối tượng tiêu thụ, khác kết quả.

**Cái không có trong 54 module đó:** APS, phân cấp Factory→Plant→Line, ca/phân công theo
skill, simulation, khung MES. `mrp_multi_level` ghi "Adds an MRP Scheduler" nhưng là **MRP-II
hoạch định vật tư** (nổ BOM + lead time + safety stock), **không phải lập lịch hữu hạn công
suất và xếp thứ tự**. → CE không có, EE không có, OCA cũng không có.

**Bất đối xứng của hối tiếc:** tách thiếu → tách thêm sau, rẻ. Tách thừa → gộp lại phải di
trú dữ liệu và `ir.model.data`, đắt. Mọc theo seam, không chia trước.

**Tham khảo được** (nguyên tắc 2 của `03_engine.md` — tham khảo, không phụ thuộc bắt buộc):
`mrp_bom_version`, `mrp_warehouse_calendar`, `quality_control_oca`.

### 2.8 Cây file `htplus_base`

```
addons/htplus_base/
├── __manifest__.py                    depends: ['base', 'mail']
├── models/
│   ├── htplus_security_mixin.py       htplus.security.mixin       (dời từ planning_base)
│   ├── htplus_workflow_mixin.py       htplus.workflow.mixin       §4.1
│   ├── htplus_undo_mixin.py           htplus.undo.mixin           §4.2 — trên mail.tracking.value
│   ├── htplus_concurrency_mixin.py    htplus.concurrency.mixin    §4.3
│   └── htplus_job.py                  htplus.job                  §8.2
├── data/ir_cron_data.xml              cron kéo job
├── security/                          group kỹ thuật + ACL cho htplus.job
├── views/htplus_job_views.xml         list/form + menu Settings › Technical
└── README.md                          hợp đồng mở rộng — API công khai (§11.1)
```

**4 mixin + 1 model hạ tầng.** Phép thử giữ trung lập: không thành phần nào được biết
"nhà máy", "work order" hay "ca" là gì.

---

## 3. Tầng primitive Odoo — phải dùng, không viết lại

| Mối quan tâm | Primitive Odoo | Core thêm gì |
|---|---|---|
| Audit trail | `mail.thread` + `mail.tracking.value` (old/new theo field, gắn author + date) | chỉ **undo** + gom theo origin |
| State machine | *(không có — sale/purchase đều viết tay)* | transition khai báo + guard state nguồn |
| Lịch làm việc, khoảng thời gian | `resource.calendar._work_intervals_batch`, `plan_hours`, `plan_days` | — **cam kết dùng** |
| Chiếm dụng công suất | `resource.calendar.leaves` | ghi leave khi APS đặt lịch |
| Lập lịch hữu hạn | `mrp.production.button_plan`, `mrp.workorder._plan_workorders` | tối ưu + replan tương tác |
| Downtime / thời gian máy | `mrp.workcenter.productivity` + `block_reason*` | phân loại nghiệp vụ HTPlus |
| OEE | `mrp.workcenter.oee`, `oee_target`, `productive_time`, `blocked_time` | tổng hợp theo line/plant |
| Bảo trì thiết bị | `maintenance.equipment` (CE) | `_inherits` (§4.5) |
| Tham số cấu hình | `ir.config_parameter` + `res.config.settings` | — **bỏ `htplus.planning.parameter`** |
| Phân tách dữ liệu | `ir.rule`, `res.company`, `check_company=True` | rule theo factory (§6) |
| Báo cáo khối lượng lớn | model `_auto = False` trên PG view + `read_group` | định nghĩa KPI |
| Chạy nền | `ir.cron` | bảng job + trạng thái (§8.2) |
| Kỹ năng nhân sự | `hr.skill`, `hr.skill.level`, `hr.employee.skill` | matching skill ↔ workorder |

### Nợ kỹ thuật trong code — trạng thái as-built

1. **`htplus.planning.parameter`** (`htplus_rule.py:52`) — key/value unique, trùng
   `ir.config_parameter`. Mà `res.config.settings` đã `_inherit` ở
   `htplus_aps_core/models/htplus_settings.py` và **đã chuyển hẳn sang `config_parameter`**
   (`htplus_aps.*`, `htplus_shift.*`). **Nợ còn lại:** model `htplus.planning.parameter` chưa
   được gỡ khỏi code — không còn nơi nào đọc nó.

2. **Không cam kết vào `resource.calendar`** — `htplus_schedule.py:82` **vẫn còn**:

   ```python
   if calendar and hasattr(calendar, 'plan_hours'):
       try:
           return calendar.plan_hours(hours, start, compute_leaves=True)
       except Exception:      # noqa
           pass
   return start + timedelta(hours=hours)     # ← wall-clock, bỏ qua lịch
   ```

   `hasattr` + `except` trần = không tin API nền tảng. Rơi nhánh cuối thì lịch **bỏ qua
   calendar và leave mà không báo gì** — sai thầm lặng. **Nợ còn lại.**

3. ~~**Lập lịch không ghi `resource.calendar.leaves`**~~ — **SAI, đã đính chính 2026-08-10.**
   `mrp.workorder.date_start/date_finished` là computed có `inverse='_set_dates'`, và inverse
   đó **tự tạo/cập nhật `leave_id`**. Kiểm trên DB: 18/18 work order do APS đặt lịch đều có
   leave. Ghi là có, tự động.

   Lỗi thật nằm ở **chiều đọc**: cursor greedy chỉ tránh va chạm với work order *trong cùng
   một run*, không hề tra chỗ đã bị chiếm. Hai run khác nhau — hoặc một run và một
   `button_plan` thường của Odoo — đặt trùng giờ trên cùng máy mà không ai biết.
   Đã sửa ở P1 #8: dùng `workcenter._get_first_available_slot()`, đúng primitive
   `button_plan` dùng. **Nợ còn lại** (quyết định §5.1.1 đã chốt dùng
   `leave_id`, chưa triển khai).

4. **Không có `ir.rule` nào trong 4 module core** — **đã xoá.** `htplus_factory` giờ có bộ
   rule fail-closed cho factory/plant/line/workcenter/machine/holiday + nhóm
   `group_htplus_all_factories` (§6). `htplus_menu` cũng có.

5. **API controller nhiều khả năng đang chết** — `htplus_aps_core/controllers/htplus_api_controller.py`
   **vẫn còn**: `@http.route(type='json', methods=['GET'])` mâu thuẫn (route JSON của Odoo
   dispatch qua POST), và `request.jsonrequest` đã bị bỏ từ Odoo 17 (thay bằng
   `request.get_json_data()`). **Nợ còn lại** — `htplus_api` (§9) chưa thay thế.

## 4. Thành phần core

### 4.1 `htplus.workflow.mixin` — `htplus_base`

Odoo **không** có state machine khai báo. Vấn đề đang giải: 16 hàm `action_*`, **không hàm
nào check state nguồn**:

```python
# htplus_aps_core/models/htplus_demand_plan.py — hiện tại
def action_approve(self):
    self._htplus_require_manager()
    self.state = 'approved'        # gọi được từ draft, từ cancelled…
```

Bảo vệ duy nhất là `invisible` trên nút — mà action gọi được qua RPC. Không chỉ là DRY.

```python
class HtplusDemandPlan(models.Model):
    _inherit = ['mail.thread', 'htplus.workflow.mixin']

    _htplus_transitions = {
        'confirm': {'from': ('draft',),                        'to': 'confirmed', 'role': 'planner'},
        'approve': {'from': ('confirmed',),                    'to': 'approved',  'role': 'manager'},
        'plan':    {'from': ('approved',),                     'to': 'planned',   'role': 'planner'},
        'cancel':  {'from': ('draft', 'confirmed', 'approved'),'to': 'cancelled', 'role': 'planner'},
        'reset':   {'from': ('cancelled',),                    'to': 'draft',     'role': 'manager'},
    }
```

| Mixin cung cấp | Vai trò |
|---|---|
| `_htplus_apply_transition(code)` | role → state nguồn → `_htplus_guard_<code>()` → ghi state → `_htplus_after_<code>()` → **emit event (§9.2)** |
| `action_confirm/approve/lock/cancel/reset` | wrapper mỏng |
| `htplus_allowed_transitions` (computed) | view bind `invisible` vào đây, thôi hardcode domain state |
| `_htplus_group_map` | `{'planner': xmlid, …}` — `htplus_factory` nạp, dự án remap |
| `_htplus_guard_<code>()` / `_htplus_after_<code>()` | **hook công khai** |

Ghi vết dùng `mail.thread` (`state` đã `tracking=True`) — mixin không tự log.

**As-built:** mixin đã triển khai ở `htplus_base` đúng thiết kế — `_htplus_transitions`,
`_htplus_group_map` (được `htplus_factory` nạp qua `_inherit`), `_htplus_guard_<code>()`,
`_htplus_after_<code>()`, `_htplus_on_transition()` (seam event, hiện no-op), role chưa map = từ
chối. **Đã dùng:** `htplus.demand.plan` và `htplus.production.plan`. **Chưa dùng:** `schedule.run`
(đang tự viết `action_confirm`/`action_lock` với `_htplus_require_*`), các model shift/workorder
actual — vẫn gán `state` tay, thiếu kiểm state nguồn. `_htplus_apply_transition` hiện **chưa**
emit event (chờ §9.2).

**Mở đường `plan_lifecycle`** (gap #1 memo 04): lifecycle tổng hợp thành computed đọc state
các document qua interface chung.

### 4.2 Hoàn tác lịch — bảng log riêng (`htplus.schedule.change`), không undo mixin

Thiết kế gốc đề xuất `htplus.undo.mixin` đọc ngược `mail.tracking.value`. **As-built chốt khác
đi:** dùng **bảng log riêng nhỏ** `htplus.schedule.change` (chính là phương án dự phòng trong
bảng PoC §4.2 gốc) — ghi `schedule_run_id | workorder_id | user_id | field | old_value |
new_value | date_change` ở `write()` của `mrp.workorder`; `action_undo_change()` hoàn nguyên bản
ghi mới nhất; cron `HTPlus: Cleanup schedule change logs` (1 ngày) dọn theo tuổi (§2.5.1).

Vì sao chọn bảng riêng: đúng cảnh báo ở thiết kế gốc — `mail.tracking.value` là cấu trúc nội bộ
của Odoo, bị dọn theo `mail.message`, và đọc ngược ép kiểu theo `field.type` phức tạp hơn ghi
sẵn. `htplus.undo.mixin` (§4.2 gốc) **không triển khai** — không cần nữa với lịch; với master
data thì revert từng field là chuyện hiếm.

### 4.3 `htplus.concurrency.mixin` — `htplus_base`

Odoo dựa vào serialize của PostgreSQL + retry tầng RPC — đủ cho form thường, **không đủ** cho
Gantt kéo-thả (client giữ trạng thái cũ nhiều phút). Kéo cơ chế ở `htplus_schedule.py:624-672`
ra mixin, **giữ nguyên context key** `htplus_expected_write_date(s)` vì Gantt JS đang dùng.

**As-built:** mixin đã triển khai ở `htplus_base` — `_htplus_concurrency_fields`,
`_htplus_check_optimistic_lock()`, context key giữ nguyên. **Nợ còn lại:** `mrp.workorder`
(`htplus_schedule.py`) **không** inherit mixin mà tự viết `_htplus_check_optimistic_lock()` +
override `write()` gần trùng logic — gom về mixin để hết hai bản.

### 4.4 `htplus.mrp.bridge.mixin` — `htplus_factory`

`htplus.downtime` và `htplus.workorder.actual` mỗi cái tự viết `_sync_productivity()`,
`_mrp_loss_xmlid()`, tự giữ `productivity_id`. Gom lại:

| Cung cấp | Nội dung |
|---|---|
| `productivity_id` + `_sync_productivity()` | chuẩn hoá |
| `_htplus_loss_xmlid()` | **hook** — map category → `mrp.block_reason*` |
| `_htplus_sync_to_mrp()` / `_htplus_sync_from_mrp()` | hợp đồng 2 chiều |

**As-built: chưa gom.** `htplus.downtime` (`htplus_downtime.py:64/101`) và
`htplus.workorder.actual` (`htplus_workorder_actual.py:25/62`) vẫn mỗi nơi một bản
`_sync_productivity()` + `productivity_id` — đúng nợ thiết kế mô tả, còn lại.

### 4.5 `htplus.machine` — uỷ quyền sang `maintenance.equipment`

Ở **`htplus_factory_maintenance`** (bridge auto_install), không phải trong `htplus_factory` —
luật 2: core không depends app tuỳ chọn.

**As-built: chốt `Many2one`, đã triển khai.** Thiết kế (sửa 2026-08-10) chọn `Many2one`
thay `_inherits` sau review vòng 2, với ba lý do:

1. **Ngữ nghĩa là HAS-A, không phải IS-A.** Máy sản xuất *có* một thiết bị được bảo trì; nó
   không *là* một thiết bị bảo trì. `product.product → product.template` là quan hệ
   biến thể–mẫu, không tương đương.
2. **Tài liệu ORM của Odoo tự khuyến cáo tránh `_inherits` khi có thể.**
3. **`_inherits` kéo ACL của maintenance vào MES/APS** — xem bảng dưới, đây là cách hỏng
   nặng nhất và nó xảy ra với người dùng bình thường nhất (operator xưởng).

```python
class HtplusMachine(models.Model):
    _inherit = 'htplus.machine'

    equipment_id = fields.Many2one('maintenance.equipment', ondelete='set null',
                                   string='Maintenance Equipment')
```

`htplus.machine` giữ **danh tính sản xuất** (code, workcenter, capacity, setup time, status);
`equipment_id` mở đường sang MTBF/MTTR/maintenance request. Không required → khách chưa mua
module bảo trì thì machine vẫn chạy với `status` thủ công, và bridge không cần backfill chặn.

**Vòng nghiệp vụ vẫn nối được** — đó mới là giá trị thật: maintenance request mở →
`_htplus_sync_machine_status()` hạ `status` và ghi unavailability cho workcenter → **bộ giải
tự tránh máy đang sửa**. Vòng này cả CE lẫn EE đều không nối sẵn, và nó **không** đòi
`_inherits`.

**`_inherits` chỉ dùng nếu PoC chứng minh đáng đổi** — bảy điểm dưới, mỗi điểm một cách hỏng
thật. Fail bất kỳ điểm nào thì giữ `Many2one`:

| Kiểm | Cách hỏng |
|---|---|
| **Quyền đọc** | `_inherits` bắt buộc đọc được bản ghi uỷ quyền. Operator xưởng không thuộc nhóm maintenance → **đọc `htplus.machine` gãy** ← rủi ro lớn nhất |
| `unlink` | xoá machine kéo theo xoá equipment (`ondelete='cascade'`) — có đúng ý không? |
| `ir.rule` của `maintenance.equipment` | rule của module bảo trì lọc mất máy mà APS cần thấy |
| `check_company` | equipment và machine lệch company |
| `create` | field required của equipment chặn tạo máy nhanh |
| Di trú | máy đã có phải sinh equipment tương ứng, không được để `equipment_id` rỗng |
| RPC / report | `display_name`, `search`, export còn đúng |

Lợi ích duy nhất `_inherits` mang lại mà `Many2one` không có là *một bản ghi logic* — tiện
khi đọc/ghi field bảo trì ngay trên form máy. Cái giá là bảy rủi ro trên. Với sản phẩm giao
cho hàng trăm khách, đánh đổi này **không đáng** trừ khi PoC sạch cả bảy.

**As-built:** `equipment_id` (Many2one, `ondelete='set null'`) đã có ở
`htplus_factory_maintenance/models/htplus_machine_maintenance.py`, kèm `open_request_count`
(computed qua `_read_group`) và `action_open_maintenance_requests()`. Vòng "maintenance request
mở → hạ trạng thái máy" (`_htplus_sync_machine_status`) **chưa** nối đủ — request mới hiện chỉ
đếm và mở được, chưa tự hạ `status`/ghi unavailability cho bộ giải.

## 5. Lõi lập lịch — chỗ core thật sự tạo giá trị

```
Lớp 1  Ràng buộc & sự thật        Odoo sở hữu
       resource.calendar · resource.calendar.leaves · mrp.workcenter capacity · BOM · stock
Lớp 2  Bộ giải                    thay thế được, sau adapter
       rule_engine (mặc định, trong Odoo) │ solver CP-SAT (services/planning)
Lớp 3  Điều phối & quản trị       core sở hữu
       schedule.run + version + lock + conflict + undo + duyệt
```

### 5.1 Sáu loại sự thật — mỗi loại một chủ sở hữu

Nói "một nguồn sự thật về công suất" là chưa đủ chính xác. Lẫn các loại sự thật dưới đây là
nguồn gốc của phần lớn bug lập lịch — và cũng là nguồn gốc của việc vô tình dựng nhiều hệ
lịch sử song song:

| Loại sự thật | Chủ sở hữu | Nghĩa |
|---|---|---|
| **Working time** — khi nào *được phép* làm | `resource.calendar` | giờ làm việc, ca, nghỉ giữa ca |
| **Unavailability** — khi nào *không thể* làm | `resource.calendar.leaves` | nghỉ lễ, máy đang sửa, workcenter time-off |
| **Reservation** — chỗ đã bị chiếm bởi một phương án | `mrp.workorder.leave_id` → `resource.calendar.leaves` (§5.1.1) | WO001 chiếm máy A 10:00–11:00 |
| **Planning intent** — định làm gì | `htplus.schedule.run` + version + lock | phương án lịch, có thể chưa áp |
| **Execution** — thực tế đang/đã làm | `mrp.workorder` + MES actual | trạng thái thi hành |
| **Audit** — ai đổi gì lúc nào | `mail.thread` / `mail.tracking.value` | vết người dùng, **không** phải kho phiên bản nghiệp vụ |

Cộng thêm hai hệ **không** phải sự thật nghiệp vụ, dễ bị nhầm là:

| | |
|---|---|
| `htplus.job` | trạng thái **thi hành tác vụ nền** — không phải lịch sử nghiệp vụ |
| event / subscription | **thông báo tích hợp** ra ngoài — không phải nguồn sự thật |

**Quy tắc suy ra:** schedule run là *ý định*, work order là *thi hành*. Bộ giải **không** ghi
thẳng vào `mrp.workorder`; nó tạo/cập nhật một schedule run, người duyệt rồi mới **Apply**.

**Hoàn tác của lịch là khôi phục version, không phải revert từng field.** `schedule.run` đã
có version — `V3 → khôi phục V2` đúng ngữ nghĩa hơn nhiều so với đọc ngược `mail.tracking.value`.
Vì thế `htplus.undo.mixin` (§4.2) **không phải hạ tầng lõi** — as-built đã chọn bảng log riêng
`htplus.schedule.change` thay vì revert từng field qua tracking value (§4.2).

#### 5.1.1 Quyết định chốt: reservation qua `mrp.workorder.leave_id`

Bản trước ghi "Apply ghi `resource.calendar.leaves`". Hai lập luận trái chiều đều hợp lý:

| Lập luận | Nội dung |
|---|---|
| **Chống** — leaves là *unavailability*, không phải *allocation* | Nhồi mọi reservation của APS vào leaves thì `calendar._work_intervals_batch()` — thứ tính giờ làm việc cho ca, cho nhân sự, cho chính Odoo — sẽ đọc chúng như **thời gian không làm việc**. Biến allocation thành unavailability là sai ngữ nghĩa và lan sang mọi chỗ đọc calendar |
| **Ủng hộ** — Odoo có thể tự làm đúng như vậy | Các dòng Odoo trước, `mrp.workorder` có `leave_id` trỏ `resource.calendar.leaves`: **Odoo chính nó** dùng leaves làm chỗ chiếm của workorder. `02_database_schema.md` của dự án cũng ghi "backed bởi `resource.calendar.leaves`". Nếu 18 vẫn vậy mà ta dựng model riêng thì đó là **tự xây lại Odoo** — vi phạm §1.1 |

**ĐÃ XÁC MINH TRÊN ODOO 18 (2026-08-10, đọc source trong image `odoo:18.0`):**

```python
# odoo/addons/mrp/models/mrp_workorder.py
leave_id = fields.Many2one(
    'resource.calendar.leaves',
    help='Slot into workcenter calendar once planned',
    check_company=True, copy=False)
```

**Odoo 18 vẫn dùng `resource.calendar.leaves` làm chỗ chiếm của work order.** Kết luận:
**không dựng `htplus.capacity.reservation`** — làm thế là cài lại thứ nền tảng đã có, vi
phạm §1.1. APS ghi qua đúng `leave_id` của Odoo, gắn `origin = schedule_run_id` để xoá/ghi
lại sạch theo lô.

Nhưng một chi tiết quan trọng đi kèm: **phát hiện xung đột của Odoo KHÔNG đọc leaves.**
`mrp.workorder._get_conflicted_workorder_ids()` chạy SQL thuần trên chính bảng work order:

```sql
WHERE wo1.workcenter_id = wo2.workcenter_id
  AND (wo2.date_start, wo2.date_finished) OVERLAPS (wo1.date_start, wo1.date_finished)
```

Nghĩa là leaves là **hình chiếu sang lịch** (để calendar và các module khác thấy máy bận),
còn **sự thật về chồng lấn nằm ở `date_start`/`date_finished` của work order**. HTPlus phải
theo đúng phân vai đó:

| Việc | Cách làm |
|---|---|
| Ghi chỗ chiếm khi Apply | qua `leave_id` — cơ chế Odoo, không model mới |
| Phát hiện xung đột | SQL `OVERLAPS` như `_get_conflicted_workorder_ids`, **không** vòng lặp Python |
| Nhất quán công ty | `leave_id` đã `check_company=True` — khớp trục company ở §6 |

Nợ kỹ thuật phát sinh: `_htplus_mark_overlaps` hiện lặp bằng Python — thay bằng
`_get_conflicted_workorder_ids()` của Odoo (§7.2). **As-built: vẫn lặp Python, chưa thay.**

**As-built:** quyết định trên là chốt (đã xác minh Odoo 18), nhưng **chưa triển khai** —
`_htplus_attach_workorders` vẫn giữ cursor greedy riêng, không ghi `leave_id`/leaves; `algorithm`
trên `schedule.run` chọn `rule_engine`/`solver_cpsat` nhưng kết quả engine chỉ vào
`htplus.simulation.scenario.line` (bản sao ngày), không ghi reservation khi Apply (xem §5.2).

Dù ngả nào, **leaves vẫn là primitive phải dùng cho unavailability** (nghỉ lễ, bảo trì,
workcenter time-off) — không thay thế nó, chỉ không lạm dụng nó.

### 5.2 Biên giao dịch của Apply

Đây là chỗ dễ hỏng nhất và **phải chốt trước khi code**:

**Batch là một thực thể, không phải một khoảng thời gian.** Bản trước lấy "cửa sổ thời gian"
làm khoá chia lô — sai: 5.000 work order có thể rơi vào cùng một giờ, và một máy khác có thể
chỉ có 2. Kích thước lô phải do *số bản ghi* quyết định, thời gian chỉ là chiều lọc.

```
htplus.apply.batch    schedule_run_id | version | sequence
                      | workorder_ids | state(pending/running/done/failed)
                      | checksum | started_at | finished_at | error
```

| Vấn đề | Quyết định |
|---|---|
| Apply 10.000 work order trong một transaction? | **Không.** Chia thành `apply.batch` theo số bản ghi cố định, mỗi batch một transaction. Transaction dài khoá `mrp_workorder` và chết vì `limit_time_real` |
| Batch giữa chừng lỗi? | `batch.state = failed`; các batch khác không bị cuốn theo. Chạy lại đúng batch đó, **không làm lại từ đầu** |
| Bấm Apply hai lần? | `idempotency_key = (schedule_run_id, version, batch.sequence)` — **không phải** `(run, version)`, vì một lần Apply gồm nhiều batch. `checksum` trên tập input chặn cả trường hợp batch bị sửa nội dung giữa chừng |
| Ai được Apply? | role `manager`, qua `_htplus_apply_transition('apply')` — chung một cửa với mọi transition (§4.1) |
| Leave/reservation cũ của lần apply trước? | Xoá theo `origin = schedule_run_id` rồi ghi lại — không để bản ghi mồ côi tích tụ |

Apply chạy qua job layer (§8.2) — có retry, backoff, idempotency sẵn, không chặn worker.

#### 5.2.1 Hai loại xung đột, hai cơ chế khác nhau

`htplus_expected_write_date` (§4.3) chỉ giải **stale write** — client ghi đè bản ghi đã đổi.
Nó **không** giải **xung đột nghiệp vụ**, thứ xảy ra khi mọi bên đều ghi trên dữ liệu mới nhất:

```
APS Apply:      máy A  10:00–11:00
Maintenance:    máy A  10:30–12:00     ← không ai ghi đè ai, nhưng lịch vẫn sai
```

Các tác nhân có thể chạy đồng thời: planner A Apply · planner B sửa tay trên Gantt ·
`button_plan` của Odoo replan một MO khác · maintenance chặn workcenter.

| Loại | Cơ chế |
|---|---|
| Stale write | `htplus_expected_write_date` — concurrency mixin (§4.3) |
| Xung đột nghiệp vụ (chồng lấn khoảng) | Kiểm tra chồng lấn **ở tầng DB** khi Apply, không phải vòng lặp Python. PostgreSQL `EXCLUDE USING gist (resource_id WITH =, tstzrange(start, end) WITH &&)` là primitive đúng cho việc này |

Ràng buộc DB làm cho hai tiến trình đồng thời **không thể** cùng chiếm một khoảng — bất kể
tầng ứng dụng có kiểm hay không. Vị trí đặt ràng buộc phụ thuộc kết quả §5.1.1.

**As-built: chưa triển khai.** Không có `htplus.apply.batch`; `schedule.run` không dùng
workflow mixin; `action_confirm`/`action_lock` ghi `mrp.workorder` **một transaction** (đúng
kịch bản chết `limit_time_real` với 10k WO); không có idempotency_key, không xoá/ghi leaves
theo `origin`. Kết quả solver chỉ lưu vào simulation scenario — chưa có bước Apply thật.

### 5.3 Hợp đồng bộ giải

```python
def _htplus_resolve_scheduler(self, code):
    """Trả về callable(workorders, constraints) -> ScheduleResult.
    HOOK CÔNG KHAI — dự án thêm thuật toán bằng override + selection_add."""
```

`ScheduleResult` là **hợp đồng kiến trúc**, không phải dict tuỳ tiện:

```
ScheduleResult
├── assignments    [{workorder_id, date_start, date_finished, workcenter_id, machine_id}]
├── unassigned     [{workorder_id, reason}]          ← bộ giải được phép bó tay, phải nói vì sao
├── conflicts      [{workorder_id, kind, detail}]
├── objective      {name, value}                      ← so sánh được giữa các phương án
├── algorithm      'rule_engine' | 'solver_cpsat' | …  ← tự khai, kể cả khi fallback
├── explanation    text                               ← "AI kèm lý do" (03_engine.md)
└── metadata       {duration_ms, solver_status, seed, …}
```

`unassigned` và `explanation` là bắt buộc: bộ giải trả về ít hơn yêu cầu **phải** giải thích,
nếu không planner không có cơ sở để can thiệp tay.

Hợp đồng này thay cho `Selection` cứng ở `htplus_schedule.py:23` và kiểm tra tư cách thành
viên cứng ở `htplus_planning_bridge/models/htplus_schedule_run.py:21` — hiện thêm 1 thuật
toán phải sửa **cả hai file core**.

**Ràng buộc đưa vào bộ giải là data**, đọc từ `htplus.planning.rule` / `capacity.rule` /
`priority.rule` + `resource.calendar` — không hardcode trong Python.

**As-built — hợp đồng đúng một phần:** engine (`services/planning`) trả `schedule_result`
(workorder_id, workcenter_id, date_start, date_finished, priority, conflict, delay_hours,
score) + `kpi` + `model` (`greedy_fallback`). `algorithm` Selection trên `schedule.run` đã có
(`manual`/`rule_engine`/`solver_cpsat`). **Chưa có:** hook `_htplus_resolve_scheduler`,
`selection_add` (thêm thuật toán vẫn phải sửa file core), và các trường `unassigned` /
`explanation` / `objective` / `metadata` trong contract — bridge đọc thẳng `schedule_result`
chứ không nhận diện `algorithm`/`explanation` từ response.

## 6. Nhiều nhà máy — hai trục trực giao

Khách có cả hai kiểu. Core **không rẽ nhánh code**; luôn có **hai trục độc lập**, cấu hình
quyết định ánh xạ 1:1 hay N:1:

| Trục | Sở hữu | Lo việc | 1 pháp nhân | Nhiều pháp nhân |
|---|---|---|---|---|
| **Company** | Odoo native | pháp lý, sổ sách, kho | 1 company, rule no-op | 1 company / nhà máy |
| **Factory** | HTPlus | vận hành: lịch, ca, năng lực, KPI | N factory | 1 factory / company |

`htplus.factory.company_id` **required**; M2O liên nhà máy dùng `check_company=True`. Cùng bộ
code chạy cả hai kiểu — khác nhau ở số bản ghi `res.company`.

### 6.1 `htplus.factory.scope.mixin` (ở `htplus_factory`)

Thiết kế này ra đời vì ban đầu **không có `ir.rule` nào trong 4 module core** — phân tách dựa
vào domain trong action, user gọi RPC thẳng là đọc được hết. **Lỗ hổng phân quyền**, không phải
tính năng thiếu. **As-built: đã vá xong** — xem chú thích cuối §6.

Cách ngây thơ là `ir.rule` traverse quan hệ:

```python
# KHÔNG dùng — ir.rule chạy trên MỌI read/search; 3 tầng = 3 subquery mỗi truy vấn
[('workcenter_id.line_id.plant_id.factory_id', 'in', user_factory_ids)]
```

Giải bằng **phi chuẩn hoá có kiểm soát**:

```python
class HtplusFactoryScopeMixin(models.AbstractModel):
    _name = 'htplus.factory.scope.mixin'

    factory_id = fields.Many2one('htplus.factory', compute='_compute_htplus_factory',
                                 store=True, index=True, readonly=True)

    def _htplus_factory_path(self):
        """Đường dẫn tới factory. HOOK CÔNG KHAI — model nào cũng phải khai."""
        raise NotImplementedError
```

`mrp.workorder` → `'workcenter_id.line_id.plant_id.factory_id'`; `htplus.line` →
`'plant_id.factory_id'`. `ir.rule` còn lại **một điều kiện trên cột đã index**, không join:

```python
[('factory_id', 'in', user.htplus_factory_ids.ids)]
```

#### 6.1.1 Dùng field computed làm security boundary — năm điều kiện

Một field stored-computed dùng để phân quyền **không được phép lệch, dù chỉ một bản ghi**.
Lệch ở đây không phải lỗi hiển thị mà là **lộ dữ liệu**. Năm điều kiện bắt buộc:

**1. Chuỗi `@api.depends` phải đầy đủ đến từng mắt xích.**

```python
@api.depends('workcenter_id',
             'workcenter_id.line_id',
             'workcenter_id.line_id.plant_id',
             'workcenter_id.line_id.plant_id.factory_id')
```

Thiếu một mắt là chuyển workcenter từ nhà máy A sang B mà `workorder.factory_id` **vẫn còn A**
— user nhà máy A tiếp tục đọc được. Đây là lỗ hổng, không phải dữ liệu cũ.

**2. `compute_sudo` phải là quyết định tường minh.** Odoo mặc định `compute_sudo=True` cho
stored computed. Với field phân quyền phải hiểu rõ: giá trị **không được** phụ thuộc vào
quyền của người ghi — nếu không, hai user ghi cùng một bản ghi sẽ ra hai `factory_id`.

**3. Invariant kiểm được, không chỉ trông vào compute.** `@api.constrains` xác nhận
`factory_id == workcenter_id.line_id.plant_id.factory_id`, và một script đối soát chạy được
theo yêu cầu để phát hiện lệch tồn đọng sau di trú.

**4. Nhất quán company.** `factory_id.company_id` phải khớp `company_id` của chính bản ghi —
nếu không, hai trục phân quyền (§6) mâu thuẫn nhau.

**5. Recompute hàng loạt là sự kiện hiệu suất.** Đổi `line_id` của một workcenter kéo theo
recompute `factory_id` của **mọi** work order thuộc workcenter đó. Với lịch sử vài năm, thao
tác master data tưởng nhỏ này có thể chạy rất lâu — phải làm qua job (§8.2), không làm đồng bộ
trong form.

**6. Đổi phạm vi của user phải xoá cache của `ir.rule`.** Odoo cache domain của record
rule **theo từng user**. Ghi `htplus_factory_ids` mà không `env.registry.clear_cache()` thì
cấp hay thu hồi nhà máy **không có tác dụng** cho tới khi cache tình cờ bị xoá — quyền truy
cập âm thầm chạy theo phạm vi cũ. Đã xác minh trên DB thật: cấp nhà máy xong vẫn đọc được 0
bản ghi, xoá cache mới ra đúng. `res.users.write()` phải override.

**7. Suy ra factory phải phủ mọi liên kết có thể có.** `htplus.machine` gắn được vào
workcenter, line hoặc chỉ plant. Suy ra từ một đường duy nhất thì các bản ghi đi đường khác
có `factory_id` rỗng — mà rỗng nghĩa là **không ai thấy**, tức mất dữ liệu một cách im lặng.
Cũng đã gặp thật khi seed.

**Ghi chú về `sudo()`:** method public gọi được qua RPC, và ACL chỉ được kiểm ở tầng CRUD.
Mọi method dùng `sudo()` (`_apply`, `_sync`, job runner, import) phải có kiểm quyền tường minh
của riêng nó — `sudo()` bên trong một method public là chỗ lọt quyền kinh điển.

### 6.2 Mặc định phải fail-closed (sửa 2026-08-10)

Bản trước ghi "`htplus_factory_ids` rỗng = tất cả factory được phép" để tránh khoá chết admin
khi cài mới. **Sai.** Rỗng là trạng thái xảy ra do *chưa cấu hình, import lỗi, di trú thiếu,
user vừa tạo* — biến một lỗi cấu hình thành **lộ dữ liệu chéo giữa các nhà máy**. Mặc định
của cơ chế phân quyền phải fail-closed.

| | |
|---|---|
| `htplus_factory_ids` rỗng | **không thấy nhà máy nào** |
| Toàn quyền | nhóm tường minh `group_htplus_all_factories`, cấp có chủ đích |
| Cài mới / di trú | script gán `group_htplus_all_factories` cho admin sẵn có — một lần, tường minh |

`ir.rule`: `['|', ('factory_id', 'in', user.htplus_factory_ids.ids),
(user.has_group('...all_factories'))]` — nhóm toàn quyền là điều kiện tường minh trong rule,
không phải hệ quả của một tập rỗng.

Trục company do `ir.rule` mặc định của Odoo lo.

**As-built — §6 đã triển khai đủ:**
- `htplus.factory.scope.mixin` ở `htplus_factory` (`_htplus_factory_path` + `factory_id`
  stored/indexed, `readonly=False` để model sở hữu master data tự gán, `@api.constrains`
  `_check_htplus_factory_consistency` giữ invariant — đúng điều kiện 1–3);
- `res.users.htplus_factory_ids` + `SELF_READABLE_FIELDS` (đúng fail-closed §6.2);
- `ir.rule` fail-closed trong `htplus_factory/security/htplus_factory_rules.xml` — 2 rule/model
  (per-user lọc theo `factory_id`, nhóm `group_htplus_all_factories` = toàn bộ), cho
  factory/plant/line/workcenter/machine/holiday;
- điểm 6 (xoá cache `ir.rule` khi đổi scope) và 7 (path phủ mọi liên kết) **đã xác minh trên
  DB thật** và ghi cách tránh ngay trong thiết kế — xem hai điểm trên;
- `_htplus_group_map` nạp ở `htplus_factory/models/htplus_workflow_roles.py` (`user`/`planner`/
  `manager`/`operator`), group giữ xmlid cũ nên `ir.model.access.csv` không phải đổi.

## 7. Hiệu suất

**7.1 KPI chọn cơ chế theo quy mô, không mặc định PG view cho mọi thứ.**

| Loại | Cơ chế |
|---|---|
| Tổng hợp đơn giản trên tập vừa | `read_group` / `_read_group` |
| Dataset báo cáo dùng lại nhiều nơi | model `_auto = False` trên PG view (cách Odoo làm cho `sale.report`, `mrp.report`) |
| KPI rất lớn hoặc tính đắt (OEE nhiều năm, xuyên nhà máy) | bảng tổng hợp/materialized, cập nhật theo lô qua job |

Sai lầm phải tránh: `.filtered()` sau `search()` — kéo record vào RAM, không xuống SQL.
Dashboard hiện đang mắc ở `htplus_dashboard.py:112`.

**7.1.1 OEE — tổng hợp, không tính lại.** Odoo CE đã có OEE trên `mrp.workcenter`, tính từ
`mrp.workcenter.productivity`. MES của HTPlus **ghi actual/downtime/NG có phân loại nghiệp vụ
và đẩy vào productivity của Odoo** (§4.4); phần HTPlus thêm là **tầng tổng hợp** theo
factory/plant/line/machine/**ca** — chiều mà Odoo không có. Không dựng `htplus.oee` tính lại
availability/performance/quality từ đầu; đó là vi phạm §1.1.

**7.2 Không loop Python trên tập lớn.** Tổng hợp bằng `read_group`/`_read_group`; ghi hàng
loạt bằng một `write()` trên recordset.

**7.3 Gantt phân trang theo cửa sổ thời gian, không `limit` cứng.** `action_open_gantt` hiện
`search(limit=500)` (`htplus_schedule.py:364`) — **âm thầm cắt dữ liệu**. Đổi sang lọc theo
khoảng ngày đang xem + line đang xem, trả kèm tổng số. **As-built: chưa đổi — `limit=500` còn.**

**7.4 Index phải xuất phát từ query plan thật, không từ danh sách field.** Truy vấn APS thực
tế lọc đồng thời `factory_id` + `workcenter_id` + khoảng `date_start/date_finished` + `state`
+ `company_id` — thứ tự cột trong index quyết định nó có được dùng hay không. Trước khi chốt:
`EXPLAIN ANALYZE` trên dữ liệu cỡ thật + `pg_stat_statements`. Danh sách dưới là **điểm khởi
đầu**, không phải kết luận: `(workorder_id, date_start)` trên actual/downtime;
`(machine_id, date_start)` trên machine.stop; `(date)` trên forecast.line; thêm
`(schedule_run_id, date_start)` và `(workcenter_id, date_start)` trên `mrp.workorder`;
`factory_id` trên mọi model dùng scope mixin (§6.1).

## 8. AI & dịch vụ ngoài

### 8.1 Vấn đề hiện tại: chặn worker

`htplus_planning_service.py:_call` gọi `requests.post` **đồng bộ** trong worker Odoo. Solver
30s = giữ 1 worker 30s. Với `ODOO_WORKERS = 2×cores+1` (README), vài request song song là đói
worker toàn hệ — và `limit_time_real` giết worker trước khi solver trả lời.

**As-built: vẫn đúng — `_call` và `wait_job` (`htplus_planning_service.py`) chạy đồng bộ trong
worker, `wait_job` poll bằng `time.sleep`. Job nền nằm ở phía planning service (§8.2), không ở
Odoo, nên worker Odoo vẫn bị giữ trong lúc solver chạy.**

### 8.2 Job layer (ở `htplus_base`)

```
htplus.job    name | model | method | payload JSONB | state(pending/running/done/failed)
              | attempts | max_attempts | scheduled_at | started_at | finished_at
              | result JSONB | error | idempotency_key(unique) | origin_model/origin_id
```

`ir.cron` kéo job. Bấm "Run solver" → tạo job, trả về ngay, UI theo dõi state. Không thêm phụ
thuộc ngoài. Cần thông lượng cao hơn thì thay bằng OCA `queue_job` — job layer đã là interface.

**As-built — chưa có `htplus.job` ở Odoo.** Thay vào đó, **planning service tự chạy job nền**
(`services/planning/app/main.py`): submit trả `job_id` ngay, thread daemon tính kết quả, bridge
poll `/api/v1/job/{job_id}`. Lợi ích một phần (solver không chặn tiến trình FastAPI, đúng
contract async), nhưng **không** có retry/backoff/idempotency trên job Odoo, không có
`FOR UPDATE SKIP LOCKED`, và bridge vẫn chờ đồng bộ (§8.1). `htplus.job`/OCA `queue_job` chưa
quyết — quyết định 0c ở lộ trình gốc còn bỏ ngỏ.

### 8.3 Adapter chịu lỗi

Ranh giới hiện tại **đúng** (AbstractModel, endpoint `/api/v1/*` ổn định — `03_engine.md`
nguyên tắc 3). Thiếu phần chịu lỗi:

| Cần | Vì sao |
|---|---|
| Retry + backoff | lỗi mạng thoáng qua không nên thành lỗi nghiệp vụ |
| Circuit breaker | engine chết → chuyển thẳng rule engine, không treo hàng loạt |
| Idempotency key | job retry không tạo hai bộ đề xuất |
| Lưu request/response | "AI kèm lý do" cần truy vết được input đã gửi |
| Degraded mode hiển thị | cảnh báo rõ trên UI khi đang chạy fallback |

Response tự khai `algorithm` đã dùng (`moving_average_fallback` / `rule_fallback` /
`solver_cpsat`) — đã có, giữ. Mọi đề xuất kèm `explanation` + `payload` JSONB, người duyệt mới áp dụng.

**As-built — §8.3 chưa làm:** `htplus.planning.service` chỉ có timeout (`timeout=120`) chứ
không có retry/backoff, không circuit breaker, không lưu request/response, không degraded mode;
`_compute_htplus_result_summary` có `try/except` gọi `_resolve_result_model` nhưng chỉ bọc lỗi
kết quả, không phải fallback của adapter. Response engine trả `algorithm`
(`rule_fallback`/`solver_cpsat`) và `warnings`, nhưng bridge đọc thẳng — không dùng để quyết
định degraded mode.

## 9. Bề mặt tích hợp bên thứ ba — `htplus_api`

Nhà máy nào cũng đã có ERP/MES/SCADA/IoT. Tích hợp **không được** làm bằng cách bắt bên thứ
ba `_inherit` model core — làm thế thì mỗi lần core đổi là mọi connector gãy, và phụ thuộc
thành mạng nhện. Hai chiều, hai cơ chế:

### 9.1 Vào — REST có version

Controller hiện tại (`htplus_api_controller.py`) không có version, không có phân trang, và
nhiều khả năng **đang chết** (§3 nợ #5). Thay bằng:

- Đường dẫn `/htplus/api/v1/...`; **v1 không bao giờ đổi ngữ nghĩa**, thay đổi phá vỡ → v2.
- Xác thực bằng API key gắn user kỹ thuật (quyền đi qua `ir.rule` §6 — connector chỉ thấy
  nhà máy được cấp).
- Phân trang + filter chuẩn; không endpoint nào trả toàn bảng.
- Lỗi trả mã ổn định (`error.code`), không trả traceback.
- Ghi log request để đối soát khi khách kêu "dữ liệu không khớp".

**As-built — §9 chưa triển khai.** `htplus_api` vẫn là controller không version từ lúc đầu
(§3 nợ #5), chưa có API key gắn user kỹ thuật, chưa có event dispatcher/subscription, chưa có
webhook — giao tiếp ngoài hiện chỉ qua `htplus_api_controller` + `/htplus/api/*`. Chỉ "vào —
REST" ở dạng thô; "ra — event" chưa tồn tại.

### 9.2 Ra — event dispatcher (KHÔNG đặt trong `htplus_api`)

Tách ba tầng, vì gộp chúng vào `htplus_api` sẽ khiến **event nội bộ cũng phải depends module
API** — đúng kiểu phụ thuộc ngược mà §2.1 luật 3 cấm:

```
Domain event   (năng lực phát ra)        →  htplus.workflow.mixin emit
Dispatcher     (định tuyến, hạ tầng)     →  htplus_base  (hoặc module hạ tầng riêng)
Transport      (webhook / queue / nội bộ) →  htplus_api chỉ giữ transport webhook
```

Core **phát sự kiện**, connector **đăng ký**. Connector không cần biết model nào tồn tại.

```
htplus.event.subscription   code | active | transport(webhook/server_action) | url | secret
                            | factory_ids | retry_policy
```

- `htplus.workflow.mixin` emit tự động ở mỗi transition (§4.1):
  `demand.plan.approved`, `schedule.run.locked`, `workorder.actual.finished`…
- Giao qua `htplus.job` → có retry, backoff, idempotency sẵn (§8.2).
- Payload là **hợp đồng có version**, không phải dump `read()` — đổi field nội bộ không phá connector.

Nhờ đó connector `depends: htplus_api` thôi, **không** depends `aps`/`mes`/`workforce`. Đây là
luật 1 và 3 áp cho bên thứ ba.

## 10. Triển khai cho hàng trăm khách

| Câu hỏi | Hướng |
|---|---|
| Một DB cho tất cả hay mỗi khách một DB? | **Mặc định: mỗi khách một DB** — cô lập, backup/restore riêng, nâng cấp độc lập. Nhiều nhà máy của *cùng* khách nằm chung DB (§6). Đây là **mặc định, không phải bất biến kiến trúc**: DB-per-tenant-group hay chiến lược khác vẫn hợp lệ tuỳ isolation/SLA/chi phí hạ tầng. Ràng buộc thật sự là chiều ngược lại — **kiến trúc không được giả định một DB dùng chung**, nên phân tách phải nằm ở `ir.rule` (§6), không ở tầng triển khai |
| Trăm khách = trăm phiên bản? | **Không.** Release train: core có version chung, khách nâng theo đợt. Càng nhiều nhánh riêng thì chi phí vận hành càng phình |
| Sửa riêng cho khách? | `htplus_<customer>_*` **inherit**, không fork. Vi phạm = mất toàn bộ §11 |
| Nâng cấp core? | `migrations/` trong từng module core — bắt buộc từ phiên bản đầu, thêm sau rất đau |
| Khách mua thêm gói? | Cài thêm module, bridge tự bật (§2.5) — không migration |

Chi phí vận hành đến từ **số biến thể**, không từ số khách. Giữ biến thể trong *data* và
*module khách hàng*, không trong nhánh core.

## 11. Bề mặt mở rộng — điều kiện để "inherit, không fork"

**11.1 Hook `_htplus_*` là API công khai.** Cái gì dự án được override phải có tên và nằm
trong `htplus_base/README.md`. Còn lại là private, core đổi tự do.

**11.2 Không `Selection` cứng cho thứ dự án sẽ thêm.** Dự án dùng `selection_add`; core phân
giải bằng hook (§5), không bằng kiểm tra tư cách thành viên.

**11.3 Không data nghiệp vụ trong core.** `htplus_planning_base/data/htplus_skill_data.xml`
seed `hr.skill.type` với `noupdate="1"` — dự án sau **không sửa được bằng upgrade**, phải sửa
tay DB hoặc fork. Chuyển sang `htplus_demo_data`.

**11.4 Bên thứ ba dùng event + REST (§9), không `_inherit` model core.**

## 12. Định nghĩa "đủ dùng" — checklist thay cho cảm tính

Số module **không** đo được năng lực (§2.7). Thước đo là checklist này.

### A. Đủ nghiệp vụ

| | |
|---|---|
| Vòng Demand → … → Actual → KPI chạy E2E trên DB sạch | ✅ seed script |
| 22 màn catalog có đường đi nghiệp vụ | ✅ phần lớn (memo 04 §3) |
| Traceability lot/serial nối vào MES · Subcontracting · Scrap/unbuild · Quality · Costing | ❌ CE có, chưa đấu — **chỉ làm khi có khách cần** |

### B. Đủ vận hành ← nhóm yếu nhất

| | |
|---|---|
| Import master data hàng loạt (factory/line/WC/machine/employee/BOM/skill) | ❌ chỉ có 1 wizard import demand — mà mọi rollout bắt đầu từ đây |
| `migrations/` + quy ước script nâng cấp | ❌ chưa module core nào có |
| Nơi xem & cảnh báo: job fail, engine down, cron kẹt | ❌ (§8.2 giải một phần) |
| Degraded mode hiển thị rõ | ⚠️ có fallback, chưa có cảnh báo |
| Phân quyền chạy thật, kiểm qua RPC | ✅ **đã xong** — scope mixin + `ir.rule` fail-closed + nhóm toàn quyền (§6.2) |
| Backup / restore | ✅ mức stack (README) |
| i18n JA / VI / EN | ⚠️ có `i18n/` ở aps_core |
| Tài liệu cho **người vận hành** | ❌ |

### C. Đủ mở rộng

| | |
|---|---|
| Hook `_htplus_*` có tên + ghi trong README | ⚠️ bắt đầu hình thành (`_htplus_factory_path`, `_htplus_sync_*`, `_htplus_on_*`), **chưa có README chốt** |
| Không `Selection` cứng | ⚠️ `algorithm` vẫn là `Selection` cứng (`htplus_schedule.py`), chưa có `selection_add` |
| Không data nghiệp vụ trong core | ❌ |
| API có version + event bus | ❌ (§9) |
| Test core chạy được sau khi dự án override | ❌ **hoãn có chủ ý** |
| Version pin + luật không sửa file core | ⚠️ đã ghi, chưa cưỡng chế |

Nhóm B quyết định chữ "dễ vận hành" — **không giải được bằng chia nhỏ module, chỉ giải được
bằng công cụ.**

## 13. Lộ trình

### P−1 — Xác minh chặn ✅ đã chốt quyết định

| # | Việc | Chặn cái gì | Kết quả |
|---|---|---|---|
| 0a | Odoo 18 `mrp` lưu chỗ chiếm của workorder ở đâu (§5.1.1) | **toàn bộ P1** — quyết định có dựng `htplus.capacity.reservation` hay không | ✅ chốt dùng `leave_id` — proof-on-Standard-Odoo-18 (§5.1.1); **chưa triển khai ghi** |
| 0b | API controller có thực sự chết không (§3 nợ #5) | ưu tiên của REST v1 | ⚠️ còn tồn tại, không version, ít endpoint — **chưa đánh giá là chết** |
| 0c | Quyết định `htplus.job` tự viết **hay** OCA `queue_job` (§8.2) | P2 #13, và việc có tách module `htplus_job` riêng hay không | ⚠️ thực tế planning service tự chạy job nền; `htplus.job`/`queue_job` **chưa quyết** (§8.2) |

0c phải quyết trước 13: nếu chọn OCA thì câu hỏi tách module biến mất. Nếu tự viết, ghi rõ
trong doc **vì sao** đáng tự viết — "sau này thay được" không phải lý do.

### P0 — An toàn kiến trúc ✅ đã xong

| # | Việc | Đụng | Trạng thái |
|---|---|---|---|
| 1 | `htplus_base` + workflow mixin | module mới | ✅ `htplus_base` có; mixin dùng ở demand.plan / production.plan (chưa ở schedule.run/shift) |
| 2 | Di trú `demand.plan` + `production.plan` — **mẫu duyệt pattern** | aps | ✅ |
| 3 | Tách `htplus_factory` khỏi `planning_base`; gỡ `hr*`/`maintenance` khỏi nền | factory | ✅ module `htplus_factory` tách riêng, dep tối thiểu |
| 4 | Tách `htplus_workforce`; `htplus_mes` **thôi depends aps** | mes, workforce | ✅ |
| 5 | 5 bridge `auto_install` tầng 3 | bridge mới | ✅ 6 bridge, đều `auto_install=True` (§2.3) |
| 6 | `factory.scope.mixin` + `ir.rule` fail-closed + `group_htplus_all_factories` (§6.2) | factory + năng lực | ✅ |

### P1 — Đúng đắn APS (đang là **sai thầm lặng**, không phải thiếu tính năng)

| # | Việc | Đụng | Trạng thái |
|---|---|---|---|
| 7 | Bỏ `hasattr`/`except` quanh `plan_hours`; cam kết `resource.calendar` | aps | ❌ còn — lịch sản xuất vẫn không ghi `resource.calendar.leaves` (§3 nợ #3) |
| 8 | Apply ghi `resource.calendar.leaves` theo `origin` (§5.1) | aps | ❌ chưa |
| 9 | Biên giao dịch Apply: lô · `apply_state` · idempotency (§5.2) | aps | ❌ **chưa** — `action_confirm`/`action_lock` vẫn một transaction đồng bộ (§5.2) |
| 10 | Hợp đồng `ScheduleResult` + hook `_htplus_resolve_scheduler` (§5.3) | aps, engine_bridge | ⚠️ một phần — contract đã khớp (§5.3); hook `_htplus_resolve_scheduler`/`selection_add` **chưa có** |
| 11 | Concurrency mixin (giữ context key) | base, aps | ✅ `htplus.concurrency.mixin` + `_htplus_concurrency` context key |
| 12 | Di trú 6 model còn lại sang workflow mixin | aps, mes, workforce | ✅ 8 model, 14 transition |

### P2 — Vận hành & hiệu suất

| # | Việc | Đụng | Trạng thái |
|---|---|---|---|
| 13 | Job layer + `FOR UPDATE SKIP LOCKED` (§8.2); solver chạy nền | base, engine_bridge | ⚠️ một phần — planning service tự chạy job nền, bridge poll; chưa có `htplus.job` (§8.2) |
| 14 | Import master data hàng loạt — **trước rollout nhà máy thật đầu tiên** | factory | ❌ |
| 15 | Khung `migrations/` + quy ước nâng cấp — **phải có từ phiên bản đầu** | mọi module core | ❌ |
| 16 | Màn theo dõi sức khoẻ: job fail · engine down · cron kẹt · degraded mode | base, engine_bridge | ❌ |
| 17 | KPI → `_auto=False` PG view; Gantt phân trang theo cửa sổ | aps | ❌ — Gantt vẫn `limit=500` (§7.3) |
| 18 | Adapter chịu lỗi: retry/circuit breaker/idempotency/lưu I-O | engine_bridge | ❌ (§8.3) |
| 19 | Bỏ `htplus.planning.parameter` → `ir.config_parameter` · tách `htplus_demo_data` | factory | ❌ |
| 20 | Tài liệu vận hành cho người dùng | docs | ❌ |

### P3 — Mở rộng (chỉ khi có nhu cầu thật)

| # | Việc | Điều kiện kích hoạt | Trạng thái |
|---|---|---|---|
| 21 | Undo mixin | sau khi PoC `mail.tracking.value` đạt (§4.2) | ❌ **chọn hướng khác** — undo bằng `htplus.schedule.change` + cron dọn (§4.2) |
| 22 | `htplus_factory_maintenance`: machine `_inherits` equipment | sau khi PoC 7 điểm đạt (§4.5) | ✅ **thay đổi quyết định** — `Many2one equipment_id` (không `_inherits`) (§4.5) |
| 23 | mrp bridge mixin — gom `_sync_productivity` | khi có module thứ ba cần | ❌ |
| 24 | `htplus_api`: REST v1 + event bus | **khi có khách tích hợp thật** | ❌ |
| 25 | `plan_lifecycle` computed (gap #1 memo 04) | khi UI cần stepper | ❌ |

**Vì sao 24 xuống P3:** thiết kế webhook/subscription trước khi có một tích hợp thật là dựng
framework đẹp trên giấy. Hợp đồng ở §9 giữ nguyên làm định hướng; code chờ khách đầu tiên.
Riêng REST v1 có thể phải làm sớm hơn nếu §3 nợ #5 đúng — API hiện tại có thể **đang chết**.

### Test — quyết định để mở

Chủ dự án chốt 2026-08-10: chưa viết test giai đoạn này. Ghi lại nguyên trạng:

Các seam ở P0/P1 (workflow, phân quyền factory, `resource.calendar`, Apply, job, concurrency,
`_inherits`) đều thuộc loại **regression âm thầm** — hỏng mà không có triệu chứng cho tới khi
sai dữ liệu ở khách. Nếu sau này muốn mức tối thiểu thay vì bộ test đầy đủ, sáu ca sau là đủ
để chặn phần lớn rủi ro, mỗi ca vài chục dòng, viết ngay sau seam tương ứng:

```
workflow transition   · RPC/phân quyền factory · tính toán calendar
Apply idempotency     · job claim không trùng  · concurrency conflict
```

**Tài liệu liên quan:** `01_business_module_review.md` · `02_database_schema.md` ·
`03_engine.md` · `04_system_operation_memo.md`.
