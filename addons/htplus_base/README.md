# HTPlus Base — hợp đồng mở rộng

Module này chứa **hạ tầng kỹ thuật** dùng chung cho toàn bộ HTPlus. Không model
nghiệp vụ, không menu ứng dụng, không data nghiệp vụ. Phép thử giữ trung lập:
**không thành phần nào ở đây được biết "nhà máy", "work order" hay "ca" là gì.**

Thiết kế đầy đủ: `docs/05_core_framework_design.md`.

---

## API công khai

Chỉ những tên dưới đây là API. Mọi thứ khác là nội bộ, core đổi tự do — dự án
override chúng thì tự chịu rủi ro khi nâng cấp.

### `htplus.workflow.mixin`

| Tên | Loại | Dùng để |
|---|---|---|
| `_htplus_transitions` | khai báo | định nghĩa các bước chuyển trạng thái hợp lệ |
| `_htplus_group_map` | khai báo | ánh xạ `role` → XML id của security group |
| `_htplus_guard_<code>()` | hook | chặn một transition; `raise UserError` kèm lý do |
| `_htplus_after_<code>()` | hook | side effect sau khi state đã đổi |
| `_htplus_on_transition(code, spec)` | hook | seam cho event dispatcher |
| `_htplus_apply_transition(code)` | gọi được | đường đi **duy nhất** để đổi state |
| `htplus_allowed_transitions` | field | bind `invisible` của nút trên view |

### `htplus.concurrency.mixin`

| Tên | Loại | Dùng để |
|---|---|---|
| `_htplus_concurrency_fields` | khai báo | field nào chạm vào thì kiểm tra bản cũ |
| `htplus_expected_write_date` | context key | **hợp đồng với client JS — không đổi tên** |
| `htplus_expected_write_dates` | context key | như trên, dạng lô |

---

## Cách dùng

```python
class HtplusDemandPlan(models.Model):
    _name = 'htplus.demand.plan'
    _inherit = ['mail.thread', 'htplus.workflow.mixin']

    state = fields.Selection([...], default='draft', tracking=True)

    _htplus_transitions = {
        'confirm': {'from': ('draft',),                         'to': 'confirmed', 'role': 'planner'},
        'approve': {'from': ('confirmed',),                     'to': 'approved',  'role': 'manager'},
        'cancel':  {'from': ('draft', 'confirmed', 'approved'), 'to': 'cancelled', 'role': 'planner'},
    }

    def _htplus_guard_approve(self):
        """Chỉ duyệt khi vật tư đã được kiểm."""
        self.line_ids.action_check_materials()
```

Tầng domain nạp `_htplus_group_map` **một lần**, bằng cách mở rộng chính mixin:

```python
class HtplusWorkflowMixin(models.AbstractModel):
    _inherit = 'htplus.workflow.mixin'

    _htplus_group_map = {
        'user':    'htplus_factory.group_aps_user',
        'planner': 'htplus_factory.group_aps_planner',
        'manager': 'htplus_factory.group_aps_manager',
    }
```

Nhờ vậy `htplus_base` **không** cần biết XML id của group nào. Các group được
khai báo ở `htplus_factory` và giữ nguyên tên cũ, nên `ir.model.access.csv` và
`has_group()` trên toàn bộ hệ thống không phải đổi.

---

## Ba luật khi dùng mixin

**1. Không bao giờ gán `state` trực tiếp.** `self.state = 'approved'` bỏ qua kiểm
tra state nguồn và kiểm tra quyền. Method public gọi được qua RPC, nên nút bị ẩn
trên view **không phải** là bảo vệ. Luôn đi qua `_htplus_apply_transition()`.

**2. `htplus_allowed_transitions` là gợi ý giao diện, không phải bảo mật.**
Dùng để ẩn/hiện nút. Thẩm quyền nằm ở `_htplus_apply_transition()`.

**3. `role` không phải hệ phân quyền thứ hai.** Nó là tên gọi tắt trỏ tới group
thật của Odoo. Thẩm quyền cuối cùng vẫn là group + ACL + `ir.rule`. Role thiếu
ánh xạ bị coi là **từ chối**, không phải cho phép.

---

## Chưa có ở phiên bản này

| | Vì sao |
|---|---|
| `htplus.job` | chờ quyết định tự viết hay dùng OCA `queue_job` (§13 P−1 mục 0c) |
| `htplus.undo.mixin` | với lịch, khôi phục version đúng ngữ nghĩa hơn revert từng field (§5.1) — P3 |
| Event dispatcher | chờ tích hợp thật đầu tiên (§13 P3) |
