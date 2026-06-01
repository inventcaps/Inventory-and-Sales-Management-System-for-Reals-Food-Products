# DB-Code Alignment Design

Date: 2026-06-01
Status: Draft
Approach: DB-driven (remove redundant Python code that duplicates DB triggers)

## Problem

The codebase's `models.py` is out of sync with the actual PostgreSQL schema, and
Python view code duplicates business logic already handled by DB triggers,
causing potential double-processing, inconsistencies, and confusion.

## Guiding Principles

1. **DB is source of truth** — triggers already run in production; Python code
   that duplicates them will be removed
2. **No schema changes** — all models remain `managed = False`
3. **Zero risk to production** — each change is a pure removal of redundant
   Python code or addition of missing model fields; no data migrations
4. **Signals.py stays** — it handles `auth_user` events (login/logout/signup)
   which have no DB triggers

## Section 1: Align models.py with Actual DB Schema

### 1.1 Add Missing Fields to Existing Models

| Model | Missing Fields (from DB) |
|---|---|
| `Products` | None — already complete |
| `Sales` | `withdrawal = models.ForeignKey(Withdrawals, null=True)` |
| `User2FASettings` | `phone_number`, `backup_email` |
| `LoginAttempts` | `browser`, `os`, `location`, `required_otp`, `is_trusted_device` |
| `TrustedDevice` | `browser`, `os` |
| `UserOTP` | `ip_address` |
| `UserActivity` | `last_logout` |
| `Notifications` | Change `item_type` max_length to 12 (was 20) |
| `Withdrawals` | `packaging_id`, `batch_id` — add FK fields |

### 1.2 Add Missing Model Classes

- **`FinancialLoss`** — maps to `financial_loss` table
  Fields: `withdrawal`, `item_type`, `item_id`, `item_name`, `quantity`,
  `unit_price`, `loss_amount`, `reason`, `loss_date`, `created_at`,
  `created_by_admin`, `is_archived`

### 1.3 NOT Adding (waste of time or dangerous)

- `current_month_expenses`/`current_month_sales` — PostgreSQL views, not tables
- Django admin/auth tables (`auth_group`, `auth_permission`, etc.) — Django
  manages these
- Changing `managed = False` → `True` — would let Django try ALTER TABLE

### Verification
- `python manage.py check` passes
- Import all new models in a Python shell
- Functional tests pass

---

## Section 2: Remove Redundant Python → Trigger Conflicts

### Inventory for What's Redundant

The following DB triggers already handle operations that Python views manually
duplicate:

| DB Trigger | What It Does | Redundant Python Code |
|---|---|---|
| `trg_withdrawals_stock_handler` | Deducts/restores batch qty & inventory on withdrawal INSERT/UPDATE/DELETE | Manual `product_batches` / `product_inventory` updates in withdrawal views |
| `log_product_batches_insert` | Auto-adds to `product_inventory` & logs stock change | Manual `product_inventory` updates after batch creation |
| `log_product_batches_delete` | Deducts from `product_inventory` & logs stock change | Manual inventory deductions in batch delete views |
| `log_product_batches_update` | Handles qty diffs & product reassignments | Manual stock adjustment on batch edit |
| `log_raw_material_batches_insert` | Auto-adds to `raw_material_inventory` | Manual inventory updates after raw batch creation |
| `log_raw_material_batches_delete` | Deducts from `raw_material_inventory` | Manual deductions in raw batch delete |
| `log_raw_material_batches_update` | Handles qty diffs | Manual stock adjustment on raw batch edit |
| `trg_handle_packaging_stock_batches_update` | Deducts/restores packaging stock | Packaging stock handling in batch views |
| `trg_create_financial_loss_func` | Auto-inserts into `financial_loss` for EXPIRED/DAMAGED withdrawals | Financial loss computation in `views/reports.py` |
| `trg_withdrawal_sales_func` | Auto-creates `sales` record for SOLD withdrawals | Manual `Sales.objects.create()` in withdrawal views |
| `log_sales_insert` / `log_sales_delete` | Updates `sales_summary` | Manual sales_summary aggregation |
| `log_expenses_insert` / `log_expenses_delete` | Updates `expenses_summary` | Manual expenses_summary aggregation |
| `log_products_insert` | Auto-creates `product_inventory` row | Manual inventory creation in product views |
| `log_raw_materials_insert` | Auto-creates `raw_material_inventory` row | Manual inventory creation in material views |

### 2.1 Removal Strategy

For each redundant block:

1. Identify the exact lines/functions in view code that duplicate trigger logic
2. Remove them — do NOT replace with anything
3. Keep HTTP-handling code (permission checks, form validation, response formatting)
4. Keep complex business logic that triggers don't handle (e.g., `generate_receipt_number`, photo upload handling)

### 2.2 Files to Modify

| File | What to Remove |
|---|---|
| `views/withdrawals.py` | Manual `product_batches` qty updates, manual `product_inventory` updates, manual `Sales.objects.create()` for withdrawals, manual financial loss computation |
| `views/products.py` | Manual `product_inventory` creation/updates in batch views, manual stock_changes inserts |
| `views/materials.py` | Manual `raw_material_inventory` creation/updates, manual stock_changes inserts |
| `views/sales.py` | Manual `sales_summary`/`expenses_summary` updates, redundant aggregation code |
| `views/reports.py` | Financial loss computation (trigger handles now) |

### 2.3 Safety Rules
- Every removal is verified: confirm the trigger handles ALL cases (INSERT,
  UPDATE, DELETE, archive toggle)
- If a trigger only handles INSERT but Python handles UPDATE+DELETE, keep the
  Python code for UPDATE/DELETE
- Session variable `app.skip_packaging_trigger` / `app.skip_batch_inventory_trigger`
  are checked by triggers — we set these in Python to prevent double-processing
  when Python intentionally does its own handling

---

## Section 3: Clean Up Dead URL Patterns & CBVs (from audit)

- Remove 3 unused CBV URL patterns: `ExpenseBulkDeleteView`,
  `RawMaterialBatchBulkDeleteView`, `WithdrawalBulkDeleteView`
- Remove their CBV view classes if nothing else references them

---

## Section 4: What Will NOT Change

- `signals.py` — stays as-is (handles auth_user events only)
- Photo file cleanup signals in `products.py` — stays (no DB trigger for file I/O)
- `generate_receipt_number` — stays (no trigger equivalent)
- `check_expiration_notifications` function (DB scheduled function) — stays
- All URL patterns for main views — stays
- All templates — stays
- Test infrastructure — stays

## Risk Mitigation

1. **Per-file diffs must be reviewed** — each file gets its own commit with
   clear message
2. **Test after every commit** — run `pytest` after each change
3. **Rollback plan** — `git revert <commit>` for any file if needed
4. **No data loss** — removing Python code that duplicates DB triggers means
   the trigger still runs; worst case is a missing log entry, not data
   corruption
5. **Order matters** — do models.py alignment FIRST so all fields exist before
   removing view code that references them
