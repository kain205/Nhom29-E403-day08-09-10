# Báo Cáo Cá Nhân — Lab Day 08: RAG Pipeline

**Họ và tên:** Hàn Quang Hiếu  
**Vai trò trong nhóm:** Eval Owner & Retrieval Owner  
**Ngày nộp:** 2026-04-13  

---

## 1. Tôi đã làm gì trong lab này?

Trong lab này, tôi đảm nhận hai vai trò song song: Eval Owner và Retrieval Owner.

Về phía Retrieval, tôi implement rerank — sau khi hybrid/dense trả về top-10 candidates, tôi dùng LLM để chấm lại và chọn ra top-3 chunk thực sự liên quan nhất với query. Tôi cũng viết script `_run_approval_matrix.py` để debug toàn bộ retrieval pipeline — liệt kê tất cả 10 kết quả tìm được trước khi chọn top-3, giúp nhìn rõ lý do tại sao một số câu hỏi bị retrieve sai.

Về phía Eval, tôi thiết kế và chạy toàn bộ scorecard với 4 metrics (Faithfulness, Relevance, Context Recall, Completeness) dùng LLM-as-Judge, so sánh A/B giữa baseline và các variant, và viết `test_question.py` để test nhanh một câu hỏi bất kỳ với một hoặc tất cả strategy, kèm log đầy đủ.

---

## 2. Điều tôi hiểu rõ hơn sau lab này

**Hybrid retrieval không phải lúc nào cũng tốt hơn dense.**

Trước khi làm lab, tôi nghĩ hybrid = dense + BM25 thì chắc chắn tốt hơn vì có thêm thông tin. Thực tế ngược lại: Context Recall của baseline đã đạt 5.00/5 — dense đã retrieve đủ rồi. BM25 không thêm giá trị mà còn gây noise: với query "Escalation trong sự cố P1", BM25 match từ khóa "escalation" và "P1" trong `access_control_sop.md` (một section về escalation cấp quyền hệ thống) và đẩy nó lên rank cao hơn chunk SLA thực sự cần. Kết quả: completeness của q06 rơi từ 5 xuống 1.

Điều này dạy tôi một nguyên tắc quan trọng: trước khi tune retrieval, hãy đo Context Recall trước. Nếu recall đã cao, bottleneck nằm ở generation, không phải retrieval.

**Prompt engineering có tác động lớn hơn tôi nghĩ.**

Chỉ thay đổi prompt từ v1 sang v3 (thêm 3-tier abstain logic) đã cải thiện Completeness từ 3.80 lên 4.50 (+0.70) — mức cải thiện lớn nhất trong toàn bộ lab, lớn hơn cả việc đổi retrieval strategy.

---

## 3. Điều tôi ngạc nhiên hoặc gặp khó khăn

Điều ngạc nhiên nhất là bug ở indexing của câu q07 ("Approval Matrix để cấp quyền hệ thống là tài liệu nào?"). Tôi ban đầu nghĩ đây là retrieval problem — hybrid sẽ fix được vì BM25 sẽ match từ "Approval Matrix". Nhưng sau khi debug với `_run_approval_matrix.py`, tôi phát hiện ra rằng cả 3 strategy đều retrieve đúng file `access-control-sop.md`, nhưng không có chunk nào chứa từ "Approval Matrix" cả.

Nguyên nhân: dòng `Ghi chú: Tài liệu này trước đây có tên "Approval Matrix for System Access"` nằm trong phần header của file, và `preprocess_document()` đã strip toàn bộ header trước khi chunk. Thông tin alias bị mất ngay từ bước indexing — retrieval và generation không có cơ hội nào để tìm thấy nó.

Đây là lỗi tôi mất nhiều thời gian nhất để debug vì nhìn bề ngoài retrieval có vẻ đúng (đúng file, đúng source), nhưng thực ra thiếu đúng một câu quan trọng.

---

## 4. Phân tích một câu hỏi trong scorecard

**Câu hỏi:** q06 — "Escalation trong sự cố P1 diễn ra như thế nào?"

**Phân tích:**

Đây là câu thú vị nhất vì nó phân biệt rõ sự khác biệt giữa dense và hybrid. Baseline (dense + prompt v1) trả lời đúng hoàn toàn: nêu đủ 4 bước escalation, bao gồm "tự động escalate lên Senior Engineer nếu không có phản hồi trong 10 phút" — Completeness = 5/5.

Variant 1 (hybrid) lại fail câu này với Completeness = 1/5. Nguyên nhân: BM25 match từ khóa "escalation" và "P1" trong `access_control_sop.md` Section 4 ("Escalation khi cần thay đổi quyền hệ thống") và đẩy chunk đó lên rank cao qua RRF. Chunk đúng — `sla_p1_2026.txt` Section 2 chứa rule "auto-escalate in 10 min" — bị đẩy xuống ngoài top-3. LLM nhận được context sai và trả lời về quy trình cấp quyền khẩn cấp thay vì SLA escalation.

Lỗi nằm ở retrieval layer, không phải generation. Tôi debug bằng `_run_q06.py` — in toàn bộ 10 candidates trước khi chọn top-3 — và xác nhận chunk sai đứng rank 1 trong hybrid. Đây là bằng chứng thực nghiệm rõ nhất cho nguyên tắc: đo Context Recall trước khi tune retrieval. Nếu recall đã tốt, hybrid không thêm giá trị mà còn có thể gây hại.

---

## 5. Nếu có thêm thời gian, tôi sẽ làm gì?

Hai việc cụ thể:

1. **Thêm metadata `doc_title` và `aliases` vào ChromaDB:** q07 fail vì alias "Approval Matrix" không có trong bất kỳ chunk nào. Thay vì chỉ fix ở indexing, tôi sẽ thêm field `aliases` vào metadata của mỗi chunk (ví dụ: `"aliases": "Approval Matrix for System Access"`), sau đó dùng ChromaDB metadata filter kết hợp với full-text search trên field đó. Cách này không phụ thuộc vào việc alias có nằm trong chunk text hay không — retriever vẫn tìm được đúng doc ngay cả khi người dùng dùng tên cũ.

2. **Cân đối latency vs quality giữa variant3 và variant4:** Scorecard cho thấy variant4 (hybrid + rerank + nuanced prompt) đạt điểm cao nhất — Completeness 4.80/5, gần như perfect trên 9/10 câu. Tuy nhiên, variant4 tốn thêm một lần gọi LLM cho rerank trên top-10 candidates, khiến latency tăng đáng kể so với variant3 (hybrid + nuanced prompt, Completeness 4.80/5 tương đương). Trong thực tế production, tôi sẽ đo thời gian phản hồi trung bình của cả hai và xem xét dùng variant3 làm default — chất lượng gần như ngang nhau nhưng nhanh hơn — chỉ bật rerank cho các query được phân loại là "high-stakes" (ví dụ: câu hỏi về policy exception hoặc access control).

---

*File: `reports/individual/han_quang_hieu.md`*
