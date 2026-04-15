# Data contract — Lab Day 10

> Đồng bộ với `contracts/data_contract.yaml` — file này là bản mô tả chi tiết dạng Markdown.

**Owner team:** Nhóm 29 — E403  
**Cập nhật:** 2026-04-15

---

## 1. Nguồn dữ liệu (source map)

| Nguồn | Phương thức ingest | Failure mode chính | Metric / alert |
|-------|-------------------|--------------------|----------------|
| `data/raw/policy_export_dirty.csv` | `load_raw_csv()` đọc CSV UTF-8 | Duplicate chunk, thiếu `effective_date`, `doc_id` ngoài allowlist, ngày sai format DD/MM/YYYY | `quarantine_records` trong log; expectation E2/E5 halt |
| `data/docs/*.txt` (5 tài liệu canonical) | Đọc trực tiếp khi cần so sánh | Version conflict (HR 10 ngày vs 12 ngày, refund 14 ngày vs 7 ngày) | E3 `refund_no_stale_14d_window` halt; E6 `hr_leave_no_stale_10d_annual` halt |

**Failure mode đã gặp trong lab:**
- Row 2: duplicate `chunk_text` với row 1 → `reason=duplicate_chunk_text`
- Row 5: `effective_date` rỗng → `reason=missing_effective_date`
- Row 7: HR policy bản 2025 (`effective_date=2025-01-01`) → `reason=stale_hr_policy_effective_date`
- Row 9: `doc_id=legacy_catalog_xyz_zzz` ngoài allowlist → `reason=unknown_doc_id`
- Row 11: `chunk_text` rỗng → `reason=missing_chunk_text`
- Row 12: `effective_date=2030-01-01` (tương lai) → `reason=future_effective_date`
- Row 13: `chunk_text="OK."` quá ngắn (3 ký tự) → `reason=chunk_too_short`

---

## 2. Schema cleaned

| Cột | Kiểu | Bắt buộc | Ghi chú |
|-----|------|----------|---------|
| `chunk_id` | string | Có | SHA-256(doc_id\|chunk_text\|seq)[:16] — ổn định theo nội dung |
| `doc_id` | string | Có | Phải thuộc `allowed_doc_ids` trong contract YAML |
| `chunk_text` | string | Có | Tối thiểu 20 ký tự sau strip; không chứa tag `[cleaned: ...]` |
| `effective_date` | date (YYYY-MM-DD) | Có | Chuẩn hóa từ DD/MM/YYYY nếu cần; không được là tương lai |
| `exported_at` | datetime (ISO 8601) | Có | Dùng để tính freshness; phải match `^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}` |

---

## 3. Quy tắc quarantine vs drop

- **Quarantine** (ghi vào `artifacts/quarantine/quarantine_<run-id>.csv`): mọi row bị loại đều được lưu kèm `reason` để audit. Không xóa vĩnh viễn.
- **Approve merge lại**: cần sửa nguồn gốc (fix `effective_date`, cập nhật allowlist, hoặc xác nhận version mới) rồi rerun pipeline — không merge thủ công vào cleaned CSV.
- **Drop hoàn toàn**: chỉ khi row là duplicate hoàn toàn (`reason=duplicate_chunk_text`) và bản gốc đã có trong cleaned.

---

## 4. Phiên bản & canonical

| Tài liệu | Source of truth | Version hiện hành | Ghi chú |
|----------|----------------|-------------------|---------|
| Policy refund | `data/docs/policy_refund_v4.txt` | v4 — 7 ngày làm việc | Bản v3 (14 ngày) là stale; R6 fix tự động |
| HR leave policy | `data/docs/hr_leave_policy.txt` | 2026 — 12 ngày phép | Bản 2025 (10 ngày) bị quarantine bởi R3 |
| SLA P1 | `data/docs/sla_p1_2026.txt` | 2026 — 15 phút / 4 giờ | — |
| IT Helpdesk FAQ | `data/docs/it_helpdesk_faq.txt` | hiện hành | — |
| Access Control SOP | `data/docs/access_control_sop.txt` | hiện hành | Chưa có trong allowlist export CSV |

**Cutoff versioning HR:** `hr_leave_min_effective_date = 2026-01-01` — định nghĩa trong `contracts/data_contract.yaml`, tham chiếu trong `cleaning_rules.py` (R3).
