# Báo Cáo Nhóm — Lab Day 08: RAG Pipeline

**Nhóm:** 29 — E403  
**Ngày:** 2026-04-13  
**Thành viên:**
- Nguyễn Bình Thành — Tech Lead & Documentation Owner
- Hàn Quang Hiếu — Eval Owner & Retrieval Owner

---

## 1. Tổng quan hệ thống

Nhóm xây dựng trợ lý nội bộ cho khối CS và IT Helpdesk, trả lời câu hỏi về chính sách hoàn tiền, SLA ticket, quy trình cấp quyền, và FAQ bằng chứng cứ retrieve có kiểm soát từ 5 tài liệu nội bộ.

**Stack:**
- Embedding: OpenAI `text-embedding-3-small`
- Vector store: ChromaDB (local persistent, cosine similarity)
- LLM: `gpt-4o-mini` (temperature=0)
- Sparse retrieval: `rank-bm25` (BM25Okapi)
- Evaluation: LLM-as-Judge (4 metrics, gpt-4o-mini)

---

## 2. Quyết định kỹ thuật chính

### Chunking
Nhóm chọn **heading-based chunking** thay vì fixed-size chunking. Mỗi tài liệu được chia theo section heading `=== ... ===` trước, sau đó mới split theo paragraph nếu section quá dài (>1600 ký tự). Lý do: các tài liệu policy có cấu trúc section rõ ràng — mỗi section là một đơn vị ngữ nghĩa độc lập (ví dụ: "Điều 2: Điều kiện hoàn tiền", "Level 3 — Elevated Access"). Cắt theo heading đảm bảo mỗi chunk không bị split giữa điều khoản.

Kết quả: 29 chunks từ 5 tài liệu, không có chunk nào thiếu metadata, Context Recall = 5.00/5 ngay từ baseline.

### Retrieval strategy
Nhóm thử 3 strategies theo thứ tự:

| Strategy | Kết quả | Lý do |
|----------|---------|-------|
| Dense (baseline) | Context Recall = 5.00 | Embedding đủ tốt cho corpus này |
| Hybrid BM25+RRF (V1) | Kém hơn baseline | BM25 gây noise — match sai context |
| Dense + LLM Rerank (V4) | Tốt nhất | Reranker chọn đúng chunk sau khi hybrid retrieve rộng |

**Kết luận retrieval:** Dense đã đủ tốt cho corpus thuần policy. Hybrid chỉ có lợi khi corpus có nhiều alias/tên riêng chưa được embed tốt. Rerank có giá trị khi cần chọn lọc chính xác từ top-10 candidates.

### Prompt engineering
Biến có tác động lớn nhất là `prompt_version`. Prompt v3 thêm 3-tier abstain logic:
- **Tier 1:** Context đủ → trả lời với citation
- **Tier 2:** Có policy chung nhưng thiếu exception cụ thể → nêu policy chung + ghi rõ exception không có tài liệu
- **Tier 3:** Topic hoàn toàn vắng → abstain + gợi ý IT Helpdesk

Tier 2 fix được q10 (VIP refund) — câu mà baseline full-abstain sai vì không phân biệt được "không có exception" vs "không có thông tin gì".

---

## 3. Kết quả scorecard

| Metric | Baseline | V1 Hybrid | V2 Hybrid+Prompt | V3 Prompt only | V4 Hybrid+Rerank |
|--------|----------|-----------|------------------|----------------|------------------|
| Faithfulness | 4.90 | 4.50 | **5.00** | 4.90 | **5.00** |
| Answer Relevance | 4.60 | 4.20 | **5.00** | **5.00** | **5.00** |
| Context Recall | 5.00 | 5.00 | 5.00 | 5.00 | 5.00 |
| Completeness | 3.90 | 3.30 | 4.40 | 4.80 | **4.80** |

**Config được chọn cho grading:** Variant 4 (hybrid + rerank + prompt v3) — điểm cao nhất trên 3/4 metrics. Tradeoff: latency cao hơn do thêm 1 LLM call cho rerank, nhưng chấp nhận được trong context grading.

---

## 4. Câu hỏi khó nhất và cách xử lý

**q07 — "Approval Matrix để cấp quyền hệ thống là tài liệu nào?"**

Đây là câu duy nhất fail ở hầu hết variant. Root cause: dòng `Ghi chú: Tài liệu này trước đây có tên "Approval Matrix for System Access"` nằm trong header của file và bị `preprocess_document()` strip trước khi chunk. Không có chunk nào chứa từ "Approval Matrix" → retriever tìm đúng file nhưng LLM không có thông tin để trả lời đúng.

Fix đã thực hiện: giữ lại dòng `Ghi chú:` trong content khi preprocess, rebuild index. Sau fix, Variant 3 và V4 trả lời đúng tên cũ và tên mới.

**q09 — "ERR-403-AUTH là lỗi gì?"**

Câu abstain — không có thông tin trong docs. Baseline hedge ("lỗi liên quan đến access rights") thay vì abstain sạch. Prompt v3 Tier 3 fix được: model trả lời đúng "Không đủ dữ liệu" + gợi ý IT Helpdesk.

---

## 5. Phân công thực tế

| Thành viên | Sprint | Đóng góp cụ thể |
|------------|--------|----------------|
| Nguyễn Bình Thành | 1, 2, 3, 4 | Setup pipeline skeleton; implement dense retrieval + baseline prompt; xây eval framework (scorecard, LLM-as-judge, A/B comparison); chạy Baseline → V1 → V3; ghi tuning-log và architecture.md |
| Hàn Quang Hiếu | 3, 4 | Implement LLM reranker; thêm V2 (hybrid + prompt v3) và V4 (hybrid + rerank + prompt v3); debug từng câu yếu (`_run_q06.py`, `_run_approval_matrix.py`); chạy full evaluation 5 variants; viết `test_question.py` với logging |

---

## 6. Key findings

1. **Context Recall = 5.00 ngay từ baseline** → chunking và embedding đủ tốt, không cần tune retrieval
2. **Hybrid BM25 gây noise ngược** khi dense đã recall tốt — BM25 match "AUTH" → access-control-sop thay vì abstain
3. **Prompt engineering là biến quan trọng nhất** — Completeness tăng +1.00 chỉ bằng cách thêm 3-tier logic
4. **Rerank (V4) cải thiện faithfulness và relevance** nhưng tốn thêm latency — V3 là sweet spot cho production
5. **Indexing bug quan trọng hơn retrieval bug** — alias bị strip ở preprocess không thể fix bằng hybrid hay rerank
