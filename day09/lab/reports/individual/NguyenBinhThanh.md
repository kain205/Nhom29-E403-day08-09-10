# Báo Cáo Cá Nhân — Lab Day 09: Multi-Agent Orchestration

**Họ và tên:** Nguyễn Bình Thành  
**Vai trò trong nhóm:** Supervisor Owner + Worker Owner  
**Ngày nộp:** 14/04/2026  

---

## 1. Tôi phụ trách phần nào?

Tôi phụ trách Sprint 1 và Sprint 2 — toàn bộ orchestration layer và workers.

**Module/file tôi chịu trách nhiệm:**
- File chính: `graph.py`, `workers/retrieval.py`, `workers/policy_tool.py`, `workers/synthesis.py`
- Functions tôi implement: `AgentState`, `supervisor_node`, `route_decision`, `human_review_node`, `retrieval_worker_node`, `policy_tool_worker_node`, `synthesis_worker_node`, `build_graph`, `run_graph`, `save_trace`; `retrieve_dense` trong retrieval.py; `analyze_policy`, `run` trong policy_tool.py; `synthesize`, `_build_context`, `_estimate_confidence` trong synthesis.py

**Cách công việc của tôi kết nối với phần của thành viên khác:**

`AgentState` là contract trung tâm — Hiếu cần biết chính xác các fields (`mcp_tools_used`, `policy_result`, `needs_tool`) để implement MCP integration trong Sprint 3. Tôi define `worker_contracts.yaml` cùng với code để Hiếu có thể implement MCP server đúng output format mà không cần đợi tôi xong.

**Bằng chứng:**

`graph.py` line 27–55: định nghĩa `AgentState` với đầy đủ fields. `workers/retrieval.py`: standalone test chạy được với `python workers/retrieval.py`. `workers/synthesis.py`: standalone test với 2 test cases.

---

## 2. Tôi đã ra một quyết định kỹ thuật gì?

**Quyết định:** Thiết kế `build_graph` theo Option A (Python thuần, không dùng LangGraph) với pre-fetch retrieval trước policy worker.

Khi implement graph, tôi có 2 lựa chọn: dùng LangGraph `StateGraph` với conditional edges (đúng chuẩn), hoặc implement bằng Python if/else đơn giản. Tôi chọn Python thuần vì lab chỉ có 4 giờ và LangGraph có learning curve — thêm dependency không cần thiết khi logic routing đơn giản.

Quyết định quan trọng hơn là pre-fetch chunks trước khi policy worker chạy:

```python
elif route == "policy_tool_worker":
    state = retrieval_worker_node(state)   # pre-fetch
    state = policy_tool_worker_node(state) # analyze với chunks có sẵn
```

**Lý do:** Policy worker cần evidence từ docs để phân tích — nếu không có chunks, LLM không có context để kết luận. Pre-fetch đảm bảo policy worker luôn có data.

**Trade-off đã chấp nhận:** Pre-fetch làm MCP `search_kb` không bao giờ được trigger (vì `not chunks` luôn False). Đây là trade-off latency vs MCP usage — chấp nhận được vì ChromaDB retrieval nhanh hơn MCP HTTP call.

**Bằng chứng từ trace:**

```
workers_called: ["retrieval_worker", "policy_tool_worker", "synthesis_worker"]
# retrieval luôn chạy trước policy_tool trong mọi 15 traces
```

---

## 3. Tôi đã sửa một lỗi gì?

**Lỗi:** `synthesis_worker` không enforce `policy_applies=False` — LLM tự kết luận ngược lại với policy_result.

**Symptom:** q12 trace cho thấy `policy_result.policy_applies=False` nhưng `final_answer` nói "Khách hàng được hoàn tiền". Mâu thuẫn hoàn toàn giữa policy worker output và synthesis output.

**Root cause:** `_build_context` chỉ đưa `exceptions_found` vào context dưới dạng text list, không nói rõ kết luận cuối. LLM đọc chunks thấy điều kiện được đáp ứng (sản phẩm lỗi, trong 7 ngày, chưa kích hoạt) rồi tự kết luận "được hoàn tiền" — bỏ qua `policy_applies=False`.

**Cách sửa:** Thêm section "KẾT QUẢ PHÂN TÍCH POLICY" vào context với dòng explicit:

```python
if policy_applies is False:
    parts.append("POLICY TỪ CHỐI: Request này KHÔNG được chấp thuận.")
    parts.append("Bắt buộc phản ánh kết luận này trong answer. KHÔNG được kết luận ngược lại.")
```

**Bằng chứng trước/sau:**

```
# Trước:
final_answer: "Khách hàng được hoàn tiền trong trường hợp này..."

# Sau:
final_answer: "Yêu cầu hoàn tiền của khách hàng không được chấp thuận..."
```

---

## 4. Tôi tự đánh giá đóng góp của mình

**Tôi làm tốt nhất ở điểm nào?**

Thiết kế `AgentState` và worker contracts rõ ràng từ đầu. Việc define đầy đủ fields và types trong `AgentState` giúp Hiếu implement MCP integration mà không cần hỏi tôi về data format. Standalone test cho từng worker cũng giúp debug nhanh khi có vấn đề.

**Tôi làm chưa tốt hoặc còn yếu ở điểm nào?**

Policy worker ban đầu dùng rule-based keyword matching quá đơn giản — gây ra nhiều false positive exceptions. Nếu thiết kế LLM-only từ đầu sẽ không cần Hiếu refactor lại ở Sprint 3, tiết kiệm thời gian cho cả nhóm.

**Nhóm phụ thuộc vào tôi ở đâu?**

`AgentState` schema và `worker_contracts.yaml` — Hiếu không thể implement MCP integration nếu chưa biết `mcp_tools_used` format và `needs_tool` flag hoạt động thế nào.

**Phần tôi phụ thuộc vào thành viên khác:**

Tôi cần Hiếu implement `mcp_server.py` để test `_call_mcp_tool` trong policy worker. Trong Sprint 2, tôi dùng mock in-process call và để TODO cho Sprint 3.

---

## 5. Nếu có thêm 2 giờ, tôi sẽ làm gì?

Tôi sẽ thêm LLM classifier cho supervisor thay vì keyword matching. Trace của q12 cho thấy supervisor trigger "flash sale" keyword trong task ("không phải Flash Sale") — keyword matching không hiểu negation. LLM classifier với prompt "classify task type: refund_request / access_request / info_query / unknown_error" sẽ chính xác hơn và xử lý được edge cases mà keyword matching bỏ sót.
