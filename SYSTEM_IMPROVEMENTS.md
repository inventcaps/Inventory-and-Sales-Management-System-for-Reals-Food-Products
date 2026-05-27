# System Improvements & Recommendations
# Inventory and Sales Management System for Real's Food Products
# Generated: May 11, 2026

---

## Priority Legend
- 🔴 **CRITICAL** — Bugs or issues that could cause data corruption or wrong results
- 🟡 **HIGH** — Important improvements for reliability and performance
- 🟢 **MEDIUM** — Code quality, maintainability, and UX enhancements
- 🔵 **LOW** — Nice-to-have optimizations and future features

---

# ═══════════════════════════════════════════════════════════════
# SECTION 1: DATABASE / TRIGGER FIXES
# ═══════════════════════════════════════════════════════════════

## 1.1 🔴 CRITICAL: Expiration Scanner Uses Wrong Date for Products

**Problem:** `check_expiration_notifications()` hardcodes `manufactured_date + INTERVAL '1 year'`
for ALL product batches, ignoring the actual `expiration_date` column. Yema products (6-month
shelf life) won't be flagged as expired until 12 months after manufacture — 6 months too late.

**SQL Fix (run in pgAdmin):**
```sql
-- Replace the product batch expiration scan section in check_expiration_notifications()
-- Change this:
--   (pb.manufactured_date + INTERVAL '1 year')::DATE AS expiration_date
-- To use the actual expiration_date column:

CREATE OR REPLACE FUNCTION public.check_expiration_notifications()
RETURNS void
LANGUAGE plpgsql
AS $function$
DECLARE
    today DATE := CURRENT_DATE;
    one_week DATE := CURRENT_DATE + INTERVAL '7 days';
    one_month DATE := CURRENT_DATE + INTERVAL '30 days';
    batch_record RECORD;
    system_user_id BIGINT;
    expired_qty DECIMAL(10,2);
    notif_type TEXT;

    expiring_soon_qty NUMERIC(10,2);
    adjusted_stock NUMERIC(10,2);

    product_row RECORD;
    material_row RECORD;

    expired_count INTEGER := 0;
    week_count INTEGER := 0;
    month_count INTEGER := 0;
    pre_low_count INTEGER := 0;
BEGIN
    SELECT id INTO system_user_id
    FROM auth_user
    WHERE is_superuser = TRUE
    ORDER BY id ASC LIMIT 1;

    IF system_user_id IS NULL THEN
        SELECT id INTO system_user_id
        FROM auth_user ORDER BY id ASC LIMIT 1;
    END IF;

    IF system_user_id IS NULL THEN
        RAISE EXCEPTION 'No user found to create withdrawal records';
    END IF;

    -- ============================================================
    -- FIXED: Use actual expiration_date column instead of hardcoded
    -- manufactured_date + 1 year. This correctly handles Yema
    -- products (6-month shelf life) and any future custom durations.
    -- ============================================================
    FOR batch_record IN
        SELECT
            pb.id AS batch_id,
            pb.product_id,
            pb.quantity,
            pb.is_expired,
            pb.expiration_date  -- USE THE ACTUAL COLUMN
        FROM product_batches pb
        WHERE pb.is_archived = FALSE
          AND (pb.is_expired = FALSE OR pb.is_expired IS NULL)
          AND pb.quantity > 0
          AND pb.expiration_date IS NOT NULL
          AND pb.expiration_date <= one_month
        ORDER BY pb.expiration_date
    LOOP
        IF batch_record.expiration_date <= today THEN
            notif_type := 'EXPIRED_TODAY';
        ELSIF batch_record.expiration_date <= one_week THEN
            notif_type := 'EXPIRES_IN_WEEK';
        ELSE
            notif_type := 'EXPIRES_IN_MONTH';
        END IF;

        IF NOT EXISTS (
            SELECT 1 FROM notifications
            WHERE item_type = 'PRODUCT'
              AND item_id = batch_record.batch_id
              AND notification_type = notif_type
        ) THEN
            IF notif_type = 'EXPIRED_TODAY' THEN
                expired_qty := batch_record.quantity;

                UPDATE product_batches
                SET is_expired = TRUE, quantity = 0
                WHERE id = batch_record.batch_id;

                UPDATE product_inventory
                SET total_stock = (
                    SELECT COALESCE(SUM(quantity),0)
                    FROM product_batches
                    WHERE product_id = batch_record.product_id
                      AND is_archived = FALSE
                )
                WHERE product_id = batch_record.product_id;

                INSERT INTO withdrawals(
                    item_type, item_id, quantity, reason, date,
                    created_by_admin_id, is_archived
                ) VALUES (
                    'PRODUCT', batch_record.product_id, expired_qty,
                    'EXPIRED', NOW(), system_user_id, FALSE
                );

                INSERT INTO notifications(item_type, item_id, notification_type,
                                         notification_timestamp, created_at)
                VALUES ('PRODUCT', batch_record.batch_id, notif_type,
                        NOW(), NOW());
                expired_count := expired_count + 1;
            ELSE
                INSERT INTO notifications(item_type, item_id, notification_type,
                                         notification_timestamp, created_at)
                VALUES ('PRODUCT', batch_record.batch_id, notif_type,
                        NOW(), NOW());

                IF notif_type = 'EXPIRES_IN_WEEK' THEN
                    week_count := week_count + 1;
                ELSE
                    month_count := month_count + 1;
                END IF;
            END IF;
        END IF;
    END LOOP;

    -- ============================================================
    -- PRE-LOW-STOCK LOGIC: Also fixed to use expiration_date column
    -- ============================================================
    FOR product_row IN
        SELECT product_id, total_stock, restock_threshold
        FROM product_inventory
    LOOP
        IF product_row.restock_threshold <= 0 THEN
            CONTINUE;
        END IF;

        SELECT COALESCE(SUM(quantity), 0)
        INTO expiring_soon_qty
        FROM product_batches
        WHERE product_id = product_row.product_id
          AND is_archived = FALSE
          AND is_expired = FALSE
          AND expiration_date IS NOT NULL
          AND expiration_date <= one_week;

        adjusted_stock := product_row.total_stock - expiring_soon_qty;
        IF adjusted_stock < 0 THEN
            adjusted_stock := 0;
        END IF;

        IF adjusted_stock <= product_row.restock_threshold
           AND adjusted_stock > 0 THEN
            IF NOT EXISTS (
                SELECT 1 FROM notifications
                WHERE item_type = 'PRODUCT'
                  AND item_id = product_row.product_id
                  AND notification_type = 'PRE_LOW_STOCK'
                  AND is_read = FALSE
            ) THEN
                INSERT INTO notifications (
                    item_type, item_id, notification_type,
                    notification_timestamp, created_at
                ) VALUES (
                    'PRODUCT', product_row.product_id, 'PRE_LOW_STOCK',
                    NOW(), NOW()
                );
                pre_low_count := pre_low_count + 1;
            END IF;
        END IF;
    END LOOP;

    -- RAW MATERIAL EXPIRATION SCAN (unchanged — already uses expiration_date)
    FOR batch_record IN
        SELECT
            rmb.id AS batch_id,
            rmb.material_id,
            rmb.expiration_date,
            rmb.quantity,
            rmb.is_expired
        FROM raw_material_batches rmb
        WHERE rmb.is_archived = FALSE
          AND (rmb.is_expired = FALSE OR rmb.is_expired IS NULL)
          AND rmb.quantity > 0
          AND rmb.expiration_date <= one_month
        ORDER BY rmb.expiration_date
    LOOP
        IF batch_record.expiration_date <= today THEN
            notif_type := 'EXPIRED_TODAY';
        ELSIF batch_record.expiration_date <= one_week THEN
            notif_type := 'EXPIRES_IN_WEEK';
        ELSE
            notif_type := 'EXPIRES_IN_MONTH';
        END IF;

        IF NOT EXISTS (
            SELECT 1 FROM notifications
            WHERE item_type = 'RAW_MATERIAL'
              AND item_id = batch_record.batch_id
              AND notification_type = notif_type
        ) THEN
            IF notif_type = 'EXPIRED_TODAY' THEN
                expired_qty := batch_record.quantity;

                UPDATE raw_material_batches
                SET is_expired = TRUE, quantity = 0
                WHERE id = batch_record.batch_id;

                UPDATE raw_material_inventory
                SET total_stock = (
                    SELECT COALESCE(SUM(quantity),0)
                    FROM raw_material_batches
                    WHERE material_id = batch_record.material_id
                      AND is_archived = FALSE
                )
                WHERE material_id = batch_record.material_id;

                INSERT INTO withdrawals(
                    item_type, item_id, quantity, reason, date,
                    created_by_admin_id, is_archived
                ) VALUES (
                    'RAW_MATERIAL', batch_record.material_id, expired_qty,
                    'EXPIRED', NOW(), system_user_id, FALSE
                );

                INSERT INTO notifications(item_type, item_id, notification_type,
                                         notification_timestamp, created_at)
                VALUES ('RAW_MATERIAL', batch_record.batch_id, notif_type,
                        NOW(), NOW());
                expired_count := expired_count + 1;
            ELSE
                INSERT INTO notifications(item_type, item_id, notification_type,
                                         notification_timestamp, created_at)
                VALUES ('RAW_MATERIAL', batch_record.batch_id, notif_type,
                        NOW(), NOW());

                IF notif_type = 'EXPIRES_IN_WEEK' THEN
                    week_count := week_count + 1;
                ELSE
                    month_count := month_count + 1;
                END IF;
            END IF;
        END IF;
    END LOOP;

    RAISE NOTICE 'Expiration scan finished.';
    RAISE NOTICE 'Expired Today: %', expired_count;
    RAISE NOTICE 'Expiring in Week: %', week_count;
    RAISE NOTICE 'Expiring in Month: %', month_count;
    RAISE NOTICE 'PRE_LOW_STOCK Alerts: %', pre_low_count;
END;
$function$;
```

---

## 1.2 🔴 CRITICAL: order_group_id Race Condition

**Problem:** Django uses `MAX(order_group_id) + 1` despite `withdrawal_order_group_seq` existing.
Two concurrent requests could get the same order_group_id.

**Django Fix (views.py ~line 4868-4875):**
```python
# BEFORE (race condition):
max_id = Withdrawals.objects.filter(order_group_id__isnull=False).aggregate(
    max_id=models.Max('order_group_id')
)['max_id']
order_group_id = (max_id or 0) + 1

# AFTER (concurrency-safe):
from django.db import connection
with connection.cursor() as cursor:
    cursor.execute("SELECT nextval('withdrawal_order_group_seq')")
    order_group_id = cursor.fetchone()[0]
```

---

## 1.3 🔴 CRITICAL: Sales Trigger Can Create Duplicates on UPDATE

**Problem:** `trg_withdrawal_sales_func` fires on both INSERT and UPDATE. If a PAID
PHYSICAL_STORE withdrawal is edited (e.g., quantity change), a second sales record is
created without removing the first.

**SQL Fix:**
```sql
CREATE OR REPLACE FUNCTION public.trg_withdrawal_sales_func()
RETURNS trigger
LANGUAGE plpgsql
AS $function$
DECLARE
    base_price NUMERIC(12,4) := 0;
    discounted_price NUMERIC(12,4) := 0;
    total_amount NUMERIC(12,2) := 0;
    discount_percent NUMERIC(12,4) := 0;
BEGIN
    -- ============================================================
    -- FIX: Only process on INSERT. UPDATE-based sales changes
    -- (like payment status updates) are handled by Django views
    -- (WithdrawalOrderUpdatePaymentView), not by this trigger.
    -- This prevents duplicate sales records.
    -- ============================================================
    IF TG_OP = 'UPDATE' THEN
        RETURN NEW;
    END IF;

    IF COALESCE(NEW.item_type, '') = 'PRODUCT'
       AND COALESCE(NEW.reason, '') = 'SOLD' THEN

        IF COALESCE(NEW.sales_channel, '') IN ('ORDER', 'CONSIGNMENT', 'RESELLER') THEN
            RETURN NEW;
        END IF;

        IF COALESCE(NEW.payment_status, 'PAID') = 'UNPAID' THEN
            RETURN NEW;
        END IF;

        IF COALESCE(NEW.payment_status, 'PAID') = 'PARTIAL' THEN
            IF NEW.paid_amount IS NULL OR NEW.paid_amount <= 0 THEN
                RAISE EXCEPTION 'Partial payment requires a valid paid_amount for withdrawal ID %', NEW.id;
            END IF;
            total_amount := ROUND(NEW.paid_amount::numeric, 2);

            INSERT INTO public.sales (category, amount, date, description, created_by_admin_id)
            VALUES (
                COALESCE(NEW.sales_channel, 'UNKNOWN'),
                total_amount,
                NOW(),
                CONCAT('Withdrawal ID: ', NEW.id, ', Channel: ', COALESCE(NEW.sales_channel, 'N/A'), ', Payment: PARTIAL (₱', NEW.paid_amount, ')'),
                NEW.created_by_admin_id
            );
            RETURN NEW;
        END IF;

        IF NEW.custom_price IS NOT NULL THEN
            base_price := NEW.custom_price;
        ELSE
            IF COALESCE(NEW.price_type,'') = 'UNIT' THEN
                SELECT up.unit_price INTO base_price
                FROM public.products p
                JOIN public.unit_prices up ON p.unit_price_id = up.id
                WHERE p.id = NEW.item_id;
            ELSIF COALESCE(NEW.price_type,'') = 'SRP' THEN
                SELECT sp.srp_price INTO base_price
                FROM public.products p
                JOIN public.srp_prices sp ON p.srp_price_id = sp.id
                WHERE p.id = NEW.item_id;
            ELSE
                RAISE EXCEPTION 'Missing price source for withdrawal ID %', NEW.id;
            END IF;
        END IF;

        IF NEW.discount_id IS NOT NULL THEN
            SELECT d.value INTO discount_percent FROM public.discounts d WHERE d.id = NEW.discount_id;
            IF discount_percent IS NULL THEN
                discount_percent := 0;
            END IF;
        ELSIF NEW.custom_discount_value IS NOT NULL THEN
            discount_percent := NEW.custom_discount_value;
        ELSE
            discount_percent := 0;
        END IF;

        discounted_price := base_price * (1 - (COALESCE(discount_percent,0) / 100.0));

        IF NEW.custom_price IS NOT NULL THEN
            total_amount := ROUND(discounted_price::numeric, 2);
        ELSE
            total_amount := ROUND((COALESCE(NEW.quantity,0) * discounted_price)::numeric, 2);
        END IF;

        INSERT INTO public.sales (category, amount, date, description, created_by_admin_id)
        VALUES (
            COALESCE(NEW.sales_channel, 'UNKNOWN'),
            total_amount,
            NOW(),
            CONCAT('Withdrawal ID: ', NEW.id, ', Channel: ', COALESCE(NEW.sales_channel, 'N/A'), ', PriceType: ', COALESCE(NEW.price_type::text, 'CUSTOM'), ', Discount: ', COALESCE(discount_percent::text,'0'), '%'),
            NEW.created_by_admin_id
        );
    END IF;

    RETURN NEW;
END;
$function$;
```

---

## 1.4 🟡 HIGH: Financial Loss Not Tracked for Product Losses

**Problem:** `trg_create_financial_loss_func` only handles `RAW_MATERIAL + DAMAGED`.
Product EXPIRED/DAMAGED/REPLACEMENT losses are calculated on-the-fly using current
unit price, which changes over time — making historical reports inaccurate.

**SQL Fix:**
```sql
CREATE OR REPLACE FUNCTION public.trg_create_financial_loss_func()
RETURNS trigger
LANGUAGE plpgsql
AS $function$
DECLARE
    v_item_name VARCHAR(255);
    v_unit_price NUMERIC(10,2);
    v_loss_amount NUMERIC(10,2);
BEGIN
    -- ============================================================
    -- EXPANDED: Now handles BOTH products and raw materials for
    -- EXPIRED, DAMAGED, and REPLACEMENT_FOR_RETURNED reasons.
    -- Captures unit price at time of loss for historical accuracy.
    -- ============================================================

    -- Only process loss-related reasons
    IF NEW.reason NOT IN ('EXPIRED', 'DAMAGED', 'REPLACEMENT_FOR_RETURNED') THEN
        RETURN NEW;
    END IF;

    IF NEW.item_type = 'PRODUCT' THEN
        -- Get product name and unit price at time of loss
        SELECT
            CONCAT(pt.name, ' - ', pv.name, ' (', s.size_label, ')'),
            up.unit_price
        INTO v_item_name, v_unit_price
        FROM products p
        LEFT JOIN product_types pt ON p.product_type_id = pt.id
        LEFT JOIN product_variants pv ON p.variant_id = pv.id
        LEFT JOIN sizes s ON p.size_id = s.id
        LEFT JOIN unit_prices up ON p.unit_price_id = up.id
        WHERE p.id = NEW.item_id;

    ELSIF NEW.item_type = 'RAW_MATERIAL' THEN
        SELECT name, price_per_unit INTO v_item_name, v_unit_price
        FROM raw_materials
        WHERE id = NEW.item_id;
    ELSE
        RETURN NEW;
    END IF;

    v_loss_amount := NEW.quantity * COALESCE(v_unit_price, 0);

    INSERT INTO financial_loss (
        withdrawal_id, item_type, item_id, item_name,
        quantity, unit_price, loss_amount, reason,
        loss_date, created_by_admin_id
    ) VALUES (
        NEW.id, NEW.item_type, NEW.item_id, v_item_name,
        NEW.quantity, v_unit_price, v_loss_amount, NEW.reason,
        NEW.date, NEW.created_by_admin_id
    );

    RETURN NEW;
END;
$function$;
```

---

## 1.5 🟡 HIGH: Missing Indexes for Common Queries

**SQL (run in pgAdmin):**
```sql
-- Withdrawal queries frequently filter by item_id
CREATE INDEX IF NOT EXISTS idx_withdrawals_item_id
ON withdrawals (item_id);

-- Grouped withdrawal list view queries by order_group_id
CREATE INDEX IF NOT EXISTS idx_withdrawals_order_group
ON withdrawals (order_group_id)
WHERE order_group_id IS NOT NULL;

-- FIFO batch selection needs expiration_date ordering
CREATE INDEX IF NOT EXISTS idx_product_batches_fifo
ON product_batches (product_id, expiration_date ASC, id ASC)
WHERE is_archived = FALSE AND quantity > 0;

-- Raw material FIFO batch selection
CREATE INDEX IF NOT EXISTS idx_raw_material_batches_fifo
ON raw_material_batches (material_id, expiration_date ASC NULLS LAST, id ASC)
WHERE is_archived = FALSE AND quantity > 0;

-- Notification duplicate checks in triggers
CREATE INDEX IF NOT EXISTS idx_notifications_item_type_id_type
ON notifications (item_type, item_id, notification_type);

-- Login lockout check: ip_address + username combo
CREATE INDEX IF NOT EXISTS idx_login_attempts_lockout
ON login_attempts (ip_address, username, "timestamp" DESC)
WHERE success = FALSE AND required_otp = FALSE;

-- Product batches archive filter (used in almost every batch query)
CREATE INDEX IF NOT EXISTS idx_product_batches_archived
ON product_batches (is_archived);

-- Stock changes date filter (list view filters by month)
CREATE INDEX IF NOT EXISTS idx_stock_changes_date
ON stock_changes (date DESC);
```

---

## 1.6 🟡 HIGH: Remove Redundant Index on receipt_number

**Problem:** `withdrawals.receipt_number` has both a UNIQUE index and a regular btree index.
The UNIQUE index already provides btree lookup capability.

```sql
-- The unique index already provides lookup. Drop the redundant regular index.
DROP INDEX IF EXISTS withdrawals_receipt_number_idx;
-- Keep: withdrawals_receipt_number_key (UNIQUE)
```

---

## 1.7 🟢 MEDIUM: Add Non-Negative CHECK Constraints

**Problem:** Stock and financial amounts can theoretically go negative since there are
no column-level constraints. Triggers prevent this, but defense-in-depth is better.

```sql
ALTER TABLE product_inventory
ADD CONSTRAINT chk_product_inventory_stock_nonneg CHECK (total_stock >= 0);

ALTER TABLE raw_material_inventory
ADD CONSTRAINT chk_raw_material_inventory_stock_nonneg CHECK (total_stock >= 0);

ALTER TABLE product_batches
ADD CONSTRAINT chk_product_batches_qty_nonneg CHECK (quantity >= 0);

ALTER TABLE raw_material_batches
ADD CONSTRAINT chk_raw_material_batches_qty_nonneg CHECK (quantity >= 0);

ALTER TABLE sales
ADD CONSTRAINT chk_sales_amount_positive CHECK (amount >= 0);

ALTER TABLE expenses
ADD CONSTRAINT chk_expenses_amount_positive CHECK (amount >= 0);

ALTER TABLE withdrawals
ADD CONSTRAINT chk_withdrawals_qty_positive CHECK (quantity > 0);
```

---

## 1.8 🟢 MEDIUM: Clean Up Expired OTPs Periodically

**Problem:** `user_otp` table grows indefinitely. Expired/used OTPs are only cleaned
when a user logs in. Add a cleanup query to run periodically.

```sql
-- Run this periodically (e.g., daily via pg_cron or manual)
DELETE FROM user_otp
WHERE is_used = TRUE
   OR expires_at < NOW() - INTERVAL '1 day';
```

---

## 1.9 🟢 MEDIUM: Clean Up Old Login Attempts

```sql
-- Archive login attempts older than 90 days
DELETE FROM login_attempts
WHERE "timestamp" < NOW() - INTERVAL '90 days';
```

---

## 1.10 🔵 LOW: Add sales.withdrawal_id FK Constraint

```sql
-- Currently no FK exists between sales and withdrawals
-- This would enforce referential integrity for linked sales
ALTER TABLE sales
ADD CONSTRAINT fk_sales_withdrawal
FOREIGN KEY (withdrawal_id) REFERENCES withdrawals(id)
ON DELETE SET NULL;
```


---

# ═══════════════════════════════════════════════════════════════
# SECTION 2: DJANGO CODE IMPROVEMENTS
# ═══════════════════════════════════════════════════════════════

## 2.1 🟡 HIGH: Fix order_group_id in WithdrawItemView

**File:** `realsproj/views.py` ~line 4868-4875

```python
# REPLACE:
max_id = Withdrawals.objects.filter(order_group_id__isnull=False).aggregate(
    max_id=models.Max('order_group_id')
)['max_id']
order_group_id = (max_id or 0) + 1

# WITH:
from django.db import connection
with connection.cursor() as cursor:
    cursor.execute("SELECT nextval('withdrawal_order_group_seq')")
    order_group_id = cursor.fetchone()[0]
```

---

## 2.2 🟡 HIGH: Sync withdrawal_order_group_seq with Existing Data

**Problem:** If `withdrawal_order_group_seq` was never used, it's still at 1. But
order_group_id values already exist from `MAX() + 1`. The sequence must be synced
before switching to `nextval()`.

```sql
-- Run ONCE before deploying the Django fix above
SELECT setval(
    'withdrawal_order_group_seq',
    COALESCE((SELECT MAX(order_group_id) FROM withdrawals), 0)
);
```

---

## 2.3 🟢 MEDIUM: Extract Financial Report Logic into Utility

**Problem:** Financial loss calculation is duplicated between `monthly_report` and
`monthly_report_export` views. Extract into a shared function.

**Create file:** `realsproj/services/reports.py`
```python
from django.db.models import Sum
from django.db.models.functions import TruncMonth
from decimal import Decimal

def get_monthly_financial_data(months_queryset):
    """
    Shared logic for monthly financial report calculations.
    Returns list of monthly report dicts and summary dict.
    Used by both monthly_report view and monthly_report_export.
    """
    # ... extract the shared calculation logic here
    pass
```

---

## 2.4 🟢 MEDIUM: Split views.py Into Modules

**Recommended structure:**
```
realsproj/
├── views/
│   ├── __init__.py          # Re-exports all views for URL compatibility
│   ├── dashboard.py         # HomeView, dashboard APIs
│   ├── products.py          # Product CRUD, batch management
│   ├── raw_materials.py     # Raw material CRUD, batch management
│   ├── withdrawals.py       # Withdrawal list, create, edit, archive
│   ├── financial.py         # Sales, expenses, monthly report, financial loss
│   ├── auth.py              # Login, register, 2FA, password reset
│   ├── users.py             # User management, profile, role toggle
│   ├── exports.py           # All CSV/PDF export functions
│   ├── notifications.py     # Notification views
│   └── stock_changes.py     # Stock changes list, archive
├── attribute_views.py       # Already extracted (keep as-is)
├── services/
│   ├── reports.py           # Shared report calculation logic
│   └── stock.py             # Shared stock validation logic
```

**Migration approach (no URL changes needed):**
```python
# realsproj/views/__init__.py
from .dashboard import *
from .products import *
from .raw_materials import *
from .withdrawals import *
from .financial import *
from .auth import *
from .users import *
from .exports import *
from .notifications import *
from .stock_changes import *
```

---

## 2.5 🟢 MEDIUM: Use select_related/prefetch_related Consistently

**Problem:** Some views query related objects in loops (N+1 queries).

**Example fix for WithdrawalsList:**
```python
# BEFORE:
qs = Withdrawals.objects.filter(is_archived=False)

# AFTER:
qs = Withdrawals.objects.filter(is_archived=False).select_related(
    'created_by_admin',
    'batch',
    'batch__product',
).order_by('-date')
```

---

## 2.6 🟢 MEDIUM: Cache Dashboard Aggregations

**Problem:** HomeView makes 15+ database queries on every page load.

```python
# In HomeView.get_context_data():
from django.core.cache import cache

cache_key = f'dashboard_data_{timezone.now().strftime("%Y%m%d%H")}'
cached = cache.get(cache_key)
if cached:
    context.update(cached)
    return context

# ... compute all dashboard data ...

cache.set(cache_key, dashboard_data, 300)  # Cache for 5 minutes
```

**Note:** Requires a cache backend. For development, Django's LocMemCache works.
For production, use Redis.

---

## 2.7 🔵 LOW: Add Type Hints to Key Functions

```python
# Example for WithdrawItemView.post
from decimal import Decimal
from typing import Optional

def calculate_discount(
    base_price: Decimal,
    discount_percent: Optional[Decimal],
    custom_discount: Optional[Decimal]
) -> tuple[Decimal, Decimal]:
    """Returns (discounted_price, actual_discount_percent)"""
    percent = discount_percent or custom_discount or Decimal('0')
    discounted = base_price * (1 - percent / 100)
    return discounted, percent
```


---

# ═══════════════════════════════════════════════════════════════
# SECTION 3: PERFORMANCE OPTIMIZATIONS
# ═══════════════════════════════════════════════════════════════

## 3.1 🟡 HIGH: BulkProductBatchForm Creates Fields for ALL Products

**Problem:** `BulkProductBatchForm.__init__` creates dynamic form fields for every
non-archived product. With 500+ products, this means 2000+ form fields on page load.

**Fix options:**
1. **Paginate products** in the bulk form (show 20 per page)
2. **Use AJAX** to dynamically load only products the user wants to batch
3. **Filter by product type** before showing the bulk form

---

## 3.2 🟡 HIGH: WithdrawalsList Loads ALL Withdrawals for Grouping

**Problem:** `get_context_data` calls `self.get_queryset()` which returns ALL filtered
withdrawals, then groups them in Python. For large datasets, this loads thousands of
rows into memory.

**Fix:** Group in SQL using a subquery:
```python
from django.db.models import Min, Count

# Get distinct groups with pagination-friendly counts
groups = (
    Withdrawals.objects
    .filter(is_archived=False)
    .values('order_group_id')
    .annotate(
        first_date=Min('date'),
        item_count=Count('id'),
    )
    .order_by('-first_date')
)
```

---

## 3.3 🟢 MEDIUM: Use Materialized View for Dashboard Sales Data

**Problem:** Dashboard calculates 12-month sales vs expenses on every load.

```sql
-- Create a materialized view for monthly aggregates
CREATE MATERIALIZED VIEW IF NOT EXISTS mv_monthly_summary AS
SELECT
    DATE_TRUNC('month', date) AS month,
    SUM(amount) AS total_amount,
    'SALES' AS record_type
FROM sales
WHERE is_archived = FALSE
GROUP BY DATE_TRUNC('month', date)
UNION ALL
SELECT
    DATE_TRUNC('month', date) AS month,
    SUM(amount) AS total_amount,
    'EXPENSES' AS record_type
FROM expenses
WHERE is_archived = FALSE
GROUP BY DATE_TRUNC('month', date);

CREATE UNIQUE INDEX ON mv_monthly_summary (month, record_type);

-- Refresh periodically (e.g., every hour via pg_cron, or after sales/expense changes)
-- REFRESH MATERIALIZED VIEW CONCURRENTLY mv_monthly_summary;
```

---

## 3.4 🔵 LOW: Add Database Connection Pooling

**Problem:** Django creates a new DB connection per request by default.

Add to `settings.py`:
```python
DATABASES = {
    'default': {
        # ... existing config ...
        'CONN_MAX_AGE': 600,  # Reuse connections for 10 minutes
    }
}
```

For production with multiple workers, use PgBouncer.


---

# ═══════════════════════════════════════════════════════════════
# SECTION 4: SECURITY HARDENING
# ═══════════════════════════════════════════════════════════════

## 4.1 🔴 CRITICAL: Disable DEBUG in Production

```python
# settings.py
DEBUG = False  # Currently True
ALLOWED_HOSTS = ['yourdomain.com', 'www.yourdomain.com']
```

---

## 4.2 🟡 HIGH: Move Secrets to Environment Variables

**Problem:** Database credentials and API keys may be exposed in settings.py.

```python
# settings.py — ensure ALL secrets use decouple
from decouple import config

SECRET_KEY = config('SECRET_KEY')
SENDGRID_API_KEY = config('SENDGRID_API_KEY')

DATABASES = {
    'default': {
        'PASSWORD': config('DB_PASSWORD'),
        # ...
    }
}
```

Verify `.env` is in `.gitignore`.

---

## 4.3 🟡 HIGH: Add Rate Limiting on Registration

**Problem:** No rate limiting on the register endpoint. Attackers could flood
with registration requests.

```python
# Option 1: Simple session-based throttle in register view
def register(request):
    if request.method == 'POST':
        # Rate limit: max 3 registrations per IP per hour
        from django.core.cache import cache
        ip = get_client_ip(request)
        cache_key = f'register_attempts_{ip}'
        attempts = cache.get(cache_key, 0)
        if attempts >= 3:
            messages.error(request, 'Too many registration attempts. Please try again later.')
            return redirect('register')
        cache.set(cache_key, attempts + 1, 3600)  # 1 hour expiry
        # ... rest of registration logic
```

---

## 4.4 🟢 MEDIUM: Add Security Headers

```python
# settings.py
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'
SECURE_REFERRER_POLICY = 'strict-origin-when-cross-origin'

# For HTTPS (production only):
# SECURE_SSL_REDIRECT = True
# SESSION_COOKIE_SECURE = True
# CSRF_COOKIE_SECURE = True
# SECURE_HSTS_SECONDS = 31536000
```

---

## 4.5 🟢 MEDIUM: Hash OTP Codes Before Storing

```python
# In login_view where OTP is created:
import hashlib

otp_code = str(random.randint(100000, 999999))

# Store hashed version
UserOTP.objects.create(
    user=user,
    otp_code=hashlib.sha256(otp_code.encode()).hexdigest(),
    expires_at=timezone.now() + timedelta(minutes=10),
    ip_address=ip_address
)

# Send plain OTP via email (unchanged)
# ...

# When verifying, hash the input before comparing:
otp_input_hash = hashlib.sha256(otp_code_input.encode()).hexdigest()
otp = UserOTP.objects.filter(
    user=user,
    otp_code=otp_input_hash,
    is_used=False,
    expires_at__gt=timezone.now()
).first()
```

**Note:** This requires updating the `otp_code` column to varchar(64) for SHA-256.
```sql
ALTER TABLE user_otp ALTER COLUMN otp_code TYPE varchar(64);
```


---

# ═══════════════════════════════════════════════════════════════
# SECTION 5: UX FLOW IMPROVEMENTS
# ═══════════════════════════════════════════════════════════════

## 5.1 🟡 HIGH: Withdrawal Form — Show Remaining Stock Per Batch

When a user selects a product to withdraw, show which batches will be consumed
(FIFO preview) before they submit. This prevents confusion when a withdrawal
spans multiple batches.

```javascript
// In withdraw form template, add AJAX preview:
// When quantity changes, call an API endpoint that returns:
// [{ batch_code: "051126-YM", quantity_to_deduct: 50, remaining: 0 },
//  { batch_code: "051226-YM", quantity_to_deduct: 30, remaining: 70 }]
```

---

## 5.2 🟡 HIGH: Dashboard — Add Loading States for Charts

**Problem:** 15+ queries run before the page renders. Users see a blank page.

Add skeleton loaders / spinners for each chart section and load chart data via
AJAX endpoints (you already have `best_sellers_api` — extend this pattern to
all dashboard charts).

---

## 5.3 🟢 MEDIUM: Notification Badge — Show Count by Type

Instead of just showing total unread count, break it down:
- 🔴 3 expired
- 🟡 2 low stock
- ⚫ 1 out of stock

This helps users prioritize which notifications to address first.

---

## 5.4 🟢 MEDIUM: Bulk Operations — Add Confirmation with Summary

For bulk archive/delete operations, show a summary modal:
"You are about to archive 5 withdrawals totaling 150 units. Continue?"

Instead of just "Are you sure?"

---

## 5.5 🟢 MEDIUM: Financial Report — Add Date Range Picker

Currently the monthly report shows one month at a time. Add a date range
picker to compare custom periods (e.g., Q1 vs Q2).

---

## 5.6 🔵 LOW: Mobile-Responsive Improvements

Test all table views on mobile. Consider using responsive table patterns
(card-based layout on small screens) for:
- Product list
- Withdrawal list
- Sales/Expenses list

---

## 5.7 🔵 LOW: Keyboard Shortcuts for Power Users

```javascript
// Example: Ctrl+N = New Product, Ctrl+W = New Withdrawal, Ctrl+B = New Batch
document.addEventListener('keydown', (e) => {
    if (e.ctrlKey && e.key === 'n') {
        e.preventDefault();
        window.location.href = '/products/add/';
    }
});
```


---

# ═══════════════════════════════════════════════════════════════
# SECTION 6: VERIFICATION QUERIES
# Run these in pgAdmin to verify current data integrity
# ═══════════════════════════════════════════════════════════════

## 6.1 Check for Inventory Drift (batch sum ≠ inventory total)

```sql
-- Products: Compare batch sum vs inventory total
SELECT
    pi.product_id,
    pi.total_stock AS inventory_total,
    COALESCE(SUM(pb.quantity), 0) AS batch_sum,
    pi.total_stock - COALESCE(SUM(pb.quantity), 0) AS drift
FROM product_inventory pi
LEFT JOIN product_batches pb
    ON pb.product_id = pi.product_id AND pb.is_archived = FALSE
GROUP BY pi.product_id, pi.total_stock
HAVING pi.total_stock != COALESCE(SUM(pb.quantity), 0);

-- Raw Materials: Same check
SELECT
    rmi.material_id,
    rmi.total_stock AS inventory_total,
    COALESCE(SUM(rmb.quantity), 0) AS batch_sum,
    rmi.total_stock - COALESCE(SUM(rmb.quantity), 0) AS drift
FROM raw_material_inventory rmi
LEFT JOIN raw_material_batches rmb
    ON rmb.material_id = rmi.material_id AND rmb.is_archived = FALSE
GROUP BY rmi.material_id, rmi.total_stock
HAVING rmi.total_stock != COALESCE(SUM(rmb.quantity), 0);
```

## 6.2 Check for Negative Stock Values

```sql
SELECT 'product_batches' AS source, id, quantity
FROM product_batches WHERE quantity < 0
UNION ALL
SELECT 'raw_material_batches', id, quantity
FROM raw_material_batches WHERE quantity < 0
UNION ALL
SELECT 'product_inventory', product_id, total_stock
FROM product_inventory WHERE total_stock < 0
UNION ALL
SELECT 'raw_material_inventory', material_id, total_stock
FROM raw_material_inventory WHERE total_stock < 0;
```

## 6.3 Check for Orphaned Withdrawals (item_id points to deleted product/material)

```sql
-- Product withdrawals pointing to non-existent products
SELECT w.id, w.item_id, w.quantity, w.reason, w.date
FROM withdrawals w
WHERE w.item_type = 'PRODUCT'
  AND NOT EXISTS (SELECT 1 FROM products p WHERE p.id = w.item_id);

-- Raw material withdrawals pointing to non-existent materials
SELECT w.id, w.item_id, w.quantity, w.reason, w.date
FROM withdrawals w
WHERE w.item_type = 'RAW_MATERIAL'
  AND NOT EXISTS (SELECT 1 FROM raw_materials rm WHERE rm.id = w.item_id);
```

## 6.4 Check for Duplicate Order Group IDs

```sql
SELECT order_group_id, COUNT(*) AS withdrawal_count
FROM withdrawals
WHERE order_group_id IS NOT NULL
GROUP BY order_group_id
HAVING COUNT(DISTINCT created_by_admin_id) > 1;
-- If any rows return, different users created withdrawals with the same group ID
```

## 6.5 Check sales_summary / expenses_summary Accuracy

```sql
-- Verify sales_summary matches actual sum
SELECT
    ss.total_amount AS summary_total,
    COALESCE(SUM(s.amount), 0) AS actual_total,
    ss.total_amount - COALESCE(SUM(s.amount), 0) AS drift
FROM sales_summary ss
CROSS JOIN sales s
WHERE ss.id = 1 AND s.is_archived = FALSE
GROUP BY ss.total_amount;

-- Verify expenses_summary matches actual sum
SELECT
    es.total_amount AS summary_total,
    COALESCE(SUM(e.amount), 0) AS actual_total,
    es.total_amount - COALESCE(SUM(e.amount), 0) AS drift
FROM expenses_summary es
CROSS JOIN expenses e
WHERE es.id = 1 AND e.is_archived = FALSE
GROUP BY es.total_amount;
```

## 6.6 Check for Yema Batches with Wrong Expiration (Pre-Fix Verification)

```sql
-- Find Yema product batches where expiration > 6 months from manufacture
SELECT
    pb.id AS batch_id,
    pb.product_id,
    pt.name AS product_type,
    pv.name AS variant,
    pb.manufactured_date,
    pb.expiration_date,
    pb.expiration_date - pb.manufactured_date AS days_shelf_life
FROM product_batches pb
JOIN products p ON pb.product_id = p.id
JOIN product_types pt ON p.product_type_id = pt.id
JOIN product_variants pv ON p.variant_id = pv.id
WHERE pb.is_archived = FALSE
  AND (LOWER(pt.name) LIKE '%yema%' OR LOWER(pv.name) LIKE '%yema%')
  AND (pb.expiration_date - pb.manufactured_date) > 200;
-- Yema should be ~183 days (6 months + 1 day). If > 200, something is wrong.
```


---

# ═══════════════════════════════════════════════════════════════
# SECTION 7: IMPLEMENTATION PRIORITY ORDER
# ═══════════════════════════════════════════════════════════════

## Phase 1: Pre-Defense Quick Wins (1-2 hours)
1. Run verification queries (Section 6) — know your data state
2. Fix order_group_id race condition (1.2 + 2.1 + 2.2) — 5 min
3. Fix expiration scanner (1.1) — paste SQL in pgAdmin
4. Add missing indexes (1.5) — paste SQL in pgAdmin

## Phase 2: Data Integrity (2-4 hours)
5. Fix sales trigger duplicate issue (1.3) — paste SQL in pgAdmin
6. Expand financial loss trigger (1.4) — paste SQL in pgAdmin
7. Add CHECK constraints (1.7) — paste SQL in pgAdmin
8. Remove redundant index (1.6) — paste SQL in pgAdmin

## Phase 3: Code Quality (ongoing)
9. Split views.py into modules (2.4)
10. Extract shared report logic (2.3)
11. Add select_related everywhere (2.5)

## Phase 4: Production Readiness
12. Disable DEBUG (4.1)
13. Security headers (4.4)
14. Environment variables audit (4.2)
15. Registration rate limiting (4.3)
