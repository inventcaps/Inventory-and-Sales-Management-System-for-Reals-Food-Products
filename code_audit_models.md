# Code Review & Audit: `realsproj/models.py`

> Full audit of the 1,756-line `models.py` file covering code cleanliness, performance, security, structure, and data integrity.

---

## 1. 🧹 Code Cleanliness

### 📍 Duplicate import of `timezone`
- **⚠️ Issue**: `from django.utils import timezone` is imported on line 10 and again on line 18.
- **✅ Suggestion**: Remove the duplicate on line 18.

### 📍 `login_required` imported in models
- **⚠️ Issue**: Line 11 — `from django.contrib.auth.decorators import login_required` is imported but never used in any model. Decorators don't belong in models.
- **✅ Suggestion**: Remove this import entirely.

### 📍 `mark_safe` imported but unused
- **⚠️ Issue**: Line 16 — `from django.utils.safestring import mark_safe` is never used anywhere in the file.
- **✅ Suggestion**: Remove this import.

### 📍 Auto-generated comment still present
- **⚠️ Issue**: Lines 1-7 — the original `inspectdb` auto-generated comment is still at the top of the file. This is a reminder that was supposed to be cleaned up.
- **✅ Suggestion**: Remove the auto-generated comment block. Add a proper module docstring instead.

### 📍 `print()` debug statements
- **⚠️ Issue**: `print()` calls left in production code:
  - `Notifications.formatted_message` — line 875
  - `Notifications._expiration_message` — line 916
- **✅ Suggestion**: Replace with `logger = logging.getLogger(__name__)` and `logger.error()`/`logger.debug()`.

### 📍 Bare `except:` clauses (14 instances)
- **⚠️ Issue**: In `HistoryLog.get_entity_display`, there are 14 bare `except:` clauses (lines 325, 344, 354, 364, 373, 383, 390, 397, 404, 411, 418, 425, 443, 447). These catch everything including `SystemExit` and `KeyboardInterrupt`.
- **✅ Suggestion**: Replace all with `except Exception:` at minimum, or better yet catch specific exceptions like `DoesNotExist`.

### 📍 Filipino comment left in code
- **⚠️ Issue**: Line 1240 — `is_archived = models.BooleanField(default=False) # <-- Idagdag ito` ("add this" in Filipino).
- **✅ Suggestion**: Remove the comment or replace with a proper English note.

### 📍 Circular import risk in model methods
- **⚠️ Issue**: Several model methods do `from .models import Products` or `from .models import RawMaterials` (lines 517, 552, 577, 1552, 1559). Since these are already inside `models.py`, the `from .models` import is redundant and risks circular imports.
- **✅ Suggestion**: Use the model class directly (e.g., `Products.objects.get(...)`) since it's already defined in the same file. If forward-reference is needed, use the string form `'Products'` or restructure.

### 📍 In-function imports that should be top-level
- **⚠️ Issue**: `from django.utils import timezone` is imported locally inside methods (lines 962, 988, 1130, 1162) despite already being imported at the top. Same with `from django.db.models import Q` (line 989).
- **✅ Suggestion**: Remove the local imports and use the top-level ones.

---

## 2. ⚡ Performance & Optimization

### 📍 `HistoryLog.get_entity_display` — massive N+1 query method
- **⚠️ Issue**: Lines 179-453 — this method does individual `Objects.get()` queries for every entity type. When displaying a list of 20 history log entries, this fires 20+ DB queries minimum.
- **✅ Suggestion**: Prefetch related entities at the queryset level in the view, or cache entity names in the `details` JSONField at creation time so no DB lookup is needed for display.

### 📍 `HistoryLog.get_details_display` — N+1 queries in `humanize_field`
- **⚠️ Issue**: Lines 492-695 — the `humanize_field` function does individual DB lookups for every FK field (product_id, variant_id, product_type_id, size_id, etc.). When called in a template loop, this is extremely expensive.
- **✅ Suggestion**: Cache humanized names at write time in the `details` JSONField, or batch-prefetch all referenced objects before rendering.

### 📍 `Notifications.formatted_message` — multiple DB queries per notification
- **⚠️ Issue**: Lines 753-890 — each call to `formatted_message` does 1-3 DB queries (product lookup, batch lookup, aggregate). In a notification list of 20 items, this is 20-60 queries.
- **✅ Suggestion**: Prefetch related objects in the view's queryset, or cache the formatted message in the model at creation time.

### 📍 `Notifications._expiration_message` — additional DB query
- **⚠️ Issue**: Lines 892-917 — does another DB query for batch lookup, duplicating work already done in `formatted_message`.
- **✅ Suggestion**: Pass the batch object from `formatted_message` to `_expiration_message` instead of re-querying.

### 📍 `ProductInventory.get_available_stock` / `get_expiring_stock` — DB queries per item
- **⚠️ Issue**: Lines 951-1009 — each call does an aggregate query. When called in a list view for N inventory items, this fires 2N queries.
- **✅ Suggestion**: Use a single annotated queryset with `Subquery` or `annotate` to compute available/expiring stock at the database level for all items at once.

### 📍 `RawMaterialInventory.get_available_stock` / `get_expiring_stock` — same pattern
- **⚠️ Issue**: Lines 1117-1182 — identical N+1 pattern as `ProductInventory`.
- **✅ Suggestion**: Same — use annotated querysets.

### 📍 `Withdrawals.compute_revenue` — DB query per withdrawal
- **⚠️ Issue**: Lines 1567-1594 — does `Products.objects.get(id=self.item_id)` for each withdrawal. In a list of 50 withdrawals, that's 50 queries.
- **✅ Suggestion**: Use `select_related` in the view's queryset, or rely on the stored `total_amount` field (which is already the first check).

### 📍 `Withdrawals.generate_receipt_number` — COUNT query every save
- **⚠️ Issue**: Lines 1596-1604 — does a `COUNT()` query every time a withdrawal is saved without a receipt number. Under concurrent writes, this can produce duplicate numbers.
- **✅ Suggestion**: Use database-level sequencing (e.g., a sequence model with `select_for_update()`, or a PostgreSQL sequence), or generate the receipt number in the view with `transaction.atomic()` and `select_for_update()`.

### 📍 `StockChanges.get_item` — DB query per stock change
- **⚠️ Issue**: Lines 1312-1322 — does `RawMaterials.objects.filter()` or `Products.objects.filter()` for each stock change.
- **✅ Suggestion**: Prefetch in the view's queryset.

### 📍 `Withdrawals.get_item_display` — DB query per call
- **⚠️ Issue**: Lines 1550-1565 — does individual DB lookups for item display.
- **✅ Suggestion**: This method is unnecessary if the view uses `select_related`. Remove or use cached data.

---

## 3. 🔒 Security

### 📍 `Withdrawals.save` — race condition on receipt number generation
- **⚠️ Issue**: Lines 1606-1610 — the `save()` method auto-generates a receipt number using `generate_receipt_number()`, which does a `COUNT()` + 1. Under concurrent saves, two withdrawals can get the same receipt number, violating the `unique=True` constraint and causing `IntegrityError`.
- **✅ Suggestion**: Wrap receipt number generation in `transaction.atomic()` with `select_for_update()` on a counter model, or use a database sequence. Better yet, generate the receipt number in the view (not the model's `save()`) where you have more control.

### 📍 `Withdrawals.generate_receipt_number` — not atomic
- **⚠️ Issue**: Lines 1596-1604 — the count-then-increment pattern is inherently non-atomic. Between the `COUNT()` and the `save()`, another transaction can insert a row.
- **✅ Suggestion**: Use `select_for_update()` on a dedicated `ReceiptCounter` model, or use PostgreSQL's `nextval()` with a sequence.

### 📍 `login_required` imported in models (misplaced)
- **⚠️ Issue**: Line 11 — `login_required` is a view decorator, not a model concern. Its presence in models suggests possible misuse.
- **✅ Suggestion**: Remove the import. If any model method needs auth checks, that's the view's responsibility.

---

## 4. 🏗️ Structure & Best Practices

### 📍 All models have `managed = False`
- **⚠️ Issue**: Every model in the file has `managed = False`, which means Django will never create, modify, or delete these tables via migrations. This was set by `inspectdb` and was supposed to be reviewed.
- **✅ Suggestion**: For custom application models (Products, Sales, Withdrawals, etc.), remove `managed = False` so Django can manage schema changes via migrations. Keep `managed = False` only for Django internal tables (auth_group, django_session, etc.) that are managed by Django's own migrations.

### 📍 All ForeignKeys use `models.DO_NOTHING`
- **⚠️ Issue**: Most ForeignKeys use `on_delete=models.DO_NOTHING` (lines 32, 43, 74, 84, 100, 101, 145, 167, 701, 923, 927, 1044, 1057, 1069, 1070, 1071, 1072, 1073, 1075, 1093, 1099, 1262, 1275, 1288, 1305, 1339). This means when a referenced row is deleted, Django does nothing, which can cause database `IntegrityError` at the DB level or leave orphaned records.
- **✅ Suggestion**: Choose appropriate `on_delete` behavior:
  - `models.CASCADE` — for strong dependencies (e.g., ProductBatches.product)
  - `models.PROTECT` — to prevent deletion if referenced (e.g., Products.unit_price)
  - `models.SET_NULL` — for optional references (e.g., created_by_admin)
  - `models.DO_NOTHING` — only for Django internal tables

### 📍 Django internal tables should not be in app models
- **⚠️ Issue**: Lines 22-136 — `AuthGroup`, `AuthGroupPermissions`, `AuthPermission`, `AuthUser`, `AuthUserGroups`, `AuthUserUserPermissions`, `DjangoAdminLog`, `DjangoContentType`, `DjangoMigrations`, `DjangoSession` are all Django internal tables. They are already defined in Django's own models and should not be duplicated.
- **✅ Suggestion**: Remove all Django internal table models from this file. Use Django's built-in `User`, `Group`, `Permission` models instead. If a custom user model is needed, extend `AbstractUser`.

### 📍 `AuthUser` duplicates Django's `User`
- **⚠️ Issue**: Lines 52-69 — `AuthUser` is a 1:1 copy of Django's built-in `User` model with `managed = False`. This causes confusion because some ForeignKeys point to `AuthUser` and others point to `User` (the Django built-in).
- **✅ Suggestion**: Use a single user model. If custom behavior is needed, create a proper custom user model extending `AbstractUser` and set `AUTH_USER_MODEL` in settings.

### 📍 Mixed FK targets: `AuthUser` vs `User`
- **⚠️ Issue**: Some models use `ForeignKey(AuthUser, ...)` (Expenses, HistoryLog, ProductBatches, ProductTypes, etc.) while others use `ForeignKey(User, ...)` (Discounts, UserActivity, Withdrawals, FinancialLoss, User2FASettings, etc.). This is inconsistent and can cause referential integrity issues since `AuthUser` and `User` point to the same table but are different Python classes.
- **✅ Suggestion**: Standardize on one. Use `settings.AUTH_USER_MODEL` (as `UserActivity` already does on line 1372) for all user references.

### 📍 `Withdrawals.get_queryset` is view logic in a model
- **⚠️ Issue**: Lines 1612-1622 — `get_queryset` is a `@staticmethod` that takes a `request` object. This is view/controller logic, not model logic.
- **✅ Suggestion**: Move this to the view class (`WithdrawSuccessView` or similar). Models should not access `request` objects.

### 📍 `HistoryLog.get_entity_display` — ~275 lines in a model method
- **⚠️ Issue**: Lines 179-453 — this single method is 275 lines with deeply nested if/elif chains. It's essentially a dispatcher for 15+ entity types.
- **✅ Suggestion**: Use a registry pattern or separate `EntityDisplayResolver` class:
  ```python
  ENTITY_DISPLAYERS = {
      'product': lambda entity_id: str(Products.objects.get(pk=entity_id)),
      'raw_material': lambda entity_id: str(RawMaterials.objects.get(pk=entity_id)),
      ...
  }
  ```

### 📍 `HistoryLog.get_details_display` — ~200 lines
- **⚠️ Issue**: Lines 492-695 — another massive method with complex formatting logic.
- **✅ Suggestion**: Extract into a `HistoryLogDetailsFormatter` utility class.

### 📍 `Notifications.formatted_message` — ~120 lines
- **⚠️ Issue**: Lines 753-890 — complex display logic with repeated product name formatting.
- **✅ Suggestion**: Extract product name formatting into a shared utility. Cache the formatted message.

### 📍 Plural model names for singular entities
- **⚠️ Issue**: Several models use plural names but represent single entities:
  - `Products` — represents one product
  - `RawMaterials` — represents one raw material
  - `Sizes` — represents one size
  - `SizeUnits` — represents one size unit
- **✅ Suggestion**: Rename to singular: `Product`, `RawMaterial`, `Size`, `SizeUnit`. Django conventions use singular model names. This would require updating all references but is worth it for clarity.

### 📍 No `related_name` on most ForeignKeys
- **⚠️ Issue**: Most ForeignKeys don't specify `related_name`, causing Django to auto-generate reverse relation names like `products_set`, `withdrawals_set`, etc. This can lead to naming conflicts.
- **✅ Suggestion**: Add explicit `related_name` to all ForeignKeys for clarity and to prevent conflicts.

### 📍 No `verbose_name` / `verbose_name_plural` on any model
- **⚠️ Issue**: None of the models define `verbose_name` or `verbose_name_plural` in their `Meta` class. This affects admin display and generated labels.
- **✅ Suggestion**: Add `verbose_name` and `verbose_name_plural` to each model's `Meta` class.

### 📍 `SalesSummary` and `ExpensesSummary` — questionable models
- **⚠️ Issue**: Lines 156-162, 1250-1256 — these models have only `id` and `total_amount` fields with `BigIntegerField` as primary key. They appear to be database views or summary tables, not proper Django models.
- **✅ Suggestion**: If these are database views, add `managed = False` (already present) and consider using Django's database view support or computed properties instead.

### 📍 `ProductBatches.__str__` is broken
- **⚠️ Issue**: Lines 938-939 — the `__str__` method references `self.date` which doesn't exist on `ProductBatches` (the field is `batch_date`). Also, the method doesn't return anything — it just assigns to `local_date` and falls off the end, returning `None`.
- **✅ Suggestion**: Fix the `__str__` method:
  ```python
  def __str__(self):
      return f"Batch {self.batch_code or self.id} - {self.product} ({self.batch_date})"
  ```

### 📍 `RawMaterialBatches` — missing `__str__` method
- **⚠️ Issue**: Lines 1091-1105 — `RawMaterialBatches` has no `__str__` method, so it displays as `RawMaterialBatches object (1)` in admin and templates.
- **✅ Suggestion**: Add a `__str__` method.

### 📍 `Notifications` — missing `__str__` method
- **⚠️ Issue**: Lines 711-917 — `Notifications` has no `__str__` method.
- **✅ Suggestion**: Add `__str__` returning a summary of the notification.

---

## 5. 🗄️ Data Integrity

### 📍 `Withdrawals.item_id` is a `BigIntegerField` instead of ForeignKey
- **⚠️ Issue**: Line 1409 — `item_id = models.BigIntegerField()` stores a reference to either a Product or RawMaterial, but without a ForeignKey constraint. This means:
  - No referential integrity at the DB level
  - Deleted products/materials leave orphaned withdrawals
  - No `select_related` / `prefetch_related` possible
- **✅ Suggestion**: This is a polymorphic relationship. Consider:
  - Using Django's `GenericForeignKey` with `content_type` + `object_id`
  - Or adding two nullable FK fields: `product = FK(Products, null=True)` and `raw_material = FK(RawMaterials, null=True)`

### 📍 `StockChanges.item_id` — same issue
- **⚠️ Issue**: Line 1301 — `item_id = models.BigIntegerField()` with no FK constraint.
- **✅ Suggestion**: Same as above — use `GenericForeignKey` or separate FK fields.

### 📍 `Notifications.item_id` — same issue
- **⚠️ Issue**: Line 714 — `item_id = models.BigIntegerField()` with no FK constraint.
- **✅ Suggestion**: Same — use `GenericForeignKey`.

### 📍 `ProductInventory.total_stock` is denormalized
- **⚠️ Issue**: Line 944 — `total_stock` is a stored field that should equal the sum of all non-archived `ProductBatches.quantity` for that product. If batches are added/removed without updating `total_stock`, the data goes out of sync.
- **✅ Suggestion**: Either:
  - Make `total_stock` a computed property that queries batches on demand
  - Or add a database trigger (PostgreSQL) to keep it in sync
  - Or add a `save` signal handler to recalculate on batch changes

### 📍 `RawMaterialInventory.total_stock` — same denormalization issue
- **⚠️ Issue**: Line 1110 — same as `ProductInventory.total_stock`.
- **✅ Suggestion**: Same approach.

### 📍 `FinancialLoss` duplicates data from `Withdrawals`
- **⚠️ Issue**: Lines 1625-1655 — `FinancialLoss` stores `item_type`, `item_id`, `quantity`, `reason`, `loss_date`, `created_by_admin` — all of which are already in `Withdrawals`. If the withdrawal is updated, `FinancialLoss` can go out of sync.
- **✅ Suggestion**: Either:
  - Make `FinancialLoss` a database view over `Withdrawals` (filtering by loss reasons)
  - Or add a signal to keep them in sync
  - Or remove `FinancialLoss` entirely and query `Withdrawals` directly

### 📍 `ProductBatches.packaging` FK to `RawMaterials` — unclear semantics
- **⚠️ Issue**: Line 932 — `packaging = models.ForeignKey('RawMaterials, ...)` — this links a product batch to a raw material as "packaging". The relationship is ambiguous.
- **✅ Suggestion**: Add `related_name='packaged_batches'` and consider a through model if the packaging relationship needs metadata.

### 📍 `Withdrawals` model has too many fields (25+)
- **⚠️ Issue**: The `Withdrawals` model has grown to include pricing, discount, payment, customer, packaging, and batch fields. This makes the model very wide and hard to reason about.
- **✅ Suggestion**: Consider splitting into:
  - `Withdrawal` — base withdrawal (item, quantity, reason, date)
  - `SaleDetail` — sale-specific fields (pricing, discount, payment, customer, receipt_number)
  - Or use a JSON field for flexible metadata

### 📍 `ProductBatches.quantity` is `IntegerField` but `ProductInventory.total_stock` is `DecimalField`
- **⚠️ Issue**: Line 924 — `ProductBatches.quantity = IntegerField` but line 944 — `ProductInventory.total_stock = DecimalField(max_digits=10, decimal_places=2)`. Type mismatch can cause precision issues when summing integer batches into a decimal total.
- **✅ Suggestion**: Make `ProductBatches.quantity` a `DecimalField` to match, or make `ProductInventory.total_stock` an `IntegerField` if quantities are always whole numbers.

### 📍 No model-level validation (clean methods)
- **⚠️ Issue**: No model defines a `clean()` method or uses validators for business rules. For example:
  - `Withdrawals.quantity` should be > 0
  - `Products.unit_price` and `srp_price` should be > 0
  - `Discounts.value` should be > 0 and < 100 for PERCENT type
  - `Expenses.amount` and `Sales.amount` should be > 0
- **✅ Suggestion**: Add `clean()` methods with appropriate validation, or use Django's `MinValueValidator`/`MaxValueValidator` on fields.

---

## Summary Statistics

| Category | Issues Found |
|---|---|
| 🧹 Code Cleanliness | 9 |
| ⚡ Performance | 9 |
| 🔒 Security | 3 |
| 🏗️ Structure & Best Practices | 16 |
| 🗄️ Data Integrity | 10 |
| **Total** | **47** |

---

## 🔥 Top Priority Fixes

1. **Fix `ProductBatches.__str__` — currently returns `None`** — Bug (line 938-939)
2. **Fix `Withdrawals.generate_receipt_number` race condition** — Security/Data integrity (lines 1596-1604)
3. **Remove Django internal table models** — Structure (lines 22-136)
4. **Replace `models.DO_NOTHING` with proper `on_delete`** — Data integrity (throughout)
5. **Standardize FK target: `AuthUser` vs `User`** — Structure (throughout)
6. **Move `Withdrawals.get_queryset` to views** — Structure (lines 1612-1622)
7. **Replace bare `except:` with `except Exception:`** — Cleanliness (14 instances)
8. **Fix `item_id` fields — add GenericForeignKey or separate FKs** — Data integrity (3 models)
9. **Remove duplicate imports and unused imports** — Cleanliness (lines 11, 16, 18)
10. **Replace `print()` with `logging`** — Cleanliness (lines 875, 916)
