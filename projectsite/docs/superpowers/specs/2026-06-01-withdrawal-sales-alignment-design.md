# Withdrawal-Sales Alignment Design

Date: 2026-06-01
Status: Draft
Approach: Per-item Sales display (Option A)

## Problem

The DB trigger `trg_withdrawal_sales_func` fires on INSERT of each SOLD withdrawal row and creates a **per-item** Sales record. Python code in `WithdrawItemView.post()` then creates an **additional** aggregate Sales record per order group. This causes a double-insert bug: an order with 3 products produces 4 Sales records (3 from trigger + 1 from Python), inflating monthly reports.

The trigger is INSERT-only — it does NOT handle UPDATE or DELETE for Sales records. Python currently handles UPDATE/DELETE by searching Sales records via fragile `description__icontains` matching instead of using the `withdrawal` FK.

Additionally, when a withdrawal's reason changes from `SOLD` to `DAMAGED`/`EXPIRED`/`OTHERS`, no code deletes the corresponding Sales record (ghost revenue).

## Guiding Principles

1. **Trigger handles INSERT** — `trg_withdrawal_sales_func` per-item Sales records are correct and sufficient
2. **No double-insert** — Python must not create duplicate Sales records
3. **Use the FK** — `Sales.withdrawal` was added to models.py; all lookups should use it
4. **Fix the gap** — reason-change must delete orphan Sales records
5. **UPDATE/DELETE stays in Python** — trigger doesn't handle these

## Changes

### A. Remove Python INSERT (WithdrawItemView.post)

**File:** `realsproj/views/withdrawals.py`

Remove `Sales.objects.create(...)` block at ~line 796-806. The per-order aggregate sales record is redundant — the trigger already creates per-item records for each SOLD withdrawal.

The condition block above:
```python
if reason == "SOLD" and sales_channel in ['ORDER', 'CONSIGNMENT', 'RESELLER'] and order_group_id:
    if payment_status in ['PAID', 'PARTIAL']:
        ...
        if total_sales_amount > 0:
```
Can be simplified to just the `total_sales_amount` logging (if any). The actual Sales creation is deleted entirely.

### B. Fix Sales Lookup in UPDATE/DELETE Views

All lookup-by-description patterns replaced with FK-based queries:

| View | Current (fragile) | New (clean) |
|---|---|---|
| `WithdrawUpdateView.form_valid()` | `desc__icontains="Order #"` + `"Status: PAID"` | `Sales.objects.filter(withdrawal=withdrawal).first()` — finds the specific trigger-created record for this withdrawal |
| `WithdrawDeleteView.post()` | `desc__icontains="Order #"` | `Sales.objects.filter(withdrawal=withdrawal).first().delete()` — deletes Sales for the deleted withdrawal; remaining Sales records already have correct per-item amounts |
| `WithdrawalGroupDeleteView.post()` | `desc__icontains="Order #"` | `Sales.objects.filter(withdrawal__order_group_id=order_group_id).delete()` — deletes all Sales linked to this group |
| `WithdrawalGroupEditView.post()` | `desc__icontains="Order #"` | After saving all withdrawals: if UNPAID → `Sales.objects.filter(withdrawal__order_group_id=order_group_id).delete()`; if PAID/PARTIAL → for each SOLD withdrawal, find-or-create its Sales record via `withdrawal` FK and update its amount |

**Behavior after change:**
- Each SOLD withdrawal now has its own Sales record (from trigger)
- UPDATE quantity/discount: update ALL Sales records in the order group, or just the specific one
- DELETE single withdrawal: delete that specific Sales record and recalculate total for remaining
- DELETE group: delete all Sales records in the group
- Edit group PAID/UNPAID: find all records in group, update/delete accordingly

### C. Fix Reason-Change Gap

In `WithdrawUpdateView.form_valid()`:
- Capture old reason before save
- If old reason was `'SOLD'` and new reason is `'DAMAGED'`/`'EXPIRED'`/`'OTHERS'`:
  - Delete `Sales.objects.filter(withdrawal=withdrawal).first()`
- If old reason was NOT `'SOLD'` and new reason is `'SOLD'`:
  - Do nothing — trigger already created the Sales record on INSERT, but since this is an UPDATE, the trigger won't fire. However, we don't need to create one here either — the original INSERT trigger created it.

### D. Update Sales Queries in sales_service.py

**File:** `realsproj/services/sales_service.py`

| Function | Current | New |
|---|---|---|
| `get_withdrawal_sales_queryset()` | `Q(description__icontains="Order #")` | `withdrawal__isnull=False` |
| `get_manual_sales_queryset()` | `~Q(description__icontains="Order #")` | `withdrawal__isnull=True` |

### E. Update Category Filtering in SalesExpensesList

**File:** `realsproj/views/sales.py`

The category dropdown in `get_context_data()` currently excludes withdrawal sales by description:
```python
Sales.objects.filter(is_archived=False).exclude(
    Q(description__icontains="Order #") | Q(description__icontains="order #")
).values_list('category', flat=True).distinct()
```

Change to:
```python
Sales.objects.filter(is_archived=False, withdrawal__isnull=True)
.values_list('category', flat=True).distinct()
```

## What Will NOT Change

- `WithdrawItemView.post()` — all OTHER logic (withdrawal creation, inventory validation, messaging, redirect) stays
- `WithdrawUpdateView.form_valid()` — all OTHER logic (quantity/discount calculation, original_quantity tracking) stays
- All other views in `withdrawals.py` — archive/unarchive/etc stay
- Templates — no template changes needed (Sales model fields unchanged from template perspective)
- The trigger `trg_withdrawal_sales_func` — no changes needed at the DB level

## Edge Cases

1. **PHYSICAL_STORE SOLD withdrawals**: Trigger creates Sales records for these too (current Python only created for ORDER/CONSIGNMENT/RESELLER). This is correct — all sales should be recorded. The monthly report will now include PHYSICAL_STORE sales that were previously missed.

2. **UNPAID SOLD withdrawals**: Trigger creates Sales records regardless of payment status. The `WithdrawalGroupEditView` handles UNPAID → deletes Sales. This is fine — the trigger creates it, and the edit view cleans it up if unpaid.

3. **Multiple withdrawals per product (FIFO batching)**: If a product needs 8 units and batch 1 has 5, batch 2 has 5, the trigger creates 2 Sales records: 5×price and 3×price. The total sum matches the expected 8×price.

4. **Zero-quantity withdrawals**: Trigger should not fire (guard condition in trigger handles this).

5. **`Sales.withdrawal` FK not populated for existing records**: Only new records (created by trigger after this change) will have the FK set. Existing Python-created records have `withdrawal_id = NULL`. The `get_withdrawal_sales_queryset()` must handle this transition period — see Migration Strategy below.

## Migration Strategy

Since existing Sales records created by the old Python code have `withdrawal_id = NULL`, switching to `withdrawal__isnull=False` would exclude ALL existing data. To handle this:

**Short-term (immediately after deploy):** Keep a fallback in the query:
```python
def get_withdrawal_sales_queryset(filters=None):
    qs = Sales.objects.filter(is_archived=False).filter(
        Q(withdrawal__isnull=False) | Q(description__icontains="Order #")
    )
    return _apply_common_filters(qs, filters)
```

**Long-term (after all old records age out):** Remove the fallback. Alternatively, run a one-time SQL UPDATE to backfill `withdrawal_id` on old records:
```sql
UPDATE sales s
SET withdrawal_id = w.id
FROM withdrawals w
WHERE s.description ILIKE '%Order #%' AND s.withdrawal_id IS NULL
AND w.order_group_id IS NOT NULL
AND s.description ILIKE '%Order #' || w.order_group_id || '%';
```

This migration is optional — the fallback query works indefinitely, just slower.

## Risk Mitigation

1. **Per-file commits** — withdrawals.py, sales_service.py, sales.py each get their own commit
2. **Test after each change** — run `pytest` after every commit
3. **No data loss** — trigger still runs; worst case is incorrect lookup (not data corruption)
4. **Rollback** — `git revert <commit>` for any file

## Files to Modify

| File | Change |
|---|---|
| `realsproj/views/withdrawals.py` | Remove `Sales.objects.create()`; fix all FK lookups; add reason-change gap fix |
| `realsproj/services/sales_service.py` | Update `get_withdrawal_sales_queryset()` and `get_manual_sales_queryset()` |
| `realsproj/views/sales.py` | Update category filtering in `SalesExpensesList.get_context_data()` |
