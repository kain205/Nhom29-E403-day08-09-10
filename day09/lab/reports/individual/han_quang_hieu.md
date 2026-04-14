# Báo Cáo Cá Nhân — Lab Day 09: Multi-Agent Orchestration

**Họ và tên:** Hàn Quang Hiếu  
**Vai trò trong nhóm:** MCP Owner + Trace & Docs Owner  
**Ngày nộp:** 14/04/2026  

---

## 1. Tôi phụ trách phần nào?

Tôi phụ trách Sprint 3 và Sprint 4 — MCP server, MCP integration trong policy worker, eval pipeline, và toàn bộ documentation.

**Module/file tôi chịu trách nhiệm:**
- File chính: `mcp_server.py`, `mcp_server_http.py`, `eval_trace.py`, `docs/`, `reports/`
- Functions tôi implement: `tool_search_kb`, `tool_get_ticket_info`, `tool_check_access_permission`, `tool_create_ticket`, `dispatch_tool`, `list_tools` trong mcp_server.py; toàn bộ FastAPI endpoints trong mcp_server_http.py; `_call_llm_policy`, `_get_mcp_tool_schemas`, `_coerce_tool_input`, `analyze_policy` (LLM-only refactor) trong policy_tool.py; `run_test_questions`, `analyze_traces`, `compare_single_vs_multi` trong eval_trace.py

**Cách công việc của tôi kết nối với phần của thành viên khác:**

`analyze_policy` trong policy_tool.py là điểm giao giữa Sprint 2 (Thành) và Sprint 3 (tôi). Thành implement `run()` entry point và basic structure, tôi refactor `analyze_policy` từ rule-based sang LLM-only và thêm MCP enrichment loop. Contract giữa hai phần là `policy_result` dict — tôi giữ nguyên output schema để synthesis worker của Thành không bị ảnh hưởng.

**Bằng chứng:**

`mcp_server.py`: 4 tools với `dispatch_tool()` và `list_tools()`. `mcp_server_http.py`: FastAPI server chạy được với `uvicorn mcp_server_http:app --port 8080`. `artifacts/traces/`: 15 trace files từ eval run.

---

## 2. Tôi đã ra một quyết định kỹ thuật gì?

**Quyết định:** LLM tự discover MCP tool schemas qua `list_tools()` thay vì hardcode parameter names trong prompt.

Ban đầu tôi hardcode schema trong `POLICY_ANALYSIS_PROMPT`:
```
"check_access_permission": tool_input schema: {"access_level": integer, "requester_role": "string"}
```

Khi chạy q15, LLM truyền `{"level": "2", "role": "contractor"}` — sai tên parameter và sai kiểu (string thay vì integer). Tôi có 2 cách fix: (1) hardcode schema đúng hơn trong prompt, hoặc (2) inject schema thực từ `list_tools()` vào mỗi LLM call.

Tôi chọn cách 2 vì đây là đúng tinh thần MCP — server là source of truth cho tool schemas, không phải prompt. Nếu sau này thêm tool mới hoặc đổi parameter name, chỉ cần sửa `mcp_server.py`, LLM tự biết.

```python
def _get_mcp_tool_schemas() -> str:
    from mcp_server import list_tools
    tools = list_tools()
    # Format schema thành text cho LLM đọc
    ...
```

**Trade-off đã chấp nhận:** Thêm 1 function call `list_tools()` mỗi lần gọi LLM. Overhead nhỏ (in-process call) nhưng đảm bảo schema luôn sync với server.

**Bằng chứng từ trace (q15 sau fix):**

```json
"mcp_tools_used": [
  {"tool": "check_access_permission", 
   "input": {"access_level": 2, "requester_role": "contractor", "is_emergency": true},
   "error": null}
]
```

---

## 3. Tôi đã sửa một lỗi gì?

**Lỗi:** Policy worker detect false positive exceptions cho câu hỏi thông tin — q02 ("hoàn tiền trong bao nhiêu ngày?") trả về 4 exceptions và `hitl_triggered=True`.

**Symptom:** Chạy eval, q02 có `policy_result.exceptions_found` gồm 4 items (flash_sale, digital_product, activated, mã_giảm_giá), `confidence=0.36`, `hitl_triggered=True`. Answer vẫn đúng nhưng policy_result hoàn toàn sai.

**Root cause:** Rule-based matching dùng `"flash sale" in context_text` — chunks từ `policy_refund_v4.txt` luôn chứa chữ "Flash Sale" vì đó là nội dung doc. Mọi câu retrieve được doc này đều bị dính exception. Ngoài ra `_is_complex_case` trả về `True` cho hầu hết câu policy → LLM đọc chunks thấy exceptions trong doc rồi list ra hết dù task không trigger chúng.

**Cách sửa:** Bỏ hoàn toàn rule-based, chuyển sang LLM-only. Thêm rule trong prompt:

```
Nếu task là câu hỏi thông tin (không phải request cụ thể) 
→ policy_applies=null, exceptions_found=[]
```

**Bằng chứng trước/sau:**

```
# Trước (q02):
exceptions_found: [flash_sale, digital_product, activated, mã_giảm_giá]
confidence: 0.36, hitl_triggered: True

# Sau (q02):
exceptions_found: []
policy_applies: null
explanation: "Câu hỏi chỉ yêu cầu thông tin về thời gian hoàn tiền..."
confidence: 0.56, hitl_triggered: False
```

---

## 4. Tôi tự đánh giá đóng góp của mình

**Tôi làm tốt nhất ở điểm nào?**

Thiết kế MCP server với `list_tools()` discovery pattern — LLM tự biết tool schemas mà không cần hardcode. Đây là điểm extensibility quan trọng: thêm tool mới vào `mcp_server.py` là đủ, không cần sửa prompt hay worker code. Ngoài ra việc implement HTTP server (`mcp_server_http.py`) với FastAPI cho phép test tools trực tiếp qua Swagger UI tại `localhost:8080/docs`.

**Tôi làm chưa tốt hoặc còn yếu ở điểm nào?**

Policy worker hiện chỉ gọi được 1 MCP tool per analysis round. q15 cần cả `check_access_permission` lẫn `get_ticket_info` — phải qua 2 rounds riêng biệt, tăng latency. Nếu có thêm thời gian, tôi sẽ implement multi-tool call trong 1 round.

**Nhóm phụ thuộc vào tôi ở đâu?**

`mcp_server.py` với `dispatch_tool()` — policy worker của Thành gọi `_call_mcp_tool` → `dispatch_tool`. Nếu tôi chưa implement MCP server, policy worker không có tool nào để gọi. Ngoài ra `eval_trace.py` và docs là deliverables cuối — nhóm cần tôi xong để nộp bài.

**Phần tôi phụ thuộc vào thành viên khác:**

Tôi cần `AgentState` schema và `worker_contracts.yaml` từ Thành để biết `mcp_tools_used` format và `needs_tool` flag. Ngoài ra `workers/policy_tool.py` structure từ Sprint 2 là base để tôi refactor `analyze_policy`.

---

## 5. Nếu có thêm 2 giờ, tôi sẽ làm gì?

Tôi sẽ implement multi-tool call trong 1 analysis round cho policy worker. Trace của q15 cho thấy pipeline gọi `check_access_permission` ở round 1, sau đó `get_ticket_info` ở round 2 riêng biệt — tổng latency 13401ms. Nếu LLM có thể request nhiều tools cùng lúc trong `needs_more_info` (dạng array thay vì single object), 2 MCP calls có thể chạy song song, giảm latency xuống còn ~8000ms cho complex queries như q15.
