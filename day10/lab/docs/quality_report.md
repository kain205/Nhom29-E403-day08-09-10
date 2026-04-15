# Quality report — Lab Day 10

**Nhóm:** Nhóm 29 — E403  
**run_id:** sprint2  
**Ngày:** 2026-04-15

---

## 1. Tóm tắt số liệu

| Chỉ số | Sprint 1 (baseline) | Sprint 2 (clean + R7–R9) | Sprint 3 (inject-bad) | Ghi chú |
|--------|--------------------|--------------------------|-----------------------|---------|
| raw_records | 10 | 13 | 10 | Sprint 2 thêm 3 row inject vào raw |
| cleaned_records | 6 | 6 | 6 | Số cleaned ổn định sau khi rules đủ |
| quarantine_records | 4 | 7 | 4 | Sprint 2: +3 row inject bị chặn đúng |
| Expectations passed | 6/6 | 8/8 | 7/8 (E3 FAIL) | Sprint 3: E3 halt vì `--no-refund-fix` |
| Pipeline halt? | Không | Không | Có (bypass bằng `--skip-validate`) | Sprint 3 cố ý |
| embed_prune_removed | — | 1 | 1 | Vector cũ bị xóa khi chunk_id thay đổi |
| freshness_check | FAIL (120.3h) | FAIL (121.2h) | FAIL (121.0h) | Data snapshot cũ — expected |

---

## 2. Before / after retrieval

### Câu hỏi then chốt: refund window (`q_refund_window`)

**Trước (inject-bad — `run_id=inject-bad`, `--no-refund-fix --skip-validate`):**
```
question_id,contains_expected,hits_forbidden,top1_preview
q_refund_window,yes,yes,"Yêu cầu được gửi trong vòng 7 ngày làm việc..."
```
→ `hits_forbidden=yes`: top-k vẫn chứa chunk "14 ngày làm việc" từ bản stale được embed.

**Sau (sprint2 — pipeline chuẩn, R6 fix refund):**
```
question_id,contains_expected,hits_forbidden,top1_preview
q_refund_window,yes,no,"Yêu cầu được gửi trong vòng 7 ngày làm việc kể từ thời điểm xác nhận đơn hàng."
```
→ `hits_forbidden=no`: chunk stale đã bị prune, chỉ còn chunk đúng "7 ngày".

**Kết luận:** Pipeline fix refund (R6) + prune vector cũ loại bỏ hoàn toàn chunk stale khỏi retrieval.

---

### Merit: versioning HR — `q_leave_version`

**Trước (nếu không có R3 quarantine HR stale):** chunk "10 ngày phép năm" (bản 2025) sẽ lọt vào index → `hits_forbidden=yes`.

**Sau (sprint2 — R3 quarantine `effective_date < 2026-01-01`):**
```
question_id,contains_expected,hits_forbidden,top1_doc_expected,top1_preview
q_leave_version,yes,no,yes,"Nhân viên dưới 3 năm kinh nghiệm được 12 ngày phép năm theo chính sách 2026."
```
→ `contains_expected=yes` (12 ngày), `hits_forbidden=no` (không có "10 ngày phép năm"), `top1_doc_expected=yes` (top-1 từ `hr_leave_policy`).

Artifact: `artifacts/eval/eval_after_clean.csv`

---

## 3. Freshness & monitor

**SLA chọn:** 24 giờ (`FRESHNESS_SLA_HOURS=24` trong `.env`).

**Kết quả sprint2:**
```
freshness_check=FAIL {"latest_exported_at": "2026-04-10T08:00:00", "age_hours": 121.207, "sla_hours": 24.0, "reason": "freshness_sla_exceeded"}
```

**Giải thích:** `latest_exported_at` lấy từ max `exported_at` của cleaned rows = `2026-04-10T08:00:00`. Tại thời điểm chạy lab (2026-04-15), data đã 121 giờ tuổi — vượt SLA 24h. Đây là hành vi **đúng và có chủ đích** với data snapshot tĩnh trong lab. Trong production, FAIL này sẽ trigger alert để rerun pipeline từ nguồn mới hơn.

---

## 4. Corruption inject (Sprint 3)

**Kịch bản:** Chạy `python etl_pipeline.py run --run-id inject-bad --no-refund-fix --skip-validate`

- `--no-refund-fix`: bỏ R6, chunk refund vẫn chứa "14 ngày làm việc" → embed vào index.
- `--skip-validate`: bypass halt khi E3 fail → pipeline tiếp tục embed dù expectation báo lỗi.

**Phát hiện:**
- Log: `expectation[refund_no_stale_14d_window] FAIL (halt) :: violations=1`
- Manifest: `"no_refund_fix": true, "skipped_validate": true`
- Eval: `artifacts/eval/eval_inject_bad.csv` → `q_refund_window: hits_forbidden=yes`

**Phục hồi:** Rerun pipeline chuẩn (sprint2) → `embed_prune_removed=1` (xóa vector stale) → eval sạch.

---

## 5. Hạn chế & việc chưa làm

- Chưa tích hợp Great Expectations hoặc pydantic validate schema thật (dùng custom expectation suite đơn giản).
- Freshness chỉ đo tại boundary `publish` — chưa đo tại `ingest` (2 boundary cho Distinction).
- Eval chỉ dùng keyword matching — chưa có LLM-judge để đánh giá chất lượng câu trả lời.
- `access_control_sop.txt` chưa được đưa vào allowlist export CSV.
