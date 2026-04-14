# Báo Cáo Nhóm — Lab Day 09: Multi-Agent Orchestration

**Tên nhóm:** Nhóm 29 — E403  
**Thành viên:**
| Tên | Vai trò | Sprint |
|-----|---------|--------|
| Nguyễn Bình Thành | Supervisor Owner + Worker Owner | 1, 2 |
| Hàn Quang Hiếu | MCP Owner + Trace & Docs Owner | 3, 4 |

**Repo:** https://github.com/kain205/Nhom29-E403-day08  
**Độ dài khuyến nghị:** 600–1000 từ

---

> **Hướng dẫn nộp group report:**
> 
> - File này nộp tại: `reports/group_report.md`
> - Deadline: Được phép commit **sau 18:00** (xem SCORING.md)
> - Tập trung vào **quyết định kỹ thuật cấp nhóm** — không trùng lặp với individual reports
> - Phải có **bằng chứng từ code/trace** — không mô tả chung chung
> - Mỗi mục phải có ít nhất 1 ví dụ cụ thể từ code hoặc trace thực tế của nhóm

---

## 1. Kiến trúc nhóm đã xây dựng (150–200 từ)

> Mô tả ngắn gọn hệ thống nhóm: bao nhiêu workers, routing logic hoạt động thế nào,
> MCP tools nào được tích hợp. Dùng kết quả từ `docs/system_architecture.md`.

**Hệ thống tổng quan:**

Hệ thống gồm 1 Supervisor và 3 Workers chạy tuần tự: `retrieval_worker` → `policy_tool_worker` (nếu cần) → `synthesis_worker`. Supervisor đọc task, quyết định route dựa vào keyword, ghi `route_reason` vào state. Mỗi worker nhận state, xử lý phần việc của mình, trả state về để worker tiếp theo dùng. Toàn bộ execution path được ghi vào trace JSON.

**Routing logic cốt lõi:**

Keyword-based (không dùng LLM). Priority order: `human_review > policy_tool_worker > retrieval_worker`.

- `policy_keywords` ("hoàn tiền", "refund", "flash sale", "level 2/3", ...) → `policy_tool_worker`
- `sla_keywords` ("p1", "sla", "ticket", "escalation", ...) → `retrieval_worker`
- `err-xxx` không có keyword khác → `human_review`
- Mặc định → `retrieval_worker`

Khi route là `policy_tool_worker`: retrieval chạy trước để lấy context, rồi mới policy check.

**MCP tools đã tích hợp:**
> *(Sprint 3 — Hàn Quang Hiếu hoàn thiện)*

- `search_kb`: ___________________
- `get_ticket_info`: ___________________
- `check_access_permission`: ___________________

---

## 2. Quyết định kỹ thuật quan trọng nhất (200–250 từ)

> Chọn **1 quyết định thiết kế** mà nhóm thảo luận và đánh đổi nhiều nhất.
> Phải có: (a) vấn đề gặp phải, (b) các phương án cân nhắc, (c) lý do chọn phương án đã chọn.

**Quyết định:** ___________________

**Bối cảnh vấn đề:**

_________________

**Các phương án đã cân nhắc:**

| Phương án | Ưu điểm | Nhược điểm |
|-----------|---------|-----------|
| ___ | ___ | ___ |
| ___ | ___ | ___ |

**Phương án đã chọn và lý do:**

_________________

**Bằng chứng từ trace/code:**
> Dẫn chứng cụ thể (VD: route_reason trong trace, đoạn code, v.v.)

```
[NHÓM ĐIỀN VÀO ĐÂY — ví dụ trace hoặc code snippet]
```

---

## 3. Kết quả grading questions (150–200 từ)

> Sau khi chạy pipeline với grading_questions.json (public lúc 17:00):
> - Nhóm đạt bao nhiêu điểm raw?
> - Câu nào pipeline xử lý tốt nhất?
> - Câu nào pipeline fail hoặc gặp khó khăn?

**Tổng điểm raw ước tính:** ___ / 96

**Câu pipeline xử lý tốt nhất:**
- ID: ___ — Lý do tốt: ___________________

**Câu pipeline fail hoặc partial:**
- ID: ___ — Fail ở đâu: ___________________  
  Root cause: ___________________

**Câu gq07 (abstain):** Nhóm xử lý thế nào?

_________________

**Câu gq09 (multi-hop khó nhất):** Trace ghi được 2 workers không? Kết quả thế nào?

_________________

---

## 4. So sánh Day 08 vs Day 09 — Điều nhóm quan sát được (150–200 từ)

> Dựa vào `docs/single_vs_multi_comparison.md` — trích kết quả thực tế.

**Metric thay đổi rõ nhất (có số liệu):**

_________________

**Điều nhóm bất ngờ nhất khi chuyển từ single sang multi-agent:**

_________________

**Trường hợp multi-agent KHÔNG giúp ích hoặc làm chậm hệ thống:**

_________________

---

## 5. Phân công và đánh giá nhóm (100–150 từ)

> Đánh giá trung thực về quá trình làm việc nhóm.

**Phân công thực tế:**

| Thành viên | Phần đã làm | Sprint |
|------------|-------------|--------|
| Nguyễn Bình Thành | graph.py (supervisor routing, state, worker wiring), workers/retrieval.py, workers/policy_tool.py, workers/synthesis.py, build_index.py, contracts update | 1, 2 |
| Hàn Quang Hiếu | mcp_server.py, MCP integration trong policy_tool, eval_trace.py, docs templates, group report | 3, 4 |

**Điều nhóm làm tốt:**

_________________

**Điều nhóm làm chưa tốt hoặc gặp vấn đề về phối hợp:**

_________________

**Nếu làm lại, nhóm sẽ thay đổi gì trong cách tổ chức?**

_________________

---

## 6. Nếu có thêm 1 ngày, nhóm sẽ làm gì? (50–100 từ)

> 1–2 cải tiến cụ thể với lý do có bằng chứng từ trace/scorecard.

_________________

---

*File này lưu tại: `reports/group_report.md`*  
*Commit sau 18:00 được phép theo SCORING.md*
