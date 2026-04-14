# System Architecture — Lab Day 09

**Nhóm:** Nhóm 29 — E403  
**Ngày:** 14/04/2026  
**Version:** 1.0

---

## 1. Tổng quan kiến trúc

**Pattern đã chọn:** Supervisor-Worker  
**Lý do chọn pattern này (thay vì single agent):**

RAG pipeline Day 08 là một monolith — một agent vừa retrieve, vừa kiểm tra policy, vừa tổng hợp. Khi pipeline trả lời sai, không rõ lỗi nằm ở bước nào. Supervisor-Worker tách rõ vai trò: supervisor quyết định luồng, mỗi worker chỉ làm một việc, có thể test độc lập và thay thế mà không ảnh hưởng toàn hệ.

---

## 2. Sơ đồ Pipeline

```
User Request
     │
     ▼
┌──────────────────────────────────────┐
│           Supervisor Node            │
│  - Phân tích task (keyword matching) │
│  - Quyết định route                  │
│  - Set risk_high, needs_tool         │
└──────────────┬───────────────────────┘
               │
         [route_decision]
               │
    ┌──────────┼──────────────┐
    │          │              │
    ▼          ▼              ▼
retrieval  policy_tool    human_review
_worker    _worker        _node
    │          │              │
    │    retrieval_worker     │
    │    (pre-fetch chunks)   │
    │          │              │
    │    policy_tool_worker   │
    │    (LLM + MCP tools)    │
    │          │              │
    └──────────┼──────────────┘
               │
               ▼
      ┌─────────────────┐
      │ Synthesis Worker │
      │ GPT-4o-mini      │
      │ grounded prompt  │
      └────────┬─────────┘
               │
               ▼
    final_answer + sources + confidence
```

---

## 3. Vai trò từng thành phần

### Supervisor (`graph.py`)

| Thuộc tính | Mô tả |
|-----------|-------|
| **Nhiệm vụ** | Phân tích task, quyết định route, set risk flag |
| **Input** | task (string) |
| **Output** | supervisor_route, route_reason, risk_high, needs_tool |
| **Routing logic** | Keyword matching: policy/access keywords → policy_tool_worker; SLA/ticket keywords → retrieval_worker; ERR- code → human_review; default → retrieval_worker |
| **HITL condition** | risk_high=True (emergency, 2am, ERR- codes) hoặc confidence < 0.4 từ synthesis |

### Retrieval Worker (`workers/retrieval.py`)

| Thuộc tính | Mô tả |
|-----------|-------|
| **Nhiệm vụ** | Embed query, query ChromaDB, trả về top-k chunks |
| **Embedding model** | OpenAI text-embedding-3-small (fallback: sentence-transformers all-MiniLM-L6-v2) |
| **Top-k** | 3 (configurable qua RETRIEVAL_TOP_K) |
| **Stateless?** | Yes — không đọc/ghi state ngoài contract |

### Policy Tool Worker (`workers/policy_tool.py`)

| Thuộc tính | Mô tả |
|-----------|-------|
| **Nhiệm vụ** | Phân tích policy bằng LLM, gọi MCP tools khi cần thêm thông tin |
| **LLM** | GPT-4o-mini với JSON response format, temperature=0.0 |
| **MCP tools gọi** | check_access_permission (access level cases), get_ticket_info (ticket status), search_kb (khi không có chunks) |
| **Exception cases xử lý** | digital_product, flash_sale, activated_product, temporal_scoping (v3/v4), emergency_bypass |
| **2-round analysis** | Round 1: LLM phân tích chunks; nếu needs_more_info → gọi MCP → Round 2 với context đầy đủ |

### Synthesis Worker (`workers/synthesis.py`)

| Thuộc tính | Mô tả |
|-----------|-------|
| **LLM model** | GPT-4o-mini (fallback: Gemini 1.5 Flash) |
| **Temperature** | 0.1 |
| **Grounding strategy** | Context gồm chunks + policy_result (policy_applies, exceptions, explanation, version_note) |
| **Abstain condition** | Khi chunks rỗng hoặc context không đủ → "Không đủ thông tin trong tài liệu nội bộ" |
| **HITL trigger** | confidence < 0.4 → hitl_triggered=True |

### MCP Server (`mcp_server.py` + `mcp_server_http.py`)

| Tool | Input | Output |
|------|-------|--------|
| search_kb | query, top_k | chunks, sources, total_found |
| get_ticket_info | ticket_id | ticket_id, priority, status, assignee, sla_deadline, notifications_sent |
| check_access_permission | access_level, requester_role, is_emergency | can_grant, required_approvers, emergency_override, notes |
| create_ticket | priority, title, description | ticket_id, url, created_at |

**Deployment:** Mock in-process (`MCP_SERVER_MODE=mock`) hoặc HTTP server FastAPI (`MCP_SERVER_MODE=http`, port 8080)

---

## 4. Shared State Schema

| Field | Type | Mô tả | Ai đọc/ghi |
|-------|------|-------|-----------|
| task | str | Câu hỏi đầu vào | supervisor đọc |
| supervisor_route | str | Worker được chọn | supervisor ghi, route_decision đọc |
| route_reason | str | Lý do route + mcp flag | supervisor ghi |
| risk_high | bool | True nếu có risk keyword | supervisor ghi |
| needs_tool | bool | True nếu cần MCP | supervisor ghi, policy_tool đọc |
| retrieved_chunks | list | Evidence từ retrieval | retrieval ghi, policy_tool + synthesis đọc |
| retrieved_sources | list | Danh sách source files | retrieval ghi |
| policy_result | dict | Kết quả phân tích policy | policy_tool ghi, synthesis đọc |
| mcp_tools_used | list | Tool calls đã thực hiện (tool, input, output, timestamp) | policy_tool ghi |
| final_answer | str | Câu trả lời cuối có citation | synthesis ghi |
| sources | list | Sources được cite | synthesis ghi |
| confidence | float | Mức tin cậy 0.0–1.0 | synthesis ghi |
| hitl_triggered | bool | True nếu cần human review | supervisor/synthesis ghi |
| history | list | Log các bước đã qua | tất cả workers append |
| workers_called | list | Danh sách workers đã chạy | tất cả workers append |
| latency_ms | int | Tổng thời gian xử lý | graph ghi |
| run_id | str | ID của run | graph ghi |

---

## 5. Lý do chọn Supervisor-Worker so với Single Agent (Day 08)

| Tiêu chí | Single Agent (Day 08) | Supervisor-Worker (Day 09) |
|----------|----------------------|--------------------------|
| Debug khi sai | Khó — không rõ lỗi ở đâu | Dễ hơn — test từng worker độc lập |
| Thêm capability mới | Phải sửa toàn prompt | Thêm MCP tool, không sửa core |
| Routing visibility | Không có | Có route_reason trong mọi trace |
| Policy exception handling | Keyword matching đơn giản | LLM phân tích với context + MCP enrichment |
| Trace & observability | Không có | worker_io_logs, history, mcp_tools_used |
| HITL | Không có | hitl_triggered khi confidence thấp hoặc risk cao |

**Quan sát từ thực tế lab:**

Khi policy worker trả về kết quả sai (q02: false positive exceptions), trace cho thấy ngay vấn đề nằm ở `policy_result.exceptions_found` — không cần đọc toàn bộ code. Việc tách policy analysis ra worker riêng cho phép iterate prompt/logic mà không ảnh hưởng retrieval hay synthesis.

---

## 6. Giới hạn và điểm cần cải tiến

1. **Routing dựa trên keyword matching** — dễ miss hoặc false positive. Cải tiến: dùng LLM classifier cho supervisor.
2. **Temporal scoping (policy v3)** — không có doc v3 nên không thể kết luận chính xác cho đơn hàng trước 01/02/2026. Cần bổ sung tài liệu hoặc escalate sang human.
3. **Single MCP call per analysis** — policy worker chỉ gọi 1 MCP tool per round. Trường hợp cần nhiều tools (q15: cả check_access_permission lẫn get_ticket_info) cần 2 rounds riêng biệt, tăng latency.
