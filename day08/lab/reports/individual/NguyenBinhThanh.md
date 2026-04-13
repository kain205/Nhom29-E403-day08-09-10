# Báo Cáo Cá Nhân — Lab Day 08: RAG Pipeline

**Họ và tên:** Nguyễn Bình Thành
**Vai trò trong nhóm:** Tech Lead
**Ngày nộp:** 2026-04-13
**Độ dài yêu cầu:** 500–800 từ

---

## 1. Tôi đã làm gì trong lab này? (100-150 từ)

Tôi đảm nhận vai trò Tech Lead và chủ yếu làm Sprint 1, 2, và phần đầu Sprint 3.

Cụ thể: tôi build toàn bộ skeleton của pipeline — từ `index.py` (preprocess, chunk, embed, upsert ChromaDB), `rag_answer.py` (dense retrieval, gọi OpenAI, grounded prompt v1), cho đến `eval.py` (scorecard với LLM-as-judge, A/B comparison framework). Trong Sprint 3, tôi chạy Baseline, Variant 1 (hybrid BM25+RRF), và Variant 3 (prompt v3 trên dense), đồng thời ghi lại toàn bộ thay đổi và kết quả vào `docs/tuning-log.md`.

Công việc của tôi là nền tảng để bạn cùng nhóm (Hàn Quang Hiếu) có thể thêm LLM reranker và chạy Variant 2, 4 mà không cần viết lại từ đầu — mọi thứ đã có config parameter rõ ràng (`retrieval_mode`, `prompt_version`, `use_rerank`).

---

## 2. Điều tôi hiểu rõ hơn sau lab này (100-150 từ)

Điều tôi thấm nhất sau lab này là **không thể một mình gánh toàn bộ pipeline từ đầu đến cuối một cách tốt được**. Tôi build skeleton nhanh, nhưng khi đến phần LLM reranker thì bắt đầu đuối — vừa phải debug eval framework, vừa phải chạy thực nghiệm, vừa phải ghi tuning-log.

Chính vì có Hiếu nhảy vào implement reranker và chạy Variant 2, 4 mà nhóm mới hoàn thành được 5 variants trong 4 giờ. Nếu tôi cố làm hết một mình, chắc chắn chỉ xong được Baseline và Variant 1 — và đúng ra Variant 1 lại là variant thất bại. Bài học cụ thể: chia việc theo layer (tôi lo retrieval + eval framework, Hiếu lo reranker) hiệu quả hơn nhiều so với chia việc theo sprint.

---

## 3. Điều tôi ngạc nhiên hoặc gặp khó khăn (100-150 từ)

Tôi không ngờ rằng chỉ thay prompt mà kết quả lại thay đổi nhiều đến vậy. Completeness nhảy từ 3.80 lên 4.50 (+0.70) — trong khi hybrid retrieval (Variant 1) làm tất cả metrics đi xuống.

Cụ thể nhất là câu q10 (VIP refund): Baseline trả lời đúng policy tiêu chuẩn nhưng bỏ qua hoàn toàn VIP clause → Completeness = 1. Chỉ cần thêm Tier 2 instruction vào prompt — "nếu context có policy chung nhưng thiếu exception, hãy nêu policy chung kèm ghi chú exception không có trong tài liệu" — là Completeness lên 5. Model không thiếu thông tin, nó chỉ thiếu instruction để biết phải làm gì với thông tin đó.

Cái khó ở đây là prompt engineering không phải "viết thêm chữ" — phải hiểu được model đang fail ở đâu, tại sao, rồi mới viết được instruction trúng.

---

## 4. Phân tích một câu hỏi trong scorecard (150-200 từ)

**Câu hỏi:** q10 — "Khách hàng VIP có được hoàn tiền theo điều khoản đặc biệt không?"

**Phân tích:**

Ở Baseline, câu này có điểm: Faithfulness=5, Relevance=1, Context Recall=5, Completeness=1. Context Recall = 5 nghĩa là retrieval đã lấy đúng doc `policy_refund_v4.txt`. Lỗi nằm hoàn toàn ở generation: mặc dù context có mention VIP exception, model prompt v1 chỉ nêu policy tiêu chuẩn (30 ngày) và bỏ qua VIP clause → Answer Relevance và Completeness đều = 1 vì không trả lời đúng trọng tâm câu hỏi.

Sau khi chuyển sang prompt v3 (Variant 3), cùng câu này đạt Faithfulness=5, Relevance=3, Context Recall=5, Completeness=5. Cơ chế Tier 2 của prompt v3 yêu cầu model: nếu context có policy chung nhưng không có exception cụ thể thì phải nêu policy chung kèm ghi chú rằng exception không có trong tài liệu. Model áp dụng đúng → câu trả lời đầy đủ hơn nhiều, Completeness từ 1 lên 5.

Kết luận: lỗi q10 ở Baseline không phải indexing hay retrieval — hoàn toàn là generation do prompt v1 không có instruction đủ cụ thể về cách xử lý edge case.

---

## 5. Nếu có thêm thời gian, tôi sẽ làm gì? (50-100 từ)

Tôi muốn cải thiện độ tin cậy của **LLM-as-judge** và thử **cross-encoder reranker** thay vì LLM reranker.

Về evaluation: q07 (Approval Matrix) là ví dụ điển hình — Hiếu nhận ra LLM judge đánh giá sai câu này, câu trả lời thực ra đúng nhưng bị chấm thấp. Đây là giới hạn của LLM-as-judge: judge cũng có thể nhầm, đặc biệt với câu hỏi có alias hay tên không xuất hiện trong tài liệu. Nếu có thêm thời gian, tôi sẽ thêm human spot-check cho những câu có điểm thấp bất thường thay vì tin hoàn toàn vào judge. Với cross-encoder: V4 dùng LLM reranker tốn thêm 1 API call/query — một cross-encoder nhỏ như `ms-marco-MiniLM` có thể rerank nhanh và rẻ hơn, eval framework đã có sẵn, chỉ cần plug in và chạy lại scorecard.

---

*File: `reports/individual/NguyenBinhThanh.md`*
