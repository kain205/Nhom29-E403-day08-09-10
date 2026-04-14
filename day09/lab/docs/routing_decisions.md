# Routing Decisions Log — Lab Day 09

**Nhóm:** Nhóm 29 — E403  
**Ngày:** 14/04/2026

---

## Routing Decision #1

**Task đầu vào:**
> "Sản phẩm kỹ thuật số (license key) có được hoàn tiền không?"

**Worker được chọn:** `policy_tool_worker`  
**Route reason (từ trace):** `task contains policy/access keyword: ['hoàn tiền', 'license'] | mcp=True (worker will call MCP tools)`  
**MCP tools được gọi:** không có (chunks đã đủ)  
**Workers called sequence:** retrieval_worker → policy_tool_worker → synthesis_worker

**Kết quả thực tế:**
- final_answer: "Sản phẩm kỹ thuật số (license key) không được hoàn tiền theo Điều 3 chính sách v4."
- confidence: 0.42
- Correct routing? Yes

**Nhận xét:** Routing đúng — keyword "license" và "hoàn tiền" trigger policy_tool_worker. LLM detect đúng exception `digital_product` từ context. Trước khi fix, rule-based còn bắt thêm `flash_sale_exception` sai vì context chunks chứa chữ "Flash Sale". Sau khi chuyển sang LLM-only, chỉ còn 1 exception đúng.

---

## Routing Decision #2

**Task đầu vào:**
> "Ticket P1 lúc 2am. Cần cấp Level 2 access tạm thời cho contractor để thực hiện emergency fix. Đồng thời cần notify stakeholders theo SLA. Nêu đủ cả hai quy trình."

**Worker được chọn:** `policy_tool_worker`  
**Route reason (từ trace):** `task contains policy/access keyword: ['level 2'] | risk_high=True (triggered by: ['emergency', '2am']) | mcp=True (worker will call MCP tools)`  
**MCP tools được gọi:** `check_access_permission` (access_level=2, requester_role=contractor, is_emergency=True), `get_ticket_info` (ticket_id=P1-LATEST)  
**Workers called sequence:** retrieval_worker → policy_tool_worker → synthesis_worker

**Kết quả thực tế:**
- final_answer: Mô tả đủ 2 quy trình: cấp Level 2 tạm thời (có emergency bypass) + SLA P1 notifications
- confidence: 0.63
- Correct routing? Yes

**Nhận xét:** Đây là case MCP thực sự có giá trị. LLM round 1 xác định cần biết emergency bypass cho Level 2 → gọi `check_access_permission` qua MCP → nhận được `emergency_override=True` → round 2 kết luận chính xác. Nếu chỉ dùng retrieval, answer có thể thiếu thông tin về emergency bypass cụ thể.

---

## Routing Decision #3

**Task đầu vào:**
> "ERR-403-AUTH là lỗi gì và cách xử lý?"

**Worker được chọn:** `retrieval_worker` (qua human_review)  
**Route reason (từ trace):** `unknown error code with no policy/SLA context → escalate to human | risk_high=True`  
**MCP tools được gọi:** không có  
**Workers called sequence:** human_review → retrieval_worker → synthesis_worker

**Kết quả thực tế:**
- final_answer: "Không đủ thông tin trong tài liệu nội bộ để xác định lỗi ERR-403-AUTH và cách xử lý."
- confidence: 0.3 → hitl_triggered=True
- Correct routing? Yes (abstain đúng)

**Nhận xét:** Supervisor detect mã lỗi `ERR-` không rõ nguồn gốc → route qua human_review trước, sau đó vẫn chạy retrieval. Retrieval không tìm được thông tin liên quan → synthesis abstain đúng. Đây là behavior mong muốn — không hallucinate khi không có evidence.

---

## Routing Decision #4 — Trường hợp khó nhất

**Task đầu vào:**
> "Khách hàng đặt đơn ngày 31/01/2026 và yêu cầu hoàn tiền ngày 07/02/2026. Sản phẩm lỗi nhà sản xuất, chưa kích hoạt, không phải Flash Sale. Được hoàn tiền không?"

**Worker được chọn:** `policy_tool_worker`  
**Route reason:** `task contains policy/access keyword: ['hoàn tiền', 'flash sale'] | mcp=True`

**Nhận xét: Đây là trường hợp routing khó nhất trong lab. Tại sao?**

Đây là temporal scoping case — đơn đặt trước 01/02/2026 áp dụng policy v3, không phải v4. Supervisor route đúng sang policy_tool_worker, và LLM detect được `policy_version_note` về v3. Tuy nhiên không có doc v3 trong knowledge base nên không thể kết luận chính xác. Pipeline hiện tại kết luận dựa trên v4 (sai về mặt nghiệp vụ). Đây là giới hạn của hệ thống khi thiếu tài liệu — cần escalate sang human hoặc bổ sung doc v3.

---

## Tổng kết

### Routing Distribution

| Worker | Số câu được route | % tổng |
|--------|------------------|--------|
| retrieval_worker | 8 | 53% |
| policy_tool_worker | 7 | 47% |
| human_review | 1 (q09, sau đó tiếp tục retrieval) | 7% |

### Routing Accuracy

- Câu route đúng: 14 / 15
- Câu route có thể cải thiện: q12 (temporal scoping — cần escalate thay vì kết luận sai version)
- Câu trigger HITL: 1 (q09 — ERR-403-AUTH, confidence=0.3)

### Lesson Learned về Routing

1. **Keyword matching đủ dùng cho lab** nhưng dễ false positive (q12 bị trigger vì "flash sale" trong task dù không phải Flash Sale exception). LLM classifier sẽ chính xác hơn nhưng tốn thêm 1 API call.
2. **`route_reason` với mcp flag** giúp debug nhanh — nhìn trace biết ngay câu nào dùng MCP, câu nào không, không cần đọc code.

### Route Reason Quality

`route_reason` hiện tại format: `task contains X keyword: [list] | risk_high=True/False | mcp=True/False`. Đủ để debug routing. Điểm cải tiến: thêm confidence score của routing decision để biết supervisor "chắc" hay "đoán" khi chọn route.
