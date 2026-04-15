# Báo Cáo Cá Nhân — Lab Day 10: Data Pipeline & Observability

**Họ và tên:** Nguyễn Bình Thành  
**Vai trò:** Embed & Idempotency Owner + Monitoring / Docs Owner  
**Ngày nộp:** 2026-04-15  
**run_id tham chiếu:** `sprint2`, `inject-bad`

---

## 1. Tôi phụ trách phần nào?

**File / module:**
- `quality/expectations.py` — toàn bộ expectation suite E1–E8, hàm `run_expectations()`, logic phân biệt `warn` vs `halt`
- `monitoring/freshness_check.py` — hàm `check_manifest_freshness()`, parse ISO timestamp, tính `age_hours`
- `etl_pipeline.py` — phần `cmd_embed_internal()`: ChromaDB upsert, prune vector cũ (`embed_prune_removed`), ghi manifest
- `app.py` — Streamlit demo UI: 4 tab tương ứng 4 sprint, chạy pipeline qua subprocess, hiển thị decision table (Kept/Quarantine), bảng eval kết quả, selector inject rule
- `docs/pipeline_architecture.md`, `docs/data_contract.md`, `docs/runbook.md`, `docs/quality_report.md`

**Kết nối với thành viên khác:**
- Nhận output `cleaned` (list dicts) từ `clean_rows()` của Hàn Quang Hiếu → chạy `run_expectations()`.
- `chunk_id` do Hàn Quang Hiếu tính (SHA-256 hash) → tôi dùng làm key upsert trong ChromaDB.
- `exported_at` trong cleaned rows → tôi lấy max để ghi `latest_exported_at` vào manifest → freshness check.

**Bằng chứng:** Hàm `cmd_embed_internal()` trong `etl_pipeline.py` có comment ghi rõ logic prune; `freshness_check.py` có docstring mô tả boundary đo.

---

## 2. Một quyết định kỹ thuật

**Quyết định: prune vector cũ trước mỗi lần upsert (index = snapshot publish).**

Khi thiết kế embed, có hai lựa chọn: (a) chỉ upsert, không xóa gì — đơn giản nhưng vector cũ tích lũy; (b) lấy toàn bộ id hiện có, tính `drop = prev_ids - new_ids`, xóa trước khi upsert.

Chọn (b) vì: nếu một chunk bị quarantine ở run sau (ví dụ R7 strip tag làm `chunk_id` thay đổi), vector cũ vẫn còn trong index và có thể xuất hiện trong top-k — đúng failure mode của `hits_forbidden`. Prune đảm bảo index luôn là **snapshot chính xác** của cleaned run gần nhất.

Tác động đo được: Sprint 2 log có `embed_prune_removed=1` — vector của chunk refund cũ (có tag `[cleaned: stale_refund_window]` trong `chunk_text`) bị xóa sau khi R7 strip tag làm `chunk_id` thay đổi. Rerun lần 2 với cùng data: `embed_prune_removed` không xuất hiện (không có gì để prune) — xác nhận idempotency.

---

## 3. Một lỗi / anomaly đã xử lý

**Triệu chứng:** Sau Sprint 3 inject-bad, chạy lại pipeline chuẩn (sprint2) nhưng `eval_retrieval.py` vẫn trả về `hits_forbidden=yes` cho `q_refund_window`.

**Phát hiện:** Kiểm tra log sprint2 — thấy `embed_prune_removed=1`, nghĩa là có vector bị xóa. Nhưng eval vẫn fail. Nguyên nhân: chạy `eval_retrieval.py` **trước** khi pipeline sprint2 hoàn thành embed — collection vẫn đang ở trạng thái inject-bad.

**Fix:** Đảm bảo thứ tự: (1) chạy pipeline chuẩn đến `PIPELINE_OK`, (2) mới chạy eval. Sau khi chạy đúng thứ tự: `embed_prune_removed=1` trong log sprint2 → eval sprint2 cho `hits_forbidden=no`.

**Metric thay đổi:** `eval_inject_bad.csv`: `q_refund_window hits_forbidden=yes` → `eval_after_clean.csv`: `q_refund_window hits_forbidden=no`. Delta rõ ràng, khớp với `embed_prune_removed=1`.

---

## 4. Bằng chứng trước / sau

**run_id=inject-bad** (vector stale còn trong index):
```
q_refund_window | hits_forbidden=yes | top1_doc_id=policy_refund_v4
q_leave_version | contains_expected=yes | hits_forbidden=no | top1_doc_expected=yes
```

**run_id=sprint2** (sau prune + upsert sạch):
```
q_refund_window | hits_forbidden=no | top1_doc_id=policy_refund_v4
q_leave_version | contains_expected=yes | hits_forbidden=no | top1_doc_expected=yes
```

`embed_prune_removed=1` trong `artifacts/logs/run_sprint2.log` là bằng chứng trực tiếp vector stale đã bị xóa. Artifact: `artifacts/eval/eval_inject_bad.csv` và `artifacts/eval/eval_after_clean.csv`.

---

## 5. Demo UI (Sprint 4 — thêm)

Tạo `app.py` — Streamlit single-file app để demo toàn bộ lab trực tiếp trên trình duyệt. Thiết kế 4 tab:

| Tab | Nội dung |
|-----|----------|
| Sprint 1 — Ingest | Chạy pipeline + bảng decision row-by-row (màu xanh=Kept, đỏ=Quarantine + reason) |
| Sprint 2 — Clean | Bảng metric_impact so sánh baseline vs sprint2 |
| Sprint 3 — Inject | Checkbox chọn rule nào bị tắt (`--no-refund-fix`, `--skip-validate`…) + bảng eval PASS/FAIL |
| Sprint 4 — Monitoring | Freshness status từ manifest, link artifact |

Quyết định kỹ thuật: dùng `subprocess.run()` để gọi `etl_pipeline.py` thay vì import trực tiếp — tránh side effect ChromaDB bị re-init khi Streamlit hot-reload. Auto-restore mặc định `False` để người demo có thể quan sát trạng thái inject trước khi restore.

**Chạy UI:**
```bash
streamlit run app.py
```

---

## 6. Cải tiến tiếp theo

Nếu có thêm 2 giờ: đo freshness tại **2 boundary** — `ingest` (khi `load_raw_csv` đọc file, ghi `ingest_timestamp` vào manifest) và `publish` (hiện tại). Hai boundary cho phép phân biệt "data cũ từ nguồn" vs "pipeline chạy chậm" — hai nguyên nhân khác nhau cần xử lý khác nhau. Hiện tại chỉ có `publish` boundary nên không phân biệt được hai trường hợp này.
