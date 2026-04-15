# Báo Cáo Cá Nhân — Lab Day 10: Data Pipeline & Observability

**Họ và tên:** Hàn Quang Hiếu  
**Vai trò:** Inject Corruption & Eval Owner (Sprint 3) + Monitoring / Docs Owner (Sprint 4)  
**Ngày nộp:** 2026-04-15  
**run_id tham chiếu:** `inject-bad`, `sprint2`

---

## 1. Tôi phụ trách phần nào?

**File / module:**
- Sprint 3: chạy inject corruption (`python etl_pipeline.py run --run-id inject-bad --no-refund-fix --skip-validate`), chạy `eval_retrieval.py` để tạo `artifacts/eval/eval_inject_bad.csv` và `artifacts/eval/eval_after_clean.csv`, so sánh before/after
- Sprint 4: `monitoring/freshness_check.py` — đọc manifest, tính `age_hours`, trả về PASS/WARN/FAIL; chạy `python etl_pipeline.py freshness --manifest artifacts/manifests/manifest_sprint2.json`; viết `docs/runbook.md` và `docs/quality_report.md`

**Kết nối với thành viên khác:**
- Nhận manifest JSON từ pipeline do Nguyễn Bình Thành viết → dùng `latest_exported_at` để tính freshness.
- Dùng kết quả eval CSV (before/after) làm bằng chứng cho quality report và group report.

**Bằng chứng:** `artifacts/eval/eval_inject_bad.csv` và `artifacts/eval/eval_after_clean.csv` được tạo trong Sprint 3; `artifacts/logs/run_inject-bad.log` ghi lại toàn bộ quá trình inject.

---

## 2. Một quyết định kỹ thuật

**Quyết định: dùng `--skip-validate` thay vì sửa expectation để tạo bằng chứng inject.**

Khi thiết kế Sprint 3, có hai cách để embed data xấu vào index: (a) tắt expectation E3 trong code, hoặc (b) giữ nguyên expectation và dùng flag `--skip-validate` để bypass halt.

Chọn (b) vì: cách (a) làm mất bằng chứng — log sẽ không còn dòng `expectation[refund_no_stale_14d_window] FAIL`, không chứng minh được pipeline đã phát hiện lỗi. Cách (b) giữ nguyên expectation hoạt động đúng (FAIL được ghi vào log), chỉ bypass halt để tiếp tục embed — đúng tinh thần "inject có chủ đích, có kiểm soát".

Kết quả: log `run_inject-bad.log` có đủ hai dòng:
```
expectation[refund_no_stale_14d_window] FAIL (halt) :: violations=1
WARN: expectation failed but --skip-validate → tiếp tục embed (chỉ dùng cho demo Sprint 3).
```
Manifest ghi `"skipped_validate": true` — audit trail rõ ràng, không nhầm với run production.

---

## 3. Một lỗi / anomaly đã xử lý

**Triệu chứng:** Sau khi chạy inject-bad và eval, chạy lại pipeline chuẩn (sprint2) rồi eval lại nhưng `eval_after_clean.csv` vẫn có `hits_forbidden=yes` cho `q_refund_window`.

**Phát hiện:** Kiểm tra thứ tự lệnh — `eval_retrieval.py` được chạy trước khi pipeline sprint2 hoàn thành (`PIPELINE_OK` chưa xuất hiện trong terminal). Collection `day10_kb` vẫn đang ở trạng thái inject-bad.

**Fix:** Chờ pipeline sprint2 in `PIPELINE_OK` và `embed_prune_removed=1` trong log, rồi mới chạy eval. Sau đó `eval_after_clean.csv` cho kết quả đúng: `q_refund_window hits_forbidden=no`.

**Metric thay đổi:** `eval_inject_bad.csv` → `q_refund_window hits_forbidden=yes`; `eval_after_clean.csv` → `q_refund_window hits_forbidden=no`. Delta trực tiếp từ `embed_prune_removed=1` trong `artifacts/logs/run_sprint2.log`.

---

## 4. Bằng chứng trước / sau

**Trước — run_id=inject-bad** (`artifacts/eval/eval_inject_bad.csv`):
```
q_refund_window | contains_expected=yes | hits_forbidden=yes | top_k_used=3
```
→ Top-k vẫn chứa chunk "14 ngày làm việc" dù top-1 đã đúng — đúng lý do `hits_forbidden` quét toàn bộ top-k.

**Sau — run_id=sprint2** (`artifacts/eval/eval_after_clean.csv`):
```
q_refund_window | contains_expected=yes | hits_forbidden=no | top_k_used=3
q_leave_version | contains_expected=yes | hits_forbidden=no | top1_doc_expected=yes
```
→ Tất cả câu đều sạch sau khi pipeline chuẩn prune vector stale.

---

## 5. Cải tiến tiếp theo

Nếu có thêm 2 giờ: thêm cột `run_id` vào output CSV của `eval_retrieval.py` — hiện tại hai file `eval_inject_bad.csv` và `eval_after_clean.csv` không có trường nào ghi rõ run_id tương ứng, phải đối chiếu thủ công với tên file. Nếu gộp thành một file có cột `scenario` (inject / clean) và `run_id`, việc so sánh before/after sẽ tự động hóa được và dễ audit hơn.
