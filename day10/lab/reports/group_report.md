# Báo Cáo Nhóm — Lab Day 10: Data Pipeline & Data Observability

**Tên nhóm:** Nhóm 29 — E403  
**Thành viên:**
| Tên | Vai trò (Day 10) | Email |
|-----|------------------|-------|
| Nguyễn Bình Thành | Ingestion / Raw Owner + Monitoring / Docs Owner | thanh14022005@gmail.com |
| Hàn Quang Hiếu | Cleaning & Quality Owner + Embed & Idempotency Owner | hieuhq14.sic@gmail.com |

**Ngày nộp:** 2026-04-15  
**Repo:** https://github.com/kain205/Nhom29-E403-day08-09-10  
**Độ dài khuyến nghị:** 600–1000 từ

---

## 1. Pipeline tổng quan

**Nguồn raw:** `data/raw/policy_export_dirty.csv` — 10 records gốc (Sprint 1–2 mở rộng lên 13 bằng cách inject thêm 3 row kiểm thử), CSV mẫu có đầy đủ các failure mode: duplicate chunk, thiếu `effective_date`, `doc_id` ngoài allowlist, ngày sai format DD/MM/YYYY, xung đột version HR (10 vs 12 ngày phép), chunk policy sai cửa sổ hoàn tiền (14 vs 7 ngày), chunk tương lai (`effective_date=2030-01-01`), và chunk quá ngắn.

**Luồng end-to-end:**
```
raw CSV → cleaning rules (R1–R9) → expectation suite (E1–E8) → embed ChromaDB (upsert + prune) → manifest → freshness check
```

**`run_id`** xuất hiện ở dòng đầu tiên của log và được ghi vào `artifacts/manifests/manifest_<run-id>.json`. Mỗi run tạo cleaned CSV, quarantine CSV, manifest JSON độc lập theo run_id.

**Lệnh chạy:**
```bash
python etl_pipeline.py run
```

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

**Người thực hiện Sprint 1:** Nguyễn Bình Thành

---

## 2. Cleaning & expectation

**Người thực hiện Sprint 2:** Hàn Quang Hiếu

Baseline đã có R1–R6 (allowlist doc_id, chuẩn hóa ngày ISO, quarantine HR stale, quarantine text rỗng, dedupe, fix refund 14→7). Nhóm thêm 3 rule mới (R7–R9) và 2 expectation mới trong Sprint 2.

### 2a. Bảng metric_impact

| Rule / Expectation mới | Loại | Severity | Tác động đo được | Chứng cứ |
|------------------------|------|----------|-----------------|-----------|
| **R7** `strip_cleaning_annotation` | cleaning rule | — | Xóa tag `[cleaned: stale_refund_window]` bị lọt vào raw từ lần chạy trước → `chunk_text` thay đổi → `chunk_id` mới → vector cũ bị prune (`embed_prune_removed=1`) | `artifacts/cleaned/cleaned_sprint2.csv` — cột `chunk_text` không còn tag |
| **R8** `quarantine_future_effective_date` | cleaning rule | — | Inject row `effective_date=2030-01-01` (row 12) → `quarantine_records` tăng từ 4 → 5; chunk không vào index | `artifacts/quarantine/quarantine_sprint2.csv` — `reason=future_effective_date` |
| **R9** `quarantine_invalid_exported_at` | cleaning rule | — | Inject row `exported_at=""` → `quarantine_records` tăng; `manifest.latest_exported_at` không bị nhiễm timestamp rác | `artifacts/quarantine/quarantine_sprint2.csv` — `reason=invalid_exported_at` |
| **E7** `no_future_effective_date` | expectation | **halt** | Double-check R8: nếu R8 bị bỏ qua, E7 FAIL → pipeline halt trước khi embed chunk ngày tương lai | Log sprint2: `expectation[no_future_effective_date] OK (halt) :: future_dated_rows=0` |
| **E8** `no_invalid_exported_at` | expectation | warn | Cảnh báo nếu chunk có `exported_at` rỗng/sai format lọt qua R9 | Log sprint2: `expectation[no_invalid_exported_at] OK (warn) :: invalid_exported_at_count=0` |

**Rule baseline đã hoạt động (Sprint 1–2):**
- R1: Quarantine `doc_id` ngoài allowlist → row 9 (`legacy_catalog_xyz_zzz`) bị quarantine
- R2: Chuẩn hóa `effective_date` DD/MM/YYYY → ISO
- R3: Quarantine HR stale (`effective_date < 2026-01-01`) → row 7 (bản HR 2025) bị quarantine
- R4: Quarantine `chunk_text` rỗng → row 11 bị quarantine
- R5: Dedupe `chunk_text` → row 2 (trùng row 1) bị quarantine
- R6: Fix refund 14→7 ngày → row 3 được sửa

**Ví dụ expectation fail có chủ đích (Sprint 3):**

Khi chạy `--no-refund-fix --skip-validate`, expectation E3 `refund_no_stale_14d_window` FAIL vì chunk vẫn chứa "14 ngày làm việc". Pipeline in `WARN: expectation failed but --skip-validate → tiếp tục embed` — hành vi có chủ đích để tạo bằng chứng before/after.

---

## 3. Before / after ảnh hưởng retrieval

**Người thực hiện Sprint 3:** Hàn Quang Hiếu

**Kịch bản inject:**  
Chạy pipeline với `--no-refund-fix --skip-validate` (run_id=s3-inject, 2026-04-15T09:18). Flag `--no-refund-fix` bỏ qua bước sửa "14 ngày làm việc" → "7 ngày làm việc", cho phép chunk sai version lọt vào cleaned. `--skip-validate` bypass expectation halt để tiếp tục embed dù suite báo vi phạm.

**Bằng chứng inject thành công:**
```
expectation[refund_no_stale_14d_window] FAIL (halt) :: violations=1   ← xác nhận 14 ngày trong cleaned
embed_prune_removed=1                                                   ← xóa chunk 7 ngày cũ khỏi DB
embed_upsert count=6                                                    ← embed chunk 14 ngày vào DB
manifest: artifacts/manifests/manifest_s3-inject.json (no_refund_fix=true)
```

**Kết quả định lượng:**

| Câu hỏi | Scenario | contains_expected | hits_forbidden | result |
|---------|----------|-------------------|----------------|--------|
| `q_refund_window` | inject-bad | yes | **yes** | FAIL |
| `q_refund_window` | sprint2 (clean) | yes | **no** | PASS |
| `q_leave_version` | inject-bad | yes | no | PASS |
| `q_leave_version` | sprint2 (clean) | yes | no | PASS |

**Phân tích:** Sau inject, `q_refund_window` có `hits_forbidden=yes` — top-k chứa chunk "14 ngày làm việc". Sau khi rerun pipeline chuẩn (sprint2), `embed_prune_removed=1` xóa vector stale → `hits_forbidden=no`. Đây là bằng chứng end-to-end: pipeline ETL làm sạch bảo vệ cả cleaning layer lẫn retrieval layer.

**Artifact:** `artifacts/eval/s3_clean_eval.csv` · `artifacts/eval/s3_inject_eval.csv`  
**Log evidence:** `artifacts/manifests/manifest_s3-inject.json`

---

## 4. Freshness & monitoring

**Người thực hiện Sprint 4:** Nguyễn Bình Thành  
**Thêm:** Demo UI (`app.py` — Streamlit)

**SLA được chọn:** 24 giờ (mặc định trong `monitoring/freshness_check.py`, có thể override qua `FRESHNESS_SLA_HOURS`).

**Ý nghĩa các trạng thái:**

| Trạng thái | Điều kiện | Hành động |
|-----------|-----------|-----------|
| **PASS** | `age_hours ≤ 24` | Data nguồn mới — pipeline đang nhận feed tươi, không cần can thiệp |
| **WARN** | Chưa áp dụng (có thể thêm ngưỡng 12h) | Cảnh báo sớm trước khi vi phạm SLA |
| **FAIL** | `age_hours > 24` | Data nguồn cũ quá SLA — kiểm tra hệ thống nguồn có đang export đúng lịch không |

**Kết quả trên bộ mẫu:**  
`freshness_check=FAIL` với `age_hours=121.2h` vì file `policy_export_dirty.csv` có `exported_at=2026-04-10T08:00:00` — cũ hơn ngày chạy pipeline 5 ngày. Đây là hành vi đúng: trong production, FAIL kích hoạt alert để đội data engineering kiểm tra lịch export từ hệ thống nguồn.

**Lệnh kiểm tra:**
```bash
python etl_pipeline.py freshness --manifest artifacts/manifests/manifest_sprint2.json
```

**Demo UI** (`app.py` — Nguyễn Bình Thành):  
Streamlit app 4 tab demo toàn bộ lab: chạy pipeline, xem decision table row-by-row (Kept/Quarantine), bảng eval PASS/FAIL, selector inject rule cho Sprint 3.
```bash
streamlit run app.py
```

---

## 5. Liên hệ Day 09

Pipeline Day 10 dùng **collection riêng** `day10_kb` (thay vì `day09_kb`) để không ảnh hưởng kết quả Day 09. Cùng corpus 5 tài liệu `data/docs/` với Day 09. Nếu tích hợp thật, agent Day 09 sẽ query `day10_kb` — được đảm bảo sạch bởi pipeline ETL này. Lý do tách collection: Day 10 thực hiện **full rebuild** với prune — mỗi lần run xoá vector cũ và upsert vector mới theo `chunk_id`, đảm bảo index là snapshot tại thời điểm publish; nếu dùng chung, các run Day 10 sẽ xoá vector Day 09 không liên quan.

---

## 6. Rủi ro còn lại & việc chưa làm

- **Freshness FAIL bình thường:** File mẫu có `exported_at` cố định (2026-04-10) — trong production cần cập nhật timestamp hoặc đổi `FRESHNESS_SLA_HOURS` cho phù hợp với chu kỳ export thực tế.
- **Eval top-k giới hạn:** `hits_forbidden` chỉ scan top-3 chunks. Với top_k thấp, chunk dirty có thể bị bỏ sót nếu semantic score không đủ cao. Giải pháp: tăng `--top-k` hoặc kết hợp LLM-judge eval.
- **Chưa tích hợp Great Expectations** hoặc pydantic validate schema thật — expectations hiện là rule-based custom.
- **Freshness chỉ đo tại boundary `publish`** — chưa đo latency tại `ingest`.
- **`access_control_sop.txt` chưa có** trong allowlist export CSV — nếu thêm doc mới cần cập nhật `ALLOWED_DOC_IDS`.
