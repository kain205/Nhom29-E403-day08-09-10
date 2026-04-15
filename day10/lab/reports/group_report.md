# Báo Cáo Nhóm — Lab Day 10: Data Pipeline & Data Observability

**Tên nhóm:** Nhóm 29 — E403  
**Thành viên:**
| Tên | Vai trò (Day 10) | Email |
|-----|------------------|-------|
| Hàn Quang Hiếu | Ingestion Owner + Cleaning & Quality Owner | — |
| Nguyễn Bình Thành | Embed & Idempotency Owner + Monitoring / Docs Owner | — |

**Ngày nộp:** 2026-04-15  
**Repo:** Nhom29-E403-day08  
**Độ dài khuyến nghị:** 600–1000 từ

---

## 1. Pipeline tổng quan

**Nguồn raw:** `data/raw/policy_export_dirty.csv` — 10 records gốc (Sprint 1–2 mở rộng lên 13 bằng cách inject thêm 3 row kiểm thử), CSV mẫu có đầy đủ các failure mode: duplicate chunk, thiếu `effective_date`, `doc_id` ngoài allowlist, ngày sai format DD/MM/YYYY, xung đột version HR (10 vs 12 ngày phép), chunk policy sai cửa sổ hoàn tiền (14 vs 7 ngày), chunk tương lai (`effective_date=2030-01-01`), và chunk quá ngắn.

**Luồng end-to-end:**
```
python etl_pipeline.py run
```
Lệnh này chạy toàn bộ: `load_raw_csv` → `clean_rows` (R1–R9) → `run_expectations` (E1–E8) → embed ChromaDB (upsert + prune) → ghi manifest → `check_manifest_freshness`.

**`run_id`** xuất hiện ở dòng đầu tiên của log (`artifacts/logs/run_<run-id>.log`) và được ghi vào `artifacts/manifests/manifest_<run-id>.json`.

**Kết quả Sprint 2 (run_id=sprint2, 2026-04-15):**

| Metric | Giá trị |
|--------|---------|
| raw_records | 13 |
| cleaned_records | 6 |
| quarantine_records | 7 |
| embed_upsert count | 6 |
| expectations passed | 8/8 (E1–E8) |
| embed_prune_removed | 1 |
| freshness_check | FAIL (age=121.2h, SLA=24h — data snapshot cũ, expected) |
| manifest | `artifacts/manifests/manifest_sprint2.json` |

---

## 2. Cleaning & expectation

Baseline đã có R1–R6 (allowlist doc_id, chuẩn hóa ngày ISO, quarantine HR stale, quarantine text rỗng, dedupe, fix refund 14→7). Nhóm thêm 3 rule mới và 2 expectation mới trong Sprint 2.

### 2a. Bảng metric_impact

| Rule / Expectation mới | Loại | Severity | Tác động đo được | Chứng cứ |
|------------------------|------|----------|-----------------|-----------|
| **R7** `strip_cleaning_annotation` | cleaning rule | — | Xóa tag `[cleaned: stale_refund_window]` bị lọt vào raw từ lần chạy trước → `chunk_text` thay đổi → `chunk_id` mới → vector cũ bị prune (`embed_prune_removed=1`) | `artifacts/cleaned/cleaned_sprint2.csv` — cột `chunk_text` không còn tag |
| **R8** `quarantine_future_effective_date` | cleaning rule | — | Inject row `effective_date=2030-01-01` (row 12) → `quarantine_records` tăng từ 4 → 5; chunk không vào index | `artifacts/quarantine/quarantine_sprint2.csv` — `reason=future_effective_date` |
| **R9** `quarantine_invalid_exported_at` | cleaning rule | — | Inject row `exported_at=""` → `quarantine_records` tăng; `manifest.latest_exported_at` không bị nhiễm timestamp rác | `artifacts/quarantine/quarantine_sprint2.csv` — `reason=invalid_exported_at` |
| **E7** `no_future_effective_date` | expectation | **halt** | Double-check R8: nếu R8 bị bỏ qua (`--no-future-date-check`), E7 FAIL → pipeline halt trước khi embed chunk ngày tương lai | Log sprint2: `expectation[no_future_effective_date] OK (halt) :: future_dated_rows=0` |
| **E8** `no_invalid_exported_at` | expectation | warn | Cảnh báo nếu chunk có `exported_at` rỗng/sai format lọt qua R9 | Log sprint2: `expectation[no_invalid_exported_at] OK (warn) :: invalid_exported_at_count=0` |

**Rule baseline đã hoạt động (Sprint 1–2):**
- R1: Quarantine `doc_id` ngoài allowlist → row 9 (`legacy_catalog_xyz_zzz`) bị quarantine
- R2: Chuẩn hóa `effective_date` DD/MM/YYYY → ISO (không có row nào cần trong bộ mẫu gốc)
- R3: Quarantine HR stale (`effective_date < 2026-01-01`) → row 7 (bản HR 2025) bị quarantine
- R4: Quarantine `chunk_text` rỗng → row 11 bị quarantine
- R5: Dedupe `chunk_text` → row 2 (trùng row 1) bị quarantine
- R6: Fix refund 14→7 ngày → row 3 được sửa

**Ví dụ expectation fail có chủ đích (Sprint 3):**

Khi chạy `--no-refund-fix --skip-validate`, expectation E3 `refund_no_stale_14d_window` FAIL vì chunk vẫn chứa "14 ngày làm việc". Pipeline in `WARN: expectation failed but --skip-validate → tiếp tục embed` — hành vi có chủ đích để tạo bằng chứng before/after. Log: `artifacts/logs/run_inject-bad.log`.

---

## 3. Before / after ảnh hưởng retrieval

**Kịch bản inject (Sprint 3):**
```bash
python etl_pipeline.py run --run-id inject-bad --no-refund-fix --skip-validate
python eval_retrieval.py --out artifacts/eval/eval_inject_bad.csv
```

Bỏ R6 → chunk refund vẫn chứa "14 ngày làm việc" → embed vào index → retrieval trả về chunk stale.

**Kết quả định lượng:**

| Câu hỏi | Scenario | contains_expected | hits_forbidden | top1_doc_expected |
|---------|----------|-------------------|----------------|-------------------|
| `q_refund_window` | inject-bad | yes | **yes** | — |
| `q_refund_window` | sprint2 (clean) | yes | **no** | — |
| `q_leave_version` | inject-bad | yes | no | yes |
| `q_leave_version` | sprint2 (clean) | yes | no | yes |

**Phân tích:** Sau inject, `q_refund_window` có `hits_forbidden=yes` — top-k chứa chunk "14 ngày làm việc" dù top-1 đã đúng. Đây là lý do `hits_forbidden` quét toàn bộ top-k, không chỉ top-1. Sau khi rerun pipeline chuẩn (sprint2), `embed_prune_removed=1` xóa vector stale → `hits_forbidden=no`.

Artifact: `artifacts/eval/eval_inject_bad.csv` (inject) và `artifacts/eval/eval_after_clean.csv` (clean).

---

## 4. Freshness & monitoring

**SLA chọn:** 24 giờ — phù hợp với chu kỳ export daily trong production.

**Kết quả trên manifest sprint2:**
- `latest_exported_at = 2026-04-10T08:00:00`
- `age_hours = 121.2h` → **FAIL** (vượt SLA 24h)

**Ý nghĩa PASS/WARN/FAIL:**
- `PASS`: data được export trong vòng 24h — pipeline đang chạy đúng chu kỳ.
- `FAIL`: data cũ hơn 24h — cần trigger rerun hoặc điều tra nguồn export.
- `WARN`: manifest thiếu timestamp — R9 chưa chặn được row `exported_at` rỗng.

Trong lab, FAIL là bình thường vì CSV mẫu có `exported_at` cố định ngày 2026-04-10. Nhóm ghi nhận đây là "data snapshot" — SLA áp cho pipeline production, không phải cho snapshot tĩnh.

---

## 5. Liên hệ Day 09

Pipeline Day 10 dùng **collection riêng** `day10_kb` (thay vì `day09_kb`) để không ảnh hưởng kết quả Day 09. Cùng corpus 5 tài liệu `data/docs/` với Day 09. Nếu tích hợp thật, agent Day 09 sẽ query `day10_kb` — được đảm bảo sạch bởi pipeline ETL này — thay vì index thủ công. Bằng chứng: `eval_after_clean.csv` dùng cùng câu hỏi golden với Day 09 và cho kết quả đúng sau khi pipeline clean.

---

## 6. Rủi ro còn lại & việc chưa làm

- Chưa tích hợp Great Expectations hoặc pydantic validate schema thật.
- Freshness chỉ đo tại boundary `publish` — chưa đo tại `ingest`.
- `access_control_sop.txt` chưa có trong allowlist export CSV.
- Eval chỉ dùng keyword matching — chưa có LLM-judge.
