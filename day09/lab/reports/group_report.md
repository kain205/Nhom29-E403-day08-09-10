# Báo Cáo Nhóm — Lab Day 09: Multi-Agent Orchestration

**Tên nhóm:** Nhóm 29 — E403  
**Thành viên:**
| Tên | Vai trò | 
|-----|---------|
| Nguyễn Bình Thành | Supervisor Owner + Worker Owner (Sprint 1, 2) |
| Hàn Quang Hiếu | MCP Owner + Trace & Docs Owner (Sprint 3, 4) |

**Ngày nộp:** 14/04/2026  

---

## 1. Kiến trúc nhóm đã xây dựng

Hệ thống gồm 1 Supervisor và 3 Workers kết nối qua shared `AgentState`. Supervisor phân tích task bằng keyword matching và quyết định route sang một trong ba nhánh: `retrieval_worker`, `policy_tool_worker`, hoặc `human_review`. Sau đó `synthesis_worker` luôn chạy để tổng hợp answer cuối.

**Routing logic cốt lõi:**

Supervisor dùng keyword matching theo 3 nhóm: (1) policy/access keywords (`hoàn tiền`, `refund`, `cấp quyền`, `license`, `flash sale`) → `policy_tool_worker`; (2) SLA/ticket keywords (`P1`, `SLA`, `ticket`, `escalation`) → `retrieval_worker`; (3) mã lỗi không rõ (`ERR-`) → `human_review`; còn lại → `retrieval_worker`. Mỗi quyết định được ghi vào `route_reason` kèm `mcp=True/False` để trace.

**MCP tools đã tích hợp:**

- `search_kb`: Tìm kiếm Knowledge Base qua ChromaDB — dùng khi policy worker không có chunks
- `get_ticket_info`: Tra cứu trạng thái ticket real-time — gọi trong q13, q15 để xác nhận P1 đang active
- `check_access_permission`: Kiểm tra emergency bypass theo access level — gọi trong q13, q15 để xác nhận Level 2/3 có bypass không
- `create_ticket`: Tạo ticket mock — available nhưng chưa được trigger trong 15 test questions

Ví dụ trace có MCP (q15): `mcp_tools_used: [check_access_permission(access_level=2, is_emergency=True), get_ticket_info(P1-LATEST)]`

---

## 2. Quyết định kỹ thuật quan trọng nhất

**Quyết định:** Bỏ hoàn toàn rule-based exception detection trong policy worker, chuyển sang LLM-only analysis.

**Bối cảnh vấn đề:**

Ban đầu policy worker dùng keyword matching để detect exceptions (flash_sale, digital_product, activated_product). Khi chạy eval, q02 ("hoàn tiền trong bao nhiêu ngày?") trả về 4 false positive exceptions và `hitl_triggered=True` dù đây chỉ là câu hỏi thông tin. Root cause: rule-based match `"flash sale" in context_text` — chunks luôn chứa chữ "Flash Sale" vì đó là nội dung của policy doc.

**Các phương án đã cân nhắc:**

| Phương án | Ưu điểm | Nhược điểm |
|-----------|---------|-----------|
| Fix rule-based (chỉ match task, không match context) | Nhanh, không tốn API | Vẫn dễ false positive với edge cases |
| Hybrid: rule-based + LLM cho complex cases | Tiết kiệm API calls | Logic phức tạp, khó maintain |
| LLM-only với structured JSON output | Hiểu ngữ cảnh, phân biệt câu hỏi thông tin vs request | Tốn thêm 1 API call mỗi policy query |

**Phương án đã chọn:** LLM-only. Prompt yêu cầu LLM trả về `policy_applies=null` cho câu hỏi thông tin, chỉ detect exceptions khi task là request cụ thể. Thêm field `needs_more_info` để LLM chủ động yêu cầu MCP data khi cần.

**Bằng chứng từ trace:**

```
# Trước khi fix (q02):
policy_result: {policy_applies: false, exceptions_found: [flash_sale, digital_product, activated, mã_giảm_giá]}
hitl_triggered: true, confidence: 0.36

# Sau khi fix (q02):
policy_result: {policy_applies: null, exceptions_found: [], explanation: "Câu hỏi chỉ yêu cầu thông tin..."}
hitl_triggered: false, confidence: 0.56
```

---

## 3. Kết quả grading questions

Grading questions chưa được public tại thời điểm nộp báo cáo (public lúc 17:00). Dựa trên kết quả 15 test questions:

**Câu pipeline xử lý tốt nhất:**
- q07 (license key không được hoàn tiền) — LLM detect đúng `digital_product` exception, answer rõ ràng, confidence=0.42
- q15 (Level 2 emergency + SLA notifications) — MCP được gọi đúng 2 tools, answer đủ cả 2 quy trình, confidence=0.63

**Câu pipeline fail hoặc partial:**
- q12 (temporal scoping — đơn trước 01/02/2026) — Pipeline detect được `policy_version_note` về v3 nhưng không có doc v3 → kết luận dựa trên v4. Root cause: thiếu tài liệu policy v3 trong knowledge base.
- q09 (ERR-403-AUTH) — Abstain đúng nhưng không cung cấp được hướng xử lý. Root cause: không có doc về error codes.

**Câu abstain (q09):** Pipeline route qua `human_review` → retrieval → synthesis abstain với "Không đủ thông tin trong tài liệu nội bộ." Đúng behavior — không hallucinate.

**Câu multi-hop khó nhất (q15):** Trace ghi được cả 2 workers (`retrieval_worker` + `policy_tool_worker`) và 2 MCP calls. Answer đủ cả quy trình cấp quyền lẫn SLA notifications.

---

## 4. So sánh Day 08 vs Day 09

**Metric thay đổi rõ nhất:**

Latency tăng từ ~2000ms (Day 08) lên ~5883ms (Day 09) — tăng ~3x do multi-agent gọi nhiều LLM calls hơn. Đây là trade-off chấp nhận được vì đổi lại có routing visibility và policy accuracy cao hơn.

**Điều nhóm bất ngờ nhất:**

LLM trong policy worker tự động discover MCP tool schemas qua `list_tools()` và tạo đúng `tool_input` mà không cần hardcode parameter names trong prompt. Khi LLM truyền sai tên parameter (`level` thay vì `access_level`), fix đúng chỗ là expose schema từ server — không phải sửa prompt.

**Trường hợp multi-agent không giúp ích:**

Câu hỏi đơn giản như q01 (SLA P1 bao lâu), q04 (tài khoản bị khóa), q05 (remote mấy ngày) — single agent RAG đủ dùng và nhanh hơn 3x. Supervisor overhead không có giá trị cho những câu này.

---

## 5. Phân công và đánh giá nhóm

**Phân công thực tế:**

| Thành viên | Phần đã làm | Sprint |
|------------|-------------|--------|
| Nguyễn Bình Thành | graph.py (AgentState, supervisor_node, route_decision, build_graph), workers/retrieval.py, workers/policy_tool.py (ban đầu), workers/synthesis.py | 1, 2 |
| Hàn Quang Hiếu | mcp_server.py, mcp_server_http.py, workers/policy_tool.py (LLM-only refactor + MCP integration), eval_trace.py, docs/, reports/ | 3, 4 |

**Điều nhóm làm tốt:**

Tách rõ contract trước khi implement — `worker_contracts.yaml` định nghĩa input/output từ đầu giúp Sprint 2 và Sprint 3 làm song song mà không conflict. Trace format nhất quán giúp debug nhanh khi có vấn đề.

**Điều nhóm làm chưa tốt:**

Policy worker ban đầu dùng rule-based quá đơn giản, phải refactor lại hoàn toàn ở Sprint 3. Nếu thiết kế LLM-only từ đầu sẽ tiết kiệm thời gian.

**Nếu làm lại:**

Thiết kế policy worker với LLM từ Sprint 2, không qua bước rule-based. Và bổ sung tài liệu policy v3 vào knowledge base ngay từ đầu để xử lý temporal scoping cases.

---

## 6. Nếu có thêm 1 ngày, nhóm sẽ làm gì?

Thêm LLM classifier cho supervisor thay vì keyword matching. Trace cho thấy q12 bị route sai keyword trigger ("flash sale" trong task dù không phải Flash Sale exception case) — LLM classifier sẽ hiểu intent thay vì match từ khóa. Ngoài ra bổ sung policy v3 vào knowledge base để xử lý đúng temporal scoping — q12 hiện tại là điểm yếu rõ nhất của pipeline.
