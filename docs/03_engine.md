# Nguyên tắc kỹ thuật — HTPlus APS/MES (Odoo 18 CE)

**Cập nhật 2026-08-10** — tách từ `05_core_framework_design.md` thành tài liệu "cách làm" cho dự án.

## 1. Kế thừa, không tạo lại

`mrp.*`, `hr.*`, `resource.*` là nền tảng Odoo. Nghiệp vụ HTPlus dùng `_inherit` để mở rộng, không
dựng model trùng lặp. Khi định viết cơ chế mới, hỏi: *"Odoo có primitive nào chưa?"* —
`resource.calendar`, `mrp.workcenter.productivity`, `maintenance.equipment`, `ir.rule`,
`ir.config_parameter`, `mail.tracking.*`. Core không được import module app (05 §2.1) và không
được phụ thuộc app tùy chọn một cách ngầm.

## 2. Logic cộng đồng để tham khảo, không bắt buộc

Module OCA/community là nguồn tham khảo cách làm. Phần quan trọng (APS/MES/Shift/Capacity) không
bị phụ thuộc bắt buộc vào chúng.

## 3. Thư viện ngoài nằm sau adapter

Core nghiệp vụ không gọi thư viện ngoài trực tiếp. Gantt, solver, engine ngoài đều đi qua
interface/adapter (vd: `htplus.planning.service` gọi HTTP `services/planning`), để đổi engine sau
này không đụng logic nghiệp vụ. Adapter phải **chịu lỗi** — retry + circuit breaker + degraded
mode (05 §8.2–8.3). Bộ giải chạy **nền** qua job layer, không chặn web worker.

## 4. Business rule thuộc về HTPlus, biến thiên là DATA

Quy tắc APS/MES/Shift/Capacity/Approval do dự án sở hữu, không phó mặc cho Odoo. Cái gì biến
thiên theo nhà máy là **data, không phải code** (05 §1.2): ca/giờ nghỉ → `htplus.shift.template`,
quy tắc → rule model, ngưỡng KPI → `ir.config_parameter`. Nhà máy mới = thêm bản ghi.

## 5. Vertical slice + test

Mỗi lần mở rộng phải kèm smoke/integration test để luôn biết hệ thống còn chạy. **Seams cần test
(05 §13):** workflow, factory security, calendar math, Apply idempotency, job claim, concurrency.
Viết ngay khi bắt đầu P0/P1 — hiện đang hoãn có chủ ý.

## 6. Hợp đồng bộ giải `ScheduleResult` (05 §5.3)

Bộ giải (rule engine hoặc solver) trả về:

```
assignments  [{ workorder_id, resource_id, date_start, date_finished, priority, locked, meta }]
unassigned   [{ workorder_id, reason }]   ← BẮT BUỘC
conflicts    [{ workorder_id, resource_id, date_start, date_finished, type }]
objective    { name, value }
algorithm    { type: manual | rule_engine | solver_cpsat, version }
explanation  ← BẮT BUỘC (AI phải nói lý do, kể cả khi từ chối)
metadata     { timestamp, duration_ms, ... }
```

Không có contract này thì không được code năng lực APS. Payload này là **hợp đồng API riêng** —
engine không dùng ORM của Odoo.

## 7. Workflow khai báo, không gán state trực tiếp (05 §4.1)

Mọi chuyển state đi qua `htplus.workflow.mixin._htplus_apply_transition()`:

```python
_htplus_apply_transition('confirm')
# → role check → state nguồn → guard → ghi state → after → event
```

Role-check được vẽ **trước** state nguồn nên lệnh `confirm` đúng quyền luôn trả lỗi rõ ràng hơn.
Không gán `.state` trực tiếp. Thêm trạng thái bằng `selection_add`, không sửa `Selection` cứng.

## 8. Hook `_htplus_*` là API công khai (05 §11.1)

Cái gì khách/đối tác được override phải có tên `_htplus_*` + ghi trong `htplus_base/README.md`
(đang nợ — P2 #9). Còn lại là private, core đổi tự do. **Security:** mọi model dùng scope mixin
phải fail-closed với `ir.rule`; user không group quyền đặc biệt không thấy nhà máy nào (05 §6.1).

## 9. Bên thứ ba: event + REST, không `_inherit` core (05 §9.2)

Khi mở API cho khách tích hợp: event dispatcher + REST endpoint. Connector của khách không sửa
model core — tránh nợ upgrade. Kênh tích hợp bên ngoài (API/cron/bridge) không bypass quy tắc
nghiệp vụ; sự thật cuối cùng là model core, không phải cache.
