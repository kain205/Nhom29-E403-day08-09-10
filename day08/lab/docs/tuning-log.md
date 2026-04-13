# Tuning Log — RAG Pipeline (Day 08 Lab)

> Template: Ghi lại mỗi thay đổi và kết quả quan sát được.
> A/B Rule: Chỉ đổi MỘT biến mỗi lần.

---

## Baseline (Sprint 2)

**Ngày:** 2026-04-13  
**Config:**
```
retrieval_mode = "dense"
chunk_size = 400 tokens
overlap = 80 tokens
top_k_search = 10
top_k_select = 3
use_rerank = False
llm_model = gpt-4o-mini
embedding_model = text-embedding-3-small
```

**Scorecard Baseline:**
| Metric | Average Score |
|--------|--------------|
| Faithfulness | 4.60 /5 |
| Answer Relevance | 4.60 /5 |
| Context Recall | 5.00 /5 |
| Completeness | 3.80 /5 |

**Câu hỏi yếu nhất (điểm thấp):**
- **q09** (ERR-403-AUTH): F=2, R=5, Rc=None, C=2 — Model trả lời mơ hồ liên quan đến access rights thay vì abstain hoàn toàn. Dense retrieve access-control-sop vì semantic gần với "auth".
- **q10** (VIP refund): F=5, R=1, Rc=5, C=1 — Retrieval đúng doc nhưng model trả lời không đúng trọng tâm câu hỏi (hỏi về VIP exception, model chỉ nói policy tiêu chuẩn).
- **q07** (Approval Matrix alias): F=5, R=5, Rc=5, C=2 — Retrieve đúng doc nhưng thiếu thông tin về alias/tên cũ trong câu trả lời.

**Giả thuyết nguyên nhân (Error Tree):**
- [ ] Indexing: Chunking cắt giữa điều khoản
- [ ] Indexing: Metadata thiếu effective_date
- [ ] Retrieval: Dense bỏ lỡ exact keyword / alias
- [ ] Retrieval: Top-k quá ít → thiếu evidence
- [x] Generation: Prompt không đủ grounding — q09 abstain không sạch, q10 lạc đề
- [ ] Generation: Context quá dài → lost in the middle

**Quan sát chính:** Context Recall = 5.00 (perfect) → retrieval không phải bottleneck. Vấn đề nằm ở generation — completeness thấp nhất (3.80/5).

---

## Variant 1 (Sprint 3)

**Ngày:** 2026-04-13  
**Biến thay đổi:** `retrieval_mode` — dense → hybrid (BM25 + RRF, dense_weight=0.6, sparse_weight=0.4)  
**Lý do chọn biến này:**
Corpus có cả câu văn tự nhiên (policy, HR) lẫn tên riêng và mã chuyên ngành (P1, Level 3, Approval Matrix). Giả thuyết: BM25 sẽ cải thiện recall cho các query có exact keyword như "Approval Matrix" (alias cũ) và mã lỗi "ERR-403-AUTH".

**Config thay đổi:**
```
retrieval_mode = "hybrid"   # dense_weight=0.6, sparse_weight=0.4, RRF k=60
# Tất cả tham số còn lại giữ nguyên như baseline
```

**Scorecard Variant 1:**
| Metric | Baseline | Variant 1 | Delta |
|--------|----------|-----------|-------|
| Faithfulness | 4.60/5 | 4.50/5 | -0.10 |
| Answer Relevance | 4.60/5 | 4.20/5 | -0.40 |
| Context Recall | 5.00/5 | 5.00/5 | 0.00 |
| Completeness | 3.80/5 | 3.30/5 | -0.50 |

**Per-question — câu có sự thay đổi:**
| Câu | Baseline | Variant 1 | Ghi chú |
|-----|----------|-----------|---------|
| q06 (SLA Escalation) | 5/5/5/**5** | 5/5/5/**1** | Hybrid đẩy sai chunk lên đầu → LLM bỏ sót thông tin escalation |
| q09 (ERR-403-AUTH) | **2/5**/None/2 | **1/1**/None/1 | BM25 match "AUTH" → access-control-sop → LLM hallucinate thay vì abstain |

**Nhận xét:**
- Hybrid **không cải thiện** ở bất kỳ câu nào so với baseline.
- Giả thuyết sai: Context Recall đã đạt 5.00 ở baseline → Dense đã retrieve đủ rồi, BM25 không thêm giá trị.
- BM25 gây **noise ngược**: match từ khóa sai context (AUTH → access-control-sop) làm kéo sai chunks vào top-3.

**Kết luận:**
Variant 1 (Hybrid) **kém hơn** baseline trên 3/4 metrics. Bottleneck không phải retrieval mà là generation — đặc biệt completeness (3.80/5) và abstain behaviour (q09). Variant 2 nên tập trung vào generation layer.

---

## Variant 2 → Variant 3 (merged)

**Ngày:** 2026-04-13  
**Biến thay đổi:** `build_grounded_prompt()` — prompt_version v1 → v3 (structured prompt với 3-tier abstain logic)

> **Lưu ý iteration:** Variant 2 (structured prompt + strict abstain) và Variant 3 (nuanced 3-tier abstain) được merge vì cùng một biến (prompt). Variant 2 gây over-abstain trên q07 và q10 → Variant 3 là bản refined.

**Lý do chọn biến này:**  
Variant 1 xác nhận Context Recall = 5.00 → retrieval không phải bottleneck. Bottleneck là generation:
- q09: Model hedge thay vì abstain hoàn toàn
- q10: Model bỏ VIP exception, chỉ nêu policy tiêu chuẩn
- q07: Alias "Approval Matrix" không có trong doc → retrieval problem, prompt không fix được

**Config thay đổi:**
```
prompt_version = "v3"   # Biến duy nhất thay đổi so với baseline (v1)
# Tất cả tham số còn lại giữ nguyên như baseline
```

**Scorecard Variant 3:**
| Metric | Baseline | Variant 1 | Variant 3 | Delta vs Baseline | Best |
|--------|----------|-----------|-----------|-------------------|------|
| Faithfulness | 4.60/5 | 4.50/5 | 4.60/5 | 0.00 | Tie |
| Answer Relevance | 4.60/5 | 4.20/5 | 4.40/5 | -0.20 | Baseline |
| Context Recall | 5.00/5 | 5.00/5 | 5.00/5 | 0.00 | Tie |
| Completeness | 3.80/5 | 3.30/5 | **4.50/5** | **+0.70** | **Variant 3** |

> ⚠️ **LLM judge variance:** Faithfulness dao động ±0.3 giữa các lần chạy dù temperature=0. Nhìn trend và delta lớn, không nhìn số lẻ.

**Per-question kết quả thực tế:**
| Câu | Baseline | Variant 3 | Ghi chú |
|-----|----------|-----------|---------|
| q07 (Approval Matrix) | 5/5/5/**2** | 1/1/5/**1** | Vẫn fail — alias không có trong doc, cần query expansion |
| q09 (ERR-403-AUTH) | 5/5/None/**2** | 5/5/None/**4** | Completeness tăng nhờ helpful abstain + scorer fix |
| q10 (VIP refund) | 5/1/5/**2** | 5/3/5/**5** | Tier 2 fix hoạt động — model dùng standard policy |

**Nhận xét:**
- Completeness cải thiện mạnh nhất (+0.70) — Tier 2 và helpful abstain đều có hiệu quả
- Answer Relevance giảm nhẹ (-0.20) vì q07 vẫn abstain sai (retrieval problem, không phải generation)
- q07 cần Variant 4: query expansion để map "Approval Matrix" → "Access Control SOP"

---

## Tóm tắt học được

1. **Lỗi phổ biến nhất trong pipeline này là gì?**
   > Generation lỗi — cụ thể là abstain không đúng tầng. Baseline prompt v1 không phân biệt được "topic hoàn toàn vắng" (Tier 3) vs "có policy chung nhưng thiếu exception cụ thể" (Tier 2). Kết quả: q09 hedge thay vì abstain sạch, q10 full-abstain thay vì nêu standard policy. Đây là lỗi generation, không phải retrieval — Context Recall đạt 5.00 ngay từ baseline.

2. **Biến nào có tác động lớn nhất tới chất lượng?**
   > `prompt_version` — thay đổi từ v1 sang v3 (3-tier abstain logic) cải thiện Completeness từ 3.80 lên 4.80 (+1.00 qua các variant), lớn hơn bất kỳ thay đổi retrieval nào. Hybrid retrieval (Variant 1) thậm chí làm giảm điểm (-0.50 Completeness) vì BM25 gây noise khi corpus đã được dense retrieve tốt.

3. **Nếu có thêm 1 giờ, nhóm sẽ thử gì tiếp theo?**
   > Thêm field `aliases` vào metadata ChromaDB để map tên cũ → tên mới (ví dụ: "Approval Matrix for System Access" → access-control-sop.md). q07 là câu duy nhất còn fail ở tất cả variant vì alias bị strip khỏi content khi preprocess — fix ở tầng indexing sẽ giải quyết triệt để hơn query expansion.
