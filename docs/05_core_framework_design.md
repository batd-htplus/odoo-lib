# Core Framework — khung MRP bán được cho nhiều nhà máy

**Cập nhật:** 2026-08-10 · **Trạng thái:** đã cài và chạy E2E trên Odoo 18 CE

Tài liệu này mô tả **hiện trạng đã triển khai**. Quyết định kiến trúc và lý do ở §9,
việc còn lại ở §10.

---

## 1. Mục tiêu

Dựng lớp khung trên Odoo 18 CE `mrp` để **bán và triển khai cho nhiều nhà máy**:

- Nhà máy mới là **cấu hình**, không phải module mới.
- Bán được **từng phần** — khách mua MES trước, APS sau.
- Bên thứ ba tích hợp được **không cần sửa lõi**.
- Phụ thuộc tối thiểu, có trật tự; chi phí vận hành thấp.

### Vì sao tự dựng thay vì mua Enterprise

| Enterprise **có** | Enterprise **không có** |
|---|---|
| `web_gantt`, `mrp_mps`, `quality`, `mrp_plm`, Shop Floor, `planning`, Barcode, IoT | **Bộ tối ưu lập lịch (APS)** — EE vẫn greedy tuần tự |
| | Phân cấp Factory→Plant→Line (EE dừng ở workcenter) |
| | Simulation what-if, phiên bản lịch, undo |
| | Lifecycle duyệt trên một *kế hoạch sản xuất* |
| | Gợi ý AI kèm lý do + degraded mode |

**OCA cũng không có.** `OCA/manufacture` có 54 module nhưng gần hết là *một field / một
nút / một report* vá lên `mrp`. `mrp_multi_level` ghi "Adds an MRP Scheduler" nhưng là
**hoạch định vật tư MRP-II**, không phải lập lịch hữu hạn công suất.

→ Lớp này không tồn tại ở CE, EE hay OCA. Đó là lý do đáng dựng.

---

## 2. Kiến trúc module

### 2.1 Bản đồ

```
Tầng 0   htplus_base                  base, mail
              │  hạ tầng kỹ thuật — không biết "nhà máy" là gì
              ▼
Tầng 1   htplus_factory               htplus_base, mrp, resource
              │  nền sản xuất: factory/plant/line/machine + phân quyền
    ┌─────────┼─────────┐
    ▼         ▼         ▼
Tầng 2   htplus_aps_core   htplus_mes_shopfloor   htplus_workforce
         NĂNG LỰC — bán riêng được, KHÔNG phụ thuộc nhau

Tầng 3   6 bridge auto_install — chỉ chứa phần nối giữa hai năng lực
Tầng 4   htplus_planning_bridge (engine AI) · htplus_menu · htplus_timeline_spike
```

### 2.2 Từng module

| Module | Ver | depends | Sở hữu |
|---|---|---|---|
| `htplus_base` | 1.1.0 | base, mail | 3 mixin + `htplus.job` |
| `htplus_factory` | 1.1.0 | htplus_base, mrp, resource | factory/plant/line/machine · security group · `ir.rule` · import master data |
| `htplus_aps_core` | 1.8.1 | htplus_factory, mail | demand · production plan · schedule run · Apply · simulation · dashboard · Gantt |
| `htplus_mes_shopfloor` | 1.2.6 | htplus_factory | actual · downtime · NG · issue · báo cáo ngày |
| `htplus_workforce` | 1.0.0 | htplus_factory, hr | shift · shift member · shift actual · **assignment** |
| `htplus_aps_workforce` | auto | aps + workforce | đề xuất phân công từ schedule run · KPI ca |
| `htplus_aps_mes` | auto | aps + mes | KPI thực thi trên dashboard APS |
| `htplus_mes_workforce` | auto | mes + workforce | confirm assignment → mở MES actual |
| `htplus_factory_maintenance` | auto | factory + maintenance | machine ↔ equipment · máy đang sửa thì không lên lịch |
| `htplus_workforce_skills` | auto | workforce + hr_skills | skill matching khi phân công |
| `htplus_workforce_holidays` | auto | workforce + hr_holidays | nghỉ phép hiện trên lịch ca |
| `htplus_planning_bridge` | 1.1.4 | htplus_aps_core | adapter HTTP → `services/planning` |

**~8.300 dòng Python**, 14 module.

### 2.3 Gói bán được

| Gói | Module | Bán cho |
|---|---|---|
| Shop Floor | base · factory · mes | nhà máy muốn theo dõi thực tích/downtime trước |
| Workforce | base · factory · workforce | quản lý ca & phân công |
| APS | base · factory · aps | lập kế hoạch & lịch |
| Full | tất cả — **bridge tự bật** | trọn vòng Demand→Actual |
| + AI | + planning_bridge | forecast / solver / gợi ý |

Khách mua thêm gói = cài thêm module, bridge `auto_install` tự xuất hiện.

### 2.4 Bốn luật phụ thuộc

| # | Luật | Kiểm bằng |
|---|---|---|
| 1 | **Module năng lực không depends module năng lực khác.** Nối chúng chỉ bằng bridge tầng 3 | đọc `depends` |
| 2 | **Core không depends app tuỳ chọn** (`hr_skills`, `hr_holidays`, `maintenance`) — keo đi vào bridge `auto_install` | đọc `depends` |
| 3 | **Phụ thuộc chỉ đi xuống tầng** — không ngang, không lên | đồ thị không chu trình |
| 4 | **Bridge không sở hữu domain độc lập.** Được phép chứa hành vi tích hợp; không được có aggregate riêng, menu ứng dụng riêng, vòng đời riêng | xem model/menu mới |

Luật 2 là pattern Odoo tự dùng (`sale_stock`, `mrp_account`): bridge `auto_install` tự
xuất hiện khi cả hai phía có mặt, nên tách bạch tối đa mà **không thêm thao tác vận hành**.

> `auto_install` *giảm* thao tác, không xoá được độ phức tạp: mỗi bridge vẫn là một module
> có version và đường nâng cấp.

### 2.5 Vì sao không nhiều module như OCA

OCA phục vụ hàng nghìn người dùng xa lạ, mỗi người muốn một 5% khác nhau — **độ hạt mịn
chính là sản phẩm của họ**. HTPlus bán **gói năng lực trọn vòng**; chia tới mức field thì
ta trả giá, không ai mua.

**Bất đối xứng của hối tiếc:** tách thiếu → tách thêm sau, rẻ. Tách thừa → gộp lại phải di
trú `ir_model_data`, đắt. Mọc theo nhu cầu thật, không chia trước.

---

## 3. Nguyên tắc

**3.1 Không cài lại primitive của Odoo.** Core = lớp *khai báo* trên primitive Odoo + đúng
phần Odoo không có. Bảng §4 là câu trả lời sẵn cho "Odoo có cái này chưa?".

**3.2 Cái gì biến thiên theo nhà máy phải là DATA.**

| Biến thiên | Nằm ở |
|---|---|
| Phân cấp, số line, workcenter | master data |
| Mẫu ca, giờ nghỉ, ngày nghỉ | `htplus.shift.template` → `resource.calendar` |
| Quy tắc công suất, ưu tiên | *chưa có* — xem ghi chú bên dưới |
| Ngưỡng KPI, mục tiêu OEE | `ir.config_parameter` + `mrp.workcenter.oee_target` |
| Bước duyệt | `_htplus_transitions` (khai báo) |
| Thuật toán lập lịch | hook + `selection_add` |

Hàng "quy tắc công suất, ưu tiên" hiện **chưa có chỗ đứng**. Ba model
`htplus.planning.rule` / `priority.rule` / `capacity.rule` từng chiếm ô đó nhưng
không bộ phận nào của solver đọc chúng, nên đã bị gỡ ở 18.0.1.8.2 thay vì để
người dùng cấu hình một thứ không có tác dụng. Khi làm capacity constraint thật,
schema sẽ do solver quyết định — nhiều khả năng khác với bản đã gỡ. Lịch sử git
giữ lại bản cũ nếu cần tham chiếu.

Chỉ tạo module `htplus_<customer>_*` khi nghiệp vụ **không thể** biểu diễn bằng cấu hình.

**3.3 Ranh giới module đi theo cái bán riêng được** (§2.3).

---

## 4. Primitive Odoo đang dùng

| Việc | Primitive | Core thêm gì |
|---|---|---|
| Audit trail | `mail.thread` + `mail.tracking.value` | — |
| Lịch làm việc | `resource.calendar.plan_hours` | — |
| Chỗ chiếm của work order | **`mrp.workorder.leave_id`** → `resource.calendar.leaves` | — |
| Tìm slot trống | `mrp.workcenter._get_first_available_slot()` | — |
| Phát hiện chồng lấn | `mrp.workorder._get_conflicted_workorder_ids()` (SQL `OVERLAPS`) | — |
| Downtime / thời gian máy | `mrp.workcenter.productivity` + `block_reason*` | phân loại nghiệp vụ |
| OEE | `mrp.workcenter.oee` | **tổng hợp** theo line/plant/ca, không tính lại |
| Tham số | `ir.config_parameter` + `res.config.settings` | — |
| Phân tách dữ liệu | `ir.rule`, `res.company`, `check_company` | rule theo factory (§6) |
| Báo cáo lớn | model `_auto = False` trên PG view | định nghĩa KPI |
| Chạy nền | `ir.cron` + `_trigger()` | bảng job (§8) |
| State machine | *(Odoo không có)* | `htplus.workflow.mixin` |

---

## 5. Các mixin

### 5.1 `htplus.workflow.mixin` — `htplus_base`

Odoo không có state machine khai báo. Trước đây 16 hàm `action_*` viết tay, **không hàm nào
check state nguồn** — mà action gọi được qua RPC, nên nút bị ẩn trên view không phải bảo vệ.

```python
class HtplusDemandPlan(models.Model):
    _inherit = ['mail.thread', 'htplus.workflow.mixin']

    _htplus_transitions = {
        'confirm': {'from': ('draft',),     'to': 'confirmed', 'role': 'planner'},
        'approve': {'from': ('confirmed',), 'to': 'approved',  'role': 'manager'},
    }

    def _htplus_guard_approve(self):
        """Chỉ duyệt khi vật tư đã kiểm."""
        self.line_ids.action_check_materials()
```

Động cơ lo: **role → state nguồn → guard → ghi state → after → event hook**.

| Thành phần | Vai trò |
|---|---|
| `_htplus_transitions` | khai báo bước chuyển hợp lệ |
| `_htplus_guard_<code>()` | hook chặn, `raise UserError` kèm lý do |
| `_htplus_after_<code>()` | hook side effect sau khi đổi state |
| `htplus_allowed_transitions` | view bind `invisible` vào đây — **gợi ý UI, không phải bảo mật** |
| `_htplus_group_map` | `role` → XML id group thật; **không phải hệ phân quyền thứ hai** |

**Phủ 7/7 document.** Luật: không bao giờ gán `state` trực tiếp.

### 5.2 `htplus.concurrency.mixin` — `htplus_base`

Optimistic lock cho view sống lâu (Gantt kéo thả). Client gửi lại `write_date` đã thấy;
ghi bị từ chối nếu bản ghi đã đổi.

```python
_htplus_concurrency_fields = ('date_start', 'date_finished', 'machine_id', 'line_id')
```

Context key `htplus_expected_write_date(s)` là **hợp đồng với client JS — không đổi tên**.

Chỉ bắt *stale write*. Xung đột nghiệp vụ (hai bên đều ghi dữ liệu mới nhưng khoảng chồng
nhau) cần kiểm ở tầng DB — xem §7.

### 5.3 `htplus.factory.scope.mixin` — `htplus_factory`

Xem §6.

### 5.4 `htplus.security.mixin` — `htplus_factory`

`_htplus_require_planner/manager` cho action **không phải** transition (check materials,
create MO…). Sẽ bỏ khi mọi chỗ dùng `_htplus_require_role`.

---

## 6. Phân quyền nhiều nhà máy

### 6.1 Hai trục trực giao

Khách có cả hai kiểu, core **không rẽ nhánh code**:

| Trục | Sở hữu | Lo việc |
|---|---|---|
| **Company** | Odoo | pháp lý, sổ sách, kho |
| **Factory** | HTPlus | vận hành: lịch, ca, năng lực, KPI |

Khách một pháp nhân = 1 company + N factory. Khách nhiều pháp nhân = 1 company mỗi nhà máy.
Cùng bộ code, khác số bản ghi `res.company`.

### 6.2 Cơ chế

`ir.rule` chạy trên **mọi** `read`/`search`. Viết kiểu traverse quan hệ
(`workcenter_id.line_id.plant_id.factory_id`) là 3 subquery mỗi truy vấn.

Giải bằng **phi chuẩn hoá có kiểm soát**: `factory_id` **stored + indexed** trên mọi model
có phạm vi, suy ra qua `_htplus_factory_path`. Rule còn lại một điều kiện trên cột đã index:

```python
[('factory_id', 'in', user.htplus_factory_ids.ids)]
```

**26 model được phủ**, mỗi model 2 rule.

### 6.3 Fail-closed

| | |
|---|---|
| `htplus_factory_ids` rỗng | **không thấy nhà máy nào** |
| Toàn quyền | group tường minh `group_htplus_all_factories` |

Rỗng là trạng thái xảy ra do *chưa cấu hình, import lỗi, di trú thiếu*. Coi rỗng = tất cả
sẽ biến một lỗi cấu hình thành lộ dữ liệu chéo.

### 6.4 Bảy điều kiện khi dùng field computed làm ranh giới bảo mật

Một `factory_id` lệch không phải lỗi hiển thị — đó là **user nhà máy A đọc dữ liệu B**.

1. **`@api.depends` phải phủ toàn bộ đường dẫn**, kể cả tiền tố. Thiếu một mắt là chuyển
   workcenter A→B mà `factory_id` vẫn còn A.
2. **`compute_sudo` phải là quyết định tường minh** — giá trị không được phụ thuộc quyền
   người ghi.
3. **`@api.constrains` xác nhận invariant** — dữ liệu còn đến từ import và SQL trực tiếp.
4. **Nhất quán company** giữa `factory_id.company_id` và `company_id` bản ghi.
5. **Recompute hàng loạt là sự kiện hiệu suất** — đổi line của một workcenter kéo theo
   recompute mọi work order của nó; phải qua job.
6. **Đổi phạm vi user phải xoá cache `ir.rule`.** Odoo cache domain theo từng user; không
   `registry.clear_cache()` thì cấp/thu hồi nhà máy **không có tác dụng**.
7. **Suy ra factory phải phủ mọi liên kết có thể có.** Machine gắn được vào workcenter,
   line hoặc chỉ plant — suy từ một đường thì các bản ghi khác có `factory_id` rỗng, tức
   **không ai thấy**.

> Điều 6 và 7 chỉ lộ ra khi chạy DB thật, checker tĩnh không bắt được.

### 6.5 Kiểm chứng

| Trạng thái planner | Kết quả |
|---|---|
| Không cấp nhà máy | 0 bản ghi ✅ |
| Cấp nhà máy | thấy đủ ✅ |
| Nhóm All Factories | thấy đủ ✅ |

`sudo()` bên trong method public là chỗ lọt quyền kinh điển — mọi method dùng nó
(`_apply`, `_sync`, job runner, import) phải kiểm quyền tường minh của riêng nó.

---

## 7. Lõi lập lịch

### 7.1 Sáu loại sự thật

Lẫn chúng là nguồn gốc phần lớn bug lập lịch:

| Loại sự thật | Chủ sở hữu |
|---|---|
| **Working time** — khi nào *được phép* làm | `resource.calendar` |
| **Unavailability** — khi nào *không thể* làm | `resource.calendar.leaves` |
| **Reservation** — chỗ đã bị chiếm | `mrp.workorder.leave_id` — **cơ chế Odoo** |
| **Planning intent** — định làm gì | `htplus.schedule.line` (+ version) |
| **Execution** — thực tế đang làm | `mrp.workorder` + MES actual |
| **Audit** — ai đổi gì lúc nào | `mail.thread` / `mail.tracking.value` |

Cộng hai hệ **không** phải sự thật nghiệp vụ: `htplus.job` là *trạng thái thi hành tác vụ*,
event là *thông báo tích hợp*.

**Odoo 18 tự ghi leave cho work order** — `date_start` là computed có `inverse='_set_dates'`,
và inverse đó tạo `leave_id`. Nên **không dựng model reservation riêng**; làm thế là cài lại
nền tảng.

Nhưng phát hiện chồng lấn của Odoo **không đọc leaves** — nó chạy SQL `OVERLAPS` trên chính
`date_start/date_finished`. Vậy leaves là *hình chiếu sang lịch*, sự thật chồng lấn nằm ở
ngày của work order.

### 7.2 Tìm slot

```python
start, end = workcenter._get_first_available_slot(horizon_start, duration_minutes)
```

Đúng primitive `button_plan` dùng. Nó tra leaves đang tồn tại nên slot rời khỏi **mọi** work
order đã lên lịch — kể cả từ run khác và downtime bảo trì.

Thiếu calendar thì **raise**, không rơi về wall-clock. Lịch bỏ qua ca/nghỉ mà trông vẫn
đúng là loại sai nguy hiểm nhất.

### 7.3 Hợp đồng `ScheduleResult`

Mọi scheduler trả về cùng một hình dạng, dù là rule engine trong Odoo hay CP-SAT sau HTTP:

```
ScheduleResult
├── assignments   [{workorder_id, date_start, date_finished, workcenter_id, machine_id}]
├── unassigned    [{workorder_id, reason}]     ← bắt buộc
├── conflicts     [{workorder_id, kind, detail}]
├── objective     {name, value}
├── algorithm     lấy từ RESPONSE, không phải request
├── explanation   text                          ← bắt buộc
└── metadata      {job_id, duration_ms, …}
```

Hai field mang sức nặng hơn vẻ ngoài:

- **`unassigned`** — scheduler được phép bó tay, **không được phép im lặng**. Planner không
  can thiệp được vào khoảng trống mà không ai báo.
- **`explanation`** — lịch không chất vấn được là lịch không tin được. Đây là thứ khiến gợi
  ý AI *xem xét được* chứ không chỉ *tuân theo*.

`validate()` cưỡng chế: mọi WO đưa vào phải quay ra dưới dạng **assigned hoặc
unassigned-kèm-lý-do**. `_htplus_store_result()` từ chối kết quả thiếu.

`algorithm` lấy từ response nên khi engine tụt về fallback, run ghi đúng cái **đã thực sự
chạy** — degraded mode nhìn thấy được.

Cắm engine riêng: override `_htplus_run_scheduler()` + `selection_add` trên `algorithm`.

### 7.4 Apply — biên giao dịch

Solver **không** ghi thẳng `mrp.workorder`. Nó tạo proposal, người duyệt, rồi Apply.

```
htplus.schedule.line    ý định     run_id · version · workorder_id · ngày đề xuất
htplus.apply.batch      giao dịch  sequence · line_ids · state · checksum
```

| Vấn đề | Quyết định |
|---|---|
| Apply 10.000 WO một transaction? | **Không.** 200 bản ghi/lô, mỗi lô một transaction. Transaction dài khoá `mrp_workorder` rồi chết vì `limit_time_real` |
| Lô lỗi giữa chừng? | lô đó `failed`, lô khác không bị cuốn theo. Chạy lại bỏ qua lô đã `done` |
| Bấm Apply hai lần? | idempotency key `(run, version, batch.sequence)` |
| Ai được Apply? | role `manager`, qua transition — chung cửa với mọi bước duyệt |

**Batch là thực thể, không phải khoảng thời gian.** 5.000 WO có thể rơi vào cùng một giờ,
và một máy có thể chỉ có 2 trong cả tuần — kích thước lô phải do *số bản ghi* quyết định.

Kiểm chứng (ép lô = 5, 18 proposal → 4 lô, làm hỏng lô 3):

```
batch states: ['done', 'done', 'failed', 'pending']
result:       {applied: 2, failed: 1, remaining: 2}
```

Lô 1–2 giữ nguyên, lô 4 **chưa đụng tới**.

### 7.5 Hai loại xung đột

| Loại | Cơ chế |
|---|---|
| Stale write (client giữ bản cũ) | `htplus_expected_write_date` — §5.2 |
| **Xung đột nghiệp vụ** (APS chiếm 10:00–11:00, bảo trì chặn 10:30–12:00 — không ai ghi đè ai) | kiểm chồng lấn ở tầng DB. PostgreSQL `EXCLUDE USING gist (resource_id WITH =, tstzrange WITH &&)` là primitive đúng |

Loại thứ hai **chưa làm** — xem §10.

---

## 8. Chạy nền, AI và dịch vụ ngoài

### 8.1 `htplus.job`

Gọi `requests.post` đồng bộ trong worker Odoo = solver 30 giây giữ 1 worker 30 giây. Với
`ODOO_WORKERS = 2×cores+1`, vài request song song là đói worker toàn hệ.

```
htplus.job   model | method | payload | state | attempts | max_attempts
             | scheduled_at | result | error | idempotency_key | origin
```

Ba điểm phải làm đúng, đều đã kiểm chứng bằng thực nghiệm:

**Claim phải bền, không dựa vào row lock.** Row lock kết thúc ở commit đầu tiên; claim bằng
`SELECT … FOR UPDATE SKIP LOCKED` rồi commit giữa các job sẽ để lô còn lại **mất khoá**.
Giải: một `UPDATE … WHERE id IN (SELECT … FOR UPDATE SKIP LOCKED) RETURNING id`, **commit
trước khi chạy bất cứ job nào**.

**Idempotency chỉ ràng buộc job còn sống.** Unique index *partial* trên
`state IN ('pending','running')` — khoá vĩnh viễn thì chạy lại cùng tác vụ sau khi xong sẽ
nổ thay vì tạo job mới.

**Kết quả không serialize được thì không được giết job.** Method trả recordset → rút gọn
thành `{model, ids, count}`, không để job `failed` và rollback công việc đã chạy đúng.

**Độ trễ:** `_enqueue()` gọi `ir.cron._trigger()` nên job được nhặt ở lần worker thức dậy kế
tiếp, không phải chờ hết chu kỳ 1 phút.

### 8.2 Adapter engine

Ranh giới đúng: `htplus.planning.service` là AbstractModel, endpoint `/api/v1/*` ổn định.
Đã có retry + backoff, circuit breaker, idempotency key, request log.

Engine chết → chuyển thẳng rule engine, `ScheduleResult.algorithm` ghi lại đúng cái đã chạy.

---

## 9. Quyết định đã chốt

| # | Quyết định | Lý do |
|---|---|---|
| 1 | **Không dựng `htplus.capacity.reservation`** | Odoo 18 đã dùng `mrp.workorder.leave_id`. Dựng model riêng là cài lại nền tảng |
| 2 | **`htplus.machine` dùng `Many2one` sang `maintenance.equipment`, không `_inherits`** | Máy *có* thiết bị bảo trì, không *là*. `_inherits` kéo ACL maintenance vào MES/APS → operator xưởng mất quyền đọc machine. Vòng nghiệp vụ "máy đang sửa thì không lên lịch" không đòi `_inherits` |
| 3 | **Tự viết `htplus.job`, không dùng OCA `queue_job`** | `queue_job` là LGPL-3 nên **không** vướng giấy phép — quyết định sát nút. Chọn tự viết vì: mỗi vendor addon là nghĩa vụ tương thích ở mỗi lần nâng Odoo (chậm hỗ trợ = mọi khách bị chặn nâng cấp); nó đòi đổi hạ tầng (`server_wide_modules` + runner), không chỉ thêm module; tải thực tế vài job/giờ chưa cần channel/priority. **Đổi khi** cần giới hạn đồng thời theo channel, hoặc job vượt vài nghìn/ngày |
| 4 | **Không tạo `htplus_demo_data`** | Sau khi tách module, core đã sạch data nghiệp vụ. Còn lại là 4 skill type + 4 level (taxonomy sản phẩm phải ship) và ~26 `hr.skill` không ai tham chiếu — tách chúng cần thêm một migration chuyển `ir_model_data`, thêm mảnh ghép nhiều hơn số bỏ đi |
| 5 | **Bỏ `noupdate="1"` khỏi skill taxonomy** | Nó khoá cứng dữ liệu: dự án sau không sửa được bằng upgrade, phải sửa tay DB hoặc fork |
| 6 | **Xoá `htplus.planning.parameter`** | Trùng `ir.config_parameter`, không code nào dùng, bảng rỗng |
| 7 | **Security group ở `htplus_factory`** | Là module mọi năng lực đều depends. `htplus_base` chỉ định nghĩa cơ chế, nạp xmlid qua `_htplus_group_map` |
| 8 | **Chưa viết test** (chủ dự án chốt) | Xem rủi ro ở §10 |

---

## 10. Trạng thái & việc còn lại

### Đã xong, đã kiểm chứng trên DB

- 14 module cài được, `-u all` sạch
- Seed E2E: 1 factory / 2 plant / 4 line / 4 machine → demand → plan (10 MO) →
  schedule run (18 WO, **0 conflict**) → 18 assignment → MES actual → shift actual
- Phân quyền factory: fail-closed đúng cả 3 trạng thái
- Apply: chia lô, idempotent, phục hồi sau lỗi
- Job: claim bền, retry/backoff, idempotency partial index
- Import master data: dry run không ghi, re-import không nhân bản
- Static check tự viết: **0 issue**

### Còn lại

| Việc | Vì sao chưa |
|---|---|
| **Test** | chủ dự án hoãn. Các seam (workflow, phân quyền, calendar, Apply, job, concurrency) thuộc loại **regression âm thầm** — hỏng mà không có triệu chứng cho tới khi sai dữ liệu ở khách. Sáu ca tối thiểu đủ chặn phần lớn rủi ro: workflow transition · phân quyền qua RPC · tính toán calendar · Apply idempotency · job claim · concurrency conflict |
| Ràng buộc chồng lấn ở DB (`EXCLUDE USING gist`) | §7.5 loại 2 — hiện chỉ kiểm ở tầng ứng dụng |
| `htplus_api` REST v1 + event bus | chờ khách tích hợp thật. API hiện có chưa version, chưa phân trang, `create_demand` chưa set `factory_id` |
| `plan_lifecycle` gộp | chờ UI cần stepper |
| `htplus_timeline_spike` | chưa cài, còn là spike |

---

## 11. Vận hành nhanh

```bash
make up                                  # dựng stack dev
make update M=htplus_aps_core            # nâng cấp một module
docker compose run --rm --no-deps -T odoo \
  odoo shell -d htplus_dev --no-http < scripts/seed_htplus_full.py   # seed demo
```

Tài khoản demo sau seed: `manager|planner|op1-3@htplus.demo`, mật khẩu `htplus123`.

**Lưu ý cho người mới:**

- User mới **không thấy gì** cho tới khi được cấp nhà máy (Users → HTPlus Factories) hoặc
  nhóm *All Factories*. Chưa cấp factory thì menu **HTPlus APS cũng ẩn luôn**, không chỉ
  chặn dữ liệu (xem `htplus_factory/models/ir_ui_menu.py`). Đây là chủ ý, không phải lỗi.
- Kế hoạch phải có **Factory** trước khi Confirm.
- Bridge `auto_install` tự bật khi cả hai phía cùng cài — không cài tay.

---

**Tài liệu liên quan:** `01_business_module_review.md` · `02_database_schema.md` ·
`03_engine.md` · `04_system_operation_memo.md` · `addons/htplus_base/README.md`
(hợp đồng mở rộng).
