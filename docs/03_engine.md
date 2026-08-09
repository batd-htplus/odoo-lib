# Nguyên tắc kỹ thuật

1. **Kế thừa, không tạo lại** — `mrp.*`, `hr.*`, `resource.*` là nền tảng Odoo. Nghiệp vụ HTPlus dùng `_inherit` để mở rộng, không dựng model trùng lặp.

2. **Logic cộng đồng để tham khảo, không bắt buộc** — module OCA/community là nguồn tham khảo cách làm; phần quan trọng (APS/MES/Shift/Capacity) không bị phụ thuộc bắt buộc vào chúng.

3. **Thư viện ngoài nằm sau adapter** — core nghiệp vụ không gọi thư viện ngoài trực tiếp. Mọi thứ bên ngoài (thư viện Gantt, solver...) đi qua interface/adapter (vd: `app/scheduler/` trong planning service), để sau này đổi engine không đụng logic nghiệp vụ.

4. **Business rule thuộc về HTPlus** — quy tắc APS/MES/Shift/Capacity/Approval do dự án tự sở hữu và kiểm soát, không phó mặc cho Odoo hay thư viện ngoài.

5. **Vertical slice + test** — mỗi lần mở rộng phải kèm smoke/integration test để luôn biết hệ thống còn chạy.
