# Lab Day 08 — Full RAG Pipeline

**Môn:** AI in Action (AICB-P1)  
**Chủ đề:** RAG Pipeline: Indexing → Retrieval → Generation → Evaluation  
**Thời gian:** 4 giờ (4 sprints x 60 phút)

---

## Bối cảnh

Nhóm xây dựng **trợ lý nội bộ cho khối CS + IT Helpdesk**: trả lời câu hỏi về chính sách, SLA ticket, quy trình cấp quyền, và FAQ bằng chứng cứ được retrieve có kiểm soát.

**Câu hỏi mẫu hệ thống phải trả lời được:**
- "SLA xử lý ticket P1 là bao lâu?"
- "Khách hàng có thể yêu cầu hoàn tiền trong bao nhiêu ngày?"
- "Ai phải phê duyệt để cấp quyền Level 3?"

---

## Mục tiêu học tập

| Mục tiêu | Sprint liên quan |
|-----------|----------------|
| Build indexing pipeline với metadata | Sprint 1 |
| Build retrieval + grounded answer function | Sprint 2 |
| So sánh dense / hybrid / rerank / prompt, chọn và justify variant | Sprint 3 |
| Đánh giá pipeline bằng scorecard, A/B comparison | Sprint 4 |

---

## Cấu trúc repo

```
lab/
├── index.py              # Sprint 1: Preprocess → Chunk → Embed → Store
├── rag_answer.py         # Sprint 2+3: Retrieve → (Rerank) → Generate
├── eval.py               # Sprint 4: Scorecard + Multi-variant Comparison
│
├── data/
│   ├── docs/             # Policy documents để index
│   │   ├── policy_refund_v4.txt
│   │   ├── sla_p1_2026.txt
│   │   ├── access_control_sop.txt
│   │   ├── it_helpdesk_faq.txt
│   │   └── hr_leave_policy.txt
│   └── test_questions.json   # 10 test questions với expected answers
│
├── results/
│   ├── scorecard_baseline_dense.md/csv
│   ├── scorecard_variant1_hybrid.md/csv
│   ├── scorecard_variant2_hybrid_nuanced.md/csv
│   ├── scorecard_variant3_nuanced_abstain.md/csv
│   ├── scorecard_variant4_hybrid_rerank.md/csv
│   └── ab_comparison_all.csv
│
├── docs/
│   ├── architecture.md
│   └── tuning-log.md
│
├── reports/
│   └── individual/
│       └── template.md
│
├── requirements.txt
└── .env.example
```

---

## Setup

### 1. Cài dependencies
```bash
pip install -r requirements.txt
```

### 2. Tạo file .env
```bash
cp .env.example .env
# Điền OPENAI_API_KEY
```

### 3. Build index
```bash
python index.py
```

---

## Chạy pipeline

### Test 1 câu nhanh
```bash
python rag_answer.py --query "SLA ticket P1 là bao lâu?"

# Chọn retrieval mode
python rag_answer.py --query "Approval Matrix là gì?" --mode hybrid

# Chọn prompt version
python rag_answer.py --query "Hoàn tiền VIP?" --prompt v1
```

### Chạy evaluation
```bash
# Chạy tất cả variants + compare
python eval.py --run all

# Chỉ chạy 1 variant
python eval.py --run baseline
python eval.py --run variant1
python eval.py --run variant2
python eval.py --run variant3
python eval.py --run variant4

# In lại bảng so sánh từ CSV (không gọi API)
python eval.py --run compare
```

---

## Kết quả thực nghiệm

### Scorecard tổng hợp

| Metric | Baseline | V1 Hybrid | V2 Hybrid+Prompt | V3 Prompt only | V4 Hybrid+Rerank |
|--------|----------|-----------|------------------|----------------|------------------|
| Faithfulness | 4.90 | 4.50 | **5.00** | 4.90 | **5.00** |
| Answer Relevance | 4.60 | 4.20 | **5.00** | **5.00** | **5.00** |
| Context Recall | 5.00 | 5.00 | 5.00 | 5.00 | 5.00 |
| Completeness | 3.90 | 3.30 | 4.40 | 4.80 | **4.80** |

### Variants

| Label | Biến thay đổi | Kết quả |
|-------|--------------|---------|
| **baseline_dense** | — | Dense + simple prompt |
| **variant1_hybrid** | `retrieval_mode`: dense → hybrid (BM25+RRF) | ❌ Kém hơn baseline — BM25 gây noise |
| **variant2_hybrid_nuanced** | V1 + `prompt_version`: v1 → v3 | ✅ F+R = 5.00, C = 4.40 |
| **variant3_nuanced_abstain** | `prompt_version`: v1 → v3 (dense giữ nguyên) | ✅ Best completeness = 4.80 |
| **variant4_hybrid_rerank** | V2 + `use_rerank`: False → True (LLM reranker) | ✅ F+R+Rc = 5.00, C = 4.80 |

### Key findings

1. **Context Recall = 5.00 ngay từ baseline** → retrieval không phải bottleneck
2. **Hybrid retrieval (V1) gây noise ngược**: BM25 match "AUTH" → kéo sai doc → hallucination
3. **Prompt v3 (3-tier abstain) là fix quan trọng nhất**: completeness 3.90 → 4.80 (+0.90)
4. **Rerank (V4) cải thiện faithfulness và relevance** nhưng tốn thêm 1 LLM call/query
5. **V3 (dense + prompt v3) là sweet spot**: gần bằng V4 về chất lượng, không tốn rerank

---

## Prompt versions

| Version | Mô tả |
|---------|-------|
| `v1` | Baseline — "Answer only from context, cite sources" |
| `v3` | Structured — Role / Instructions / 3-tier Constraints / Output Format |

**3-tier abstain logic trong v3:**
- Tier 1: Context đủ → trả lời với citation
- Tier 2: Có policy chung nhưng không có exception cụ thể (VIP, special case) → nêu policy chung + ghi chú exception không có
- Tier 3: Topic hoàn toàn vắng → abstain + gợi ý IT Helpdesk

---

## 4 Sprints

### Sprint 1 (60') — Build Index
**File:** `index.py`

**Việc phải làm:**
1. Implement `get_embedding()` — chọn OpenAI hoặc Sentence Transformers
2. Implement phần TODO trong `build_index()` — embed và upsert vào ChromaDB
3. Chạy `build_index()` và kiểm tra với `list_chunks()`

**Definition of Done:**
- [x] Script chạy được, index đủ 5 tài liệu
- [x] Mỗi chunk có ít nhất 3 metadata fields: `source`, `section`, `effective_date`
- [x] `list_chunks()` cho thấy chunk hợp lý, không bị cắt giữa điều khoản

---

### Sprint 2 (60') — Baseline Retrieval + Answer
**File:** `rag_answer.py`

**Việc phải làm:**
1. Implement `retrieve_dense()` — query ChromaDB với embedding
2. Implement `call_llm()` — gọi OpenAI
3. Test `rag_answer()` với 3+ câu hỏi mẫu

**Definition of Done:**
- [x] `rag_answer("SLA ticket P1?")` → trả về câu trả lời có citation `[1]`
- [x] `rag_answer("ERR-403-AUTH")` → trả về abstain
- [x] Output có `sources` field không rỗng

---

### Sprint 3 (60') — Tuning
**File:** `rag_answer.py`

| Variant | Biến thay đổi | Config |
|---------|--------------|--------|
| V1 | `retrieval_mode` | `"hybrid"` — BM25 + RRF |
| V2 | V1 + `prompt_version` | `"v3"` — 3-tier abstain |
| V3 | `prompt_version` only | `"v3"` trên dense |
| V4 | V2 + `use_rerank` | `True` — LLM reranker |

**A/B Rule:** Chỉ đổi MỘT biến mỗi lần.

**Definition of Done:**
- [x] Tất cả variants chạy end-to-end
- [x] Scorecard cho từng variant
- [x] Giải thích được vì sao chọn biến đó (ghi vào `docs/tuning-log.md`)

---

### Sprint 4 (60') — Evaluation + Docs + Report
**File:** `eval.py`

**Việc phải làm:**
1. Chạy `python eval.py --run all`
2. Điền vào `docs/architecture.md` và `docs/tuning-log.md`
3. Viết báo cáo cá nhân (500-800 từ)

**Definition of Done:**
- [x] `python eval.py --run all` chạy thành công
- [x] Scorecard tất cả variants đã lưu trong `results/`
- [x] `docs/tuning-log.md` hoàn chỉnh
- [ ] Mỗi người có file báo cáo trong `reports/individual/`

---

## Deliverables (Nộp bài)

| Item | File | Owner |
|------|------|-------|
| Code pipeline | `index.py`, `rag_answer.py`, `eval.py` | Tech Lead |
| Test questions | `data/test_questions.json` | Eval Owner |
| Scorecards | `results/scorecard_*.md` | Eval Owner |
| A/B comparison | `results/ab_comparison_all.csv` | Eval Owner |
| Architecture docs | `docs/architecture.md` | Documentation Owner |
| Tuning log | `docs/tuning-log.md` | Documentation Owner |
| Báo cáo cá nhân | `reports/individual/[ten].md` | Từng người |

---

## Phân công thực tế

| Thành viên | Đóng góp |
|------------|----------|
| **Nguyễn Bình Thành** | Setup toàn bộ pipeline skeleton (index, rag_answer, eval); implement dense retrieval + baseline prompt; xây eval framework (scorecard, LLM-as-judge, A/B comparison); chạy Baseline → Variant 1 (hybrid) → Variant 3 (prompt v3); ghi tuning-log |
| **Hàn Quang Hiếu** | Implement LLM reranker; thêm Variant 2 (hybrid + prompt v3) và Variant 4 (hybrid + rerank + prompt v3); debug từng câu yếu (_run_q06, _run_approval_matrix); chạy full evaluation 5 variants → đạt F/R/Rc = 5.00 |

---

## Gợi ý Debug (Error Tree)

```
1. Indexing?
   → list_chunks() → Chunk có đúng không? Metadata có đủ không?

2. Retrieval?
   → score_context_recall() → Expected source có được retrieve không?
   → Thử thay dense → hybrid nếu query có keyword/alias

3. Generation?
   → score_faithfulness() → Answer có bám context không?
   → Kiểm tra prompt version: v1 hay v3?
   → Thử --query để test từng câu nhanh
```

---

## Tài nguyên tham khảo

- Slide Day 08: `../lecture-08.html`
- ChromaDB docs: https://docs.trychroma.com
- OpenAI Embeddings: https://platform.openai.com/docs/guides/embeddings
- rank-bm25: https://github.com/dorianbrown/rank_bm25
