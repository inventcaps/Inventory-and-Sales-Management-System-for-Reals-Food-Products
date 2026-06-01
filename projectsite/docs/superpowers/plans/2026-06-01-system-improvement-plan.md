# System Improvement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) for syntax tracking.

**Goal:** Fix security, performance, code quality, and architectural issues identified in system audit across 4 prioritized phases.

**Architecture:** Incremental improvements to existing Django monolith — no framework changes. Each phase is independent and deployable. Phase 1 is critical (data integrity/security), Phase 2 is performance, Phases 3-4 are maintainability.

**Tech Stack:** Django 5.2, PostgreSQL, pytest, factory_boy, django-cachalot

---

## Phase 1: Critical Fixes (Data Integrity & Security)

### Task 1.1: Add database unique constraints

**Files:**
- Create: `realsproj/migrations/0002_add_unique_constraints.py` (or use `./manage.py makemigrations` against unmanaged models — see note)
- Read: `realsproj/models.py`

**Context:** All models use `managed = False`, so Django `makemigrations` won't detect changes. Constraints must be added via direct SQL migration or by running raw SQL against the database. We'll create a data migration.

- [ ] **Step 1: Create migration file**

```python
# migrations/0002_add_unique_constraints.py
from django.db import migrations

class Migration(migrations.Migration):
    dependencies = [
        ('realsproj', '0001_initial'),
    ]
    
    operations = [
        migrations.RunSQL(
            "CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS idx_products_code_unique ON products (product_code) WHERE is_archived = FALSE;",
            "DROP INDEX IF EXISTS idx_products_code_unique;"
        ),
        migrations.RunSQL(
            "CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS idx_products_barcode_unique ON products (barcode) WHERE barcode IS NOT NULL AND is_archived = FALSE;",
            "DROP INDEX IF EXISTS idx_products_barcode_unique;"
        ),
        migrations.RunSQL(
            "CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS idx_withdrawals_receipt_unique ON withdrawals (receipt_number) WHERE receipt_number IS NOT NULL;",
            "DROP INDEX IF EXISTS idx_withdrawals_receipt_unique;"
        ),
    ]
```

Note: Since models are `managed=False`, this migration is for documentation/tracking. The SQL must also be applied manually or via a separate migration script.

- [ ] **Step 2: Add receipt_number unique constraint to Withdrawals**

Add to the migration:
```python
migrations.RunSQL(
    "ALTER TABLE withdrawals ADD CONSTRAINT IF NOT EXISTS withdrawals_receipt_number_key UNIQUE (receipt_number);",
    "ALTER TABLE withdrawals DROP CONSTRAINT IF EXISTS withdrawals_receipt_number_key;"
)
```

- [ ] **Step 3: Fix `generate_receipt_number` race condition**

In `realsproj/models.py:1402-1410`, replace the count-based approach with database-level retry:

```python
def generate_receipt_number(self):
    """Generate a unique continuous receipt number with retry on collision."""
    from django.db import connection
    for attempt in range(5):
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT COALESCE(MAX(CAST(SUBSTRING(receipt_number, 5) AS INTEGER)), 0) + 1 "
                "FROM withdrawals WHERE receipt_number ~ '^REC-[0-9]+$'"
            )
            next_num = cursor.fetchone()[0]
            receipt_num = f"REC-{next_num:06d}"
            # Try to claim it — rely on DB unique constraint
            try:
                cursor.execute(
                    "UPDATE withdrawals SET receipt_number = %s WHERE id = %s AND receipt_number IS NULL",
                    [receipt_num, self.id]
                )
                if cursor.rowcount > 0:
                    return receipt_num
            except Exception:
                continue
    # Fallback: use timestamp-based
    from datetime import datetime
    return f"REC-{datetime.now().strftime('%y%m%d%H%M%S')}-{self.id}"
```

Also update the `save()` method at line 1412 to set `receipt_number` before the first save (not rely on the post-save signal path):

```python
def save(self, *args, **kwargs):
    if not self.receipt_number:
        self.receipt_number = self.generate_receipt_number()
    super().save(*args, **kwargs)
```

- [ ] **Step 4: Add AuthUser model `id` field explicit declaration**

In models.py, `AuthUser` (line 43) inherits the implicit id from `models.Model` but since the table is managed=False and uses `BigAutoField` as pk, this works. No action needed.

- [ ] **Step 5: Commit**

```bash
git add realsproj/migrations/0002_add_unique_constraints.py realsproj/models.py
git commit -m "fix: add DB unique constraints and fix receipt number race condition"
```

### Task 1.2: Fix permission gating inconsistencies

**Files:**
- Modify: `projectsite/urls.py`
- Modify: `realsproj/views/products.py`
- Modify: `realsproj/views/sales.py`
- Modify: `realsproj/views/withdrawals.py`

- [ ] **Step 1: Audit all URL patterns for missing auth**

Add `@login_required` or `LoginRequiredMixin` to any view that handles data mutations. Currently affected public endpoints:

In `products.py`, add login_required to:
```python
@require_GET
@login_required
def check_barcode_availability(request):
```

In `sales.py`, add login_required to:
```python
@login_required
def revenue_change_api(request):
```

- [ ] **Step 2: Add login_required to API endpoints in urls.py**

For function-based API views, add the decorator. For class-based, add `LoginRequiredMixin`.

Check each path in `urls.py` — any path that isn't `login/`, `password_reset/`, `register/`, or `privacy-policy/`/`terms-of-use/` should require authentication.

- [ ] **Step 3: Add CSRF protection to JSON endpoints**

For `@require_http_methods(["POST"])` endpoints returning JsonResponse, ensure `@csrf_protect` or proper CSRF token in frontend AJAX calls. Current inconsistent state — some use `@csrf_exempt`, some don't.

```python
from django.views.decorators.csrf import csrf_protect, ensure_csrf_cookie

@require_http_methods(["POST"])
@csrf_protect
def product_bulk_archive(request):
    # ... existing code
```

- [ ] **Step 4: Commit**

```bash
git add projectsite/urls.py realsproj/views/products.py realsproj/views/sales.py realsproj/views/withdrawals.py
git commit -m "fix: add missing auth decorators to API endpoints and CSRF protection"
```

### Task 1.3: Replace broad exception handlers

**Files:**
- Read/modify: `realsproj/views/products.py`
- Read/modify: `realsproj/views/sales.py`
- Read/modify: `realsproj/views/withdrawals.py`
- Read/modify: `realsproj/views/materials.py`
- Read/modify: `realsproj/views/users.py`

- [ ] **Step 1: Identify all `except Exception` blocks in view files**

Search pattern: `except Exception` across all files in `realsproj/views/`. Replace with specific exception types.

Example — in `products.py` line 388:
```python
# Before:
except Exception as e:
    transaction.set_rollback(True)
    messages.error(self.request, f"Product did not save. {e}")
    return redirect(self.request.path)

# After:
except ValidationError as e:
    transaction.set_rollback(True)
    messages.error(self.request, f"Validation error: {e}")
    return redirect(self.request.path)
except (IntegrityError, OperationalError) as e:
    transaction.set_rollback(True)
    messages.error(self.request, f"Database error: {e}")
    return redirect(self.request.path)
```

- [ ] **Step 2: Apply to all view files**

Repeat pattern for each `except Exception` in views/products.py, sales.py, withdrawals.py, materials.py, users.py, reports.py. Map to:
- `ValidationError` for form/data validation
- `ObjectDoesNotExist` / `DoesNotExist` for missing records
- `IntegrityError` for FK constraint violations
- `OperationalError` for DB connection issues
- Keep `Exception` only as last-resort with logging

- [ ] **Step 3: Commit**

```bash
git add realsproj/views/
git commit -m "refactor: replace broad except Exception with specific exception types"
```

### Task 1.4: Add `xhtml2pdf` to requirements.txt

**Files:**
- Modify: `requirements.txt`

- [ ] **Step 1: Add missing dependency**

```txt
# PDF generation for exports
xhtml2pdf==0.2.16
```

Insert after the `schedule` line (line 26), before `pywin32`.

- [ ] **Step 2: Commit**

```bash
git add requirements.txt
git commit -m "fix: add missing xhtml2pdf dependency to requirements.txt"
```

---

## Phase 2: Performance Improvements

### Task 2.1: Fix N+1 queries in `WithdrawSuccessView`

**Files:**
- Modify: `realsproj/views/withdrawals.py:86-207`

**Analysis:** `get_queryset()` uses `select_related('created_by_admin')` but then `get_context_data()` iterates all withdrawals calling `get_item_display()` (which fires individual queries per item).

- [ ] **Step 1: Add prefetching to the queryset**

```python
def get_queryset(self):
    qs = Withdrawals.objects.filter(is_archived=False).select_related(
        'created_by_admin'
    ).prefetch_related(
        models.Prefetch(
            'product',
            queryset=Products.objects.select_related(
                'product_type', 'variant', 'size', 'size_unit'
            )
        ),
        models.Prefetch(
            'material',
            queryset=RawMaterials.objects.select_related('unit')
        )
    ).order_by('-date')
    # ... rest of filter logic
```

Note: `Withdrawals` FK to Products is via `item_id` — this is a generic FK pattern, not a real FK. Prefetch_related won't work directly. Instead, batch-load all referenced products/materials.

Better approach:
```python
def get_context_data(self, **kwargs):
    context = super().get_context_data(**kwargs)
    all_withdrawals = self.get_queryset()
    
    # Batch-load all referenced products and materials
    product_ids = set()
    material_ids = set()
    for w in all_withdrawals:
        if w.item_type == 'PRODUCT':
            product_ids.add(w.item_id)
        elif w.item_type == 'RAW_MATERIAL':
            material_ids.add(w.item_id)
    
    products = {p.id: p for p in Products.objects.select_related(
        'product_type', 'variant', 'size', 'size_unit'
    ).filter(id__in=product_ids)}
    
    materials = {m.id: m for m in RawMaterials.objects.select_related(
        'unit'
    ).filter(id__in=material_ids)}
    
    # Replaced get_item_display() calls with dict lookups
    for withdrawal in all_withdrawals:
        if withdrawal.item_type == 'PRODUCT':
            withdrawal._item_cache = products.get(withdrawal.item_id)
        elif withdrawal.item_type == 'RAW_MATERIAL':
            withdrawal._item_cache = materials.get(withdrawal.item_id)
    
    # ... rest of context logic
```

- [ ] **Step 2: Commit**

```bash
git add realsproj/views/withdrawals.py
git commit -m "perf: batch-load products/materials in WithdrawSuccessView to fix N+1"
```

### Task 2.2: Add caching for repeated aggregate queries

**Files:**
- Modify: `projectsite/settings.py`
- Modify: `realsproj/views/sales.py` (`SalesExpensesList`)
- Modify: `realsproj/views/products.py` (`ProductInventoryList`)

- [ ] **Step 1: Install django-cachalot**

```bash
pip install django-cachalot==2.6.1
```

Add to `settings.py` INSTALLED_APPS:
```python
INSTALLED_APPS = [
    ...
    'cachalot',
]
```

Add to `requirements.txt`:
```txt
# Query caching
django-cachalot==2.6.1
```

- [ ] **Step 2: Add manual caching for expensive operations in sales.py**

In `SalesExpensesList.get_context_data()`, wrap the summary aggregation queries:

```python
from django.core.cache import cache

def get_context_data(self, **kwargs):
    cache_key = f"sales_summary_{self.request.GET.urlencode()}"
    cached = cache.get(cache_key)
    if cached:
        return cached
    
    # ... existing 500-line method ...
    
    # Cache for 5 minutes
    cache.set(cache_key, context, 300)
    return context
```

- [ ] **Step 3: Commit**

```bash
git add projectsite/settings.py requirements.txt realsproj/views/sales.py
git commit -m "perf: add django-cachalot and manual caching for expensive sales summary queries"
```

### Task 2.3: Optimize `SalesExpensesList.get_context_data()`

**Files:**
- Create: `realsproj/services/sales_service.py`
- Modify: `realsproj/views/sales.py`

**Goal:** Decompose the ~500-line method into focused service functions.

- [ ] **Step 1: Extract service layer**

```python
# realsproj/services/__init__.py
```

```python
# realsproj/services/sales_service.py
from decimal import Decimal
from django.db.models import Sum, Avg, Count, Q
from django.utils import timezone
from realsproj.models import Sales, Expenses, Withdrawals, Products, RawMaterials

def get_manual_sales_queryset(filters=None):
    """Return queryset for manual (non-withdrawal) sales with filters applied."""
    qs = Sales.objects.filter(is_archived=False).exclude(
        Q(description__icontains="Order #") | Q(description__icontains="order #")
    )
    return _apply_common_filters(qs, filters)

def get_withdrawal_sales_queryset(filters=None):
    """Return queryset for withdrawal-based sales entries."""
    qs = Sales.objects.filter(is_archived=False).filter(
        Q(description__icontains="Order #") | Q(description__icontains="order #")
    )
    return _apply_common_filters(qs, filters)

def get_expenses_queryset(filters=None):
    qs = Expenses.objects.filter(is_archived=False)
    return _apply_common_filters(qs, filters)

def _apply_common_filters(qs, filters):
    if not filters:
        return qs
    month = filters.get('month')
    show_all = filters.get('show_all')
    category = filters.get('category')
    query = filters.get('query')
    
    if show_all:
        pass
    elif month:
        try:
            year_str, month_str = month.split("-")
            qs = qs.filter(date__year=int(year_str), date__month=int(month_str.lstrip("0")))
        except ValueError:
            today = timezone.now()
            qs = qs.filter(date__year=today.year, date__month=today.month)
    else:
        today = timezone.now()
        qs = qs.filter(date__year=today.year, date__month=today.month)
    
    if category:
        qs = qs.filter(category__iexact=category)
    if query:
        from django.db.models import Q
        qs = qs.filter(
            Q(category__icontains=query) | Q(amount__icontains=query) | Q(date__icontains=query)
        )
    return qs

def compute_sales_summary(queryset):
    return queryset.aggregate(
        total_sales=Sum("amount"),
        average_sales=Avg("amount"),
        sales_count=Count("id"),
    )

def compute_financial_loss(filters=None):
    qs = Withdrawals.objects.filter(
        reason__in=['EXPIRED', 'DAMAGED', 'REPLACEMENT_FOR_RETURNED'],
        is_archived=False
    )
    qs = _apply_common_filters(qs, filters)
    
    total = Decimal('0.00')
    for w in qs:
        try:
            if w.item_type == 'PRODUCT':
                product = Products.objects.select_related('unit_price').get(id=w.item_id)
                total += Decimal(w.quantity) * product.unit_price.unit_price
            elif w.item_type == 'RAW_MATERIAL':
                material = RawMaterials.objects.get(id=w.item_id)
                total += Decimal(w.quantity) * material.price_per_unit
        except (Products.DoesNotExist, RawMaterials.DoesNotExist):
            continue
    return total

def get_filter_params(request):
    """Extract filter parameters from request GET into a dict."""
    return {
        'month': request.GET.get('month', '').strip(),
        'category': request.GET.get('category', '').strip(),
        'query': request.GET.get('q', '').strip(),
        'show_all': request.GET.get('show_all', '').strip(),
    }
```

- [ ] **Step 2: Refactor `SalesExpensesList.get_context_data()`**

Replace the inline logic with calls to `sales_service` functions. The method body becomes:

```python
def get_context_data(self, **kwargs):
    context = super().get_context_data(**kwargs)
    filters = get_filter_params(self.request)
    
    # Manual sales
    manual_qs = get_manual_sales_queryset(filters)
    context["manual_sales_summary"] = compute_sales_summary(manual_qs)
    
    # Withdrawal sales
    withdrawal_qs = get_withdrawal_sales_queryset(filters)
    context["withdrawal_sales_summary"] = compute_sales_summary(withdrawal_qs)
    
    # Totals
    manual_total = context["manual_sales_summary"]["total_sales"] or 0
    withdrawal_total = context["withdrawal_sales_summary"]["total_sales"] or 0
    context["sales_summary"] = {
        'total_sales': manual_total + withdrawal_total,
        'sales_count': (context["manual_sales_summary"]["sales_count"] or 0) +
                       (context["withdrawal_sales_summary"]["sales_count"] or 0),
    }
    
    # Expenses
    expense_filters = get_filter_params_expenses(self.request)
    expenses_qs = get_expenses_queryset(expense_filters)
    context["expenses_summary"] = compute_sales_summary(expenses_qs)
    
    # Financial loss
    context["financial_loss"] = compute_financial_loss(filters)
    
    # Net calculations
    total_sales = context["sales_summary"]["total_sales"] or 0
    total_expenses = context["expenses_summary"]["total_expenses"] or 0
    context["net_sales"] = total_sales - context["financial_loss"]
    context["net_profit"] = total_sales - total_expenses
    
    # ... remaining pagination and category formatting logic stays in view
    # until Task 3.2 extracts it further
    return context
```

- [ ] **Step 3: Commit**

```bash
git add realsproj/services/ realsproj/views/sales.py
git commit -m "refactor: extract sales summary logic into service layer"
```

### Task 2.4: Add pagination to exports

**Files:**
- Modify: `realsproj/views/withdrawals.py:210-346`
- Modify: `realsproj/views/products.py` (product-inventory-export)
- Modify: `realsproj/views/reports.py`

- [ ] **Step 1: Add chunked processing to withdrawal export**

```python
@require_GET
@login_required
def export_withdrawals(request):
    # ... same filter logic up to qs definition ...
    
    # Process in chunks of 1000
    CHUNK_SIZE = 1000
    total = qs.count()
    
    for offset in range(0, total, CHUNK_SIZE):
        chunk = qs[offset:offset + CHUNK_SIZE]
        for withdrawal in chunk:
            writer.writerow([...])
```

- [ ] **Step 2: Commit**

```bash
git add realsproj/views/withdrawals.py realsproj/views/products.py realsproj/views/reports.py
git commit -m "perf: chunk export queries to prevent memory exhaustion"
```

---

## Phase 3: Code Quality & Maintainability

### Task 3.1: Clean up duplicate URL patterns

**Files:**
- Modify: `projectsite/urls.py`

- [ ] **Step 1: Remove duplicate path registrations**

Current duplicates to fix:
```python
# Lines 33-34: Keep one, rename to match
path('products/', a.ProductsList.as_view(), name='products'),
path('products/', a.ProductsList.as_view(), name='product-list'),  # REMOVE

# Lines 56-57
path('rawmaterials/', a.RawMaterialsList.as_view(), name='rawmaterials-list'),
path('rawmaterials/', a.RawMaterialsList.as_view(), name='rawmaterials'),  # REMOVE

# Lines 104-105
path('prodbatch/', a.ProductBatchList.as_view(), name='product-batch'),
path('prodbatch/', a.ProductBatchList.as_view(), name='product-batch-list'),  # REMOVE
```

After removing, find and update any `reverse('product-list')` calls to `reverse('products')` (in `products.py` line 214), `reverse('rawmaterials')` to `reverse('rawmaterials-list')` (in `materials.py`), `reverse('product-batch-list')` to `reverse('product-batch')`.

- [ ] **Step 2: Commit**

```bash
git add projectsite/urls.py realsproj/views/products.py realsproj/views/materials.py
git commit -m "cleanup: remove duplicate URL patterns and fix reverse() calls"
```

### Task 3.2: Consolidate duplicate bulk operations

**Files:**
- Read: `realsproj/views/sales.py`
- Read: `realsproj/views/withdrawals.py`

- [ ] **Step 1: Identify functional duplicates**

Current duplicates:
- `sales_bulk_delete` (function, line 272) vs `SaleBulkDeleteView` (class, line 324)
- `SaleBulkRestoreView` (line 308) vs — ensure there's no duplicate
- `WithdrawalBulkRestoreView` (line 818) vs `withdrawals_bulk_restore` 

Check each pair: if both exist and do the same thing, remove the lesser-used one and update any template URL references.

- [ ] **Step 2: Promote class-based views as canonical**

Class-based views are more testable. For each duplicate pair:
1. Keep the class-based view
2. Remove the function-based view
3. Update URL patterns to point to the class-based view
4. Update any AJAX endpoint URLs in templates

- [ ] **Step 3: Commit**

```bash
git add realsproj/views/sales.py realsproj/views/withdrawals.py projectsite/urls.py
git commit -m "cleanup: consolidate duplicate bulk operation views into class-based"
```

### Task 3.3: Replace `*` imports with explicit imports

**Files:**
- Modify: `realsproj/views/__init__.py`
- Modify: `realsproj/views/products.py` (lines 22-84)
- Modify: `realsproj/views/sales.py` (lines 22-84)
- Modify: `realsproj/views/withdrawals.py` (lines 22-84)
- Modify: `realsproj/views/materials.py` (lines 22-84)
- Modify: `realsproj/views/users.py` (lines 22-84)
- Modify: `realsproj/views/reports.py` (lines 22-84)

- [ ] **Step 1: Replace `from realsproj.views.products import *` etc. in `__init__.py`**

```python
# Before (__init__.py):
from realsproj.views.helpers import *
from realsproj.views.products import *
from realsproj.views.materials import *
from realsproj.views.sales import *
from realsproj.views.withdrawals import *
from realsproj.views.users import *
from realsproj.views.reports import *

# After (__init__.py):
"""Views package - re-exports for URL configuration."""
# Individual view imports used by urls.py are accessed via the 'a' alias in urls.py
# Each view module is imported directly where needed.
```

Then update `projectsite/urls.py` to import directly from each module instead of from `realsproj.views`:

```python
# Before:
from realsproj import views as a

# After:
from realsproj.views.products import (
    ProductsList, ProductCreateView, ProductsUpdateView, ProductsDeleteView,
    ProductArchiveView, ArchivedProductsListView, ProductUnarchiveView,
    ProductArchiveOldView, product_bulk_delete, product_bulk_archive,
    product_bulk_restore, product_scan_phone, check_barcode_availability,
    check_product_batches, ProductBatchList, BulkProductBatchCreateView,
    ProductBatchUpdateView, ProductBatchDeleteView, ProductBatchArchiveView,
    ArchivedProductBatchListView, ProductBatchUnarchiveView,
    ProductBatchArchiveOldView, product_batch_bulk_delete,
    product_batch_bulk_archive, product_batch_bulk_restore,
    ProductInventoryList, export_product_inventory, BestSellerProductsView,
    export_bestseller_report, ProductAttributesView, ProductTypeAddView,
    ProductTypeEditView, ProductTypeDeleteView, ProductVariantAddView,
    ProductVariantEditView, ProductVariantDeleteView, SizeAddView,
    SizeEditView, SizeDeleteView, SizeUnitAddView, SizeUnitEditView,
    SizeUnitDeleteView, UnitPriceAddView, UnitPriceEditView,
    UnitPriceDeleteView, SrpPriceAddView, SrpPriceEditView,
    SrpPriceDeleteView, PriceHistoryList, export_price_history,
)
from realsproj.views.materials import ( ... )
from realsproj.views.sales import ( ... )
from realsproj.views.withdrawals import ( ... )
from realsproj.views.users import ( ... )
from realsproj.views.reports import ( ... )
from realsproj.views.helpers import ( ... )
```

Then update `urls.py` references from `a.ViewName` to `ViewName` directly (remove the `a.` prefix).

- [ ] **Step 2: Remove unused imports from each view module**

Check each view file — many import the same 30+ models but only use 10-15. Use `flake8` or `pylint` to identify unused imports:

```bash
pip install flake8
flake8 realsproj/views/ --select=F401
```

Remove unused imports per file.

- [ ] **Step 3: Commit**

```bash
git add realsproj/views/ projectsite/urls.py
git commit -m "refactor: replace wildcard imports with explicit imports"
```

### Task 3.4: Add test infrastructure

**Files:**
- Create: `pyproject.toml` (or modify existing)
- Create: `realsproj/tests/__init__.py`
- Create: `realsproj/tests/conftest.py`
- Create: `realsproj/tests/test_models.py`
- Create: `realsproj/tests/test_withdrawals.py`

- [ ] **Step 1: Install test dependencies and configure**

```bash
pip install pytest pytest-django factory-boy pytest-cov
```

Add to `requirements.txt`:
```txt
# Testing
pytest==8.3.5
pytest-django==4.10.0
factory-boy==3.3.3
pytest-cov==6.1.1
```

Create `pyproject.toml` at project root:
```toml
[tool.pytest.ini_options]
DJANGO_SETTINGS_MODULE = "projectsite.settings"
python_files = ["test_*.py"]
testpaths = ["realsproj/tests"]

[tool.coverage.run]
source = ["realsproj"]
omit = ["*/migrations/*", "*/tests/*"]
```

- [ ] **Step 2: Create test factories**

```python
# realsproj/tests/factories.py
import factory
from django.contrib.auth.models import User
from realsproj.models import ProductTypes, ProductVariants, Sizes, SizeUnits, UnitPrices, SrpPrices, Products

class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = User
    username = factory.Sequence(lambda n: f"user_{n:04d}")
    password = factory.PostGenerationMethodCall('set_password', 'testpass123')

class ProductTypeFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ProductTypes
    name = factory.Sequence(lambda n: f"Type_{n}")
    created_by_admin = factory.SubFactory(UserFactory)

class ProductVariantFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ProductVariants
    name = factory.Sequence(lambda n: f"Variant_{n}")
    created_by_admin = factory.SubFactory(UserFactory)

class SizeUnitFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = SizeUnits
    unit_name = factory.Sequence(lambda n: f"Unit_{n}")
    created_by_admin = factory.SubFactory(UserFactory)

class SizeFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Sizes
    size_label = factory.Sequence(lambda n: f"Size_{n}")
    created_by_admin = factory.SubFactory(UserFactory)

class UnitPriceFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = UnitPrices
    unit_price = 10.00
    created_by_admin = factory.SubFactory(UserFactory)

class SrpPriceFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = SrpPrices
    srp_price = 15.00
    created_by_admin = factory.SubFactory(UserFactory)
```

- [ ] **Step 3: Write critical path tests**

```python
# realsproj/tests/test_withdrawals.py
import pytest
from decimal import Decimal
from django.utils import timezone
from realsproj.models import Withdrawals, Products
from .factories import (
    UserFactory, ProductTypeFactory, ProductVariantFactory,
    SizeUnitFactory, SizeFactory, UnitPriceFactory, SrpPriceFactory
)

@pytest.mark.django_db
class TestWithdrawalCreation:
    def test_create_sold_withdrawal(self):
        user = UserFactory()
        product_type = ProductTypeFactory(created_by_admin=user)
        variant = ProductVariantFactory(created_by_admin=user)
        size_unit = SizeUnitFactory(created_by_admin=user)
        size = SizeFactory(created_by_admin=user)
        unit_price = UnitPriceFactory(created_by_admin=user)
        srp_price = SrpPriceFactory(created_by_admin=user)
        
        product = Products.objects.create(
            product_type=product_type,
            variant=variant,
            size_unit=size_unit,
            size=size,
            unit_price=unit_price,
            srp_price=srp_price,
            product_code="TEST01",
            created_by_admin=user,
        )
        
        withdrawal = Withdrawals.objects.create(
            item_id=product.id,
            item_type="PRODUCT",
            quantity=Decimal("5.00"),
            reason="SOLD",
            sales_channel="ORDER",
            price_type="SRP",
            date=timezone.now(),
            created_by_admin=user,
        )
        
        assert withdrawal.item_type == "PRODUCT"
        assert withdrawal.quantity == Decimal("5.00")
        assert withdrawal.receipt_number is not None
        assert withdrawal.receipt_number.startswith("REC-")

    def test_generate_receipt_number_is_unique(self):
        user = UserFactory()
        product_type = ProductTypeFactory(created_by_admin=user)
        variant = ProductVariantFactory(created_by_admin=user)
        size_unit = SizeUnitFactory(created_by_admin=user)
        size = SizeFactory(created_by_admin=user)
        unit_price = UnitPriceFactory(created_by_admin=user)
        srp_price = SrpPriceFactory(created_by_admin=user)
        
        product = Products.objects.create(
            product_type=product_type, variant=variant,
            size_unit=size_unit, size=size,
            unit_price=unit_price, srp_price=srp_price,
            product_code="TEST02", created_by_admin=user,
        )
        
        w1 = Withdrawals.objects.create(
            item_id=product.id, item_type="PRODUCT", quantity=Decimal("1"),
            reason="SOLD", date=timezone.now(), created_by_admin=user,
        )
        w2 = Withdrawals.objects.create(
            item_id=product.id, item_type="PRODUCT", quantity=Decimal("1"),
            reason="SOLD", date=timezone.now(), created_by_admin=user,
        )
        
        assert w1.receipt_number != w2.receipt_number
```

- [ ] **Step 4: Run tests**

```bash
pytest realsproj/tests/ -v --cov=realsproj
Expected: 2 passed, coverage report
```

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml requirements.txt realsproj/tests/
git commit -m "test: add pytest infrastructure and critical path tests"
```

---

## Phase 4: Architecture Improvements

### Task 4.1: Standardize timezone usage

**Files:**
- Search all files in `realsproj/` and `projectsite/` for `datetime.now()` (bare, non-timezone-aware)

- [ ] **Step 1: Find and replace bare datetime usage**

```bash
rg "datetime\.now\(\)" --type py realsproj/ projectsite/
rg "datetime\.today\(\)" --type py realsproj/ projectsite/
```

Replace each instance with `timezone.now()` (for datetimes) or `timezone.localdate()` (for dates).

Add import if missing:
```python
from django.utils import timezone
```

- [ ] **Step 2: Commit**

```bash
git add realsproj/ projectsite/
git commit -m "fix: standardize timezone usage across codebase"
```

### Task 4.2: Add `is_active` middleware check for deactivated users

**Files:**
- Read: `realsproj/middleware.py`
- Modify: `realsproj/middleware.py`

- [ ] **Step 1: Add authenticated-but-deactivated check**

```python
# realsproj/middleware.py
from django.shortcuts import redirect
from django.contrib import messages
from django.urls import reverse

class DeactivatedUserMiddleware:
    """Redirect deactivated users to login page."""
    def __init__(self, get_response):
        self.get_response = get_response
    
    def __call__(self, request):
        if request.user.is_authenticated and not request.user.is_active:
            from django.contrib.auth import logout
            logout(request)
            messages.error(request, "Your account has been deactivated. Please contact an administrator.")
            return redirect('login')
        return self.get_response(request)
```

Add to `settings.py` MIDDLEWARE:
```python
MIDDLEWARE = [
    ...
    'realsproj.middleware.DeactivatedUserMiddleware',
]
```

- [ ] **Step 2: Remove username-pattern-based deactivation checks**

In `models.py:HistoryLog.get_admin_display()` (lines 440-463), the `inactive_user_` and `deleted_user_` username prefixes are used to detect deactivated users. Replace with proper `is_active` check:

```python
def get_admin_display(self):
    try:
        if self.admin:
            if not self.admin.is_active:
                original = self.admin.first_name if self.admin.first_name else self.admin.username
                # Strip ORIGINAL_USERNAME: prefix if present
                if 'ORIGINAL_USERNAME:' in original:
                    original = original.split('ORIGINAL_USERNAME:')[1].split('|')[0]
                return f"{original} (Deactivated)"
            return self.admin.username
    except Exception:
        ...
```

- [ ] **Step 3: Commit**

```bash
git add realsproj/middleware.py projectsite/settings.py realsproj/models.py
git commit -m "feat: add deactivated user middleware, replace username pattern checks"
```

### Task 4.3: Extract business logic into service layer (foundation)

**Files:**
- Create: `realsproj/services/pricing_service.py`
- Create: `realsproj/services/inventory_service.py`
- Create: `realsproj/services/__init__.py`

- [ ] **Step 1: Create pricing service**

```python
# realsproj/services/pricing_service.py
from decimal import Decimal, InvalidOperation
from realsproj.models import Products, Discounts

def calculate_unit_price(product, price_type):
    """Get base unit price for a product by price type."""
    if price_type == 'UNIT':
        return product.unit_price.unit_price
    elif price_type == 'SRP':
        return product.srp_price.srp_price
    raise ValueError(f"Unknown price_type: {price_type}")

def calculate_discount_amount(base_price, discount_obj=None, custom_discount_percent=None):
    """Calculate discount amount from either a Discount object or custom percentage."""
    if discount_obj:
        if discount_obj.discount_type == 'PERCENT':
            return base_price * (discount_obj.value / 100)
        return discount_obj.value
    elif custom_discount_percent:
        return base_price * (custom_discount_percent / 100)
    return Decimal('0.00')

def calculate_final_price(product, price_type, quantity, discount_obj=None, custom_discount_percent=None):
    """Compute final total for a product sale."""
    base_price = calculate_unit_price(product, price_type)
    discount_amount = calculate_discount_amount(base_price, discount_obj, custom_discount_percent)
    final_unit_price = base_price - discount_amount
    total = quantity * final_unit_price
    return {
        'base_price': base_price,
        'discount_amount': discount_amount,
        'final_unit_price': final_unit_price,
        'discount_percent': discount_obj.value if discount_obj else (custom_discount_percent or Decimal('0.00')),
        'total': total,
    }
```

- [ ] **Step 2: Create inventory service**

```python
# realsproj/services/inventory_service.py
from decimal import Decimal
from django.utils import timezone
from realsproj.models import ProductBatches, RawMaterialBatches

def get_fifo_batches(product, quantity, packaging=None):
    """Get batches for FIFO deduction. Returns list of (batch, deduct_qty) tuples."""
    filters = {
        'product': product,
        'is_archived': False,
        'quantity__gt': 0,
    }
    if packaging:
        filters['packaging'] = packaging
    
    batches = ProductBatches.objects.filter(**filters).order_by('expiration_date', 'id')
    
    remaining = quantity
    result = []
    for batch in batches:
        if remaining <= 0:
            break
        deduct = min(remaining, Decimal(batch.quantity))
        result.append((batch, deduct))
        remaining -= deduct
    
    return result

def check_stock_available(product, quantity):
    """Check if product has sufficient stock."""
    inv = product.productinventory
    return Decimal(inv.total_stock) >= quantity
```

- [ ] **Step 3: Refactor `WithdrawItemView.post()` to use services**

In `withdrawals.py:458-770`, replace the inline FIFO logic:

```python
# Before (inline in post method):
fifo_batches = ProductBatches.objects.filter(...)
for batch in fifo_batches:
    ...

# After:
from realsproj.services.inventory_service import get_fifo_batches, check_stock_available
from realsproj.services.pricing_service import calculate_final_price

if not check_stock_available(product, quantity):
    messages.error(request, f"Insufficient stock for {product}.")
    continue

batches_to_deduct = get_fifo_batches(product, quantity, selected_packaging)

if sum(d for _, d in batches_to_deduct) < quantity:
    messages.error(request, f"Insufficient stock for {product}.")
    continue

price_info = None
if reason == "SOLD" and price_type:
    price_info = calculate_final_price(product, price_type, quantity, discount_obj, custom_value)
```

- [ ] **Step 4: Commit**

```bash
git add realsproj/services/ realsproj/views/withdrawals.py
git commit -m "refactor: extract pricing and inventory business logic into service layer"
```

---

## Verification & Rollout

### Task V.1: Final smoke test

- [ ] **Step 1: Run all tests**

```bash
pytest realsproj/tests/ -v
Expected: all tests pass
```

- [ ] **Step 2: Run a manual smoke test**

```bash
python manage.py check --deploy
Expected: no errors (or known warnings only)
```

- [ ] **Step 3: Start dev server and verify critical paths**

```bash
python manage.py runserver
# Visit: /products/ (list loads)
# Visit: /withdrawals/ (list loads, pagination works)
# Visit: /salesexpenses/ (summary loads without error)
# Test creating a withdrawal
# Test exporting CSV
```

- [ ] **Step 4: Commit any fixes**

```bash
git add -A
git commit -m "fix: address issues found during verification"
```
