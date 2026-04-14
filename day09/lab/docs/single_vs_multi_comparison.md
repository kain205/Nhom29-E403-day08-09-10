# Single Agent vs Multi-Agent Comparison — Lab Day 09

**Nhóm:** Nhóm 29 — E403  
**Ngày:** 14/04/2026

---

## 1. Metrics Comparison

| Metric | Day 08 (Single Agent) | Day 09 (Multi-Agent) | Delta | Ghi chú |
|--------|----------------------|---------------------|-------|---------|
| Avg confidence | N/A | 0.542 | N/A | Day 08 không có confidence metric |
| Avg latency (ms) | ~2000 (est.) | 5883 | +3883ms | Multi-agent gọi nhiều LLM calls hơn |
| Abstain rate (%) | N/A | 7% (1/15) | N/A | q09 abstain đúng |
| HITL triggered | Không có | 7% (1/15) | N/A | q09 confidence=0.3 |
| MCP usage | Không có | 13% (2/15) | N/A | q13, q15 gọi MCP |
| Routing visibility | ✗ Không có | ✓ Có route_reason | N/A | Mọi trace đều có lý do routing |
| Debug time (estimate) | ~20 phút | ~5 phút | -15 phút | Trace cho biết ngay lỗi ở worker nào |
| Policy exception accuracy | Thấp (keyword only) | Cao hơn (LLM + context) | + | LLM hiểu ngữ cảnh, tránh false positive |

---

## 2. Phân tích theo loại câu hỏi

### 2.1 Câu hỏi đơn giản (single-document)

| Nhận xét | Day 08 | Day 09 |
|---------|--------|--------|
| Accuracy | Tốt | Tốt |
| Latency | ~1500ms | ~4000ms |
| Observation | Retrieval + generate đơn giản | Thêm overhead supervisor + worker routing |

**Kết luận:** Multi-agent không cải thiện accuracy cho câu đơn giản, nhưng tăng latency đáng kể. Trade-off không có lợi cho simple queries — single agent đủ dùng.

### 2.2 Câu hỏi multi-hop (cross-document)

| Nhận xét | Day 08 | Day 09 |
|---------|--------|--------|
| Accuracy | Thấp (không có policy check) | Cao hơn (policy_tool_worker + MCP) |
| Routing visible? | ✗ | ✓ |
| Observation | Một agent xử lý hết, dễ nhầm lẫn giữa SLA rule và policy exception | Supervisor phân loại đúng, policy worker chuyên biệt |

**Kết luận:** Multi-agent rõ ràng tốt hơn cho multi-hop. q13 và q15 cần cross-document reasoning (access_control_sop + sla_p1_2026) kết hợp MCP real-time data — single agent không có cơ chế này.

### 2.3 Câu hỏi cần abstain

| Nhận xét | Day 08 | Day 09 |
|---------|--------|--------|
| Abstain rate | N/A | 7% (1/15) |
| Hallucination cases | Không đo được | 0 (q09 abstain đúng) |
| Observation | Không có confidence metric để trigger abstain | confidence < 0.4 → hitl_triggered, synthesis abstain |

**Kết luận:** Multi-agent có cơ chế abstain rõ ràng hơn nhờ confidence score và hitl_triggered flag.

---

## 3. Debuggability Analysis

### Day 08 — Debug workflow
```
Khi answer sai → phải đọc toàn bộ RAG pipeline code
→ Không biết lỗi ở indexing, retrieval, hay generation
→ Không có trace → không biết bắt đầu từ đâu
Thời gian ước tính: ~20 phút
```

### Day 09 — Debug workflow
```
Khi answer sai → đọc trace → xem supervisor_route + route_reason
  → Route sai? → sửa supervisor keyword list
  → Retrieval sai? → test retrieval_worker độc lập với cùng query
  → Policy sai? → xem policy_result.exceptions_found + llm_used
  → Synthesis sai? → xem policy_applies có được enforce không
Thời gian ước tính: ~5 phút
```

**Câu cụ thể nhóm đã debug:**

q02 ("hoàn tiền trong bao nhiêu ngày") ban đầu trả về 4 false positive exceptions và `hitl_triggered=True`. Trace cho thấy ngay `policy_result.exceptions_found` có 4 items và `llm_used=True`. Vấn đề: LLM đọc chunks thấy Flash Sale/digital product trong doc rồi list ra hết dù task không trigger chúng. Fix: cập nhật prompt để LLM phân biệt câu hỏi thông tin vs request cụ thể → `policy_applies=null`, `exceptions_found=[]`. Toàn bộ debug + fix mất ~10 phút nhờ trace rõ ràng.

---

## 4. Extensibility Analysis

| Scenario | Day 08 | Day 09 |
|---------|--------|--------|
| Thêm 1 tool/API mới | Phải sửa toàn prompt | Thêm tool vào mcp_server.py, LLM tự discover qua list_tools() |
| Thêm 1 domain mới | Phải retrain/re-prompt toàn bộ | Thêm worker mới + route rule trong supervisor |
| Thay đổi retrieval strategy | Sửa trực tiếp trong pipeline | Sửa retrieval_worker.py độc lập, không ảnh hưởng workers khác |
| A/B test một phần | Khó — phải clone toàn pipeline | Dễ — swap worker, giữ nguyên phần còn lại |
| Thay LLM provider | Sửa 1 chỗ | Sửa từng worker độc lập (mỗi worker có fallback riêng) |

**Nhận xét:**

MCP là điểm extensibility quan trọng nhất. Khi thêm tool mới vào `mcp_server.py`, LLM tự động biết qua `list_tools()` — không cần sửa prompt hay worker code. Đây là lợi thế lớn so với Day 08 nơi mọi capability đều phải hardcode vào prompt.

---

## 5. Cost & Latency Trade-off

| Scenario | Day 08 calls | Day 09 calls |
|---------|-------------|-------------|
| Simple query (retrieval path) | 1 LLM call (generate) | 2 LLM calls (synthesis) + 1 embedding |
| Policy query (no MCP) | 1 LLM call | 2 LLM calls (policy analysis + synthesis) + 1 embedding |
| Policy query (with MCP) | 1 LLM call | 3–4 LLM calls (policy round1 + round2 + synthesis) + 1 embedding |
| MCP tool call | N/A | 1 HTTP call (hoặc in-process) |

**Nhận xét về cost-benefit:**

Multi-agent tốn gấp 2–4x LLM calls so với single agent. Với simple queries, overhead không đáng. Với complex policy queries cần MCP enrichment, cost cao hơn nhưng accuracy cũng cao hơn đáng kể. Trong production, có thể optimize bằng cách chỉ route sang policy_tool_worker khi thực sự cần — supervisor hiện tại đã làm điều này với keyword matching.

---

## 6. Kết luận

**Multi-agent tốt hơn single agent ở điểm nào?**

1. **Debuggability** — trace rõ ràng, biết ngay lỗi ở worker nào, không cần đọc toàn bộ code
2. **Complex policy handling** — policy worker chuyên biệt với LLM + MCP enrichment xử lý exception cases chính xác hơn
3. **Extensibility** — thêm capability qua MCP mà không sửa core pipeline
4. **Observability** — mọi quyết định đều được log: route_reason, worker_io_logs, mcp_tools_used, confidence

**Multi-agent kém hơn hoặc không khác biệt ở điểm nào?**

1. **Latency** — chậm hơn ~3x so với single agent do nhiều LLM calls
2. **Simple queries** — overhead không cần thiết cho câu hỏi đơn giản chỉ cần retrieval + generate

**Khi nào KHÔNG nên dùng multi-agent?**

Khi hệ thống chỉ xử lý một loại task đồng nhất (ví dụ: chỉ Q&A đơn giản từ docs), không có policy logic phức tạp, và latency là ưu tiên hàng đầu. Single agent RAG đủ dùng và nhanh hơn.

**Nếu tiếp tục phát triển hệ thống này, nhóm sẽ thêm gì?**

1. LLM classifier cho supervisor thay vì keyword matching — chính xác hơn cho edge cases
2. Bổ sung policy v3 vào knowledge base để xử lý temporal scoping
3. Parallel worker execution — retrieval và policy tool chạy song song thay vì tuần tự để giảm latency
4. Caching MCP responses — tránh gọi lại cùng tool với cùng input trong một session
