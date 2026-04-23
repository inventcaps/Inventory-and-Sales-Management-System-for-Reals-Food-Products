from django.shortcuts import render, redirect, get_object_or_404
from django.views.generic.list import ListView
from django.views.generic import (
    ListView, CreateView, UpdateView, DeleteView, TemplateView, View
)
from django.views.generic.edit import ModelFormMixin
from django.contrib import messages
from django.views import View
from django.http import JsonResponse
from django.views.decorators.http import require_GET
from django.db import transaction, models
from django.utils.decorators import method_decorator
from django.contrib.auth.decorators import login_required
from decimal import Decimal, InvalidOperation
from django.urls import reverse, reverse_lazy
from django.contrib.auth.forms import AuthenticationForm, UserChangeForm
from django.contrib.auth import login, authenticate, update_session_auth_hash
from django.contrib.auth import get_user_model
from .forms import CustomUserCreationForm
from django.db.models import Avg, Count, Sum
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.views.decorators.http import require_http_methods
from django.forms import modelformset_factory
import threading
from realsproj.forms import (
    ProductsForm,
    RawMaterialsForm,
    HistoryLogForm,
    SalesForm,
    ExpensesForm,
    SalesExpensesForm,
    ProductBatchForm,
    ProductInventoryForm,
    RawMaterialBatchForm,
    RawMaterialInventoryForm,
    ProductTypesForm,
    ProductVariantsForm,
    SizesForm,
    SizeUnitsForm,
    UnitPricesForm,
    SrpPricesForm,
    NotificationsForm,
    BulkProductBatchForm,
    StockChangesForm,
    BulkRawMaterialBatchForm,
    UnifiedWithdrawForm,
    CustomUserCreationForm,
    WithdrawEditForm
)

from realsproj.models import (
    Products,
    RawMaterials,
    HistoryLog,
    HistoryLogTypes,
    Sales,
    Expenses,
    ProductBatches,
    ProductInventory,
    RawMaterialBatches,
    RawMaterialInventory,
    ProductTypes,
    ProductVariants,
    Sizes,
    SizeUnits,
    UnitPrices,
    SrpPrices,
    Withdrawals,
    Notifications,
    AuthUser,
    StockChanges,
    SalesSummary,
    ExpensesSummary,
    Discounts,
    UserActivity,
    PriceHistory
)

from django.db.models import Q, CharField
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.views.generic import TemplateView
from django.db.models.functions import TruncMonth, TruncDay
from django.db.models.functions import Cast
from django.contrib.auth.models import User
import os
from django.http import HttpResponse
import csv
from datetime import datetime, timedelta, date
from django.db.models.signals import pre_save, post_delete
from django.dispatch import receiver
from django.utils import timezone
from django.contrib.auth.signals import user_logged_in, user_logged_out
from django.db.models import Q, F, CharField
from django.db.models.functions import Cast
import re
from urllib.parse import urlparse, parse_qs
from django.db.models import Count


def get_or_create_auth_user(user):
    """
    Get or create AuthUser record from Django User.
    This handles database sync issues when switching between databases.
    """
    try:
        return AuthUser.objects.get(id=user.id)
    except AuthUser.DoesNotExist:

        return AuthUser.objects.create(
            id=user.id,
            password=user.password,
            last_login=user.last_login,
            is_superuser=user.is_superuser,
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name,
            email=user.email,
            is_staff=user.is_staff,
            is_active=user.is_active,
            date_joined=user.date_joined
        )


# Helper function for creating history logs
def create_history_log(admin, log_category, entity_type, entity_id, before=None, after=None):
    """
    Create a history log entry.
    
    Args:
        admin: User instance who performed the action
        log_category: String category (e.g., "Withdrawal Edited", "Withdrawal Deleted")
        entity_type: String entity type (e.g., "withdrawal")
        entity_id: ID of the entity
        before: Dict of values before change (for updates)
        after: Dict of values after change (for creates/updates)
    """
    try:
        # Get or create log type
        log_type, _ = HistoryLogTypes.objects.get_or_create(
            category=log_category,
            defaults={'created_by_admin_id': admin.id}
        )
        
        # Build details
        details = {}
        if before:
            details['before'] = before
        if after:
            details['after'] = after
        
        # Create log entry
        HistoryLog.objects.create(
            admin_id=admin.id,
            log_type_id=log_type.id,
            log_date=timezone.now(),
            entity_type=entity_type,
            entity_id=entity_id,
            details=details if details else None,
            is_archived=False
        )
    except Exception as e:
        # Silently fail to avoid breaking the main operation
        pass


@method_decorator(login_required, name='dispatch')

class HomePageView(LoginRequiredMixin, TemplateView):
    template_name = "home.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        sales_summary = SalesSummary.objects.first()
        total_sales = sales_summary.total_amount if sales_summary else 0

        expenses_summary = ExpensesSummary.objects.first()
        total_expenses = expenses_summary.total_amount if expenses_summary else 0

        context['total_revenue'] = total_sales - total_expenses

        context['total_stocks'] = ProductInventory.objects.aggregate(
            total=Sum('total_stock')
        )['total'] or 0

        context['recent_sales'] = Withdrawals.objects.filter(
            item_type="PRODUCT", reason="SOLD"
        ).order_by('-date')[:6]

        return context


@login_required
def sales_vs_expenses(request):
    # Restrict to superusers only
    if not request.user.is_superuser:
        messages.error(request, "❌ You don't have permission to access financial reports.")
        return redirect('home')
    sales_monthly = (
        Sales.objects
        .annotate(month=TruncMonth('date'))
        .values('month')
        .annotate(total=Sum('amount'))
        .order_by('month')
    )
    expenses_monthly = (
        Expenses.objects
        .annotate(month=TruncMonth('date'))
        .values('month')
        .annotate(total=Sum('amount'))
        .order_by('month')
    )

    months = sorted(
        set([s['month'].strftime("%Y-%m") for s in sales_monthly] +
            [e['month'].strftime("%Y-%m") for e in expenses_monthly])
    )

    sales_totals = []
    expenses_totals = []

    for m in months:
        sales_totals.append(
            next((float(s['total']) for s in sales_monthly if s['month'].strftime("%Y-%m") == m), 0)
        )
        expenses_totals.append(
            next((float(e['total']) for e in expenses_monthly if e['month'].strftime("%Y-%m") == m), 0)
        )

    sales_daily = (
        Sales.objects
        .annotate(day=TruncDay('date'))
        .values('day')
        .annotate(total=Sum('amount'))
        .order_by('day')
    )
    expenses_daily = (
        Expenses.objects
        .annotate(day=TruncDay('date'))
        .values('day')
        .annotate(total=Sum('amount'))
        .order_by('day')
    )

    daily_dates = sorted(
        set([s['day'].strftime("%Y-%m-%d") for s in sales_daily] +
            [e['day'].strftime("%Y-%m-%d") for e in expenses_daily])
    )

    sales_daily_totals = []
    expenses_daily_totals = []

    for d in daily_dates:
        sales_daily_totals.append(
            next((float(s['total']) for s in sales_daily if s['day'].strftime("%Y-%m-%d") == d), 0)
        )
        expenses_daily_totals.append(
            next((float(e['total']) for e in expenses_daily if e['day'].strftime("%Y-%m-%d") == d), 0)
        )

    return JsonResponse({
        "months": months,
        "sales": sales_totals,
        "expenses": expenses_totals,
        "daily_dates": daily_dates,
        "sales_daily": sales_daily_totals,
        "expenses_daily": expenses_daily_totals,
    })

def revenue_change_api(request):
    year = request.GET.get("year")
    month = request.GET.get("month")

    sales_qs = Sales.objects.all()

    if year:
        sales_qs = sales_qs.filter(date__year=year)

    if month and month != "all":
        sales_qs = sales_qs.filter(date__month=month)
        sales_data = (
            sales_qs.annotate(day=TruncDay('date'))
            .values('day')
            .annotate(total=Sum('amount'))
            .order_by('day')
        )
        labels = [s['day'].strftime("%Y-%m-%d") for s in sales_data]
    else:
        sales_data = (
            sales_qs.annotate(month=TruncMonth('date'))
            .values('month')
            .annotate(total=Sum('amount'))
            .order_by('month')
        )
        labels = [s['month'].strftime("%Y-%m") for s in sales_data]

    revenues = [float(s['total']) for s in sales_data]

    return JsonResponse({
        "labels": labels,
        "revenues": revenues,
    })


@login_required
def monthly_report(request):
    if not request.user.is_superuser:
        messages.error(request, "❌ You don't have permission to view financial reports.")
        return redirect('home')

    sales = (
        Sales.objects.annotate(month=TruncMonth("date"))
        .values("month")
        .annotate(total_sales=Sum("amount"))
        .order_by("month")
    )

    expenses = (
        Expenses.objects.annotate(month=TruncMonth("date"))
        .values("month")
        .annotate(total_expenses=Sum("amount"))
        .order_by("month") 
    )

    # Calculate financial loss per month (expired, damaged, replacement items)
    financial_loss_withdrawals = Withdrawals.objects.filter(
        reason__in=['EXPIRED', 'DAMAGED', 'REPLACEMENT_FOR_RETURNED'],
        is_archived=False
    ).annotate(month=TruncMonth("date")).values("month", "item_type", "item_id", "quantity")
    
    # Group financial loss by month
    financial_loss_dict = {}
    for withdrawal in financial_loss_withdrawals:
        month = withdrawal["month"]
        if month not in financial_loss_dict:
            financial_loss_dict[month] = Decimal('0.00')
        
        try:
            if withdrawal["item_type"] == 'PRODUCT':
                product = Products.objects.select_related('unit_price').get(id=withdrawal["item_id"])
                loss_amount = Decimal(withdrawal["quantity"]) * product.unit_price.unit_price
                financial_loss_dict[month] += loss_amount
            elif withdrawal["item_type"] == 'RAW_MATERIAL':
                material = RawMaterials.objects.get(id=withdrawal["item_id"])
                loss_amount = Decimal(withdrawal["quantity"]) * material.price_per_unit
                financial_loss_dict[month] += loss_amount
        except (Products.DoesNotExist, RawMaterials.DoesNotExist):
            continue

    # Normalize all dictionaries to use date objects as keys
    def normalize_date(dt):
        if hasattr(dt, 'date'):
            return dt.date()
        return dt

    expenses_dict = {normalize_date(e["month"]): e["total_expenses"] for e in expenses}
    sales_dict = {normalize_date(s["month"]): s["total_sales"] for s in sales}
    
    # Normalize financial_loss_dict keys as well
    normalized_financial_loss_dict = {}
    for month, loss in financial_loss_dict.items():
        normalized_month = normalize_date(month)
        normalized_financial_loss_dict[normalized_month] = loss

    # Get all unique months from sales, expenses, and financial loss
    all_months = set()
    all_months.update(sales_dict.keys())
    all_months.update(expenses_dict.keys())
    all_months.update(normalized_financial_loss_dict.keys())
    
    # Sort months chronologically
    all_months = sorted(all_months)

    report = []
    prev = None

    for month in all_months:
        gross_revenue = sales_dict.get(month, 0) or 0
        financial_loss = normalized_financial_loss_dict.get(month, 0) or 0
        revenue = gross_revenue - financial_loss  # Net revenue after financial loss
        cost = expenses_dict.get(month, 0) or 0
        profit = revenue - cost

        revenue_change = None
        profit_change = None
        if prev:
            revenue_change = revenue - prev["revenue"]
            profit_change = profit - prev["profit"]

        report.append({
            "month": month,
            "revenue": revenue,
            "financial_loss": financial_loss,
            "expenses": cost,
            "profit": profit,
            "revenue_change": revenue_change,
            "profit_change": profit_change,
        })
        prev = report[-1]

    summary = {
        "total_revenue": sum(r["revenue"] for r in report),
        "total_financial_loss": sum(r["financial_loss"] for r in report),
        "total_profit": sum(r["profit"] for r in report),
        "average_profit": (sum(r["profit"] for r in report) / len(report)) if report else 0,
    }

    return render(request, "reports/monthly_report.html", {
        "report": report,
        "summary": summary,
    })

@login_required
def monthly_report_export(request):
    if not request.user.is_superuser:
        messages.error(request, "❌ You don't have permission to export financial reports.")
        return redirect('home')
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="financial_report.csv"'
    response.write(u'\ufeff'.encode('utf8'))
    writer = csv.writer(response)
    writer.writerow(["Month", "Revenue", "Financial Loss", "Expenses", "Profit", "Revenue Change", "Profit Change", "Trend"])
    sales = (
        Sales.objects.annotate(month=TruncMonth("date"))
        .values("month")
        .annotate(total_sales=Sum("amount"))
        .order_by("month")
    )
    expenses = (
        Expenses.objects.annotate(month=TruncMonth("date"))
        .values("month")
        .annotate(total_expenses=Sum("amount"))
        .order_by("month")
    )
    
    # Calculate financial loss per month (same logic as main view)
    financial_loss_withdrawals = Withdrawals.objects.filter(
        reason__in=['EXPIRED', 'DAMAGED', 'REPLACEMENT_FOR_RETURNED'],
        is_archived=False
    ).annotate(month=TruncMonth("date")).values("month", "item_type", "item_id", "quantity")
    
    financial_loss_dict = {}
    for withdrawal in financial_loss_withdrawals:
        month = withdrawal["month"]
        if month not in financial_loss_dict:
            financial_loss_dict[month] = Decimal('0.00')
        
        try:
            if withdrawal["item_type"] == 'PRODUCT':
                product = Products.objects.select_related('unit_price').get(id=withdrawal["item_id"])
                loss_amount = Decimal(withdrawal["quantity"]) * product.unit_price.unit_price
                financial_loss_dict[month] += loss_amount
            elif withdrawal["item_type"] == 'RAW_MATERIAL':
                material = RawMaterials.objects.get(id=withdrawal["item_id"])
                loss_amount = Decimal(withdrawal["quantity"]) * material.price_per_unit
                financial_loss_dict[month] += loss_amount
        except (Products.DoesNotExist, RawMaterials.DoesNotExist):
            continue
    
    # Normalize all dictionaries to use date objects as keys
    def normalize_date(dt):
        if hasattr(dt, 'date'):
            return dt.date()
        return dt

    sales_dict = {normalize_date(s["month"]): Decimal(s["total_sales"] or 0) for s in sales}
    expenses_dict = {normalize_date(e["month"]): Decimal(e["total_expenses"] or 0) for e in expenses}
    
    # Normalize financial_loss_dict keys as well
    normalized_financial_loss_dict = {}
    for month, loss in financial_loss_dict.items():
        normalized_month = normalize_date(month)
        normalized_financial_loss_dict[normalized_month] = loss
    
    # Get all unique months from sales, expenses, and financial loss
    all_months = set()
    all_months.update(sales_dict.keys())
    all_months.update(expenses_dict.keys())
    all_months.update(normalized_financial_loss_dict.keys())
    all_months = sorted(all_months)

    report = []
    for month in all_months:
        gross_revenue = sales_dict.get(month, Decimal(0))
        financial_loss = normalized_financial_loss_dict.get(month, Decimal(0))
        revenue = gross_revenue - financial_loss  # Net revenue after financial loss
        cost = expenses_dict.get(month, Decimal(0))
        profit = revenue - cost
        report.append({
            "month": month,
            "revenue": revenue,
            "financial_loss": financial_loss,
            "expenses": cost,
            "profit": profit,
        })

    for i in range(len(report)):
        if i > 0: 
            older = report[i - 1]
            rc = report[i]["revenue"] - older["revenue"]
            pc = report[i]["profit"] - older["profit"]

            rev_change = f"↑ ₱{rc:,.2f}" if rc > 0 else f"↓ ₱{abs(rc):,.2f}" if rc < 0 else "₱0.00"
            prof_change = f"↑ ₱{pc:,.2f}" if pc > 0 else f"↓ ₱{abs(pc):,.2f}" if pc < 0 else "₱0.00"

            if rc > 0 and pc > 0:
                trend = "Revenue & Profit Increased"
            elif rc > 0 and pc < 0:
                trend = "Revenue Increased, Profit Decreased"
            elif rc < 0 and pc > 0:
                trend = "Revenue Decreased, Profit Increased"
            elif rc == 0 and pc == 0:
                trend = "No Change"
            else:
                trend = "Revenue & Profit Decreased"
        else:
            rev_change = "-"
            prof_change = "-"
            trend = "-"

        writer.writerow([
            report[i]["month"].strftime("%B %Y"),
            f"₱{report[i]['revenue']:,.2f}",
            f"₱{report[i]['financial_loss']:,.2f}",
            f"₱{report[i]['expenses']:,.2f}",
            f"₱{report[i]['profit']:,.2f}",
            rev_change,
            prof_change,
            trend,
        ])

    return response

class ProductsList(ListView):
    model = Products
    context_object_name = 'products'
    template_name = "prod_list.html"
    paginate_by = 10

    def get_queryset(self):
        
        queryset = (
            Products.objects.filter(is_archived=False)
            .select_related("product_type", "variant", "size", "size_unit", "unit_price", "srp_price")
            .order_by("-id")
        )

        # Unified search: Code, Product Type, Variant, and Size
        search = self.request.GET.get("search", "").strip()
        if search:
            queryset = queryset.filter(
                Q(product_code__icontains=search) |
                Q(product_type__name__icontains=search) |
                Q(variant__name__icontains=search) |
                Q(size__size_label__icontains=search)
            )
        
        date_created = self.request.GET.get("date_created")
        barcode = self.request.GET.get("barcode")

        if barcode:
            queryset = queryset.filter(barcode__icontains=barcode)
        if date_created:
            date_created = date_created.replace("/", "-").strip()
            parts = date_created.split("-")

            year, month, day = None, None, None

            if len(parts) == 3:
                if len(parts[0]) == 4:
                    year, month, day = parts
                else:
                    month, day, year = parts
            elif len(parts) == 2:
                if len(parts[0]) == 4:
                    year, month = parts
                else:
                    month, year = parts
            elif len(parts) == 1:
                if len(parts[0]) == 4: 
                    year = parts[0]
                elif len(parts[0]) <= 2:
                    month = parts[0]

            filters = {}
            if year and year.isdigit():
                filters["date_created__year"] = int(year)
            if month and month.isdigit():
                filters["date_created__month"] = int(month)
            if day and day.isdigit():
                filters["date_created__day"] = int(day)

            if filters:
                queryset = queryset.filter(**filters)

        return queryset.order_by('-date_created')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["query_params"] = self.request.GET

        total_products = Products.objects.filter(is_archived=False).count()
        context['total_products'] = total_products
        return context


def product_scan_phone(request):
    
    return render(request, "product_scan_phone.html")

@require_GET
def check_barcode_availability(request):
    """API endpoint to check if a barcode already exists"""
    barcode = request.GET.get('barcode', '').strip()
    product_id = request.GET.get('product_id', None)  # For edit mode
    
    if not barcode:
        return JsonResponse({'available': True, 'message': ''})
    
    # Check if barcode exists
    qs = Products.objects.filter(barcode=barcode)
    
    # Exclude current product if editing
    if product_id:
        qs = qs.exclude(pk=product_id)
    
    if qs.exists():
        product = qs.first()
        return JsonResponse({
            'available': False,
            'message': f'Barcode already used by: {product.product_type.name} - {product.variant.name}',
            'product_id': product.id
        })
    
    return JsonResponse({
        'available': True,
        'message': 'Barcode is available'
    })

class ProductArchiveView(View):
    def post(self, request, pk):
        product = get_object_or_404(Products, pk=pk)
        
        # Set current user for trigger
        from django.db import connection
        with connection.cursor() as cursor:
            cursor.execute("SET LOCAL app.current_user_id = %s", [request.user.id])
        
        product.is_archived = True
        product.save()  # Trigger will handle logging
        
        # Handle AJAX requests
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': True, 'message': 'Product archived successfully'})
        
        page = request.POST.get('page')
        if page:
            return redirect(f"{reverse('product-list')}?page={page}")
        return redirect('product-list')

class ArchivedProductsListView(ListView):
    model = Products
    template_name = 'archived_products.html'
    context_object_name = 'object_list'
    paginate_by = 10

    def get_queryset(self):
        return Products.objects.filter(is_archived=True).order_by('-date_created')

class ProductUnarchiveView(View):
    def post(self, request, pk):
        product = get_object_or_404(Products, pk=pk)
        
        # Set current user for trigger
        from django.db import connection
        with connection.cursor() as cursor:
            cursor.execute("SET LOCAL app.current_user_id = %s", [request.user.id])
        
        product.is_archived = False
        product.save()  # Trigger will handle logging
        
        return redirect('products-archived-list')

class ProductArchiveOldView(View):
    def post(self, request):
        one_year_ago = timezone.now() - timedelta(days=365)
        old_products = Products.objects.filter(is_archived=False, date_created__lt=one_year_ago)
        
        # Log each archived product
        for product in old_products:
            product_data = {
                'product_type': product.product_type.name,
                'variant': product.variant.name,
                'size': f"{product.size.size_label} {product.size_unit.unit_name}",
                'unit_price': str(product.unit_price.unit_price),
                'srp_price': str(product.srp_price.srp_price),
                'date_created': str(product.date_created),
            }
            
            create_history_log(
                admin=request.user,
                log_category="Product Archived (Old Data)",
                entity_type="product",
                entity_id=product.id,
                after=product_data
            )
        
        old_products.update(is_archived=True)
        return redirect('product-list')

@require_http_methods(["POST"])
def product_bulk_delete(request):
    # Only superusers can delete products
    if not request.user.is_superuser:
        return JsonResponse({'success': False, 'message': 'Permission denied. Only administrators can delete products.'})
    try:
        ids = request.POST.get('ids', '').split(',')
        ids = [int(id.strip()) for id in ids if id.strip()]
        
        if not ids:
            return JsonResponse({'success': False, 'message': 'No products selected'})
        
        deleted_count = Products.objects.filter(id__in=ids).delete()[0]
        return JsonResponse({
            'success': True,
            'message': f'Successfully deleted {deleted_count} product(s)'
        })
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)})

@require_http_methods(["POST"])
def product_bulk_archive(request):
    try:
        ids = request.POST.get('ids', '').split(',')
        ids = [int(id.strip()) for id in ids if id.strip()]
        
        if not ids:
            return JsonResponse({'success': False, 'message': 'No products selected'})
        
        # Set current user for trigger
        from django.db import connection
        with connection.cursor() as cursor:
            cursor.execute("SET LOCAL app.current_user_id = %s", [request.user.id])
        
        # Update will trigger database triggers for each product
        archived_count = Products.objects.filter(id__in=ids).update(is_archived=True)
        return JsonResponse({
            'success': True,
            'message': f'Successfully archived {archived_count} product(s)'
        })
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)})

@require_http_methods(["POST"])
def product_bulk_restore(request):
    try:
        ids = request.POST.get('ids', '').split(',')
        ids = [int(id.strip()) for id in ids if id.strip()]
        
        if not ids:
            return JsonResponse({'success': False, 'message': 'No products selected'})
        
        # Set current user for trigger
        from django.db import connection
        with connection.cursor() as cursor:
            cursor.execute("SET LOCAL app.current_user_id = %s", [request.user.id])
        
        # Update will trigger database triggers for each product
        restored_count = Products.objects.filter(id__in=ids).update(is_archived=False)
        return JsonResponse({
            'success': True,
            'message': f'Successfully restored {restored_count} product(s)'
        })
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)})

class ProductCreateView(CreateView):
    model = Products
    form_class = ProductsForm
    template_name = 'prod_add.html'
    success_url = reverse_lazy('products')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['product_types'] = ProductTypes.objects.all()
        context['variants'] = ProductVariants.objects.all()
        context['sizes'] = Sizes.objects.all()
        context['size_units'] = SizeUnits.objects.all()
        context['unit_prices'] = UnitPrices.objects.all()
        context['srp_prices'] = SrpPrices.objects.all()
        return context  

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        auth_user = AuthUser.objects.get(id=self.request.user.id)
        kwargs['created_by_admin'] = auth_user
        return kwargs

    def post(self, request, *args, **kwargs):
        request.POST = request.POST.copy()
        
        size_unit_name = request.POST.get('size_unit')
        if size_unit_name:
            try:
                unit_obj = SizeUnits.objects.get(unit_name=size_unit_name)
                request.POST['size_unit'] = unit_obj.id
            except SizeUnits.DoesNotExist:
                pass
        
        # Note: unit_price and srp_price are handled by forms.py clean methods
        # No need to process them here to avoid double conversion
        
        return super().post(request, *args, **kwargs)

    @transaction.atomic
    def form_valid(self, form):
        try:
            auth_user = AuthUser.objects.get(username=self.request.user.username)
            form.instance.created_by_admin = auth_user

            # Save ONE product
            self.object = form.save()

        except Exception as e:
            transaction.set_rollback(True)
            messages.error(self.request, f"❌ Product did not save. {e}")
            return redirect(self.request.path)  

        messages.success(self.request, "✅ Product added successfully.")
        return redirect('products')

    def form_invalid(self, form):
        """Handle validation errors (e.g., duplicate barcode)"""
        # Check if barcode error exists
        if 'barcode' in form.errors:
            messages.error(self.request, f"❌ {form.errors['barcode'][0]}")
        elif form.non_field_errors():
            messages.error(self.request, f"❌ {form.non_field_errors()[0]}")
        else:
            messages.error(self.request, "❌ Please correct the errors below.")
        
        return super().form_invalid(form)


class ProductsUpdateView(UpdateView):
    model = Products
    form_class = ProductsForm
    template_name = "prod_edit.html"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        auth_user = AuthUser.objects.get(id=self.request.user.id)
        kwargs['created_by_admin'] = auth_user
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Add all required context data
        context['product_types'] = ProductTypes.objects.all()
        context['variants'] = ProductVariants.objects.all()
        context['sizes'] = Sizes.objects.all()
        context['size_units'] = SizeUnits.objects.all()
        context['unit_prices'] = UnitPrices.objects.all()
        context['srp_prices'] = SrpPrices.objects.all()
        
        # Store the current page number
        referer = self.request.META.get('HTTP_REFERER', '')
        if 'page=' in referer:
            try:
                context['current_page'] = re.search(r'page=(\d+)', referer).group(1)
            except (AttributeError, IndexError):
                pass
        
        return context

    def get_success_url(self):
        # Try to get page from POST data first
        page = self.request.POST.get('current_page')
        
        # If not in POST, try to get from session
        if not page and 'current_page' in self.request.session:
            page = self.request.session['current_page']
            
        # Construct URL with page if available
        url = reverse('products')
        if page:
            url = f'{url}?page={page}'
            
        return url

    def post(self, request, *args, **kwargs):
        # Convert field names to ForeignKey IDs
        request.POST = request.POST.copy()
        
        # Handle size_unit
        size_unit_name = request.POST.get('size_unit')
        if size_unit_name:
            try:
                unit_obj = SizeUnits.objects.get(unit_name=size_unit_name)
                request.POST['size_unit'] = unit_obj.id
            except SizeUnits.DoesNotExist:
                pass
        
        # Note: unit_price and srp_price are handled by forms.py clean methods
        # No need to process them here to avoid double conversion
        
        # Store the current page in session
        referer = request.META.get('HTTP_REFERER', '')
        if 'page=' in referer:
            try:
                page = re.search(r'page=(\d+)', referer).group(1)
                request.session['current_page'] = page
            except (AttributeError, IndexError):
                pass

        # Handle photo deletion
        self.object = self.get_object()
        if "delete_photo" in request.POST:
            if self.object.photo:
                self.object.photo = None
                self.object.save(update_fields=["photo"])
                messages.success(request, "Product photo deleted.")
            else:
                messages.info(request, "No photo to delete.")
            return redirect(reverse("product-edit", kwargs={"pk": self.object.pk}))

        return super().post(request, *args, **kwargs)

    def form_valid(self, form):
        auth_user = AuthUser.objects.get(username=self.request.user.username)
        form.instance.created_by_admin = auth_user
        
        # Check if photo should be deleted
        if self.request.POST.get('delete_photo_flag') == '1':
            form.instance.photo = None

        from django.db import connection
        with connection.cursor() as cursor:
            cursor.execute("SET LOCAL app.current_user_id = %s", [auth_user.id])
        
        product = form.save()
        
        messages.success(self.request, "✅ Product updated successfully.")
        
        # Use get_success_url() to maintain the page number
        return redirect(self.get_success_url())

    def form_invalid(self, form):
        if 'barcode' in form.errors:
            messages.error(self.request, f"❌ {form.errors['barcode'][0]}")
        elif form.non_field_errors():
            messages.error(self.request, f"❌ {form.non_field_errors()[0]}")
        else:
            messages.error(self.request, "❌ Please correct the errors below.")
        return super().form_invalid(form)

@receiver(pre_save, sender=Products)
def delete_old_product_photo_on_change(sender, instance, **kwargs):
    if not instance.pk:
        return

    try:
        old_instance = Products.objects.get(pk=instance.pk)
    except Products.DoesNotExist:
        return

    old_file = old_instance.photo
    new_file = instance.photo

    if old_file and old_file.name:
        if (not new_file) or (old_file.name != getattr(new_file, 'name', None)):
            try:
                old_file.delete(save=False)
            except Exception:
                pass

@receiver(post_delete, sender=Products)
def delete_product_photo_on_delete(sender, instance, **kwargs):
    if instance.photo and instance.photo.name:
        try:
            instance.photo.delete(save=False)
        except Exception:
            pass


class ProductsDeleteView(UserPassesTestMixin, DeleteView):
    model = Products
    success_url = reverse_lazy("products")

    def test_func(self):
        return self.request.user.is_superuser

    def delete(self, request, *args, **kwargs):
        """Set current user ID in database session for trigger to use"""
        from django.db import connection
        
        with connection.cursor() as cursor:
            cursor.execute("SET LOCAL app.current_user_id = %s", [request.user.id])
        
        return super().delete(request, *args, **kwargs)

    def get_success_url(self):
        messages.success(self.request, "🗑️ Product deleted successfully.")
        page = self.request.POST.get('page')
        if page:
            return f"{reverse_lazy('products')}?page={page}"
        return super().get_success_url()


class RawMaterialsList(ListView):
    model = RawMaterials
    context_object_name = 'rawmaterials'
    template_name = "rawmaterial_list.html"
    paginate_by = 10
    
    def get_queryset(self):
        queryset = RawMaterials.objects.filter(is_archived=False).select_related("unit", "created_by_admin").order_by('-date_created')
        
        query = self.request.GET.get("q", "").strip()
        date_created = self.request.GET.get("date_created", "").strip()
        category = self.request.GET.get("category", "").strip().upper()

        if query:
            queryset = queryset.filter(
                Q(name__icontains=query) |
                Q(unit__unit_name__icontains=query) |
                Q(price_per_unit__icontains=query) |
                Q(date_created__icontains=query) |
                Q(created_by_admin__username__icontains=query)
            )
        
        if date_created:
            try:
                # Parse only year and month (from YYYY-MM)
                parsed_date = datetime.strptime(date_created, "%Y-%m")
                queryset = queryset.filter(
                    Q(date_created__year=parsed_date.year, date_created__month=parsed_date.month)
                )
            except ValueError:
                pass  # Ignore invalid format

        distinct_categories = (
            RawMaterials.objects.filter(is_archived=False)
            .values_list("category", flat=True)
            .distinct()
        )
        valid_categories = {c.upper() for c in distinct_categories if c}
        if category and category in valid_categories:
            queryset = queryset.filter(category__iexact=category)

        return queryset.order_by('-date_created')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        category = self.request.GET.get("category", "").strip().upper()
        distinct_categories = (
            RawMaterials.objects.filter(is_archived=False)
            .values_list('category', flat=True)
            .distinct()
        )
        context['category_choices'] = sorted({c.upper() for c in distinct_categories if c})
        context['category_filter'] = category if category in context['category_choices'] else ""
        context['total_raw_materials'] = context['paginator'].count if 'paginator' in context else 0
        return context

class RawMaterialArchiveView(View):
    def post(self, request, pk):
        item = get_object_or_404(RawMaterials, pk=pk)
        
        # Set current user for trigger
        from django.db import connection
        with connection.cursor() as cursor:
            cursor.execute("SET LOCAL app.current_user_id = %s", [request.user.id])
        
        item.is_archived = True
        item.save()  # Trigger will handle logging
        next_url = request.POST.get('next')
        if next_url:
            return redirect(next_url)
        return redirect('rawmaterials-list')

class RawMaterialArchiveOldView(View):
    def post(self, request):
        one_year_ago = timezone.now() - timedelta(days=365)
        RawMaterials.objects.filter(is_archived=False, date_created__lt=one_year_ago).update(is_archived=True)
        return redirect('rawmaterials-list')

@require_http_methods(["POST"])
def rawmaterial_bulk_delete(request):
    try:
        ids = request.POST.get('ids', '').split(',')
        ids = [int(id.strip()) for id in ids if id.strip()]
        
        if not ids:
            return JsonResponse({'success': False, 'message': 'No raw materials selected'})
        
        deleted_count = RawMaterials.objects.filter(id__in=ids).delete()[0]
        return JsonResponse({
            'success': True,
            'message': f'Successfully deleted {deleted_count} raw material(s)'
        })
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)})

@require_http_methods(["POST"])
def rawmaterial_bulk_archive(request):
    try:
        ids = request.POST.get('ids', '').split(',')
        ids = [int(id.strip()) for id in ids if id.strip()]
        
        if not ids:
            return JsonResponse({'success': False, 'message': 'No raw materials selected'})
        
        # Set current user for trigger
        from django.db import connection
        with connection.cursor() as cursor:
            cursor.execute("SET LOCAL app.current_user_id = %s", [request.user.id])
        
        # Update will trigger database triggers for each raw material
        archived_count = RawMaterials.objects.filter(id__in=ids).update(is_archived=True)
        
        return JsonResponse({
            'success': True,
            'message': f'Successfully archived {archived_count} raw material(s)'
        })
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)})

@require_http_methods(["POST"])
def rawmaterial_bulk_restore(request):
    try:
        ids = request.POST.get('ids', '').split(',')
        ids = [int(id.strip()) for id in ids if id.strip()]
        
        if not ids:
            return JsonResponse({'success': False, 'message': 'No raw materials selected'})
        
        # Set current user for trigger
        from django.db import connection
        with connection.cursor() as cursor:
            cursor.execute("SET LOCAL app.current_user_id = %s", [request.user.id])
        
        # Update will trigger database triggers for each raw material
        restored_count = RawMaterials.objects.filter(id__in=ids).update(is_archived=False)
        
        return JsonResponse({
            'success': True,
            'message': f'Successfully restored {restored_count} raw material(s)'
        })
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)})

class ArchivedRawMaterialsListView(ListView):
    model = RawMaterials
    template_name = 'archived_rawmaterials.html'
    context_object_name = 'object_list'
    paginate_by = 10

    def get_queryset(self):
        return RawMaterials.objects.filter(is_archived=True).order_by('-date_created')


class ArchivedPackagingMaterialsListView(ArchivedRawMaterialsListView):
    template_name = 'archived_packaging.html'

    def get_queryset(self):
        return (super().get_queryset()
                .filter(category__iexact='PACKAGING'))


class RawMaterialUnarchiveView(View):
    def post(self, request, pk):
        item = get_object_or_404(RawMaterials, pk=pk)
        
        # Set current user for trigger
        from django.db import connection
        with connection.cursor() as cursor:
            cursor.execute("SET LOCAL app.current_user_id = %s", [request.user.id])
        
        item.is_archived = False
        item.save()  # Trigger will handle logging
        next_url = request.POST.get('next')
        if next_url:
            return redirect(next_url)
        return redirect('rawmaterials-archived-list')

class RawMaterialsCreateView(CreateView):
    model = RawMaterials
    form_class = RawMaterialsForm
    template_name = 'rawmaterial_add.html'
    success_url = reverse_lazy('rawmaterials')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['size_units'] = SizeUnits.objects.all()
        return context

    def post(self, request, *args, **kwargs):
        unit_name = request.POST.get('unit')
        if unit_name:
            try:
                unit_obj = SizeUnits.objects.get(unit_name=unit_name)
                request.POST = request.POST.copy()
                request.POST['unit'] = unit_obj.id
            except SizeUnits.DoesNotExist:
                messages.error(request, f"Unit '{unit_name}' not found.")
                return redirect(self.request.path)
        return super().post(request, *args, **kwargs)

    @transaction.atomic
    def form_valid(self, form):
        try:
            auth_user = AuthUser.objects.get(id=self.request.user.id)
            form.instance.created_by_admin = auth_user
            self.object = form.save()
        except Exception as e:
            transaction.set_rollback(True)
            messages.error(self.request, f"Raw material creation failed: {e}")
            return redirect(self.request.path)  
        messages.success(self.request, "Raw material created successfully.")
        return redirect(self.success_url)

    def form_invalid(self, form):
        messages.error(self.request, "Please complete all required fields. The form was reset.")
        return redirect(self.request.path)  


class RawMaterialsUpdateView(UpdateView):
    model = RawMaterials
    form_class = RawMaterialsForm
    template_name = 'rawmaterial_edit.html'
    success_url = reverse_lazy('rawmaterials')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['size_units'] = SizeUnits.objects.all()
        return context

    def post(self, request, *args, **kwargs):
        # Convert unit name to unit ID
        unit_name = request.POST.get('unit')
        if unit_name:
            try:
                unit_obj = SizeUnits.objects.get(unit_name=unit_name)
                request.POST = request.POST.copy()
                request.POST['unit'] = unit_obj.id
            except SizeUnits.DoesNotExist:
                messages.error(request, f"Unit '{unit_name}' not found.")
                return redirect(reverse('rawmaterial-edit', kwargs={'pk': self.get_object().pk}))
        return super().post(request, *args, **kwargs)

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, "Raw Material updated successfully.")
        return response



class RawMaterialsDeleteView(LoginRequiredMixin, DeleteView):
    model = RawMaterials
    success_url = reverse_lazy('rawmaterials')

    def dispatch(self, request, *args, **kwargs):
        # Restrict to superusers only
        if not request.user.is_superuser:
            messages.error(request, "❌ You don't have permission to delete raw materials.")
            return redirect('rawmaterials-list')
        return super().dispatch(request, *args, **kwargs)

    def delete(self, request, *args, **kwargs):
        """Set current user ID in database session for trigger to use"""
        from django.db import connection
        
        with connection.cursor() as cursor:
            cursor.execute("SET LOCAL app.current_user_id = %s", [request.user.id])
        
        return super().delete(request, *args, **kwargs)

    def get_success_url(self):
        messages.success(self.request, "🗑️ Raw material deleted successfully.")
        next_url = self.request.POST.get('next')
        if next_url:
            return next_url
        return reverse_lazy('rawmaterials')


class CategoryFilteredRawMaterialsList(RawMaterialsList):
    category_value = None
    template_name = "rawmaterial_list.html"

    def get_queryset(self):
        queryset = super().get_queryset()
        if self.category_value:
            queryset = queryset.filter(category__iexact=self.category_value)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.category_value:
            context['total_raw_materials'] = RawMaterials.objects.filter(
                is_archived=False,
                category__iexact=self.category_value
            ).count()
        return context


class CategoryRawMaterialsCreateView(RawMaterialsCreateView):
    category_value = None

    def form_valid(self, form):
        if self.category_value:
            form.instance.category = self.category_value
        return super().form_valid(form)


class CategoryRawMaterialsUpdateView(RawMaterialsUpdateView):
    category_value = None

    def form_valid(self, form):
        if self.category_value:
            form.instance.category = self.category_value
        return super().form_valid(form)

    def get_queryset(self):
        queryset = super().get_queryset()
        if self.category_value:
            queryset = queryset.filter(category__iexact=self.category_value)
        return queryset


class PackagingMaterialsList(CategoryFilteredRawMaterialsList):
    category_value = 'PACKAGING'
    template_name = 'packaging_list.html'


class PackagingMaterialsCreateView(CategoryRawMaterialsCreateView):
    template_name = 'packaging_add.html'
    success_url = reverse_lazy('packaging-materials')
    category_value = 'PACKAGING'


class PackagingMaterialsUpdateView(CategoryRawMaterialsUpdateView):
    template_name = 'packaging_edit.html'
    success_url = reverse_lazy('packaging-materials')
    category_value = 'PACKAGING'


class HistoryLogList(ListView):
    model = HistoryLog
    context_object_name = 'historylog'
    template_name = "historylog_list.html"
    paginate_by = 10

    def get_queryset(self):
        user = self.request.user
        qs = HistoryLog.objects.select_related("admin", "log_type").filter(is_archived=False).order_by("-log_date")

        if not user.is_superuser:
            qs = qs.filter(admin=user.id)
        admin_filter = self.request.GET.get("admin", "").strip()
        log_filter = self.request.GET.get("log", "").strip()
        date_str = self.request.GET.get("date", "").strip()
        show_all = self.request.GET.get("show_all", "").strip()

        if user.is_superuser and admin_filter:
            try:
                admin_id = int(admin_filter)
                qs = qs.filter(admin_id=admin_id)
            except ValueError:
                pass 

        if log_filter:
            qs = qs.filter(log_type__category=log_filter)

        if date_str:
            try:
                year, month = map(int, date_str.split('-'))
                import calendar
                last_day = calendar.monthrange(year, month)[1]

                start_date = timezone.make_aware(datetime(year, month, 1))
                end_date = timezone.make_aware(datetime(year, month, last_day, 23, 59, 59))

                qs = qs.filter(log_date__gte=start_date, log_date__lte=end_date)
            except Exception:
                pass

        elif not show_all:
            today = timezone.now()
            import calendar
            last_day = calendar.monthrange(today.year, today.month)[1]

            start_date = timezone.make_aware(datetime(today.year, today.month, 1))
            end_date = timezone.make_aware(datetime(today.year, today.month, last_day, 23, 59, 59))

            qs = qs.filter(log_date__gte=start_date, log_date__lte=end_date)

        return qs.order_by('-log_date')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        today = timezone.now()
        context['current_month_value'] = today.strftime("%Y-%m")

        if self.request.user.is_superuser:

            admin_ids = (
                HistoryLog.objects.filter(is_archived=False)
                .values_list("admin_id", flat=True)
                .distinct()
            )

            admins = AuthUser.objects.filter(id__in=admin_ids)

            context['admins'] = [{"id": a.id, "name": a.username} for a in admins]
        else:
            context['admins'] = []

        context['logs'] = (
            HistoryLog.objects.filter(is_archived=False)
            .values_list('log_type__category', flat=True)
            .distinct()
            .order_by('log_type__category')
        )

        context['can_view_all_history'] = self.request.user.is_superuser

        params = self.request.GET.copy()
        params.pop("page", None)
        context["filter_params"] = params.urlencode()

        context["current_admin"] = self.request.GET.get("admin", "")
        context["current_log"] = self.request.GET.get("log", "")
        context["current_date"] = self.request.GET.get("date", "")

        return context
    
class SaleArchiveView(View):
    def post(self, request, pk):
        sale = get_object_or_404(Sales, pk=pk)
        
        # Set current user for trigger
        from django.db import connection
        with connection.cursor() as cursor:
            cursor.execute("SET LOCAL app.current_user_id = %s", [request.user.id])
        
        sale.is_archived = True
        sale.save()  # Trigger will handle logging
        
        return redirect('salesexpenses')

class SaleArchiveOldView(View):
    def post(self, request):
        one_year_ago = timezone.now() - timedelta(days=365)
        Sales.objects.filter(is_archived=False, date__lt=one_year_ago).update(is_archived=True)
        return redirect('salesexpenses')
    
class ArchivedSalesListView(ListView):
    model = Sales
    template_name = 'archived_sales.html'
    context_object_name = 'object_list'
    paginate_by = 10

    def get_queryset(self):
        return Sales.objects.filter(is_archived=True).order_by('-date')

class ArchivedSalesExpensesCombinedView(TemplateView):
    """Combined view for archived sales and expenses with filtering"""
    template_name = 'archived_sales_expenses.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Get filter type from query params
        filter_type = self.request.GET.get('type', '')
        
        # Fetch archived sales
        if not filter_type or filter_type == 'sales':
            context['archived_sales'] = Sales.objects.filter(is_archived=True).order_by('-date')
        else:
            context['archived_sales'] = []
        
        # Fetch archived expenses
        if not filter_type or filter_type == 'expenses':
            context['archived_expenses'] = Expenses.objects.filter(is_archived=True).order_by('-date')
        else:
            context['archived_expenses'] = []
        
        return context

class SaleUnarchiveView(View):
    def post(self, request, pk):
        sale = get_object_or_404(Sales, pk=pk)
        
        # Set current user for trigger
        from django.db import connection
        with connection.cursor() as cursor:
            cursor.execute("SET LOCAL app.current_user_id = %s", [request.user.id])
        
        sale.is_archived = False
        sale.save()  # Trigger will handle logging
        
        messages.success(request, "✅ Sale restored successfully.")
        return redirect('salesexpense-archive')

@require_http_methods(["POST"])
def sales_bulk_delete(request):
    try:
        ids = request.POST.get('ids', '').split(',')
        ids = [int(id.strip()) for id in ids if id.strip()]
        
        if not ids:
            return JsonResponse({'success': False, 'message': 'No sales selected'})
        
        deleted_count = Sales.objects.filter(id__in=ids).delete()[0]
        return JsonResponse({
            'success': True,
            'message': f'Successfully deleted {deleted_count} sale(s)'
        })
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)})

@require_http_methods(["POST"])
def sales_bulk_archive(request):
    try:
        ids = request.POST.get('ids', '').split(',')
        ids = [int(id.strip()) for id in ids if id.strip()]
        
        if not ids:
            return JsonResponse({'success': False, 'message': 'No sales selected'})
        
        archived_count = Sales.objects.filter(id__in=ids).update(is_archived=True)
        return JsonResponse({
            'success': True,
            'message': f'Successfully archived {archived_count} sale(s)'
        })
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)})

class SaleBulkRestoreView(View):
    def post(self, request):
        import json
        try:
            sale_ids = json.loads(request.POST.get('sale_ids', '[]'))
            if not sale_ids:
                return JsonResponse({'success': False, 'message': 'No sales selected'})
            
            # Restore selected sales
            count = Sales.objects.filter(id__in=sale_ids, is_archived=True).update(is_archived=False)
            
            return JsonResponse({'success': True, 'count': count})
        except Exception as e:
            return JsonResponse({'success': False, 'message': str(e)})

class SaleBulkDeleteView(View):
    def post(self, request):
        import json
        try:
            sale_ids = json.loads(request.POST.get('sale_ids', '[]'))
            if not sale_ids:
                return JsonResponse({'success': False, 'message': 'No sales selected'})
            
            # Delete selected sales
            count, _ = Sales.objects.filter(id__in=sale_ids, is_archived=True).delete()
            
            return JsonResponse({'success': True, 'count': count})
        except Exception as e:
            return JsonResponse({'success': False, 'message': str(e)})

class SalesExpensesList(ListView):
    model = Sales
    context_object_name = 'sales'
    template_name = "salesexpenses_list.html"
    paginate_by = 10

    def dispatch(self, request, *args, **kwargs):
        # Restrict to superusers only
        if not request.user.is_superuser:
            messages.error(request, " You don't have permission to access sales records.")
            return redirect('home')
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        # Exclude withdrawal-based sales (they have their own table below)
        # Withdrawal sales have "Order #" or "order #" in description
        qs = Sales.objects.filter(
            is_archived=False
        ).exclude(
            Q(description__icontains="Order #") | Q(description__icontains="order #")
        ).select_related("created_by_admin").order_by("-date")

        query = self.request.GET.get("q", "").strip()
        if query:
            qs = qs.filter(
                Q(category__icontains=query) |
                Q(amount__icontains=query) |
                Q(date__icontains=query) |
                Q(description__icontains=query) |
                Q(created_by_admin__username__icontains=query)
            )

        # --- Category filter ---
        category = self.request.GET.get("category", "").strip()
        if category:
            # Use exact match with the category value from database
            qs = qs.filter(category=category)

        # Accept 'month' parameter from JavaScript
        date_filter = self.request.GET.get("month", "").strip()
        show_all = self.request.GET.get("show_all", "").strip()
        
        # Apply month filter logic
        if show_all:
            # Show all data - no date filter
            pass
        elif date_filter:
            try:
                year_str, month_str = date_filter.split("-")
                year = int(year_str)
                month_num = int(month_str.lstrip("0"))
                qs = qs.filter(date__year=year, date__month=month_num)
            except ValueError:
                # If invalid format, default to current month
                today = timezone.now()
                qs = qs.filter(date__year=today.year, date__month=today.month)
        else:
            # No filter specified - default to current month
            today = timezone.now()
            qs = qs.filter(date__year=today.year, date__month=today.month)

        self._full_queryset = qs
        return qs.order_by('-date')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Get the filtered queryset for display (excludes withdrawal sales)
        display_qs = getattr(self, "_full_queryset", Sales.objects.all())

        # For total sales computation, include ALL sales (manual + withdrawal)
        # Apply same filters (month, category, search) but don't exclude withdrawal sales
        month = self.request.GET.get("month", "").strip()
        category = self.request.GET.get("category", "").strip()
        query = self.request.GET.get("q", "").strip()
        show_all = self.request.GET.get("show_all", "").strip()
        
        total_qs = Sales.objects.filter(is_archived=False).order_by("-date")
        
        # Apply month filter
        if show_all:
            pass
        elif month:
            try:
                year_str, month_str = month.split("-")
                year = int(year_str)
                month_num = int(month_str.lstrip("0"))
                total_qs = total_qs.filter(date__year=year, date__month=month_num)
            except ValueError:
                pass
        else:
            today = timezone.now()
            total_qs = total_qs.filter(date__year=today.year, date__month=today.month)
         # Apply category filter (only affects manual sales display, not total)
        if category:
            total_qs = total_qs.filter(category__iexact=category)
        
        # Apply search filter
        if query:
            total_qs = total_qs.filter(
                Q(category__icontains=query) |
                Q(amount__icontains=query) |
                Q(date__icontains=query) |
                Q(description__icontains=query) |
                Q(created_by_admin__username__icontains=query)
            )
        
        # Calculate MANUAL sales summary (excludes withdrawal sales)
        manual_sales_qs = Sales.objects.filter(is_archived=False).exclude(
            Q(description__icontains="Order #") | Q(description__icontains="order #")
        ).order_by("-date")
        
        # Apply same filters to manual sales
        if show_all:
            pass
        elif month:
            try:
                year_str, month_str = month.split("-")
                year = int(year_str)
                month_num = int(month_str.lstrip("0"))
                manual_sales_qs = manual_sales_qs.filter(date__year=year, date__month=month_num)
            except ValueError:
                pass
        else:
            today = timezone.now()
            manual_sales_qs = manual_sales_qs.filter(date__year=today.year, date__month=today.month)
        
        if category:
            manual_sales_qs = manual_sales_qs.filter(category__iexact=category)
        
        if query:
            manual_sales_qs = manual_sales_qs.filter(
                Q(category__icontains=query) |
                Q(amount__icontains=query) |
                Q(date__icontains=query) |
                Q(description__icontains=query) |
                Q(created_by_admin__username__icontains=query)
            )
        
        context["manual_sales_summary"] = manual_sales_qs.aggregate(
            total_sales=Sum("amount"),
            average_sales=Avg("amount"),
            sales_count=Count("id"),
        )
        
        # Calculate WITHDRAWAL sales summary (only from Sales table with "Order #")
        withdrawal_sales_qs = Sales.objects.filter(
            is_archived=False
        ).filter(
            Q(description__icontains="Order #") | Q(description__icontains="order #")
        ).order_by("-date")
        
        # Apply same month filter
        if show_all:
            pass
        elif month:
            try:
                year_str, month_str = month.split("-")
                year = int(year_str)
                month_num = int(month_str.lstrip("0"))
                withdrawal_sales_qs = withdrawal_sales_qs.filter(date__year=year, date__month=month_num)
            except ValueError:
                pass
        else:
            today = timezone.now()
            withdrawal_sales_qs = withdrawal_sales_qs.filter(date__year=today.year, date__month=today.month)
        
        context["withdrawal_sales_summary"] = withdrawal_sales_qs.aggregate(
            total_sales=Sum("amount"),
            average_sales=Avg("amount"),
            sales_count=Count("id"),
        )
        
        # Calculate TOTAL sales summary (manual + withdrawal)
        manual_total = context["manual_sales_summary"]["total_sales"] or 0
        withdrawal_total = context["withdrawal_sales_summary"]["total_sales"] or 0
        manual_count = context["manual_sales_summary"]["sales_count"] or 0
        withdrawal_count = context["withdrawal_sales_summary"]["sales_count"] or 0
        
        context["sales_summary"] = {
            'total_sales': manual_total + withdrawal_total,
            'sales_count': manual_count + withdrawal_count,
        }
        
        # Add expenses summary for combined display
        expenses_qs = Expenses.objects.filter(is_archived=False)
        
        # Get expense-specific filter parameters
        expense_category = self.request.GET.get("expense_category", "").strip()
        expense_month = self.request.GET.get("expense_month", "").strip()
        expense_show_all = self.request.GET.get("expense_show_all", "").strip()
        
        # Apply expense category filter
        if expense_category:
            expenses_qs = expenses_qs.filter(category__iexact=expense_category)
        
        # Apply expense month filter
        if expense_month:
            try:
                year_str, month_str = expense_month.split("-")
                year = int(year_str)
                month_num = int(month_str.lstrip("0"))
                expenses_qs = expenses_qs.filter(date__year=year, date__month=month_num)
            except ValueError:
                pass
        elif not expense_show_all:
            # Default to current month if no filter and not showing all
            today = timezone.now()
            expenses_qs = expenses_qs.filter(date__year=today.year, date__month=today.month)
        
        context["expenses_summary"] = expenses_qs.aggregate(
            total_expenses=Sum("amount"),
            average_expenses=Avg("amount"),
            expenses_count=Count("id"),
        )
        
        # Calculate financial loss (expired, damaged, replacement items)
        # Determine which month to calculate financial loss for
        if show_all:
            financial_loss_qs = Withdrawals.objects.filter(
                reason__in=['EXPIRED', 'DAMAGED', 'REPLACEMENT_FOR_RETURNED'],
                is_archived=False
            )
        elif month:
            try:
                year_str, month_str = month.split("-")
                year = int(year_str)
                month_num = int(month_str.lstrip("0"))
                financial_loss_qs = Withdrawals.objects.filter(
                    reason__in=['EXPIRED', 'DAMAGED', 'REPLACEMENT_FOR_RETURNED'],
                    is_archived=False,
                    date__year=year,
                    date__month=month_num
                )
            except ValueError:
                today = timezone.now()
                financial_loss_qs = Withdrawals.objects.filter(
                    reason__in=['EXPIRED', 'DAMAGED', 'REPLACEMENT_FOR_RETURNED'],
                    is_archived=False,
                    date__year=today.year,
                    date__month=today.month
                )
        else:
            today = timezone.now()
            financial_loss_qs = Withdrawals.objects.filter(
                reason__in=['EXPIRED', 'DAMAGED', 'REPLACEMENT_FOR_RETURNED'],
                is_archived=False,
                date__year=today.year,
                date__month=today.month
            )
        
        # Calculate total financial loss
        total_financial_loss = Decimal('0.00')
        for withdrawal in financial_loss_qs:
            try:
                if withdrawal.item_type == 'PRODUCT':
                    product = Products.objects.select_related('unit_price').get(id=withdrawal.item_id)
                    loss_amount = Decimal(withdrawal.quantity) * product.unit_price.unit_price
                    total_financial_loss += loss_amount
                elif withdrawal.item_type == 'RAW_MATERIAL':
                    material = RawMaterials.objects.get(id=withdrawal.item_id)
                    loss_amount = Decimal(withdrawal.quantity) * material.price_per_unit
                    total_financial_loss += loss_amount
            except (Products.DoesNotExist, RawMaterials.DoesNotExist):
                continue
        
        context["financial_loss"] = total_financial_loss
        
        # Calculate net sales (sales - financial loss)
        total_sales = context["sales_summary"]["total_sales"] or 0
        context["net_sales"] = total_sales - total_financial_loss
        
        # Calculate net profit (sales - expenses - financial loss)
        total_expenses = context["expenses_summary"]["total_expenses"] or 0
        context["net_profit"] = total_sales - total_expenses
        
        # Add expenses list for display with pagination
        from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
        
        expenses_list = expenses_qs.order_by("-date")
        expense_page = self.request.GET.get('expense_page', 1)
        expenses_paginator = Paginator(expenses_list, 10)  # 10 expenses per page
        
        try:
            expenses_page_obj = expenses_paginator.page(expense_page)
        except PageNotAnInteger:
            expenses_page_obj = expenses_paginator.page(1)
        except EmptyPage:
            expenses_page_obj = expenses_paginator.page(expenses_paginator.num_pages)
        
        context["expenses_list"] = expenses_page_obj
        context["expenses_paginator"] = expenses_paginator
        context["expenses_page_obj"] = expenses_page_obj
        context["expenses_is_paginated"] = expenses_paginator.num_pages > 1
        
        # Format categories for display (exclude withdrawal-based sales)
        raw_categories = Sales.objects.filter(
            is_archived=False
        ).exclude(
            Q(description__icontains="Order #") | Q(description__icontains="order #")
        ).values_list('category', flat=True).distinct()
        
        # Create clean list of unique categories with proper formatting
        # Convert UPPERCASE_WITH_UNDERSCORE to Title Case
        # Use a dict to ensure uniqueness by normalized display name
        categories_dict = {}
        for cat in raw_categories:
            if cat:  # Skip empty/None values
                # Replace underscores with spaces and convert to title case for display
                formatted = cat.replace('_', ' ').title()
                
                # Use the formatted display name as the key to prevent duplicates
                # This ensures "Physical Store" and "PHYSICAL_STORE" are treated as the same
                if formatted not in categories_dict:
                    # Use original category value from database (don't convert to uppercase)
                    categories_dict[formatted] = {'value': cat, 'display': formatted}
        
        # Sort by display name
        categories = sorted(categories_dict.values(), key=lambda x: x['display'])
        context['categories'] = categories

        # Format expense categories for display
        raw_expense_categories = Expenses.objects.filter(
            is_archived=False
        ).values_list('category', flat=True).distinct()
        
        # Create clean list of unique expense categories with proper formatting
        expense_categories_dict = {}
        for cat in raw_expense_categories:
            if cat:  # Skip empty/None values
                # Replace underscores with spaces and convert to title case for display
                formatted = cat.replace('_', ' ').title()
                
                if formatted not in expense_categories_dict:
                    expense_categories_dict[formatted] = {'value': cat, 'display': formatted}
        
        # Sort by display name
        expense_categories = sorted(expense_categories_dict.values(), key=lambda x: x['display'])
        context['expense_categories'] = expense_categories

        # Add withdrawal-based sales grouped by order_group_id
        # Get withdrawal-specific filter parameters
        withdrawal_channel = self.request.GET.get("withdrawal_channel", "").strip()
        withdrawal_date_filter = self.request.GET.get("withdrawal_date_filter", "").strip()
        withdrawal_payment_status = self.request.GET.get("withdrawal_payment_status", "").strip()
        withdrawal_show_all = self.request.GET.get("withdrawal_show_all", "").strip()
        
        withdrawal_sales_qs = Withdrawals.objects.filter(
            reason='SOLD',
            is_archived=False,
            sales_channel__in=['ORDER', 'CONSIGNMENT', 'RESELLER']
        ).select_related("created_by_admin").order_by("-date")
        
        # Apply channel filter
        if withdrawal_channel:
            withdrawal_sales_qs = withdrawal_sales_qs.filter(sales_channel=withdrawal_channel)
        
        # Apply payment status filter
        if withdrawal_payment_status:
            withdrawal_sales_qs = withdrawal_sales_qs.filter(payment_status=withdrawal_payment_status)
        
        # Apply month filter
        if withdrawal_show_all:
            # Show all data - no date filter
            pass
        elif withdrawal_date_filter:
            try:
                year_str, month_str = withdrawal_date_filter.split("-")
                year = int(year_str)
                month_num = int(month_str.lstrip("0"))
                withdrawal_sales_qs = withdrawal_sales_qs.filter(date__year=year, date__month=month_num)
            except ValueError:
                # If invalid format, default to current month
                today = timezone.now()
                withdrawal_sales_qs = withdrawal_sales_qs.filter(date__year=today.year, date__month=today.month)
        else:
            # Default to current month
            today = timezone.now()
            withdrawal_sales_qs = withdrawal_sales_qs.filter(date__year=today.year, date__month=today.month)
        
        # Group withdrawals by order_group_id
        from collections import defaultdict
        grouped_orders = defaultdict(list)
        for withdrawal in withdrawal_sales_qs:
            if withdrawal.order_group_id:
                grouped_orders[withdrawal.order_group_id].append(withdrawal)
            else:
                # For withdrawals without order_group_id, treat each as individual
                grouped_orders[f"single_{withdrawal.id}"].append(withdrawal)
        
        # Convert to list of dicts for template
        withdrawal_orders = []
        for group_id, withdrawals in grouped_orders.items():
            first_withdrawal = withdrawals[0]
            
            # Check if this is a real order group or a single withdrawal
            is_single = isinstance(group_id, str) and group_id.startswith('single_')
            actual_group_id = group_id if not is_single else None
            
            # Format sales channel to title case (e.g., "Order" instead of "ORDER")
            sales_channel_display = first_withdrawal.get_sales_channel_display()
            if sales_channel_display:
                sales_channel_display = sales_channel_display.title()
            
            withdrawal_orders.append({
                'group_id': group_id,
                'actual_group_id': actual_group_id,
                'is_single': is_single,
                'receipt_number': first_withdrawal.receipt_number,
                'customer_name': first_withdrawal.customer_name,
                'sales_channel': sales_channel_display,
                'payment_status': first_withdrawal.payment_status,
                'payment_status_display': first_withdrawal.get_payment_status_display() if first_withdrawal.payment_status else 'N/A',
                'paid_amount': first_withdrawal.paid_amount,
                'date': first_withdrawal.date,
                'item_count': len(withdrawals),
                'withdrawals': withdrawals,
            })
        
        # Sort withdrawal orders by date
        sorted_withdrawal_orders = sorted(withdrawal_orders, key=lambda x: x['date'], reverse=True)
        
        # Add pagination for withdrawal orders
        from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
        withdrawal_page = self.request.GET.get('withdrawal_page', 1)
        withdrawal_paginator = Paginator(sorted_withdrawal_orders, 10)  # 10 orders per page
        
        try:
            withdrawal_page_obj = withdrawal_paginator.page(withdrawal_page)
        except PageNotAnInteger:
            withdrawal_page_obj = withdrawal_paginator.page(1)
        except EmptyPage:
            withdrawal_page_obj = withdrawal_paginator.page(withdrawal_paginator.num_pages)
        
        context['withdrawal_orders'] = withdrawal_page_obj
        context['withdrawal_paginator'] = withdrawal_paginator
        context['withdrawal_page_obj'] = withdrawal_page_obj
        context['withdrawal_is_paginated'] = withdrawal_paginator.num_pages > 1
        
        # Calculate withdrawal sales totals from Sales table (same logic as the card sa taas)
        # This ensures custom prices, partial payments, and payment status changes are reflected
        withdrawal_sales_from_sales = Sales.objects.filter(
            is_archived=False
        ).filter(
            Q(description__icontains="Order #") | Q(description__icontains="order #")
        )
        
        # Apply withdrawal-specific filters
        # Filter by channel - extract from category field in Sales table
        if withdrawal_channel:
            # Sales category format: "Order - CustomerName" or "Consignment - CustomerName"
            withdrawal_sales_from_sales = withdrawal_sales_from_sales.filter(
                category__icontains=withdrawal_channel.title()
            )
        
        # Filter by date
        if withdrawal_show_all:
            pass
        elif withdrawal_date_filter:
            try:
                year_str, month_str = withdrawal_date_filter.split("-")
                year = int(year_str)
                month_num = int(month_str.lstrip("0"))
                withdrawal_sales_from_sales = withdrawal_sales_from_sales.filter(date__year=year, date__month=month_num)
            except ValueError:
                today = timezone.now()
                withdrawal_sales_from_sales = withdrawal_sales_from_sales.filter(date__year=today.year, date__month=today.month)
        else:
            today = timezone.now()
            withdrawal_sales_from_sales = withdrawal_sales_from_sales.filter(date__year=today.year, date__month=today.month)
        
        # Sum the sales amounts (this includes custom prices, partial payments, final payments)
        withdrawal_sales_agg = withdrawal_sales_from_sales.aggregate(
            total=Sum('amount'),
            count=Count('id')
        )
        
        context['withdrawal_sales_total'] = withdrawal_sales_agg['total'] or 0
        context['withdrawal_sales_count'] = withdrawal_sales_agg['count'] or 0
        
        # Add available sales channels for the filter dropdown (only channels that exist in data)
        # Get unique channels from actual withdrawal sales records
        existing_channels = Withdrawals.objects.filter(
            reason='SOLD',
            is_archived=False,
            sales_channel__in=['ORDER', 'CONSIGNMENT', 'RESELLER']
        ).values_list('sales_channel', flat=True).distinct().order_by('sales_channel')
        context['channels'] = list(existing_channels)
        
        # Add current month value for default display
        today = timezone.now()
        context['current_month_value'] = today.strftime("%Y-%m")

        return context


class SalesCreateView(CreateView):
    model = Sales
    form_class = SalesForm
    template_name = 'sales_add.html'
    success_url = reverse_lazy('salesexpenses')

    @transaction.atomic
    def form_valid(self, form):
        try:
            auth_user = AuthUser.objects.get(id=self.request.user.id)
            form.instance.created_by_admin = auth_user
            self.object = form.save()
        except Exception as e:
            transaction.set_rollback(True)
            messages.error(self.request, f"Sale creation failed: {e}")
            return redirect(self.request.path)
        messages.success(self.request, "✅ Sale recorded successfully.")
        return redirect(self.success_url)

    def form_invalid(self, form):
        messages.error(self.request, "Please complete all required fields. The form was reset.")
        return redirect(self.request.path) 

class SalesUpdateView(UpdateView):
    model = Sales
    form_class = SalesForm
    template_name = 'sales_edit.html'
    success_url = reverse_lazy('salesexpenses')

    def form_valid(self, form):
        # Set current user ID for database trigger
        auth_user = AuthUser.objects.get(id=self.request.user.id)
        from django.db import connection
        with connection.cursor() as cursor:
            cursor.execute("SET LOCAL app.current_user_id = %s", [auth_user.id])
        
        response = super().form_valid(form)
        
        messages.success(self.request, "✏️ Sale updated successfully.")
        return response

class SalesDeleteView(DeleteView):
    model = Sales
    success_url = reverse_lazy('salesexpenses')

    def dispatch(self, request, *args, **kwargs):
        # Restrict to superusers only
        if not request.user.is_superuser:
            messages.error(request, "❌ You don't have permission to delete sales records.")
            return redirect('salesexpenses')
        return super().dispatch(request, *args, **kwargs)

    def get_success_url(self):
        messages.success(self.request, "🗑️ Sale deleted successfully.")
        return super().get_success_url()


# Withdrawal Order Views
class WithdrawalOrderDetailView(View):
    """View details of a withdrawal order (grouped withdrawals)"""
    template_name = "withdrawal_order_detail.html"
    
    def get(self, request, order_group_id):
        withdrawals = Withdrawals.objects.filter(
            order_group_id=order_group_id,
            is_archived=False
        ).select_related('created_by_admin').order_by('id')
        
        if not withdrawals.exists():
            messages.error(request, "Order not found.")
            return redirect('salesexpenses')
        
        first_withdrawal = withdrawals.first()
        
        # Calculate total amount and add subtotals to each withdrawal
        total_amount = Decimal(0)
        withdrawal_list = []
        
        # Check if this order was created with prices (during withdrawal) or will be priced later (during payment update)
        # If any withdrawal has price_type or custom_price, it was priced during withdrawal
        # Otherwise, pricing happens during payment update
        has_initial_pricing = any(w.price_type or w.custom_price for w in withdrawals)
        has_custom_price = any(w.custom_price for w in withdrawals)
        
        # For PARTIAL payment, paid_amount is the TOTAL for the order, not per item
        is_partial = first_withdrawal.payment_status == 'PARTIAL'
        partial_amount_added = False
        
        # For custom price or no initial pricing, get total from Sales table
        if has_custom_price or not has_initial_pricing:
            if first_withdrawal.payment_status in ['PAID', 'PARTIAL']:
                # Get all sales entries for this order (case-insensitive search)
                sales_entries_list = Sales.objects.filter(
                    is_archived=False
                ).filter(
                    Q(description__icontains=f"Order #{order_group_id}") | 
                    Q(description__icontains=f"order #{order_group_id}")
                )
                
                total_sum = sales_entries_list.aggregate(total=Sum('amount'))['total']
                if total_sum:
                    total_amount = total_sum
                    partial_amount_added = True
        
        for withdrawal in withdrawals:
            subtotal = None
            unit_price = None
            price_type_display = None
            
            if withdrawal.payment_status == 'PAID':
                if has_initial_pricing:
                    # Order was created with prices - show individual item prices
                    if withdrawal.custom_price:
                        # Custom price - don't show individual subtotals
                        # The total will be fetched from Sales table
                        subtotal = None
                        unit_price = None
                        price_type_display = "Custom Price"
                    elif withdrawal.price_type:
                        if withdrawal.total_amount is not None and withdrawal.final_price_per_unit is not None:
                            unit_price = withdrawal.final_price_per_unit
                            subtotal = withdrawal.total_amount
                            price_type_display = "Unit Price" if withdrawal.price_type == 'UNIT' else "SRP Price"
                        else:
                            product = Products.objects.get(id=withdrawal.item_id)
                            if withdrawal.price_type == 'UNIT':
                                unit_price = product.unit_price.unit_price
                                subtotal = Decimal(withdrawal.quantity) * unit_price
                                price_type_display = "Unit Price"
                            elif withdrawal.price_type == 'SRP':
                                unit_price = product.srp_price.srp_price
                                subtotal = Decimal(withdrawal.quantity) * unit_price
                                price_type_display = "SRP Price"
                    if subtotal:
                        total_amount += subtotal
                else:
                    # Order was created as UNPAID, then updated to PAID with total amount
                    # Don't show individual prices, just show total at the end
                    subtotal = None
                    unit_price = None
                    price_type_display = None
                    # Get total from Sales table for this order
                    if not partial_amount_added:
                        sales_entries = Sales.objects.filter(
                            description__contains=f"order #{order_group_id}",
                            is_archived=False
                        ).aggregate(total=Sum('amount'))
                        if sales_entries['total']:
                            total_amount = sales_entries['total']
                        partial_amount_added = True
            elif withdrawal.payment_status == 'PARTIAL':
                # For partial, paid_amount is the TOTAL for the entire order
                if withdrawal.paid_amount and not partial_amount_added:
                    total_amount = Decimal(withdrawal.paid_amount)
                    partial_amount_added = True
                # Don't show individual prices
                subtotal = None
                price_type_display = None
            else:  # UNPAID
                subtotal = None
                price_type_display = None
            
            # Add attributes to the withdrawal object
            withdrawal.subtotal = subtotal
            withdrawal.unit_price_display = unit_price
            withdrawal.price_type_display = price_type_display
            withdrawal_list.append(withdrawal)
        
        # Get payment history from Sales table
        payment_history = []
        if order_group_id:
            sales_payments = Sales.objects.filter(
                is_archived=False
            ).filter(
                Q(description__icontains=f"Order #{order_group_id}") | 
                Q(description__icontains=f"order #{order_group_id}")
            ).order_by('date')
            
            payment_count = 0
            for payment in sales_payments:
                
                if 'Status: PARTIAL' in payment.description or 'Partial payment' in payment.description:
                    payment_count += 1
                    payment_history.append({
                        'label': f'1st Payment (Partial)',
                        'amount': payment.amount
                    })
                elif 'Final payment' in payment.description:
                    payment_count += 1
                    payment_history.append({
                        'label': f'2nd Payment (Final)',
                        'amount': payment.amount
                    })
                elif 'Status: PAID' in payment.description or 'Payment received' in payment.description:
                    payment_count += 1
                    payment_history.append({
                        'label': f'Payment',
                        'amount': payment.amount
                    })
                else:
                    payment_count += 1
                    payment_history.append({
                        'label': f'Payment #{payment_count}',
                        'amount': payment.amount
                    })
        
        context = {
            'order_group_id': order_group_id,
            'customer_name': first_withdrawal.customer_name,
            'sales_channel': first_withdrawal.get_sales_channel_display(),
            'payment_status': first_withdrawal.payment_status,
            'payment_status_display': first_withdrawal.get_payment_status_display(),
            'date': first_withdrawal.date,
            'withdrawals': withdrawal_list,
            'total_amount': total_amount,
            'payment_history': payment_history,
        }
        
        return render(request, self.template_name, context)


class WithdrawalOrderUpdatePaymentView(View):
    """Update payment status of a withdrawal order"""
    
    def post(self, request, order_group_id):
        new_payment_status = request.POST.get('payment_status')
        paid_amount = request.POST.get('paid_amount')
        total_price = request.POST.get('total_price')
        
        if new_payment_status not in ['PAID', 'UNPAID', 'PARTIAL']:
            messages.error(request, "Invalid payment status.")
            return redirect('withdrawal-order-detail', order_group_id=order_group_id)
        
        withdrawals = Withdrawals.objects.filter(
            order_group_id=order_group_id,
            is_archived=False
        )
        
        if not withdrawals.exists():
            messages.error(request, "Order not found.")
            return redirect('salesexpenses')
        
        # Determine the amount for sales entry
        sales_amount = Decimal(0)
        
        if new_payment_status == 'PAID':
            # Use the total_price entered by user
            if total_price:
                try:
                    sales_amount = Decimal(total_price)
                except (ValueError, InvalidOperation):
                    messages.error(request, "Invalid total price.")
                    return redirect('withdrawal-order-detail', order_group_id=order_group_id)
            else:
                messages.error(request, "Please enter the total price paid.")
                return redirect('withdrawal-order-detail', order_group_id=order_group_id)
        elif new_payment_status == 'PARTIAL':
            # Use the partial paid_amount
            if paid_amount:
                try:
                    sales_amount = Decimal(paid_amount)
                except (ValueError, InvalidOperation):
                    messages.error(request, "Invalid paid amount.")
                    return redirect('withdrawal-order-detail', order_group_id=order_group_id)
            else:
                messages.error(request, "Please enter the partial amount paid.")
                return redirect('withdrawal-order-detail', order_group_id=order_group_id)
        
        # Check if transitioning from PARTIAL to PAID
        old_payment_status = withdrawals.first().payment_status
        previous_partial_amount = Decimal(0)
        
        if old_payment_status == 'PARTIAL' and withdrawals.first().paid_amount:
            previous_partial_amount = Decimal(withdrawals.first().paid_amount)
        
        # Update all withdrawals in the order
        for withdrawal in withdrawals:
            withdrawal.payment_status = new_payment_status
            
            if new_payment_status == 'PARTIAL':
                # Store the total paid amount (same for all withdrawals in the order)
                withdrawal.paid_amount = sales_amount
            elif new_payment_status == 'PAID':
                withdrawal.paid_amount = None
                # Don't set custom_price - let the detail view fetch from Sales table
            else:  # UNPAID
                withdrawal.paid_amount = None
            
            withdrawal.save()
        
        # Create our consolidated sales entry based on payment status
        # Get AuthUser instance from request.user
        from .models import AuthUser
        auth_user = AuthUser.objects.get(id=request.user.id)
        
        if new_payment_status == 'PAID':
            # Add full amount to sales
            if previous_partial_amount > 0:
                description = f"Final payment for order #{order_group_id} (Previous: ₱{previous_partial_amount:,.2f}, Additional: ₱{sales_amount:,.2f}, Total: ₱{previous_partial_amount + sales_amount:,.2f})"
                success_msg = f"✅ Order marked as PAID. ₱{sales_amount:,.2f} added to sales. Total paid: ₱{previous_partial_amount + sales_amount:,.2f}"
            else:
                description = f"Payment received for order #{order_group_id}"
                success_msg = f"✅ Order marked as PAID. ₱{sales_amount:,.2f} added to sales."
            
            Sales.objects.create(
                category=f"{withdrawals.first().get_sales_channel_display()} - {withdrawals.first().customer_name}",
                amount=sales_amount,
                date=timezone.now().date(),
                description=description,
                created_by_admin=auth_user
            )
            # print(f"PAID Sales entry created: Amount=P{sales_amount}, Date={timezone.now().date()}")
            messages.success(request, success_msg)
        elif new_payment_status == 'PARTIAL':
            # Add partial amount to sales
            Sales.objects.create(
                category=f"{withdrawals.first().get_sales_channel_display()} - {withdrawals.first().customer_name}",
                amount=sales_amount,
                date=timezone.now().date(),
                description=f"Partial payment for order #{order_group_id}",
                created_by_admin=auth_user
            )
            # print(f"PARTIAL Sales entry created: Amount=P{sales_amount}, Date={timezone.now().date()}")
            messages.success(request, f"✅ Partial payment recorded. ₱{sales_amount:,.2f} added to sales.")
        else:  # UNPAID
            messages.success(request, "✅ Order marked as UNPAID. No sales recorded.")
        
        return redirect('salesexpenses')


class ExpenseArchiveView(View):
    def post(self, request, pk):
        expense = get_object_or_404(Expenses, pk=pk)
        
        # Set current user for trigger
        from django.db import connection
        with connection.cursor() as cursor:
            cursor.execute("SET LOCAL app.current_user_id = %s", [request.user.id])
        
        expense.is_archived = True
        expense.save()  # Trigger will handle logging
        
        messages.success(request, "✅ Expense archived successfully.")
        return redirect('salesexpenses')

class ExpenseArchiveOldView(View):
    def post(self, request):
        one_year_ago = timezone.now() - timedelta(days=365)
        Expenses.objects.filter(is_archived=False, date__lt=one_year_ago).update(is_archived=True)
        messages.success(request, " Old expenses archived successfully.")
        return redirect('salesexpenses')

@require_http_methods(["POST"])
def expenses_bulk_delete(request):
    try:
        ids = request.POST.get('ids', '').split(',')
        ids = [int(id.strip()) for id in ids if id.strip()]
        
        if not ids:
            return JsonResponse({'success': False, 'message': 'No expenses selected'})
        
        deleted_count = Expenses.objects.filter(id__in=ids).delete()[0]
        return JsonResponse({
            'success': True,
            'message': f'Successfully deleted {deleted_count} expense(s)'
        })
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)})

@require_http_methods(["POST"])
def expenses_bulk_archive(request):
    try:
        ids = request.POST.get('ids', '').split(',')
        ids = [int(id.strip()) for id in ids if id.strip()]
        
        if not ids:
            return JsonResponse({'success': False, 'message': 'No expenses selected'})
        
        archived_count = Expenses.objects.filter(id__in=ids).update(is_archived=True)
        return JsonResponse({
            'success': True,
            'message': f'Successfully archived {archived_count} expense(s)'
        })
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)})

class ArchivedExpensesListView(ListView):
    model = Expenses
    template_name = 'archived_expenses.html'
    context_object_name = 'object_list'
    paginate_by = 10

    def get_queryset(self):
        return Expenses.objects.filter(is_archived=True).order_by('-date')

class ExpenseUnarchiveView(View):
    def post(self, request, pk):
        expense = get_object_or_404(Expenses, pk=pk)
        
        # Set current user for trigger
        from django.db import connection
        with connection.cursor() as cursor:
            cursor.execute("SET LOCAL app.current_user_id = %s", [request.user.id])
        
        expense.is_archived = False
        expense.save()  # Trigger will handle logging
        
        messages.success(request, "✅ Expense restored successfully.")
        return redirect('salesexpense-archive')

class ExpenseBulkRestoreView(View):
    def post(self, request):
        import json
        try:
            expense_ids = json.loads(request.POST.get('expense_ids', '[]'))
            if not expense_ids:
                return JsonResponse({'success': False, 'message': 'No expenses selected'})
            
            # Set current user for trigger
            from django.db import connection
            with connection.cursor() as cursor:
                cursor.execute("SET LOCAL app.current_user_id = %s", [request.user.id])
            
            # Restore selected expenses
            count = Expenses.objects.filter(id__in=expense_ids, is_archived=True).update(is_archived=False)
            
            return JsonResponse({'success': True, 'count': count})
        except Exception as e:
            return JsonResponse({'success': False, 'message': str(e)})

class ExpenseBulkDeleteView(View):
    def post(self, request):
        import json
        try:
            expense_ids = json.loads(request.POST.get('expense_ids', '[]'))
            if not expense_ids:
                return JsonResponse({'success': False, 'message': 'No expenses selected'})
            
            # Delete selected expenses
            count, _ = Expenses.objects.filter(id__in=expense_ids, is_archived=True).delete()
            
            return JsonResponse({'success': True, 'count': count})
        except Exception as e:
            return JsonResponse({'success': False, 'message': str(e)})

class ExpensesCreateView(CreateView):
    model = Expenses
    form_class = ExpensesForm
    template_name = 'expenses_add.html'
    success_url = reverse_lazy('salesexpenses')

    @transaction.atomic
    def form_valid(self, form):
        try:
            auth_user = AuthUser.objects.get(id=self.request.user.id)
            form.instance.created_by_admin = auth_user
            self.object = form.save()
        except Exception as e:
            transaction.set_rollback(True)
            messages.error(self.request, f"Expense creation failed: {e}")
            return redirect(self.request.path)  # reset form
        messages.success(self.request, "✅ Expense recorded successfully.")
        return redirect(self.success_url)

    def form_invalid(self, form):
        messages.error(self.request, "Please complete all required fields. The form was reset.")
        return redirect(self.request.path)  # reset form


class ExpensesUpdateView(UpdateView):
    model = Expenses
    form_class = ExpensesForm
    template_name = 'expenses_edit.html'
    success_url = reverse_lazy('salesexpenses')

    def form_valid(self, form):
        # Set current user ID for database trigger
        auth_user = AuthUser.objects.get(id=self.request.user.id)
        from django.db import connection
        with connection.cursor() as cursor:
            cursor.execute("SET LOCAL app.current_user_id = %s", [auth_user.id])
        
        response = super().form_valid(form)
        
        messages.success(self.request, "✏️ Expense updated successfully.")
        return response

class ExpensesDeleteView(LoginRequiredMixin, DeleteView):
    model = Expenses
    success_url = reverse_lazy('salesexpenses')

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_superuser:
            messages.error(request, "❌ You don't have permission to delete expense records.")
            return redirect('expenses')
        return super().dispatch(request, *args, **kwargs)


    def get_success_url(self):
        messages.success(self.request, "🗑️ Expense deleted successfully.")
        return super().get_success_url()


class SalesExpensesCreateView(View):
    """View for creating both sales and expenses together"""
    template_name = 'sales_expenses_add.html'
    
    def get(self, request):
        form = SalesExpensesForm()
        return render(request, self.template_name, {'form': form})
    
    @transaction.atomic
    def post(self, request):
        form = SalesExpensesForm(request.POST)
        
        if form.is_valid():
            try:
                auth_user = AuthUser.objects.get(id=request.user.id)
                
                # Create Sales record
                sales = Sales.objects.create(
                    category=form.cleaned_data['sales_category'],
                    amount=form.cleaned_data['sales_amount'],
                    date=form.cleaned_data['date'],
                    description=form.cleaned_data['sales_description'] or '',
                    created_by_admin=auth_user,
                    is_archived=False
                )
                
                # Create Expenses record with "Sales-related expenses" as category
                expenses = Expenses.objects.create(
                    category=f"Expenses for {form.cleaned_data['sales_category']}",
                    amount=form.cleaned_data['total_expenses'],
                    date=form.cleaned_data['date'],
                    description=form.cleaned_data['expenses_description'] or 'Auto-generated from sales entry',
                    created_by_admin=auth_user,
                    is_archived=False
                )
                
                # Calculate profit
                profit = form.cleaned_data['sales_amount'] - form.cleaned_data['total_expenses']
                
                messages.success(
                    request, 
                    f"✅ Sales & Expenses recorded successfully! Net Profit: ₱{profit:,.2f}"
                )
                return redirect('salesexpenses')
                
            except Exception as e:
                messages.error(request, f"Failed to create sales & expenses: {e}")
                return render(request, self.template_name, {'form': form})
        else:
            messages.error(request, "Please correct the errors below.")
            return render(request, self.template_name, {'form': form})


class ProductBatchList(ListView):
    model = ProductBatches
    context_object_name = 'product_batch'
    template_name = "prodbatch_list.html"
    paginate_by = 10

    def get_queryset(self):
        queryset = (
            super()
            .get_queryset()
            .select_related("product", "created_by_admin")
            .filter(is_archived=False)
        )
        
        search = self.request.GET.get("search", "").strip()
        date_filter = self.request.GET.get("date_filter", "").strip()
        show_all = self.request.GET.get("show_all", "").strip()

        if search:
            queryset = queryset.filter(
                Q(product__product_type__name__icontains=search) |
                Q(product__variant__name__icontains=search) |
                Q(product__size__size_label__icontains=search)
            )

        if date_filter:
            try:
                parsed_date = datetime.strptime(date_filter, "%Y-%m")
                queryset = queryset.filter(
                    batch_date__year=parsed_date.year,
                    batch_date__month=parsed_date.month
                )
            except ValueError:
                pass
        elif not show_all:
            # Default: show only current month
            today = timezone.now()
            queryset = queryset.filter(
                batch_date__year=today.year,
                batch_date__month=today.month
            )

        # 🔥 Sort newest batches first, breaking ties by latest created record
        return queryset.order_by('-batch_date', '-id')

        
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        today = timezone.now()
        month_names = ["January", "February", "March", "April", "May", "June",
                      "July", "August", "September", "October", "November", "December"]
        context['current_month_display'] = f"{month_names[today.month - 1]} {today.year}"
        context['current_month_value'] = today.strftime("%Y-%m")
        return context
    

class ProductBatchCreateView(CreateView):
    model = ProductBatches
    form_class = ProductBatchForm
    template_name = 'prodbatch_add.html'
    success_url = reverse_lazy('product-batch')
    
    def form_valid(self, form):
        auth_user = AuthUser.objects.get(id=self.request.user.id)
        form.instance.created_by_admin = auth_user
        response = super().form_valid(form)
        
        # Note: Product inventory and original_quantity are updated by database triggers
        messages.success(self.request, "✅ Product Batch created successfully.")
        return response

class ProductBatchUpdateView(UpdateView):
    model = ProductBatches
    form_class = ProductBatchForm
    template_name = 'prodbatch_edit.html'
    success_url = reverse_lazy('product-batch')

    def form_valid(self, form):
        # Capture old values before the save
        old_obj = self.get_object()
        old_quantity = old_obj.quantity
        old_original_quantity = old_obj.original_quantity

        auth_user = AuthUser.objects.get(id=self.request.user.id)
        form.instance.created_by_admin = auth_user

        # Update original_quantity to reflect the manual edit
        new_quantity = form.cleaned_data['quantity']
        if old_original_quantity is None or old_quantity >= old_original_quantity:
            # No prior deductions (or already-broken state): original matches new quantity
            form.instance.original_quantity = new_quantity
        else:
            # Partially deducted: adjust original by the same delta to preserve deducted amount
            form.instance.original_quantity = old_original_quantity + (new_quantity - old_quantity)

        response = super().form_valid(form)
        
        # Note: Product inventory is updated by database trigger log_product_batches_update
        messages.success(self.request, "✅ Product Batch updated successfully.")
        return response

    def form_invalid(self, form):
        return super().form_invalid(form)


class ProductBatchDeleteView(DeleteView):
    model = ProductBatches
    success_url = reverse_lazy("product-batch")

    def dispatch(self, request, *args, **kwargs):
        # Restrict to superusers only
        if not request.user.is_superuser:
            messages.error(request, "❌ You don't have permission to delete product batches.")
            return redirect('product-batch')
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        # Trigger trg_handle_packaging_stock_batches_delete handles packaging stock restoration automatically
        return super().form_valid(form)

    def get_success_url(self):
        messages.success(self.request, "🗑️ Product Batch deleted successfully.")
        return super().get_success_url()


class ProductBatchArchiveView(View):
    def post(self, request, pk):
        batch = get_object_or_404(ProductBatches, pk=pk)
        
        # Set current user for trigger
        from django.db import connection
        with connection.cursor() as cursor:
            cursor.execute("SET LOCAL app.current_user_id = %s", [request.user.id])
        
        batch.is_archived = True
        batch.save()  # Trigger will handle logging
        
        messages.success(request, "📦 Product Batch archived successfully.")
        page = request.GET.get('page')
        if page:
            return redirect(f"{reverse('product-batch')}?page={page}")
        return redirect('product-batch')


class ArchivedProductBatchListView(ListView):
    model = ProductBatches
    template_name = 'archived_product_batch.html'
    context_object_name = 'object_list'
    paginate_by = 10

    def get_queryset(self):
        return ProductBatches.objects.filter(is_archived=True).select_related('product', 'created_by_admin').order_by('-batch_date')


class ProductBatchUnarchiveView(View):
    def post(self, request, pk):
        batch = get_object_or_404(ProductBatches, pk=pk)
        
        # Set current user for trigger
        from django.db import connection
        with connection.cursor() as cursor:
            cursor.execute("SET LOCAL app.current_user_id = %s", [request.user.id])
        
        batch.is_archived = False
        batch.save()  # Trigger will handle logging
        
        messages.success(request, "✅ Product Batch restored successfully.")
        return redirect('product-batch-archived-list')


class ProductBatchArchiveOldView(View):
    def post(self, request):
        from datetime import timedelta
        one_year_ago = timezone.now() - timedelta(days=365)
        # Note: Database triggers will automatically create history logs
        archived_count = ProductBatches.objects.filter(is_archived=False, batch_date__lt=one_year_ago).update(is_archived=True)
        messages.success(request, f"📦 {archived_count} product batch(es) older than 1 year have been archived.")
        return redirect('product-batch')

@require_http_methods(["POST"])
def product_batch_bulk_delete(request):
    try:
        ids = request.POST.get('ids', '').split(',')
        ids = [int(id.strip()) for id in ids if id.strip()]

        if not ids:
            return JsonResponse({'success': False, 'message': 'No batches selected'})

        # Trigger trg_handle_packaging_stock_batches_delete handles packaging stock restoration automatically
        deleted_count = ProductBatches.objects.filter(id__in=ids).delete()[0]
        return JsonResponse({
            'success': True,
            'message': f'Successfully deleted {deleted_count} batch(es)'
        })
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)})

@require_http_methods(["POST"])
def product_batch_bulk_archive(request):
    try:
        ids = request.POST.get('ids', '').split(',')
        ids = [int(id.strip()) for id in ids if id.strip()]
        
        if not ids:
            return JsonResponse({'success': False, 'message': 'No batches selected'})
        
        # Set current user for trigger
        from django.db import connection
        with connection.cursor() as cursor:
            cursor.execute("SET LOCAL app.current_user_id = %s", [request.user.id])
        
        # Update will trigger database triggers for each batch
        archived_count = ProductBatches.objects.filter(id__in=ids).update(is_archived=True)
        
        return JsonResponse({
            'success': True,
            'message': f'Successfully archived {archived_count} batch(es)'
        })
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)})

@require_http_methods(["POST"])
def product_batch_bulk_restore(request):
    try:
        ids = request.POST.get('ids', '').split(',')
        ids = [int(id.strip()) for id in ids if id.strip()]
        
        if not ids:
            return JsonResponse({'success': False, 'message': 'No batches selected'})
        
        # Set current user for trigger
        from django.db import connection
        with connection.cursor() as cursor:
            cursor.execute("SET LOCAL app.current_user_id = %s", [request.user.id])
        
        # Update will trigger database triggers for each batch
        restored_count = ProductBatches.objects.filter(id__in=ids).update(is_archived=False)
        
        return JsonResponse({
            'success': True,
            'message': f'Successfully restored {restored_count} batch(es)'
        })
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)})

class ProductInventoryList(ListView):
    model = ProductInventory
    context_object_name = 'product_inventory'
    template_name = "prodinvent_list.html"
    paginate_by = 10

    def get_queryset(self):
        # Filter out archived products and their inventory
        queryset = super().get_queryset().select_related(
            "product",
            "product__product_type",
            "product__variant",
            "product__size",
            "product__size_unit",
        ).filter(product__is_archived=False)

        # Unified search field for Product Type, Variant, and Size
        search = self.request.GET.get("search", "").strip()
        if search:
            queryset = queryset.filter(
                Q(product__product_type__name__icontains=search) |
                Q(product__variant__name__icontains=search) |
                Q(product__size__size_label__icontains=search)
            )

        return queryset.order_by("product_id")
    
    def filter_by_reorder_status(self, queryset, status):
        """Filter inventory based on reorder status considering expiration dates."""
        if not status:
            return queryset
        
        filtered_items = []
        for inv in queryset:
            reorder_status = inv.get_reorder_status()
            available_stock = reorder_status['available_stock']
            threshold = inv.restock_threshold
            
            if status == "on_stock" and available_stock > threshold:
                filtered_items.append(inv.product_id)
            elif status == "low_stock" and available_stock < threshold and available_stock > 0:
                filtered_items.append(inv.product_id)
            elif status == "warning" and available_stock == threshold:
                filtered_items.append(inv.product_id)
            elif status == "out_of_stock" and available_stock == 0:
                filtered_items.append(inv.product_id)
        
        return queryset.filter(product_id__in=filtered_items) if filtered_items else queryset.none()
    
    def get_context_data(self, **kwargs):
        from django.db.models import Sum
        from django.core.paginator import Paginator
        context = super().get_context_data(**kwargs)
        
        # Apply status filter if provided
        status = self.request.GET.get("status", "")
        if status:
            filtered_queryset = self.filter_by_reorder_status(self.get_queryset(), status)
            paginator = Paginator(filtered_queryset, self.paginate_by)
            page_number = self.request.GET.get('page', 1)
            page_obj = paginator.get_page(page_number)
            context['product_inventory'] = page_obj
            context['paginator'] = paginator
            context['is_paginated'] = paginator.num_pages > 1
            context['page_obj'] = page_obj
        
        # Add reorder status data for each inventory item
        inventory_list = context.get('product_inventory', [])
        if hasattr(inventory_list, 'object_list'):
            inventory_list = inventory_list.object_list
        
        # Ensure reorder_status is added to ALL items
        for inv in inventory_list:
            if not hasattr(inv, 'reorder_status') or inv.reorder_status is None:
                inv.reorder_status = inv.get_reorder_status()
            
            # Get packaging information and stock from batches
            batches = ProductBatches.objects.filter(
                product=inv.product,
                is_archived=False
            ).select_related('packaging')

            packaging_stock = {}
            packaging_expiring = {}
            packaging_list = []

            from django.utils import timezone
            today = timezone.localdate()
            expiration_cutoff = today + timezone.timedelta(days=7)

            for batch in batches:
                if batch.packaging:
                    packaging_name = batch.packaging.name.title()
                    if batch.packaging.size and batch.packaging.unit:
                        unit_name = batch.packaging.unit.unit_name if hasattr(batch.packaging.unit, 'unit_name') else str(batch.packaging.unit)
                        packaging_name = f"{packaging_name} ({batch.packaging.size} {unit_name})"

                    # Include expiration date in key to keep batches separate
                    exp_date_str = batch.expiration_date.strftime('%Y-%m-%d') if batch.expiration_date else 'No Date'
                    packaging_key = f"{packaging_name}|{exp_date_str}|{batch.id}"

                    # Track total stock per packaging + expiration date combination
                    if packaging_key not in packaging_stock:
                        packaging_stock[packaging_key] = 0
                    packaging_stock[packaging_key] += batch.quantity

                    # Track expiring stock per packaging + expiration date combination
                    if (batch.expiration_date and
                        batch.expiration_date <= expiration_cutoff and
                        batch.expiration_date >= today and
                        batch.quantity > 0):
                        if packaging_key not in packaging_expiring:
                            packaging_expiring[packaging_key] = 0
                        packaging_expiring[packaging_key] += batch.quantity

                    if packaging_key not in packaging_list:
                        packaging_list.append(packaging_key)

            # Create formatted packaging stock breakdown with expiration status
            packaging_breakdown = []
            for packaging_key in packaging_list:
                stock_qty = packaging_stock.get(packaging_key, 0)
                expiring_qty = packaging_expiring.get(packaging_key, 0)
                packaging_name, exp_date_str, batch_id = packaging_key.split('|')
                packaging_breakdown.append({
                    'name': packaging_name,
                    'stock': stock_qty,
                    'expiring': expiring_qty,
                    'expiration_date': exp_date_str
                })

            inv.packaging_used = ', '.join(packaging_list) if packaging_list else None
            inv.packaging_stock_breakdown = packaging_breakdown
        
        # Calculate total stock across all non-archived products
        total_stock = ProductInventory.objects.filter(
            product__is_archived=False
        ).aggregate(total=Sum('total_stock'))['total'] or 0
        context['total_product_stock'] = total_stock
        return context


class RawMaterialBatchList(ListView):
    model = RawMaterialBatches
    context_object_name = 'rawmatbatch'
    template_name = "rawmatbatch_list.html"
    paginate_by = 10

    def get_queryset(self):
        queryset = (
            super()
            .get_queryset()
            .select_related("material", "created_by_admin")
            .filter(is_archived=False)
            .order_by('-batch_date')
        )

        query = self.request.GET.get("q", "").strip()
        date_filter = self.request.GET.get("date_filter", "").strip()
        show_all = self.request.GET.get("show_all", "").strip()

        if query:
            queryset = queryset.filter(
                Q(material__name__icontains=query) |
                Q(batch_date__icontains=query) |
                Q(received_date__icontains=query) |
                Q(quantity__icontains=query) |
                Q(expiration_date__icontains=query) |
                Q(created_by_admin__username__icontains=query)
            )

        if date_filter:
            try:
                # Parse only year and month (from YYYY-MM)
                parsed_date = datetime.strptime(date_filter, "%Y-%m")
                queryset = queryset.filter(batch_date__year=parsed_date.year, batch_date__month=parsed_date.month)
            except ValueError:
                pass
        elif not show_all:
            today = timezone.now()
            queryset = queryset.filter(batch_date__year=today.year, batch_date__month=today.month)

        return queryset
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = timezone.now()
        month_names = ["January", "February", "March", "April", "May", "June",
                      "July", "August", "September", "October", "November", "December"]
        context['current_month_display'] = f"{month_names[today.month - 1]} {today.year}"
        context['current_month_value'] = today.strftime("%Y-%m")
        return context


class RawMaterialBatchCreateView(CreateView):
    model = RawMaterialBatches
    form_class = RawMaterialBatchForm
    template_name = 'rawmatbatch_add.html'
    success_url = reverse_lazy('rawmaterial-batch')

    def form_valid(self, form):
        auth_user = AuthUser.objects.get(id=self.request.user.id)
        form.instance.created_by_admin = auth_user
        messages.success(self.request, "✅ Packaging batch created successfully.")
        return super().form_valid(form)  

class RawMaterialBatchUpdateView(UpdateView):
    model = RawMaterialBatches
    form_class = RawMaterialBatchForm
    template_name = 'rawmatbatch_edit.html'
    success_url = reverse_lazy('rawmaterial-batch')

    def form_valid(self, form):
        # Capture old values before the save
        old_obj = self.get_object()
        old_quantity = old_obj.quantity
        old_original_quantity = old_obj.original_quantity

        auth_user = AuthUser.objects.get(id=self.request.user.id)
        form.instance.created_by_admin = auth_user

        # Update original_quantity to reflect the manual edit
        new_quantity = form.cleaned_data['quantity']
        if old_original_quantity is None or old_quantity >= old_original_quantity:
            # No prior deductions (or already-broken state): original matches new quantity
            form.instance.original_quantity = new_quantity
        else:
            # Partially deducted: adjust original by the same delta to preserve deducted amount
            form.instance.original_quantity = old_original_quantity + (new_quantity - old_quantity)

        messages.success(self.request, "✅ Packaging batch updated successfully.")
        return super().form_valid(form)
    
class RawMaterialBatchDeleteView(LoginRequiredMixin, DeleteView):
    model = RawMaterialBatches
    success_url = reverse_lazy('rawmaterial-batch')

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_superuser:
            messages.error(request, "❌ You don't have permission to delete product batches.")
            return redirect('rawmaterial-batch')
        return super().dispatch(request, *args, **kwargs)

    def delete(self, request, *args, **kwargs):
        batch = self.get_object()
        material = batch.material
        quantity = batch.quantity
        
        # Delete the batch first
        result = super().delete(request, *args, **kwargs)
        
        # Update the inventory total_stock
        try:
            inventory = RawMaterialInventory.objects.get(material=material)
            inventory.total_stock = max(0, inventory.total_stock - quantity)
            inventory.save()
        except RawMaterialInventory.DoesNotExist:
            pass
        
        messages.success(request, "✅ Packaging batch deleted successfully.")
        return result


class RawMaterialBatchArchiveView(View):
    def post(self, request, pk):
        batch = get_object_or_404(RawMaterialBatches, pk=pk)
        
        # Set current user for trigger
        from django.db import connection
        with connection.cursor() as cursor:
            cursor.execute("SET LOCAL app.current_user_id = %s", [request.user.id])
        
        batch.is_archived = True
        batch.save()  # Trigger will handle logging
        
        messages.success(request, "📦 Raw Material Batch archived successfully.")
        page = request.GET.get('page')
        if page:
            return redirect(f"{reverse('rawmaterial-batch')}?page={page}")
        return redirect('rawmaterial-batch')


class ArchivedRawMaterialBatchListView(ListView):
    model = RawMaterialBatches
    template_name = 'archived_rawmaterial_batch.html'
    context_object_name = 'object_list'
    paginate_by = 10

    def get_queryset(self):
        return RawMaterialBatches.objects.filter(is_archived=True).select_related('material', 'created_by_admin').order_by('-batch_date')


class RawMaterialBatchUnarchiveView(View):
    def post(self, request, pk):
        batch = get_object_or_404(RawMaterialBatches, pk=pk)
        
        # Set current user for trigger
        from django.db import connection
        with connection.cursor() as cursor:
            cursor.execute("SET LOCAL app.current_user_id = %s", [request.user.id])
        
        batch.is_archived = False
        batch.save()  # Trigger will handle logging
        
        messages.success(request, "✅ Raw Material Batch restored successfully.")
        return redirect('rawmaterial-batch-archived-list')

class RawMaterialBatchBulkRestoreView(View):
    def post(self, request):
        try:
            # Get IDs from comma-separated string
            ids_str = request.POST.get('ids', '')
            if not ids_str:
                return JsonResponse({'success': False, 'message': 'No batches selected'})
            
            batch_ids = [int(id.strip()) for id in ids_str.split(',') if id.strip()]
            
            if not batch_ids:
                return JsonResponse({'success': False, 'message': 'No valid batch IDs provided'})
            
            # Set current user for trigger
            from django.db import connection
            with connection.cursor() as cursor:
                cursor.execute("SET LOCAL app.current_user_id = %s", [request.user.id])
            
            # Restore selected batches (triggers will handle logging)
            count = RawMaterialBatches.objects.filter(id__in=batch_ids, is_archived=True).update(is_archived=False)
            
            return JsonResponse({
                'success': True, 
                'message': f'✅ {count} raw material batch(es) restored successfully!'
            })
        except Exception as e:
            return JsonResponse({'success': False, 'message': str(e)})

class RawMaterialBatchBulkDeleteView(View):
    def post(self, request):
        import json
        from collections import defaultdict
        from decimal import Decimal
        try:
            batch_ids = json.loads(request.POST.get('batch_ids', '[]'))
            if not batch_ids:
                return JsonResponse({'success': False, 'message': 'No batches selected'})
            
            # Get batches before deletion to update inventory
            batches = RawMaterialBatches.objects.filter(id__in=batch_ids, is_archived=True)
            
            # Group quantities by material for inventory update
            material_quantities = defaultdict(Decimal)
            for batch in batches:
                material_quantities[batch.material_id] += batch.quantity
            
            # Delete selected batches
            count, _ = batches.delete()
            
            # Update inventory for each affected material
            for material_id, quantity in material_quantities.items():
                try:
                    inventory = RawMaterialInventory.objects.get(material_id=material_id)
                    inventory.total_stock = max(0, inventory.total_stock - quantity)
                    inventory.save()
                except RawMaterialInventory.DoesNotExist:
                    pass
            
            return JsonResponse({'success': True, 'count': count})
        except Exception as e:
            return JsonResponse({'success': False, 'message': str(e)})

class RawMaterialBatchArchiveOldView(View):
    def post(self, request):
        from datetime import timedelta
        one_year_ago = timezone.now() - timedelta(days=365)
        archived_count = RawMaterialBatches.objects.filter(is_archived=False, batch_date__lt=one_year_ago).update(is_archived=True)
        messages.success(request, f"📦 {archived_count} raw material batch(es) older than 1 year have been archived.")
        return redirect('rawmaterial-batch')

@require_http_methods(["POST"])
def rawmaterial_batch_bulk_delete(request):
    try:
        ids = request.POST.get('ids', '').split(',')
        ids = [int(id.strip()) for id in ids if id.strip()]
        
        if not ids:
            return JsonResponse({'success': False, 'message': 'No batches selected'})
        
        # Get batches before deletion to update inventory
        batches = RawMaterialBatches.objects.filter(id__in=ids)
        
        # Group quantities by material for inventory update
        from collections import defaultdict
        from decimal import Decimal
        material_quantities = defaultdict(Decimal)
        for batch in batches:
            material_quantities[batch.material_id] += batch.quantity
        
        # Delete the batches
        deleted_count = batches.delete()[0]
        
        # Update inventory for each affected material
        for material_id, quantity in material_quantities.items():
            try:
                inventory = RawMaterialInventory.objects.get(material_id=material_id)
                inventory.total_stock = max(0, inventory.total_stock - quantity)
                inventory.save()
            except RawMaterialInventory.DoesNotExist:
                pass
        
        return JsonResponse({
            'success': True,
            'message': f'Successfully deleted {deleted_count} batch(es)'
        })
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)})

@require_http_methods(["POST"])
def rawmaterial_batch_bulk_archive(request):
    try:
        ids = request.POST.get('ids', '').split(',')
        ids = [int(id.strip()) for id in ids if id.strip()]
        
        if not ids:
            return JsonResponse({'success': False, 'message': 'No batches selected'})
        
        archived_count = RawMaterialBatches.objects.filter(id__in=ids).update(is_archived=True)
        return JsonResponse({
            'success': True,
            'message': f'Successfully archived {archived_count} batch(es)'
        })
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)})

class RawMaterialInventoryList(ListView):
    model = RawMaterialInventory
    context_object_name = 'rawmatinvent'
    template_name = "rawmatinvent_list.html"
    paginate_by = 10
    
    def get_queryset(self):
        # Filter out archived raw materials and their inventory
        queryset = super().get_queryset().select_related("material").filter(
            material__is_archived=False
        ).order_by('material_id')

        q = self.request.GET.get("q", "").strip()
        category = self.request.GET.get("category", "").strip().upper()

        if q:
            queryset = queryset.filter(
                Q(material__name__icontains=q) |
                Q(total_stock__icontains=q) |
                Q(reorder_threshold__icontains=q)
            )

        valid_cats = {
            c.upper()
            for c in RawMaterials.objects.filter(is_archived=False)
            .values_list("category", flat=True)
            .distinct()
            if c
        }
        if category and category in valid_cats:
            queryset = queryset.filter(material__category__iexact=category)

        return queryset
    
    def filter_by_reorder_status(self, queryset, status):
        """Filter inventory based on reorder status considering expiration dates."""
        if not status:
            return queryset
        
        filtered_items = []
        for inv in queryset:
            reorder_status = inv.get_reorder_status()
            available_stock = reorder_status['available_stock']
            threshold = inv.reorder_threshold
            
            if status == "on_stock" and available_stock > threshold:
                filtered_items.append(inv.material_id)
            elif status == "low_stock" and available_stock < threshold and available_stock > 0:
                filtered_items.append(inv.material_id)
            elif status == "warning" and available_stock == threshold:
                filtered_items.append(inv.material_id)
            elif status == "out_of_stock" and available_stock == 0:
                filtered_items.append(inv.material_id)
        
        return queryset.filter(material_id__in=filtered_items) if filtered_items else queryset.none()
    
    def get_context_data(self, **kwargs):
        from django.db.models import Sum
        from django.core.paginator import Paginator
        context = super().get_context_data(**kwargs)
        
        # Apply status filter if provided
        status = self.request.GET.get("status", "").strip()
        if status:
            filtered_queryset = self.filter_by_reorder_status(self.get_queryset(), status)
            paginator = Paginator(filtered_queryset, self.paginate_by)
            page_number = self.request.GET.get('page', 1)
            page_obj = paginator.get_page(page_number)
            context['rawmatinvent'] = page_obj
            context['paginator'] = paginator
            context['is_paginated'] = paginator.num_pages > 1
            context['page_obj'] = page_obj
        
        # Add reorder status data for each inventory item
        inventory_list = context.get('rawmatinvent', [])
        if hasattr(inventory_list, 'object_list'):
            inventory_list = inventory_list.object_list
        
        for inv in inventory_list:
            inv.reorder_status = inv.get_reorder_status()
        
        # Calculate total stock across all non-archived raw materials
        total_stock = RawMaterialInventory.objects.filter(
            material__is_archived=False
        ).aggregate(total=Sum('total_stock'))['total'] or 0
        context['total_rawmat_stock'] = total_stock
        category = self.request.GET.get("category", "").strip().upper()
        distinct_categories = (
            RawMaterials.objects.filter(is_archived=False)
            .values_list('category', flat=True)
            .distinct()
        )
        context['category_choices'] = sorted({c.upper() for c in distinct_categories if c})
        context['category_filter'] = category if category in context['category_choices'] else ""
        return context

@require_GET
@login_required
def export_rawmaterial_inventory(request):
    qs = RawMaterialInventory.objects.select_related('material').filter(
        material__is_archived=False
    ).order_by('material_id')

    q = request.GET.get("q", "").strip()
    status = request.GET.get("status", "").strip()
    category = request.GET.get("category", "").strip().upper()

    if q:
        qs = qs.filter(
            Q(material__name__icontains=q) |
            Q(total_stock__icontains=q) |
            Q(reorder_threshold__icontains=q)
        )

    valid_cats = {
        c.upper()
        for c in RawMaterials.objects.filter(is_archived=False)
        .values_list("category", flat=True)
        .distinct()
        if c
    }
    if category and category in valid_cats:
        qs = qs.filter(material__category__iexact=category)

    if status == "on_stock":
        qs = qs.filter(total_stock__gt=F("reorder_threshold"))
    elif status == "low_stock":
        qs = qs.filter(total_stock__lt=F("reorder_threshold"), total_stock__gt=0)
    elif status == "warning":
        qs = qs.filter(total_stock=F("reorder_threshold"))
    elif status == "out_of_stock":
        qs = qs.filter(total_stock=0)

    response = HttpResponse(content_type='text/csv')
    any_filter = bool(q or category or status)
    suffix = 'filtered' if any_filter else 'all'
    response['Content-Disposition'] = f'attachment; filename="raw_material_inventory_{suffix}.csv"'

    writer = csv.writer(response)
    writer.writerow(['Exported At', timezone.now().strftime('%Y-%m-%d %H:%M:%S')])
    writer.writerow(['Filters', f"q={q}", f"category={category}", f"status={status}"])
    total_stock_sum = qs.aggregate(total=Sum('total_stock'))['total'] or 0
    writer.writerow(['Total Materials', qs.count()])
    writer.writerow(['Total Stock (Units)', f"{total_stock_sum:.0f}"])
    writer.writerow([])

    writer.writerow(['Material', 'Unit Size', 'Unit', 'Price Per Unit', 'Category', 'Current Stock', 'Reorder Threshold', 'Status'])
    for item in qs:
        mat = item.material
        unit_obj = getattr(mat, 'unit', None)
        unit_name = getattr(unit_obj, 'unit_name', str(unit_obj)) if unit_obj is not None else ''
        unit_size = f"{mat.size:.0f}" if mat.size is not None else ''
        price = f"{mat.price_per_unit:.2f}" if mat.price_per_unit is not None else ''
        status_label = (
            'Out of Stock' if item.total_stock == 0 else
            'Low Stock' if item.total_stock < item.reorder_threshold else
            'Warning' if item.total_stock == item.reorder_threshold else
            'On Stock'
        )
        writer.writerow([
            mat.name,
            unit_size,
            unit_name,
            price,
            (mat.category or '').title() if getattr(mat, 'category', None) else '',
            f"{item.total_stock:.0f}",
            f"{item.reorder_threshold:.0f}",
            status_label,
        ])

    return response

class ProductVariantCreateView(CreateView):
    model = ProductVariants
    form_class = ProductVariantsForm
    template_name = "prodvar_add.html"
    success_url = reverse_lazy("product-add")


    def form_valid(self, form):
        auth_user = AuthUser.objects.get(id=self.request.user.id)
        form.instance.created_by_admin = auth_user
        return super().form_valid(form)

class SizesCreateView(CreateView):
    model = Sizes
    form_class = SizesForm
    template_name = "sizes_add.html"
    success_url = reverse_lazy("product-add")

    def form_valid(self, form):
        auth_user = AuthUser.objects.get(id=self.request.user.id)
        form.instance.created_by_admin = auth_user
        return super().form_valid(form)

class SizeUnitsCreateView(CreateView):
    model = SizeUnits
    form_class = SizeUnitsForm
    template_name = "sizeunits_add.html"
    success_url = reverse_lazy("product-add")

    def form_valid(self, form):
        auth_user = AuthUser.objects.get(id=self.request.user.id)
        form.instance.created_by_admin = auth_user
        return super().form_valid(form)

class UnitPricesCreateView(CreateView):
    model = UnitPrices
    form_class = UnitPricesForm
    template_name = "unitprices_add.html"
    success_url = reverse_lazy("product-add")

    def form_valid(self, form):
        auth_user = AuthUser.objects.get(id=self.request.user.id)
        form.instance.created_by_admin = auth_user
        return super().form_valid(form)

class SrpPricesCreateView(CreateView):
    model = SrpPrices
    form_class = SrpPricesForm
    template_name = "srpprices_add.html"
    success_url = reverse_lazy("product-add")

    def form_valid(self, form):
        auth_user = AuthUser.objects.get(id=self.request.user.id)
        form.instance.created_by_admin = auth_user
        return super().form_valid(form)


# Product Attributes Management View
class ProductAttributesView(LoginRequiredMixin, TemplateView):
    template_name = "product_attributes.html"
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['product_types'] = ProductTypes.objects.all().order_by('name')
        context['product_variants'] = ProductVariants.objects.all().order_by('name')
        context['sizes'] = Sizes.objects.all().order_by('size_label')
        context['size_units'] = SizeUnits.objects.all().order_by('unit_name')
        context['unit_prices'] = UnitPrices.objects.all().order_by('unit_price')
        context['srp_prices'] = SrpPrices.objects.all().order_by('srp_price')
        return context


# Product Type CRUD
@method_decorator(login_required, name='dispatch')
class ProductTypeAddView(View):
    def post(self, request):
        name = request.POST.get('name', '').strip()
        
        if not name:
            messages.error(request, '❌ Please enter a product type name!')
            return redirect('product-attributes')
        
        # Check for duplicates (case-insensitive)
        if ProductTypes.objects.filter(name__iexact=name).exists():
            messages.error(request, f'❌ Product Type "{name}" already exists!')
            return redirect('product-attributes')
        
        try:
            auth_user = AuthUser.objects.get(id=request.user.id)
            ProductTypes.objects.create(name=name, created_by_admin=auth_user)
            messages.success(request, f'✅ Product Type "{name}" added successfully!')
        except Exception as e:
            messages.error(request, f'❌ Error adding Product Type. Please try again.')
        
        return redirect('product-attributes')

@method_decorator(login_required, name='dispatch')
class ProductTypeEditView(View):
    def post(self, request, pk):
        product_type = get_object_or_404(ProductTypes, pk=pk)
        name = request.POST.get('name', '').strip()
        
        if name and name != product_type.name:
            # Check for duplicates (case-insensitive), excluding current record
            if ProductTypes.objects.filter(name__iexact=name).exclude(pk=pk).exists():
                messages.error(request, f'❌ Product Type "{name}" already exists!')
                return redirect('product-attributes')
            
            product_type.name = name
            product_type.save()
            messages.success(request, '✅ Product Type updated successfully!')
        
        return redirect('product-attributes')

@method_decorator(login_required, name='dispatch')
class ProductTypeDeleteView(View):
    def post(self, request, pk):
        from django.db import IntegrityError
        product_type = get_object_or_404(ProductTypes, pk=pk)
        try:
            product_type.delete()
            messages.success(request, 'Product Type deleted successfully!')
        except IntegrityError:
            messages.error(request, '❌ Cannot delete this Product Type because it is being used by existing products.')
        return redirect('product-attributes')


# Product Variant CRUD
@method_decorator(login_required, name='dispatch')
class ProductVariantAddView(View):
    def post(self, request):
        name = request.POST.get('name', '').strip()
        
        if not name:
            messages.error(request, '❌ Please enter a variant name!')
            return redirect('product-attributes')
        
        # Check for duplicates (case-insensitive)
        if ProductVariants.objects.filter(name__iexact=name).exists():
            messages.error(request, f'❌ Variant "{name}" already exists!')
            return redirect('product-attributes')
        
        try:
            auth_user = AuthUser.objects.get(id=request.user.id)
            ProductVariants.objects.create(name=name, created_by_admin=auth_user)
            messages.success(request, f'✅ Variant "{name}" added successfully!')
        except Exception as e:
            messages.error(request, f'❌ Error adding Variant. Please try again.')
        
        return redirect('product-attributes')

@method_decorator(login_required, name='dispatch')
class ProductVariantEditView(View):
    def post(self, request, pk):
        variant = get_object_or_404(ProductVariants, pk=pk)
        name = request.POST.get('name', '').strip()
        
        if name and name != variant.name:
            # Check for duplicates (case-insensitive), excluding current record
            if ProductVariants.objects.filter(name__iexact=name).exclude(pk=pk).exists():
                messages.error(request, f'❌ Variant "{name}" already exists!')
                return redirect('product-attributes')
            
            variant.name = name
            variant.save()
            messages.success(request, '✅ Variant updated successfully!')
        
        return redirect('product-attributes')

@method_decorator(login_required, name='dispatch')
class ProductVariantDeleteView(View):
    def post(self, request, pk):
        from django.db import IntegrityError
        product_variant = get_object_or_404(ProductVariants, pk=pk)
        try:
            product_variant.delete()
            messages.success(request, 'Product Variant deleted successfully!')
        except IntegrityError:
            messages.error(request, '❌ Cannot delete this Product Variant because it is being used by existing products.')
        return redirect('product-attributes')


# Size CRUD
@method_decorator(login_required, name='dispatch')
class SizeAddView(View):
    def post(self, request):
        size_label = request.POST.get('size_label', '').strip()
        
        if not size_label:
            messages.error(request, '❌ Please enter a size label!')
            return redirect('product-attributes')
        
        # Check for duplicates (case-insensitive)
        if Sizes.objects.filter(size_label__iexact=size_label).exists():
            messages.error(request, f'❌ Size "{size_label}" already exists!')
            return redirect('product-attributes')
        
        try:
            auth_user = AuthUser.objects.get(id=request.user.id)
            Sizes.objects.create(size_label=size_label, created_by_admin=auth_user)
            messages.success(request, f'✅ Size "{size_label}" added successfully!')
        except Exception as e:
            messages.error(request, f'❌ Error adding Size. Please try again.')
        
        return redirect('product-attributes')

@method_decorator(login_required, name='dispatch')
class SizeEditView(View):
    def post(self, request, pk):
        size = get_object_or_404(Sizes, pk=pk)
        size_label = request.POST.get('size_label', '').strip()
        
        if size_label and size_label != size.size_label:
            # Check for duplicates (case-insensitive), excluding current record
            if Sizes.objects.filter(size_label__iexact=size_label).exclude(pk=pk).exists():
                messages.error(request, f'❌ Size "{size_label}" already exists!')
                return redirect('product-attributes')
            
            size.size_label = size_label
            size.save()
            messages.success(request, '✅ Size updated successfully!')
        
        return redirect('product-attributes')

@method_decorator(login_required, name='dispatch')
class SizeDeleteView(View):
    def post(self, request, pk):
        from django.db import IntegrityError
        size = get_object_or_404(Sizes, pk=pk)
        try:
            size.delete()
            messages.success(request, 'Size deleted successfully!')
        except IntegrityError:
            messages.error(request, '❌ Cannot delete this Size because it is being used by existing products.')
        return redirect('product-attributes')


# Size Unit CRUD
@method_decorator(login_required, name='dispatch')
class SizeUnitAddView(View):
    def post(self, request):
        from django.db import IntegrityError
        unit_name = request.POST.get('unit_name', '').strip()
        if unit_name:
            # Check if already exists (case-insensitive)
            if SizeUnits.objects.filter(unit_name__iexact=unit_name).exists():
                messages.error(request, '❌ This Size Unit already exists!')
                return redirect('product-attributes')
            
            try:
                auth_user = AuthUser.objects.get(id=request.user.id)
                SizeUnits.objects.create(unit_name=unit_name, created_by_admin=auth_user)
                messages.success(request, '✅ Size Unit added successfully!')
            except IntegrityError:
                messages.error(request, '❌ This Size Unit already exists!')
        return redirect('product-attributes')

@method_decorator(login_required, name='dispatch')
class SizeUnitEditView(View):
    def post(self, request, pk):
        from django.db import IntegrityError
        size_unit = get_object_or_404(SizeUnits, pk=pk)
        unit_name = request.POST.get('unit_name', '').strip()
        if unit_name:
            # Check if another record with same name exists (excluding current)
            if SizeUnits.objects.filter(unit_name__iexact=unit_name).exclude(pk=pk).exists():
                messages.error(request, '❌ This Size Unit already exists!')
                return redirect('product-attributes')
            
            try:
                size_unit.unit_name = unit_name
                size_unit.save()
                messages.success(request, '✅ Size Unit updated successfully!')
            except IntegrityError:
                messages.error(request, '❌ This Size Unit already exists!')
        return redirect('product-attributes')

@method_decorator(login_required, name='dispatch')
class SizeUnitDeleteView(View):
    def post(self, request, pk):
        from django.db import IntegrityError
        size_unit = get_object_or_404(SizeUnits, pk=pk)
        try:
            size_unit.delete()
            messages.success(request, 'Size Unit deleted successfully!')
        except IntegrityError:
            messages.error(request, '❌ Cannot delete this Size Unit because it is being used by existing products.')
        return redirect('product-attributes')


# Unit Price CRUD
@method_decorator(login_required, name='dispatch')
class UnitPriceAddView(View):
    def post(self, request):
        from django.db import IntegrityError
        unit_price = request.POST.get('unit_price', '').strip()
        
        if not unit_price:
            messages.error(request, '❌ Please enter a price!')
            return redirect('product-attributes')
        
        try:
            # Convert to Decimal for validation
            price_value = Decimal(unit_price)
            
            # Validate positive number
            if price_value <= 0:
                messages.error(request, '❌ Price must be greater than zero!')
                return redirect('product-attributes')
            
        except (InvalidOperation, ValueError):
            messages.error(request, '❌ Invalid price format! Please enter a valid number.')
            return redirect('product-attributes')
        
        # Check if already exists
        if UnitPrices.objects.filter(unit_price=price_value).exists():
            messages.error(request, f'❌ Unit Price ₱{price_value} already exists!')
            return redirect('product-attributes')
        
        try:
            auth_user = AuthUser.objects.get(id=request.user.id)
            UnitPrices.objects.create(unit_price=price_value, created_by_admin=auth_user)
            messages.success(request, f'✅ Unit Price ₱{price_value} added successfully!')
        except IntegrityError as e:
            messages.error(request, f'❌ Database error: This Unit Price already exists!')
        except Exception as e:
            messages.error(request, f'❌ Error: {str(e)}')
        
        return redirect('product-attributes')

@method_decorator(login_required, name='dispatch')
class UnitPriceEditView(View):
    def post(self, request, pk):
        from django.db import IntegrityError
        unit_price_obj = get_object_or_404(UnitPrices, pk=pk)
        unit_price = request.POST.get('unit_price', '').strip()
        if unit_price:
            try:
                # Convert to Decimal for comparison
                price_value = Decimal(unit_price)
                
                # Validate positive number
                if price_value <= 0:
                    messages.error(request, '❌ Price must be greater than zero!')
                    return redirect('product-attributes')
                
                # Check if another record with same price exists (excluding current)
                if UnitPrices.objects.filter(unit_price=price_value).exclude(pk=pk).exists():
                    messages.error(request, '❌ This Unit Price already exists!')
                    return redirect('product-attributes')
                
                unit_price_obj.unit_price = price_value
                unit_price_obj.save()
                messages.success(request, '✅ Unit Price updated successfully!')
            except InvalidOperation:
                messages.error(request, '❌ Invalid price format! Please enter a valid number.')
            except ValueError:
                messages.error(request, '❌ Invalid price value!')
            except IntegrityError as e:
                messages.error(request, f'❌ Database error: {str(e)}')
            except Exception as e:
                messages.error(request, f'❌ Error updating Unit Price: {str(e)}')
        return redirect('product-attributes')

@method_decorator(login_required, name='dispatch')
class UnitPriceDeleteView(View):
    def post(self, request, pk):
        from django.db import IntegrityError
        unit_price = get_object_or_404(UnitPrices, pk=pk)
        
        # Check if being used by products
        products_using = Products.objects.filter(unit_price_id=pk)
        if products_using.exists():
            count = products_using.count()
            messages.error(request, f'❌ Cannot delete this Unit Price because it is being used by {count} product(s).')
            return redirect('product-attributes')
        
        try:
            unit_price.delete()
            messages.success(request, '✅ Unit Price deleted successfully!')
        except IntegrityError:
            messages.error(request, '❌ Cannot delete this Unit Price because it is being used by existing products.')
        except Exception as e:
            messages.error(request, f'❌ Error deleting Unit Price: {str(e)}')
        return redirect('product-attributes')


# SRP Price CRUD
@method_decorator(login_required, name='dispatch')
class SrpPriceAddView(View):
    def post(self, request):
        from django.db import IntegrityError
        srp_price = request.POST.get('srp_price', '').strip()
        
        if not srp_price:
            messages.error(request, '❌ Please enter a price!')
            return redirect('product-attributes')
        
        try:
            # Convert to Decimal for validation
            price_value = Decimal(srp_price)
            
            # Validate positive number
            if price_value <= 0:
                messages.error(request, '❌ Price must be greater than zero!')
                return redirect('product-attributes')
            
        except (InvalidOperation, ValueError):
            messages.error(request, '❌ Invalid price format! Please enter a valid number.')
            return redirect('product-attributes')
        
        # Check if already exists
        if SrpPrices.objects.filter(srp_price=price_value).exists():
            messages.error(request, f'❌ SRP Price ₱{price_value} already exists!')
            return redirect('product-attributes')
        
        try:
            auth_user = AuthUser.objects.get(id=request.user.id)
            SrpPrices.objects.create(srp_price=price_value, created_by_admin=auth_user)
            messages.success(request, f'✅ SRP Price ₱{price_value} added successfully!')
        except IntegrityError:
            messages.error(request, f'❌ This SRP Price already exists!')
        except Exception as e:
            messages.error(request, f'❌ Error adding SRP Price. Please try again.')
        
        return redirect('product-attributes')

@method_decorator(login_required, name='dispatch')
class SrpPriceEditView(View):
    def post(self, request, pk):
        from django.db import IntegrityError
        srp_price_obj = get_object_or_404(SrpPrices, pk=pk)
        srp_price = request.POST.get('srp_price', '').strip()
        if srp_price:
            try:
                # Convert to Decimal for comparison
                price_value = Decimal(srp_price)
                
                # Validate positive number
                if price_value <= 0:
                    messages.error(request, '❌ Price must be greater than zero!')
                    return redirect('product-attributes')
                
                # Check if another record with same price exists (excluding current)
                if SrpPrices.objects.filter(srp_price=price_value).exclude(pk=pk).exists():
                    messages.error(request, '❌ This SRP Price already exists!')
                    return redirect('product-attributes')
                
                srp_price_obj.srp_price = price_value
                srp_price_obj.save()
                messages.success(request, '✅ SRP Price updated successfully!')
            except InvalidOperation:
                messages.error(request, '❌ Invalid price format! Please enter a valid number.')
            except ValueError:
                messages.error(request, '❌ Invalid price value!')
            except IntegrityError as e:
                messages.error(request, f'❌ Database error: {str(e)}')
            except Exception as e:
                messages.error(request, f'❌ Error updating SRP Price: {str(e)}')
        return redirect('product-attributes')

@method_decorator(login_required, name='dispatch')
class SrpPriceDeleteView(View):
    def post(self, request, pk):
        from django.db import IntegrityError, connection
        srp_price = get_object_or_404(SrpPrices, pk=pk)
        
        # Check if being used by products
        products_using = Products.objects.filter(srp_price_id=pk)
        if products_using.exists():
            count = products_using.count()
            messages.error(request, f'❌ Cannot delete this SRP Price because it is being used by {count} product(s).')
            return redirect('product-attributes')
        
        try:
            srp_price.delete()
            messages.success(request, '✅ SRP Price deleted successfully!')
        except IntegrityError:
            messages.error(request, '❌ Cannot delete this SRP Price because it is being used by existing products.')
        except Exception as e:
            messages.error(request, f'❌ Error deleting SRP Price: {str(e)}')
        return redirect('product-attributes')


class WithdrawSuccessView(ListView):
    model = Withdrawals
    context_object_name = 'withdrawals'
    template_name = "withdrawn.html"
    paginate_by = 10

    def paginate_queryset(self, queryset, page_size):
        # Disable automatic pagination since we do manual pagination in get_context_data
        return (None, None, queryset, False)

    def get_queryset(self):
        # Use select_related to reduce database queries
        qs = Withdrawals.objects.filter(is_archived=False).select_related('created_by_admin').order_by('-date')
        
        show_all = self.request.GET.get('show_all', '').strip()
        
        if not show_all:

            date_filter = self.request.GET.get('date_filter', '').strip()
            
            if date_filter:
                try:
                    parsed_date = datetime.strptime(date_filter, "%Y-%m")
                    qs = qs.filter(date__year=parsed_date.year, date__month=parsed_date.month)
                except ValueError:

                    today = timezone.now()
                    qs = qs.filter(date__year=today.year, date__month=today.month)
            else:

                today = timezone.now()
                qs = qs.filter(date__year=today.year, date__month=today.month)
        
        item_type = self.request.GET.get('item_type', '').strip()
        if item_type:
            qs = qs.filter(item_type=item_type)

        reason = self.request.GET.get('reason', '').strip()
        if reason:
            qs = qs.filter(reason=reason)
        
        return qs

    def get_context_data(self, **kwargs):
        from django.core.cache import cache
        from collections import defaultdict
        from django.core.paginator import Paginator
        from django.db.models import Sum
        
        context = super().get_context_data(**kwargs)
        
        today = timezone.now()
        context['current_month_value'] = today.strftime("%Y-%m")
        
        # Group withdrawals by order_group_id or by timestamp for non-grouped items
        # Get all withdrawals (not paginated yet)
        all_withdrawals = self.get_queryset()

        total_withdrawals = all_withdrawals.aggregate(total=Sum('quantity'))['total'] or 0
        context['total_withdrawals'] = total_withdrawals

        product_withdrawals = all_withdrawals.filter(item_type='PRODUCT')
        context['product_withdrawals_qty'] = product_withdrawals.aggregate(total=Sum('quantity'))['total'] or 0
        context['product_withdrawals_count'] = product_withdrawals.count()
 
        rawmat_withdrawals = all_withdrawals.filter(item_type='RAW_MATERIAL')
        context['rawmat_withdrawals_qty'] = rawmat_withdrawals.aggregate(total=Sum('quantity'))['total'] or 0
        context['rawmat_withdrawals_count'] = rawmat_withdrawals.count()
        
        grouped_withdrawals = defaultdict(list)
        for withdrawal in all_withdrawals:
            # Use order_group_id if available, otherwise use a unique key based on timestamp
            if withdrawal.order_group_id:
                group_key = f"order_{withdrawal.order_group_id}"
            else:
                # For non-grouped withdrawals, create individual groups
                group_key = f"single_{withdrawal.id}"
            
            grouped_withdrawals[group_key].append(withdrawal)
        
        # Convert to list of dicts for template
        withdrawal_groups = []
        for group_key, withdrawals_list in grouped_withdrawals.items():
            first_withdrawal = withdrawals_list[0]
            is_single = group_key.startswith('single_')
            actual_group_id = first_withdrawal.order_group_id if not is_single else None
            
            withdrawal_groups.append({
                'group_key': group_key,
                'order_group_id': actual_group_id,
                'is_single': is_single,
                'date': first_withdrawal.date,
                'reason': first_withdrawal.reason,
                'reason_display': first_withdrawal.get_reason_display(),
                'item_type': first_withdrawal.item_type,
                'item_type_display': first_withdrawal.get_item_type_display(),
                'sales_channel': first_withdrawal.sales_channel,
                'sales_channel_display': first_withdrawal.get_sales_channel_display() if first_withdrawal.sales_channel else None,
                'payment_status': first_withdrawal.payment_status,
                'payment_status_display': first_withdrawal.get_payment_status_display() if first_withdrawal.payment_status else None,
                'customer_name': first_withdrawal.customer_name,
                'created_by_admin': first_withdrawal.created_by_admin,
                'item_count': len(withdrawals_list),
                'withdrawals': withdrawals_list,
            })
        
        # Sort by date (most recent first)
        withdrawal_groups.sort(key=lambda x: x['date'], reverse=True)
        
        # Manual pagination for grouped withdrawals
        paginator = Paginator(withdrawal_groups, self.paginate_by)
        page_number = self.request.GET.get('page', 1)
        page_obj = paginator.get_page(page_number)
        
        # Replace the context with grouped data
        context['withdrawal_groups'] = page_obj
        context['is_paginated'] = paginator.num_pages > 1
        context['paginator'] = paginator
        context['page_obj'] = page_obj
        
        return context

@require_GET
@login_required
def export_withdrawals(request):
    qs = Withdrawals.objects.filter(is_archived=False).select_related('created_by_admin').order_by('-date')
    
    show_all = request.GET.get('show_all', '').strip()
    date_filter = request.GET.get('date_filter', '').strip()
    item_type = request.GET.get('item_type', '').strip()
    reason = request.GET.get('reason', '').strip()
    
    if not show_all:
        if date_filter:
            try:
                parsed_date = datetime.strptime(date_filter, "%Y-%m")
                qs = qs.filter(date__year=parsed_date.year, date__month=parsed_date.month)
            except ValueError:
                today = timezone.now()
                qs = qs.filter(date__year=today.year, date__month=today.month)
        else:
            today = timezone.now()
            qs = qs.filter(date__year=today.year, date__month=today.month)
    
    if item_type:
        qs = qs.filter(item_type=item_type)
    
    if reason:
        qs = qs.filter(reason=reason)
    
    response = HttpResponse(content_type='text/csv')
    suffix = 'all' if show_all else 'current_month'
    if date_filter and not show_all:
        suffix = 'filtered'
    response['Content-Disposition'] = f'attachment; filename="withdrawals_{suffix}.csv"'
    
    writer = csv.writer(response)
    writer.writerow(['Exported At', timezone.now().strftime('%Y-%m-%d %H:%M:%S')])
    writer.writerow(['Filters', f"show_all={show_all}", f"date_filter={date_filter if not show_all else ''}", f"item_type={item_type}", f"reason={reason}"])
    writer.writerow(['Total Records', qs.count()])
    writer.writerow([])
    
    writer.writerow(['Date & Time', 'Item Type', 'Reason', 'Item Display', 'Quantity', 'Created By'])
    for withdrawal in qs:
        writer.writerow([
            withdrawal.date.strftime('%Y-%m-%d %H:%M:%S'),
            withdrawal.get_item_type_display(),
            withdrawal.get_reason_display(),
            withdrawal.get_item_display(),
            f"{withdrawal.quantity:.2f}",
            withdrawal.created_by_admin.username,
        ])
    
    return response
    
class WithdrawItemView(View):
    template_name = "withdraw_item.html"

    def get(self, request):
        products = Products.objects.all().order_by('id').select_related(
            "product_type", "variant", "size", "size_unit", "productinventory"
        )
        rawmaterials = RawMaterials.objects.all().select_related(
            "unit", "rawmaterialinventory"
        )
        discounts = Discounts.objects.all()
        
        # Get packaging materials (category = PACKAGING)
        packaging_materials = RawMaterials.objects.filter(
            category='PACKAGING',
            is_archived=False
        ).select_related('unit', 'rawmaterialinventory')
        
        # Build packaging information for each product and attach to product object
        from django.utils import timezone
        today = timezone.localdate()
        expiration_cutoff = today + timezone.timedelta(days=7)

        for product in products:
            # Get batches with packaging information
            batches = ProductBatches.objects.filter(
                product=product,
                is_archived=False,
                packaging__isnull=False
            ).select_related('packaging', 'packaging__unit', 'packaging__rawmaterialinventory')

            # Create individual batch options instead of grouping by packaging
            packaging_options = []
            for batch in batches:
                packaging = batch.packaging
                if packaging:
                    packaging_name = f"{packaging.name}"
                    if packaging.size and packaging.unit:
                        unit_name = packaging.unit.unit_name if hasattr(packaging.unit, 'unit_name') else str(packaging.unit)
                        packaging_name = f"{packaging_name} ({packaging.size} {unit_name})"

                    # Calculate expiring stock for this batch
                    expiring_qty = 0
                    if (batch.expiration_date and
                        batch.expiration_date <= expiration_cutoff and
                        batch.expiration_date >= today and
                        batch.quantity > 0):
                        expiring_qty = batch.quantity

                    # Add batch as individual option
                    exp_date_str = batch.expiration_date.strftime('%Y-%m-%d') if batch.expiration_date else 'No Date'
                    mfg_date_str = batch.batch_date.strftime('%Y-%m-%d') if batch.batch_date else 'No Date'

                    packaging_options.append({
                        'id': batch.id,  # Use batch ID instead of packaging ID
                        'name': packaging_name,
                        'quantity': batch.quantity,
                        'expiring': expiring_qty,
                        'expiration_date': exp_date_str,
                        'manufactured_date': mfg_date_str,
                        'packaging_id': packaging.id  # Keep packaging ID for reference
                    })

            # Sort by expiration date (oldest first) then by packaging name
            product.packaging_options = sorted(packaging_options, key=lambda x: (x['expiration_date'], x['name']))

        return render(request, self.template_name, {
            "products": products,
            "rawmaterials": rawmaterials,
            "discounts": discounts,
            "packaging_materials": packaging_materials
        })

    def post(self, request):
        
        item_type = request.POST.get("item_type")
        reason = request.POST.get("reason")
        sales_channel = request.POST.get("sales_channel")
        
        # Auto-set reason to DAMAGED for RAW_MATERIAL (packaging) withdrawals
        if item_type == "RAW_MATERIAL":
            reason = "DAMAGED"
        price_input = request.POST.get("price_input")
        customer_name = request.POST.get("customer_name")
        payment_status = request.POST.get("payment_status", "PAID")
        paid_amount_input = request.POST.get("paid_amount")
       
        if reason == "REPLACEMENT_FOR_RETURNED":
            print(f"DEBUG: Processing REPLACEMENT_FOR_RETURNED withdrawal")
            print(f"DEBUG: item_type={item_type}, reason={reason}")
            print(f"DEBUG: POST data keys: {list(request.POST.keys())}")

        # Parse price input
        if price_input in ['UNIT', 'SRP']:
            price_type = price_input
            custom_price = None
        else:
            price_type = None
            try:
                custom_price = float(price_input) if price_input else None
            except (TypeError, ValueError):
                custom_price = None
        
        # Parse paid amount for partial payments
        paid_amount = None
        if paid_amount_input:
            try:
                paid_amount = Decimal(paid_amount_input)
            except (TypeError, ValueError, InvalidOperation):
                paid_amount = None

        # Generate order_group_id for ORDER, CONSIGNMENT, RESELLER
        order_group_id = None
        if reason == "SOLD" and sales_channel in ['ORDER', 'CONSIGNMENT', 'RESELLER']:
            # Get the max order_group_id and increment
            max_id = Withdrawals.objects.filter(order_group_id__isnull=False).aggregate(
                max_id=models.Max('order_group_id')
            )['max_id']
            order_group_id = (max_id or 0) + 1

        count = 0

        if item_type == "PRODUCT":
            for key, value in request.POST.items():
                if key.startswith("product_") and value:
                    try:
                        product_id = key.split("_")[1]
                        quantity = Decimal(value)  # Use Decimal instead of float
                        if quantity <= 0:
                            continue
                        
                        if reason == "REPLACEMENT_FOR_RETURNED":
                            print(f"DEBUG: Processing product {product_id} with quantity {quantity}")
                        
                        product = Products.objects.get(id=product_id)
                        inv = product.productinventory

                        if quantity > inv.total_stock:
                            messages.error(request, f"⚠️ Insufficient stock for {product}. Available: {inv.total_stock}")
                            continue

                        discount_val = request.POST.get(f"discount_{product_id}")
                        discount_obj = None
                        custom_value = None
                        if discount_val:
                            try:
                                discount_obj = Discounts.objects.get(value=discount_val)
                            except Discounts.DoesNotExist:
                                custom_value = discount_val

                        # Initialize all price-related fields
                        actual_unit_price = None
                        actual_discount_percent = None
                        actual_discount_amount = None
                        final_price_per_unit = None
                        total_amount = None
                        
                        if reason == "SOLD" and price_type:
                            # Get base price at time of sale
                            base_price = Decimal(0)
                            if price_type == 'UNIT':
                                base_price = product.unit_price.unit_price
                            elif price_type == 'SRP':
                                base_price = product.srp_price.srp_price
                            
                            # Calculate discount
                            discount_percent = Decimal(0)
                            if discount_obj:
                                discount_percent = Decimal(discount_obj.value)
                            elif custom_value:
                                discount_percent = Decimal(custom_value)
                            
                            # Calculate final prices
                            discount_amount = base_price * (discount_percent / 100)
                            final_price = base_price - discount_amount
                            total = quantity * final_price
                            
                            # Store calculated values
                            actual_unit_price = base_price
                            actual_discount_percent = discount_percent
                            actual_discount_amount = discount_amount
                            final_price_per_unit = final_price
                            total_amount = total

                       
                        # Get selected batch from form (changed from packaging to batch)
                        batch_id = request.POST.get(f"batch_{product_id}")
                        selected_batch = None
                        selected_packaging = None

                        if batch_id:
                            try:
                                selected_batch = ProductBatches.objects.get(id=batch_id, product=product, is_archived=False)
                                selected_packaging = selected_batch.packaging
                            except ProductBatches.DoesNotExist:
                                messages.error(request, f"Invalid batch selected for {product}")
                                continue

                        if reason == "REPLACEMENT_FOR_RETURNED":
                            print(f"DEBUG: About to create withdrawal for product {product.id}, quantity {quantity}")
                            print(f"DEBUG: Current stock before deduction: {inv.total_stock}")
                            print(f"DEBUG: Selected batch: {selected_batch}")
                            print(f"DEBUG: Selected packaging: {selected_packaging}")

                        withdrawal = Withdrawals.objects.create(
                            item_id=product.id,
                            item_type="PRODUCT",
                            quantity=quantity,
                            reason=reason,
                            date=timezone.now(),
                            created_by_admin=request.user,
                            sales_channel=sales_channel if reason == "SOLD" else None,
                            price_type=price_type if reason == "SOLD" and payment_status == "PAID" else None,
                            custom_price=custom_price if custom_price else None,
                            discount_id=discount_obj.id if discount_obj else None,
                            custom_discount_value=custom_value,
                            customer_name=customer_name if sales_channel in ['ORDER', 'CONSIGNMENT', 'RESELLER'] else None,
                            payment_status=payment_status if sales_channel in ['ORDER', 'CONSIGNMENT', 'RESELLER'] else 'PAID',
                            paid_amount=paid_amount if payment_status == 'PARTIAL' else None,
                            order_group_id=order_group_id,
                            packaging=selected_packaging,
                            batch=selected_batch,

                            actual_unit_price=actual_unit_price,
                            actual_discount_percent=actual_discount_percent,
                            actual_discount_amount=actual_discount_amount,
                            final_price_per_unit=final_price_per_unit,
                            total_amount=total_amount,
                        )

                        if reason == "REPLACEMENT_FOR_RETURNED":
                            print(f"DEBUG: Withdrawal created successfully with ID: {withdrawal.id}")

                        count += 1
                    except Exception as e:
                        import traceback
                        error_details = traceback.format_exc()
                        print(f"ERROR withdrawing product {product_id}: {str(e)}")
                        print(f"Full traceback: {error_details}")
                        messages.error(request, f"❌ Error withdrawing product: {str(e)}")
                        continue

        elif item_type == "RAW_MATERIAL":
            for key, value in request.POST.items():
                if key.startswith("material_") and value:
                    try:
                        material_id = key.split("_")[1]
                        quantity = Decimal(value)  # Use Decimal instead of float
                        if quantity <= 0:
                            continue
                        material = RawMaterials.objects.get(id=material_id)
                        inv = material.rawmaterialinventory

                        if quantity > inv.total_stock:
                            messages.error(request, f"⚠️ Insufficient stock for {material}. Available: {inv.total_stock}")
                            continue

                        withdrawal = Withdrawals.objects.create(
                            item_id=material.id,
                            item_type="RAW_MATERIAL",
                            quantity=quantity,
                            reason=reason,
                            date=timezone.now(),
                            created_by_admin=request.user,
                            sales_channel=sales_channel if reason == "SOLD" else None,
                            price_type=price_type if reason == "SOLD" and payment_status == "PAID" else None,
                            custom_price=custom_price if custom_price else None,
                            customer_name=customer_name if sales_channel in ['ORDER', 'CONSIGNMENT', 'RESELLER'] else None,
                            payment_status=payment_status if sales_channel in ['ORDER', 'CONSIGNMENT', 'RESELLER'] else 'PAID',
                            paid_amount=paid_amount if payment_status == 'PARTIAL' else None,
                            order_group_id=order_group_id,
                        )
                        count += 1
                    except Exception as e:
                        import traceback
                        error_details = traceback.format_exc()
                        print(f"ERROR withdrawing raw material {material_id}: {str(e)}")
                        print(f"Full traceback: {error_details}")
                        messages.error(request, f"❌ Error withdrawing raw material: {str(e)}")
                        continue

        if reason == "REPLACEMENT_FOR_RETURNED":
            print(f"DEBUG: Final count of processed items: {count}")
        
        if count > 0:
            
            if reason == "SOLD" and sales_channel in ['ORDER', 'CONSIGNMENT', 'RESELLER'] and order_group_id:
                if payment_status in ['PAID', 'PARTIAL']:
                    # Calculate total amount for the order
                    withdrawals = Withdrawals.objects.filter(order_group_id=order_group_id)
                    total_sales_amount = Decimal(0)
                    
                    if payment_status == 'PARTIAL':
                        # For partial, use the paid_amount
                        total_sales_amount = paid_amount if paid_amount else Decimal(0)
                    else:
                        # For PAID, calculate from withdrawals
                        has_custom_price = any(w.custom_price for w in withdrawals)
                        
                        if has_custom_price:
                            # Custom price is the TOTAL for the entire order, not per item
                            # Just use the custom_price from the first withdrawal
                            total_sales_amount = Decimal(withdrawals.first().custom_price)
                        else:
                            # PRICE FIX: Use stored total_amount if available, otherwise calculate
                            for w in withdrawals:
                                if w.total_amount is not None:
                                    # Use stored price (after fix implementation)
                                    total_sales_amount += w.total_amount
                                elif w.price_type:
                                    product = Products.objects.get(id=w.item_id)
                                    base_price = Decimal(0)
                                    
                                    if w.price_type == 'UNIT':
                                        base_price = product.unit_price.unit_price
                                    elif w.price_type == 'SRP':
                                        base_price = product.srp_price.srp_price
                                    
                                    # Apply discount if exists
                                    discount_percent = Decimal(0)
                                    if w.discount_id:
                                        discount = Discounts.objects.get(id=w.discount_id)
                                        discount_percent = Decimal(discount.value)
                                    elif w.custom_discount_value:
                                        discount_percent = Decimal(w.custom_discount_value)
                                    
                                    # Calculate discounted price
                                    discounted_price = base_price * (1 - (discount_percent / 100))
                                    item_total = Decimal(w.quantity) * discounted_price
                                    total_sales_amount += item_total
                                    
                                    # print(f"  Item: {product}, Qty: {w.quantity}, Base: P{base_price}, Discount: {discount_percent}%, Final: P{item_total} (calculated)")
                    
                    # Create ONE sales entry for the entire order
                    # print(f"Total sales amount calculated: P{total_sales_amount}")
                    
                    if total_sales_amount > 0:
                        from .models import AuthUser
                        auth_user = AuthUser.objects.get(id=request.user.id)
                        
                        sales_entry = Sales.objects.create(
                            category=f"{sales_channel} - {customer_name}",
                            amount=total_sales_amount,
                            date=timezone.now().date(),
                            description=f"Order #{order_group_id}, Status: {payment_status}",
                            created_by_admin=auth_user
                        )
            
            messages.success(request, f"✅ Success! {count} item(s) withdrawn. Inventory updated!")
        else:
            messages.warning(request, "⚠️ No items withdrawn. Please enter quantity for at least one item.")

        return redirect("withdrawals")


class WithdrawalsArchiveView(View):
    def post(self, request, pk):
        withdrawal = get_object_or_404(Withdrawals, pk=pk)
        
        # Set current user for trigger
        from django.db import connection
        with connection.cursor() as cursor:
            cursor.execute("SET LOCAL app.current_user_id = %s", [request.user.id])
        
        withdrawal.is_archived = True
        withdrawal.save()  # Trigger will handle logging
        
        messages.success(request, "📦 Withdrawal archived successfully.")
        page = request.GET.get('page')
        if page:
            return redirect(f"{reverse('withdrawals')}?page={page}")
        return redirect('withdrawals')


class ArchivedWithdrawalsListView(ListView):
    model = Withdrawals
    template_name = 'archived_withdrawals.html'
    context_object_name = 'object_list'
    paginate_by = 10

    def get_queryset(self):
        return Withdrawals.objects.filter(is_archived=True).order_by('-date')


class WithdrawalsUnarchiveView(View):
    def post(self, request, pk):
        withdrawal = get_object_or_404(Withdrawals, pk=pk)
        
        # Set current user for trigger
        from django.db import connection
        with connection.cursor() as cursor:
            cursor.execute("SET LOCAL app.current_user_id = %s", [request.user.id])
        
        withdrawal.is_archived = False
        withdrawal.save()  # Trigger will handle logging
        
        messages.success(request, "✅ Withdrawal restored successfully.")
        return redirect('withdrawals-archived-list')

class WithdrawalBulkRestoreView(View):
    def post(self, request):
        import json
        try:
            withdrawal_ids = json.loads(request.POST.get('withdrawal_ids', '[]'))
            if not withdrawal_ids:
                return JsonResponse({'success': False, 'message': 'No withdrawals selected'})
            
            # Restore selected withdrawals
            count = Withdrawals.objects.filter(id__in=withdrawal_ids, is_archived=True).update(is_archived=False)
            
            return JsonResponse({'success': True, 'count': count})
        except Exception as e:
            return JsonResponse({'success': False, 'message': str(e)})

class WithdrawalBulkDeleteView(View):
    def post(self, request):
        import json
        try:
            withdrawal_ids = json.loads(request.POST.get('withdrawal_ids', '[]'))
            if not withdrawal_ids:
                return JsonResponse({'success': False, 'message': 'No withdrawals selected'})
            
            # Delete selected withdrawals
            count, _ = Withdrawals.objects.filter(id__in=withdrawal_ids, is_archived=True).delete()
            
            return JsonResponse({'success': True, 'count': count})
        except Exception as e:
            return JsonResponse({'success': False, 'message': str(e)})

class WithdrawalsArchiveOldView(View):
    def post(self, request):
        from datetime import timedelta
        one_year_ago = timezone.now() - timedelta(days=365)
        archived_count = Withdrawals.objects.filter(is_archived=False, date__lt=one_year_ago).update(is_archived=True)
        messages.success(request, f"📦 {archived_count} withdrawal(s) older than 1 year have been archived.")
        return redirect('withdrawals')

@require_http_methods(["POST"])
def withdrawals_bulk_delete(request):
    try:
        ids = request.POST.get('ids', '').split(',')
        ids = [int(id.strip()) for id in ids if id.strip()]
        
        if not ids:
            return JsonResponse({'success': False, 'message': 'No withdrawals selected'})
        
        deleted_count = Withdrawals.objects.filter(id__in=ids).delete()[0]
        return JsonResponse({
            'success': True,
            'message': f'Successfully deleted {deleted_count} withdrawal(s)'
        })
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)})

@require_http_methods(["POST"])
def withdrawals_bulk_archive(request):
    try:
        ids = request.POST.get('ids', '').split(',')
        ids = [int(id.strip()) for id in ids if id.strip()]
        
        if not ids:
            return JsonResponse({'success': False, 'message': 'No withdrawals selected'})
        
        archived_count = Withdrawals.objects.filter(id__in=ids).update(is_archived=True)
        return JsonResponse({
            'success': True,
            'message': f'Successfully archived {archived_count} withdrawal(s)'
        })
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)})

class WithdrawUpdateView(UpdateView):
    model = Withdrawals
    form_class = WithdrawEditForm
    template_name = "withdraw_edit.html"
    success_url = reverse_lazy("withdrawals")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['is_raw_material'] = self.object.item_type == 'RAW_MATERIAL'
        return context

    def form_valid(self, form):
        withdrawal = self.get_object()
        
        original_date = withdrawal.date
        current_time = timezone.now()
        print(f"Current time: {current_time}")
        print(f"Original date before save: {original_date}")

        before = {
            'item_type': withdrawal.item_type,
            'item_id': withdrawal.item_id,
            'quantity': withdrawal.quantity,
            'reason': withdrawal.reason,
            'sales_channel': withdrawal.sales_channel,
            'price_type': withdrawal.price_type,
            'custom_price': str(withdrawal.custom_price),
            'discount_id': withdrawal.discount_id,
            'custom_discount_value': str(withdrawal.custom_discount_value),
            'date': str(original_date),
        }

        # Get form data but don't save yet
        self.object = form.save(commit=False)
        self.object.date = original_date

        # -----------------------------------------
        # ✅ IMPORTANT FIX:
        # RAW MATERIAL withdrawals must NOT have:
        # - sales_channel
        # - price_type
        # - discounts
        # - custom discount
        # -----------------------------------------
        if self.object.item_type == "RAW_MATERIAL":
            self.object.sales_channel = None
            self.object.price_type = None
            self.object.discount = None
            self.object.custom_discount_value = None
            self.object.custom_price = None
        # -----------------------------------------

        old_quantity = before['quantity']
        new_quantity = self.object.quantity
        old_item_id = before['item_id']
        new_item_id = self.object.item_id
        inventory_changed = (old_item_id != new_item_id or old_quantity != new_quantity)

        # Inventory validation
        if inventory_changed:
            try:
                if self.object.item_type == 'PRODUCT':
                    if old_item_id != new_item_id:
                        new_product = Products.objects.get(id=new_item_id)
                        new_inv = new_product.productinventory
                        if new_quantity > new_inv.total_stock:
                            messages.error(self.request,
                                f"⚠️ Insufficient stock for {new_product}. "
                                f"Available: {new_inv.total_stock}, Needed: {new_quantity}")
                            return redirect(self.get_success_url())
                    else:
                        product = Products.objects.get(id=new_item_id)
                        inv = product.productinventory
                        restored_stock = inv.total_stock + old_quantity
                        if new_quantity > restored_stock:
                            messages.error(self.request,
                                f"⚠️ Insufficient stock for {product}. "
                                f"Available after restore: {restored_stock}, Needed: {new_quantity}")
                            return redirect(self.get_success_url())

                elif self.object.item_type == 'RAW_MATERIAL':
                    if old_item_id != new_item_id:
                        new_material = RawMaterials.objects.get(id=new_item_id)
                        new_inv = new_material.rawmaterialinventory
                        if new_quantity > new_inv.total_stock:
                            messages.error(self.request,
                                f"⚠️ Insufficient stock for {new_material}. "
                                f"Available: {new_inv.total_stock}, Needed: {new_quantity}")
                            return redirect(self.get_success_url())
                    else:
                        material = RawMaterials.objects.get(id=new_item_id)
                        inv = material.rawmaterialinventory
                        restored_stock = inv.total_stock + old_quantity
                        if new_quantity > restored_stock:
                            messages.error(self.request,
                                f"⚠️ Insufficient stock for {material}. "
                                f"Available after restore: {restored_stock}, Needed: {new_quantity}")
                            return redirect(self.get_success_url())

            except Exception as e:
                messages.error(self.request, f"❌ Error validating stock: {str(e)}")
                return redirect(self.get_success_url())

        # Set trigger context
        from django.db import connection
        with connection.cursor() as cursor:
            cursor.execute("SET LOCAL app.current_user_id = %s", [self.request.user.id])

        # Save changes (inventory handled by trigger)
        self.object.save(update_fields=[
            'item_id', 'quantity', 'reason',
            'sales_channel', 'price_type',
            'custom_price', 'discount_id',
            'custom_discount_value'
        ])

        if inventory_changed:
            messages.success(self.request,
                "✅ Withdrawal updated successfully! Inventory has been adjusted.")

        withdrawal.refresh_from_db()
        print(f"Date after save: {withdrawal.date}")

        after = {
            'item_type': withdrawal.item_type,
            'item_id': withdrawal.item_id,
            'quantity': str(withdrawal.quantity),
            'reason': withdrawal.reason,
            'sales_channel': withdrawal.sales_channel,
            'price_type': withdrawal.price_type,
            'custom_price': str(withdrawal.custom_price),
            'discount_id': withdrawal.discount_id,
            'custom_discount_value': str(withdrawal.custom_discount_value),
            'date': str(withdrawal.date),
        }

        # Update sales entry if needed
        if (withdrawal.reason == 'SOLD' and
            withdrawal.item_type == 'PRODUCT' and
            withdrawal.sales_channel in ['ORDER', 'CONSIGNMENT', 'RESELLER'] and
            withdrawal.payment_status == 'PAID' and
            withdrawal.price_type in ['UNIT', 'SRP'] and
            withdrawal.order_group_id):

            quantity_changed = before['quantity'] != after['quantity']
            discount_changed = (before['discount_id'] != after['discount_id'] or
                                before['custom_discount_value'] != after['custom_discount_value'])

            if quantity_changed or discount_changed:
                print(f"🔄 Updating sales entry for order #{withdrawal.order_group_id}")

                order_withdrawals = Withdrawals.objects.filter(order_group_id=withdrawal.order_group_id)
                new_total = Decimal(0)

                for w in order_withdrawals:
                    if w.price_type:
                        product = Products.objects.get(id=w.item_id)
                        base_price = product.unit_price.unit_price if w.price_type == 'UNIT' else product.srp_price.srp_price

                        discount_percent = Decimal(0)
                        if w.discount_id:
                            discount = Discounts.objects.get(id=w.discount_id)
                            discount_percent = Decimal(discount.value)
                        elif w.custom_discount_value:
                            discount_percent = Decimal(w.custom_discount_value)

                        discounted_price = base_price * (1 - (discount_percent / 100))
                        item_total = Decimal(w.quantity) * discounted_price
                        new_total += item_total

                sales_entry = Sales.objects.filter(
                    Q(description__icontains=f"Order #{withdrawal.order_group_id}") &
                    Q(description__icontains="Status: PAID"),
                    is_archived=False
                ).first()

                if sales_entry:
                    sales_entry.amount = new_total
                    sales_entry.save()
                    messages.success(self.request,
                        f"✅ Withdrawal and sales entry updated. New total: ₱{new_total:,.2f}")
            else:
                messages.success(self.request, "✅ Withdrawal successfully updated.")
        else:
            messages.success(self.request, "✅ Withdrawal successfully updated.")

        return redirect(self.get_success_url())

    def form_invalid(self, form):
        messages.error(self.request, "❌ Please correct the errors below.")
        return super().form_invalid(form)


class WithdrawDeleteView(DeleteView):
    model = Withdrawals
    success_url = reverse_lazy('withdrawals')

    def post(self, request, *args, **kwargs):
        """Override post to capture data before delete is called"""
        # Capture withdrawal data before deletion
        withdrawal = self.get_object()
        before = {
            'item_type': withdrawal.item_type,
            'item_id': withdrawal.item_id,
            'quantity': str(withdrawal.quantity),
            'reason': withdrawal.reason,
            'sales_channel': withdrawal.sales_channel,
            'price_type': withdrawal.price_type,
        }
        
        withdrawal_id = withdrawal.id
        order_group_id = withdrawal.order_group_id
        reason = withdrawal.reason
        sales_channel = withdrawal.sales_channel
        payment_status = withdrawal.payment_status
        
        # Call parent delete
        response = super().post(request, *args, **kwargs)
        
        # History logging is now handled by PostgreSQL triggers
        # Removed manual create_history_log call to prevent double logging
        
        # Update sales entry if this was part of a PAID/PARTIAL order
        if (reason == 'SOLD' and 
            sales_channel in ['ORDER', 'CONSIGNMENT', 'RESELLER'] and
            payment_status in ['PAID', 'PARTIAL'] and
            order_group_id):
            
            # Check if there are remaining withdrawals in this order
            remaining_withdrawals = Withdrawals.objects.filter(order_group_id=order_group_id)
            
            if remaining_withdrawals.exists():
                # Recalculate total for remaining items
                new_total = Decimal(0)
                
                for w in remaining_withdrawals:
                    if w.custom_price:
                        new_total = Decimal(w.custom_price)
                        break
                    elif w.price_type:
                        product = Products.objects.get(id=w.item_id)
                        base_price = Decimal(0)
                        
                        if w.price_type == 'UNIT':
                            base_price = product.unit_price.unit_price
                        elif w.price_type == 'SRP':
                            base_price = product.srp_price.srp_price
                        
                        discount_percent = Decimal(0)
                        if w.discount_id:
                            discount = Discounts.objects.get(id=w.discount_id)
                            discount_percent = Decimal(discount.value)
                        elif w.custom_discount_value:
                            discount_percent = Decimal(w.custom_discount_value)
                        
                        discounted_price = base_price * (1 - (discount_percent / 100))
                        item_total = Decimal(w.quantity) * discounted_price
                        new_total += item_total
                
                # Update sales entry
                sales_entry = Sales.objects.filter(
                    Q(description__icontains=f"Order #{order_group_id}"),
                    is_archived=False
                ).first()
                
                if sales_entry:
                    sales_entry.amount = new_total
                    sales_entry.save()
                    messages.success(request, f"🗑️ Withdrawal deleted. Sales updated to ₱{new_total:,.2f}")
                else:
                    messages.success(request, "🗑️ Withdrawal deleted successfully.")
            else:
                # No more withdrawals, delete the sales entry
                sales_entry = Sales.objects.filter(
                    Q(description__icontains=f"Order #{order_group_id}"),
                    is_archived=False
                ).first()
                
                if sales_entry:
                    sales_entry.delete()
                    messages.success(request, "🗑️ Withdrawal and sales entry deleted successfully.")
                else:
                    messages.success(request, "🗑️ Withdrawal deleted successfully.")
        
        return response

    def get_success_url(self):
        return reverse_lazy('withdrawals')


# Withdrawal Group Actions
class WithdrawalGroupArchiveView(View):
    """Archive all withdrawals in a group"""
    def post(self, request, order_group_id):
        withdrawals = Withdrawals.objects.filter(order_group_id=order_group_id, is_archived=False)
        count = withdrawals.count()
        
        if count > 0:
            # History logging is now handled by PostgreSQL triggers
            # Removed manual create_history_log calls to prevent double logging
            
            withdrawals.update(is_archived=True)
            messages.success(request, f"✅ Archived {count} withdrawal(s) from Order #{order_group_id}")
        else:
            messages.warning(request, "No withdrawals found to archive.")
        
        return redirect('withdrawals')


class WithdrawalGroupDeleteView(View):
    """Delete all withdrawals in a group"""
    def post(self, request, order_group_id):
        withdrawals = Withdrawals.objects.filter(order_group_id=order_group_id, is_archived=False)
        count = withdrawals.count()
        
        if count > 0:
            # Check if this is a SOLD order with PAID/PARTIAL status
            first_withdrawal = withdrawals.first()
            should_delete_sales = (
                first_withdrawal.reason == 'SOLD' and
                first_withdrawal.sales_channel in ['ORDER', 'CONSIGNMENT', 'RESELLER'] and
                first_withdrawal.payment_status in ['PAID', 'PARTIAL']
            )
            
            # History logging is now handled by PostgreSQL triggers
            # Removed manual create_history_log calls to prevent double logging
            
            # Delete all withdrawals in the group
            withdrawals.delete()
            
            # Delete corresponding sales entry if applicable
            if should_delete_sales:
                sales_entry = Sales.objects.filter(
                    Q(description__icontains=f"Order #{order_group_id}"),
                    is_archived=False
                ).first()
                
                if sales_entry:
                    sales_entry.delete()
                    messages.success(request, f"🗑️ Deleted {count} withdrawal(s) and sales entry from Order #{order_group_id}")
                else:
                    messages.success(request, f"🗑️ Deleted {count} withdrawal(s) from Order #{order_group_id}")
            else:
                messages.success(request, f"🗑️ Deleted {count} withdrawal(s) from Order #{order_group_id}")
        else:
            messages.warning(request, "No withdrawals found to delete.")
        
        return redirect('withdrawals')


class WithdrawalGroupEditView(View):
    """Edit all withdrawals in a group"""
    template_name = "withdrawal_group_edit.html"
    
    def get(self, request, order_group_id):
        withdrawals = Withdrawals.objects.filter(
            order_group_id=order_group_id, 
            is_archived=False
        ).select_related('created_by_admin')
        
        if not withdrawals.exists():
            messages.error(request, "Withdrawal group not found.")
            return redirect('withdrawals')
        
        # Get products and discounts for the form
        products = Products.objects.all().order_by('id').select_related(
            "product_type", "variant", "size", "size_unit", "productinventory"
        )
        discounts = Discounts.objects.all()
        
        # Get first withdrawal for common data
        first_withdrawal = withdrawals.first()
        
        context = {
            'withdrawals': withdrawals,
            'order_group_id': order_group_id,
            'products': products,
            'discounts': discounts,
            'reason': first_withdrawal.reason,
            'sales_channel': first_withdrawal.sales_channel,
            'customer_name': first_withdrawal.customer_name,
            'payment_status': first_withdrawal.payment_status,
        }
        
        return render(request, self.template_name, context)
    
    def post(self, request, order_group_id):
        withdrawals = Withdrawals.objects.filter(
            order_group_id=order_group_id, 
            is_archived=False
        )
        
        if not withdrawals.exists():
            messages.error(request, "Withdrawal group not found.")
            return redirect('withdrawals')
        
        try:
            # Get common fields
            reason = request.POST.get("reason")
            sales_channel = request.POST.get("sales_channel")
            customer_name = request.POST.get("customer_name")
            payment_status = request.POST.get("payment_status", "PAID")
            price_or_custom = request.POST.get("price_or_custom", "").strip().upper()
            paid_amount = request.POST.get("paid_amount")
            
            # Determine if it's price type or custom amount
            price_type = None
            custom_total_price = None
            if price_or_custom in ['UNIT', 'SRP']:
                price_type = price_or_custom
            elif price_or_custom:
                try:
                    custom_total_price = Decimal(price_or_custom)
                except:
                    pass  # Invalid input, ignore
            
            # Track if any changes were made
            updated_count = 0
            
            # Track items to delete
            items_to_delete = []
            
            # Update each withdrawal in the group
            for withdrawal in withdrawals:
                # Check if item should be removed
                remove_key = f"remove_{withdrawal.id}"
                if request.POST.get(remove_key) == '1':
                    items_to_delete.append(withdrawal)
                    continue
                
                # Get the new values for this specific withdrawal
                item_id_key = f"item_id_{withdrawal.id}"
                quantity_key = f"quantity_{withdrawal.id}"
                discount_key = f"discount_{withdrawal.id}"
                
                new_item_id = request.POST.get(item_id_key)
                new_quantity = request.POST.get(quantity_key)
                discount_val = request.POST.get(discount_key)
                
                if new_quantity and new_item_id:
                    new_quantity = Decimal(new_quantity)
                    
                    # Handle pricing based on payment status
                    if payment_status == 'PAID':
                        if custom_total_price:
                            # Custom total price for entire order
                            withdrawal.price_type = None
                            withdrawal.custom_price = Decimal(custom_total_price)
                        elif price_type in ['UNIT', 'SRP']:
                            # Unit/SRP price type (same for all items)
                            withdrawal.price_type = price_type
                            withdrawal.custom_price = None
                        else:
                            withdrawal.price_type = None
                            withdrawal.custom_price = None
                    elif payment_status == 'PARTIAL':
                        # Partial payment - store paid amount
                        withdrawal.price_type = None
                        withdrawal.custom_price = None
                        if paid_amount:
                            withdrawal.paid_amount = Decimal(paid_amount)
                    else:
                        # UNPAID - clear pricing
                        withdrawal.price_type = None
                        withdrawal.custom_price = None
                        withdrawal.paid_amount = None
                    
                    # Handle discount (only for Unit/SRP, not for custom price)
                    discount_obj = None
                    custom_discount = None
                    if discount_val and withdrawal.price_type:  # Only apply discount if price_type is set
                        try:
                            discount_obj = Discounts.objects.get(value=discount_val)
                        except Discounts.DoesNotExist:
                            custom_discount = discount_val
                    else:
                        # Clear discount if custom price
                        withdrawal.discount_id = None
                        withdrawal.custom_discount_value = None
                    
                    # Update withdrawal
                    withdrawal.item_id = int(new_item_id)  # Update item_id
                    withdrawal.quantity = new_quantity
                    withdrawal.reason = reason
                    withdrawal.sales_channel = sales_channel if reason == "SOLD" else None
                    withdrawal.customer_name = customer_name if sales_channel in ['ORDER', 'CONSIGNMENT', 'RESELLER'] else None
                    withdrawal.payment_status = payment_status if sales_channel in ['ORDER', 'CONSIGNMENT', 'RESELLER'] else 'PAID'
                    
                    if discount_obj or custom_discount:
                        withdrawal.discount_id = discount_obj.id if discount_obj else None
                        withdrawal.custom_discount_value = custom_discount
                    
                    if withdrawal.price_type:
                        product = Products.objects.get(id=withdrawal.item_id)
                        base_price = Decimal(0)
                        
                        if withdrawal.price_type == 'UNIT':
                            base_price = product.unit_price.unit_price
                        elif withdrawal.price_type == 'SRP':
                            base_price = product.srp_price.srp_price
                        
                        # Calculate discount
                        discount_percent = Decimal(0)
                        if withdrawal.discount_id:
                            discount = Discounts.objects.get(id=withdrawal.discount_id)
                            discount_percent = Decimal(discount.value)
                        elif withdrawal.custom_discount_value:
                            discount_percent = Decimal(withdrawal.custom_discount_value)
                        
                        # Calculate and store actual prices
                        discount_amount = base_price * (discount_percent / 100)
                        final_price = base_price - discount_amount
                        total = withdrawal.quantity * final_price
                        
                        withdrawal.actual_unit_price = base_price
                        withdrawal.actual_discount_percent = discount_percent
                        withdrawal.actual_discount_amount = discount_amount
                        withdrawal.final_price_per_unit = final_price
                        withdrawal.total_amount = total
                    
                    withdrawal.save()
                    updated_count += 1
            
            # Delete marked items
            deleted_count = 0
            for withdrawal in items_to_delete:
                withdrawal.delete()
                deleted_count += 1
            
            # Handle sales entry based on payment status
            sales_entry = Sales.objects.filter(
                Q(description__icontains=f"Order #{order_group_id}"),
                is_archived=False
            ).first()
            
            if (reason == 'SOLD' and 
                sales_channel in ['ORDER', 'CONSIGNMENT', 'RESELLER']):
                
                if payment_status == 'UNPAID':
                    # Delete sales entry if changing to UNPAID
                    if sales_entry:
                        sales_entry.delete()
                        msg = f"✅ Updated {updated_count} withdrawal(s)"
                        if deleted_count > 0:
                            msg += f", deleted {deleted_count} item(s)"
                        msg += ". Sales entry removed (UNPAID)"
                        messages.success(request, msg)
                    else:
                        msg = f"✅ Updated {updated_count} withdrawal(s)"
                        if deleted_count > 0:
                            msg += f", deleted {deleted_count} item(s)"
                        messages.success(request, msg)
                
                elif payment_status in ['PAID', 'PARTIAL']:
                    # Recalculate total based on payment status
                    new_total = Decimal(0)
                    
                    if payment_status == 'PARTIAL':
                        # Use paid amount for partial payments
                        if paid_amount:
                            new_total = Decimal(paid_amount)
                    elif payment_status == 'PAID':
                        # Calculate from withdrawals
                        for w in withdrawals:
                            if w.custom_price:
                                # Custom price is the TOTAL for the entire order
                                new_total = Decimal(w.custom_price)
                                break  # Stop after first custom price (should only be one)
                            elif w.price_type:
                                # Unit/SRP price with discount
                                product = Products.objects.get(id=w.item_id)
                                base_price = Decimal(0)
                                
                                if w.price_type == 'UNIT':
                                    base_price = product.unit_price.unit_price
                                elif w.price_type == 'SRP':
                                    base_price = product.srp_price.srp_price
                                
                                # Apply discount
                                discount_percent = Decimal(0)
                                if w.discount_id:
                                    discount = Discounts.objects.get(id=w.discount_id)
                                    discount_percent = Decimal(discount.value)
                                elif w.custom_discount_value:
                                    discount_percent = Decimal(w.custom_discount_value)
                                
                                discounted_price = base_price * (1 - (discount_percent / 100))
                                item_total = Decimal(w.quantity) * discounted_price
                                new_total += item_total
                    
                    # Update or create sales entry
                    if sales_entry:
                        sales_entry.amount = new_total
                        sales_entry.save()
                        msg = f"✅ Updated {updated_count} withdrawal(s)"
                        if deleted_count > 0:
                            msg += f", deleted {deleted_count} item(s)"
                        msg += f". Sales updated to ₱{new_total:,.2f}"
                        messages.success(request, msg)
                    else:
                        # Create new sales entry if it doesn't exist
                        Sales.objects.create(
                            amount=new_total,
                            description=f"Order #{order_group_id} - {customer_name or 'N/A'} - Status: {payment_status}",
                            date=timezone.now().date(),
                            created_by_admin=request.user
                        )
                        msg = f"✅ Updated {updated_count} withdrawal(s)"
                        if deleted_count > 0:
                            msg += f", deleted {deleted_count} item(s)"
                        msg += f". Sales entry created: ₱{new_total:,.2f}"
                        messages.success(request, msg)
            else:
                msg = f"✅ Updated {updated_count} withdrawal(s)"
                if deleted_count > 0:
                    msg += f", deleted {deleted_count} item(s)"
                messages.success(request, msg)
            
        except Exception as e:
            messages.error(request, f"❌ Error updating withdrawals: {str(e)}")
        
        return redirect('withdrawals')


def get_total_revenue():
    withdrawals = Withdrawals.objects.filter(item_type="PRODUCT", reason="SOLD")
    total = 0
    for w in withdrawals:
        total += w.compute_revenue()
    return total

    
@require_GET
def get_stock(request):
    item_type = request.GET.get("type")
    item_id = request.GET.get("id")

    if item_type == "PRODUCT":
        inventory = ProductInventory.objects.filter(product_id=item_id).first()
    elif item_type == "RAW_MATERIAL":
        inventory = RawMaterialInventory.objects.filter(material_id=item_id).first()
    else:
        return JsonResponse({"stock": None})

    return JsonResponse({"stock": inventory.total_stock if inventory else 0})

class NotificationsList(ListView):
    model = Notifications
    context_object_name = 'notifications'
    template_name = "notification.html"
    paginate_by = 10

    def get_queryset(self):
        qs = Notifications.objects.filter(is_archived=False).order_by('-notification_timestamp')
        
        # Date filter
        date_filter = self.request.GET.get('date_filter', '').strip()
        show_all = self.request.GET.get('show_all', '').strip()
        category = self.request.GET.get('category', '').strip()
        
        # Apply category filter
        if category:
            if category == 'low_stock':
                qs = qs.filter(notification_type='LOW_STOCK')
            elif category == 'out_of_stock':
                qs = qs.filter(notification_type='OUT_OF_STOCK')
            elif category == 'expired':
                qs = qs.filter(notification_type='EXPIRED_TODAY')
            elif category == 'expire_week':
                qs = qs.filter(notification_type='EXPIRES_IN_WEEK')
            elif category == 'expire_month':
                qs = qs.filter(notification_type='EXPIRES_IN_MONTH')
        
        # Apply date filter
        if date_filter:
            try:
                year_str, month_str = date_filter.split('-')
                year = int(year_str)
                month_num = int(month_str.lstrip('0'))
                qs = qs.filter(notification_timestamp__year=year, notification_timestamp__month=month_num)
            except ValueError:
                pass
        elif not show_all:
            # Default to current month
            today = timezone.now()
            qs = qs.filter(notification_timestamp__year=today.year, notification_timestamp__month=today.month)
        
        return qs
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Add current month value for default display
        today = timezone.now()
        context['current_month_value'] = today.strftime("%Y-%m")
        return context

    def get(self, request, *args, **kwargs):
        # Mark all as read
        Notifications.objects.filter(is_read=False).update(is_read=True)
        
        # Handle pagination - if page doesn't exist, redirect to page 1 with same filters
        try:
            return super().get(request, *args, **kwargs)
        except Exception as e:
            if 'Invalid page' in str(e) or 'That page contains no results' in str(e):
                # Preserve all query parameters except page
                from django.shortcuts import redirect
                params = request.GET.copy()
                params['page'] = '1'
                return redirect(f"{request.path}?{params.urlencode()}")
            raise

# NotificationsDeleteView removed - notifications should not be deleted


class BulkProductBatchCreateView(View):
    template_name = "prodbatch_add.html"

    def get(self, request):
        form = BulkProductBatchForm()
        return render(request, self.template_name, {
            'form': form,
            'products': form.products
        })

    def post(self, request):
        form = BulkProductBatchForm(request.POST)

        if not form.is_valid():
            return render(request, self.template_name, {
                'form': form,
                'products': form.products
            })

        batch_date = timezone.localdate()
        default_manufactured = form.cleaned_data.get('manufactured_date') or timezone.localdate()
        default_expiration = form.cleaned_data.get('expiration_date')
        auth_user = get_or_create_auth_user(request.user)

        try:
            with transaction.atomic():
                added_any = False

                for product_info in form.products:
                    product = product_info['product']
                    qty = form.cleaned_data.get(f'product_{product.id}_qty')

                    if not qty or float(qty) <= 0:
                        continue

                    manufactured_field_name = f'product_{product.id}_manufactured'
                    expiration_field_name = f'product_{product.id}_expiration'
                    packaging_field_name = f'product_{product.id}_packaging'

                    manufactured_date = form.cleaned_data.get(manufactured_field_name) or default_manufactured
                    expiration_date = form.cleaned_data.get(expiration_field_name) or default_expiration
                    packaging_id = form.cleaned_data.get(packaging_field_name)

                    product_code = (product.product_code or '').strip().upper()
                    if not product_code:
                        raise ValueError(f"❌ Product '{product}' is missing a product code. Please set one before creating batches.")

                    batch_code = f"{manufactured_date.strftime('%m%d%y')}{product_code}"

                    # Validate packaging stock BEFORE creating batch (trigger will handle deduction)
                    if packaging_id:
                        try:
                            from .models import RawMaterialInventory, RawMaterials
                            raw_material = RawMaterials.objects.get(id=packaging_id)
                            raw_material_inventory = RawMaterialInventory.objects.get(material=raw_material)

                            # Check if enough stock is available
                            from decimal import Decimal
                            qty_decimal = Decimal(str(qty))
                            if raw_material_inventory.total_stock < qty_decimal:
                                raise ValueError(f"Not enough stock for {raw_material.name}. Available: {raw_material_inventory.total_stock}, Required: {qty}")
                        except RawMaterials.DoesNotExist:
                            raise ValueError(f"Selected packaging material not found.")
                        except RawMaterialInventory.DoesNotExist:
                            raise ValueError(f"Packaging inventory not found for {raw_material.name}.")

                    ProductBatches.objects.create(
                        product=product,
                        quantity=qty,
                        batch_date=batch_date,
                        manufactured_date=manufactured_date,
                        expiration_date=expiration_date,
                        batch_code=batch_code,
                        created_by_admin=auth_user,
                        packaging_id=packaging_id,  # Store the packaging ID
                    )
                    
                    added_any = True

                if not added_any:
                    raise ValueError("⚠️ No product quantities were entered.")

        except Exception as e:
            error_message = str(e)

            if "Not enough stock" in error_message:
                error_message = error_message.split("CONTEXT:")[0].strip()
            elif "insufficient" in error_message.lower():
                error_message = "❌ Insufficient raw materials to create this batch."
            elif "No product quantities" in error_message:
                error_message = "⚠️ No product quantities were entered."
            else:
                error_message = f"❌ {error_message}"

            messages.error(request, error_message)

            return render(request, self.template_name, {
                'form': form,
                'products': form.products
            })

        messages.success(request, "✅ Product Batch added successfully.")
        return redirect("product-batch")


class BulkRawMaterialBatchCreateView(LoginRequiredMixin, View):
    template_name = "rawmatbatch_add.html"

    def get(self, request):
        category = request.GET.get('category', 'PACKAGING')
        form = BulkRawMaterialBatchForm(initial={'category': category})
        return render(request, self.template_name, {'form': form, 'raw_materials': form.rawmaterials})

    def get_queryset(self):
        queryset = (
            super()
            .order_by('material_id')
        )

    def post(self, request):
        form = BulkRawMaterialBatchForm(request.POST)
        if form.is_valid():
            batch_date = timezone.localdate()
            received_date = form.cleaned_data['received_date']
            auth_user = get_or_create_auth_user(request.user)

            for rawmaterial_info in form.rawmaterials:
                rawmaterial = rawmaterial_info['rawmaterial']
                qty = form.cleaned_data.get(f'rawmaterial_{rawmaterial.id}_qty')

                if qty:
                    RawMaterialBatches.objects.create(
                        material=rawmaterial,
                        quantity=qty,
                        batch_date=batch_date,
                        received_date=received_date,
                        created_by_admin=auth_user
                    )

            return redirect('rawmaterial-batch')

        return render(request, self.template_name, {'form': form, 'raw_materials': form.rawmaterials})

@login_required
def profile_view(request):
    return render(request, "profile.html")

@login_required
def download_my_data(request):
    """
    Generate and download a CSV file containing all user data
    """
    import csv
    from io import StringIO
    
    user = request.user
    # Convert Django User to AuthUser for querying
    auth_user = AuthUser.objects.get(id=user.id)
    
    # Create CSV in memory
    output = StringIO()
    writer = csv.writer(output)
    
    # Write header
    writer.writerow(['=== MY DATA EXPORT ==='])
    writer.writerow([f'Generated: {timezone.now().strftime("%B %d, %Y at %I:%M %p")}'])
    writer.writerow([])
    
    # Account Information Section
    writer.writerow(['ACCOUNT INFORMATION'])
    writer.writerow(['Field', 'Value'])
    writer.writerow(['Username', user.username])
    writer.writerow(['Email', user.email])
    writer.writerow(['First Name', user.first_name or 'Not set'])
    writer.writerow(['Last Name', user.last_name or 'Not set'])
    writer.writerow(['Staff Status', 'Yes' if user.is_staff else 'No'])
    writer.writerow(['Administrator', 'Yes' if user.is_superuser else 'No'])
    writer.writerow(['Account Active', 'Yes' if user.is_active else 'No'])
    writer.writerow(['Date Joined', user.date_joined.strftime('%B %d, %Y') if user.date_joined else 'N/A'])
    writer.writerow(['Last Login', user.last_login.strftime('%B %d, %Y at %I:%M %p') if user.last_login else 'Never'])
    writer.writerow([])
    
    # Two-Factor Authentication Section
    writer.writerow(['TWO-FACTOR AUTHENTICATION'])
    writer.writerow(['Field', 'Value'])
    try:
        if hasattr(user, 'twofa_settings'):
            writer.writerow(['2FA Enabled', 'Yes' if user.twofa_settings.is_enabled else 'No'])
            writer.writerow(['Method', user.twofa_settings.method or 'N/A'])
            writer.writerow(['Backup Email', user.twofa_settings.backup_email or 'Not set'])
        else:
            writer.writerow(['2FA Enabled', 'No'])
    except:
        writer.writerow(['2FA Enabled', 'No'])
    writer.writerow([])
    
    # User Activity Section
    writer.writerow(['USER ACTIVITY'])
    writer.writerow(['Field', 'Value'])
    try:
        if hasattr(user, 'useractivity'):
            writer.writerow(['Last Logout', user.useractivity.last_logout.strftime('%B %d, %Y at %I:%M %p') if user.useractivity.last_logout else 'N/A'])
            writer.writerow(['Currently Active', 'Yes' if user.useractivity.active else 'No'])
        else:
            writer.writerow(['Activity Tracking', 'Not available'])
    except:
        writer.writerow(['Activity Tracking', 'Not available'])
    writer.writerow([])
    
    # Products Created
    writer.writerow(['PRODUCTS CREATED'])
    try:
        products = Products.objects.filter(created_by_admin=auth_user)
        if products.exists():
            writer.writerow(['ID', 'Name', 'Barcode', 'Created At'])
            for product in products:
                writer.writerow([
                    product.id,
                    str(product),
                    product.barcode or 'N/A',
                    product.date_created.strftime('%B %d, %Y') if hasattr(product, 'date_created') and product.date_created else 'N/A'
                ])
        else:
            writer.writerow(['No products created'])
    except Exception as e:
        writer.writerow([f'Error retrieving products: {str(e)}'])
    writer.writerow([])
    
    # Raw Materials Created
    writer.writerow(['RAW MATERIALS CREATED'])
    try:
        raw_materials = RawMaterials.objects.filter(created_by_admin=auth_user)
        if raw_materials.exists():
            writer.writerow(['ID', 'Name', 'Created At'])
            for rm in raw_materials:
                writer.writerow([
                    rm.id,
                    rm.name,
                    rm.date_created.strftime('%B %d, %Y') if hasattr(rm, 'date_created') and rm.date_created else 'N/A'
                ])
        else:
            writer.writerow(['No raw materials created'])
    except Exception as e:
        writer.writerow([f'Error retrieving raw materials: {str(e)}'])
    writer.writerow([])
    
    # Sales Created
    writer.writerow(['SALES RECORDS CREATED'])
    try:
        sales = Sales.objects.filter(created_by_admin=auth_user)
        if sales.exists():
            writer.writerow(['ID', 'Date', 'Amount'])
            for sale in sales:
                writer.writerow([
                    sale.id,
                    sale.date.strftime('%B %d, %Y') if sale.date else 'N/A',
                    f'₱{float(sale.amount):,.2f}' if sale.amount else '₱0.00'
                ])
        else:
            writer.writerow(['No sales records created'])
    except Exception as e:
        writer.writerow([f'Error retrieving sales: {str(e)}'])
    writer.writerow([])
    
    # Expenses Created
    writer.writerow(['EXPENSE RECORDS CREATED'])
    try:
        expenses = Expenses.objects.filter(created_by_admin=auth_user)
        if expenses.exists():
            writer.writerow(['ID', 'Date', 'Amount', 'Description'])
            for expense in expenses:
                writer.writerow([
                    expense.id,
                    expense.date.strftime('%B %d, %Y') if expense.date else 'N/A',
                    f'₱{float(expense.amount):,.2f}' if expense.amount else '₱0.00',
                    expense.description if hasattr(expense, 'description') else 'N/A'
                ])
        else:
            writer.writerow(['No expense records created'])
    except Exception as e:
        writer.writerow([f'Error retrieving expenses: {str(e)}'])
    writer.writerow([])
    
    # Withdrawals Created
    writer.writerow(['WITHDRAWAL RECORDS CREATED'])
    try:
        withdrawals = Withdrawals.objects.filter(created_by_admin=user)
        if withdrawals.exists():
            writer.writerow(['ID', 'Date', 'Item Type', 'Quantity', 'Reason'])
            for withdrawal in withdrawals:
                writer.writerow([
                    withdrawal.id,
                    withdrawal.date.strftime('%B %d, %Y at %I:%M %p') if withdrawal.date else 'N/A',
                    withdrawal.item_type,
                    float(withdrawal.quantity) if withdrawal.quantity else 0,
                    withdrawal.reason
                ])
        else:
            writer.writerow(['No withdrawal records created'])
    except Exception as e:
        writer.writerow([f'Error retrieving withdrawals: {str(e)}'])
    writer.writerow([])
    
    # Product Batches Created
    writer.writerow(['PRODUCT BATCHES CREATED'])
    try:
        product_batches = ProductBatches.objects.filter(created_by_admin=auth_user)
        if product_batches.exists():
            writer.writerow(['ID', 'Product', 'Quantity', 'Batch Date'])
            for batch in product_batches:
                writer.writerow([
                    batch.id,
                    str(batch.product) if batch.product else 'N/A',
                    batch.quantity if hasattr(batch, 'quantity') else 'N/A',
                    batch.batch_date.strftime('%B %d, %Y') if hasattr(batch, 'batch_date') and batch.batch_date else 'N/A'
                ])
        else:
            writer.writerow(['No product batches created'])
    except Exception as e:
        writer.writerow([f'Error retrieving product batches: {str(e)}'])
    writer.writerow([])
    
    # Raw Material Batches Created
    writer.writerow(['RAW MATERIAL BATCHES CREATED'])
    try:
        rm_batches = RawMaterialBatches.objects.filter(created_by_admin=auth_user)
        if rm_batches.exists():
            writer.writerow(['ID', 'Material', 'Quantity', 'Batch Date'])
            for batch in rm_batches:
                writer.writerow([
                    batch.id,
                    str(batch.material) if batch.material else 'N/A',
                    batch.quantity if hasattr(batch, 'quantity') else 'N/A',
                    batch.batch_date.strftime('%B %d, %Y') if hasattr(batch, 'batch_date') and batch.batch_date else 'N/A'
                ])
        else:
            writer.writerow(['No raw material batches created'])
    except Exception as e:
        writer.writerow([f'Error retrieving raw material batches: {str(e)}'])
    
    # Create CSV response
    response = HttpResponse(output.getvalue(), content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="my_data_{user.username}_{timezone.now().strftime("%Y%m%d_%H%M%S")}.csv"'
    
    return response

def best_sellers_api(request):
    from datetime import datetime
    TOP_N = 5
    
    year = request.GET.get('year')
    month = request.GET.get('month')

    now = datetime.now()
    if not year:
        year = now.year
    if not month:
        month = now.month

    qs = Withdrawals.objects.filter(item_type="PRODUCT", reason="SOLD")
  
    if month and month != 'all':
        qs = qs.filter(date__year=year, date__month=month)
    else:
        qs = qs.filter(date__year=year)
    
    qs = (
        qs.values("item_id")
        .annotate(total_sold=Sum("quantity"))
        .order_by("-total_sold")
    )

    sold_list = list(qs)
    product_ids = [item["item_id"] for item in sold_list]
    products = Products.objects.in_bulk(product_ids)

    labels, data = [], []
    for item in sold_list[:TOP_N]: 
        prod = products.get(item["item_id"])
        labels.append(str(prod) if prod else f"Unknown {item['item_id']}")
        data.append(float(item["total_sold"]))

    return JsonResponse({"labels": labels, "data": data})

def mark_notification_read(request, pk):
    notif = get_object_or_404(Notifications, pk=pk)
    notif.is_read = True
    notif.save()
    return redirect('notifications')


class StockChangesList(ListView):
    model = StockChanges
    context_object_name = 'stock_changes'
    template_name = "stock_changes.html"
    paginate_by = 10

    def get_queryset(self):
        qs = StockChanges.objects.filter(is_archived=False).order_by('-date')
        
        # Check for show_all parameter
        show_all = self.request.GET.get('show_all', '').strip()
        
        if not show_all:
            # Check for date filter
            date_filter = self.request.GET.get('date_filter', '').strip()
            
            if date_filter:
                try:
                    parsed_date = datetime.strptime(date_filter, "%Y-%m")
                    qs = qs.filter(date__year=parsed_date.year, date__month=parsed_date.month)
                except ValueError:

                    today = timezone.now()
                    qs = qs.filter(date__year=today.year, date__month=today.month)
            else:

                today = timezone.now()
                qs = qs.filter(date__year=today.year, date__month=today.month)
        
        return qs
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = timezone.now()
        context['current_month_value'] = today.strftime("%Y-%m")
        return context


@require_GET
@login_required
def export_stock_changes(request):
    qs = StockChanges.objects.filter(is_archived=False).order_by('-date')
    
    show_all = request.GET.get('show_all', '').strip()
    date_filter = request.GET.get('date_filter', '').strip()
    
    if not show_all:
        if date_filter:
            try:
                parsed_date = datetime.strptime(date_filter, "%Y-%m")
                qs = qs.filter(date__year=parsed_date.year, date__month=parsed_date.month)
            except ValueError:
                today = timezone.now()
                qs = qs.filter(date__year=today.year, date__month=today.month)
        else:
            today = timezone.now()
            qs = qs.filter(date__year=today.year, date__month=today.month)
    
    response = HttpResponse(content_type='text/csv')
    any_filter = bool(date_filter if not show_all else False)
    suffix = 'filtered' if any_filter else ('all' if show_all else 'current_month')
    response['Content-Disposition'] = f'attachment; filename="stock_changes_{suffix}.csv"'
    
    writer = csv.writer(response)
    writer.writerow(['Exported At', timezone.now().strftime('%Y-%m-%d %H:%M:%S')])
    writer.writerow(['Filters', f"show_all={show_all}", f"date_filter={date_filter if not show_all else ''}"])
    writer.writerow(['Total Records', qs.count()])
    writer.writerow([])
    
    writer.writerow(['Item Type', 'Item ID', 'Item Display', 'Quantity Change', 'Category', 'Date & Time'])
    for item in qs:
        writer.writerow([
            item.item_type,
            item.item_id,
            item.item_display,
            f"{item.quantity_change:.2f}",
            item.category,
            item.date.strftime('%Y-%m-%d %H:%M:%S'),
        ])
    
    return response

class StockChangesArchiveView(View):
    def post(self, request, pk):
        stock_change = get_object_or_404(StockChanges, pk=pk)
        
        # Set current user for trigger
        from django.db import connection
        with connection.cursor() as cursor:
            cursor.execute("SET LOCAL app.current_user_id = %s", [request.user.id])
        
        stock_change.is_archived = True
        stock_change.save()  # Trigger will handle logging
        messages.success(request, "📦 Stock change archived successfully.")
        page = request.GET.get('page')
        if page:
            return redirect(f"{reverse('stock-changes')}?page={page}")
        return redirect('stock-changes')

@require_http_methods(["POST"])
def stock_changes_bulk_archive(request):
    try:
        ids = request.POST.get('ids', '').split(',')
        ids = [int(id.strip()) for id in ids if id.strip()]
        
        if not ids:
            return JsonResponse({'success': False, 'message': 'No stock changes selected'})
        
        # Set current user for trigger
        from django.db import connection
        with connection.cursor() as cursor:
            cursor.execute("SET LOCAL app.current_user_id = %s", [request.user.id])
        
        archived_count = StockChanges.objects.filter(id__in=ids).update(is_archived=True)
        return JsonResponse({
            'success': True,
            'message': f'Successfully archived {archived_count} stock change(s)'
        })
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)})

class ArchivedStockChangesListView(ListView):
    model = StockChanges
    template_name = 'archived_stock_changes.html'
    context_object_name = 'object_list'
    paginate_by = 10

    def get_queryset(self):
        return StockChanges.objects.filter(is_archived=True).order_by('-date')


class StockChangesUnarchiveView(View):
    def post(self, request, pk):
        stock_change = get_object_or_404(StockChanges, pk=pk)
        stock_change.is_archived = False
        stock_change.save()
        messages.success(request, "✅ Stock change restored successfully.")
        return redirect('stock-changes-archived-list')


class StockChangesBulkRestoreView(View):
    def post(self, request):
        import json
        try:
            stock_change_ids = json.loads(request.POST.get('stock_change_ids', '[]'))
            if not stock_change_ids:
                return JsonResponse({'success': False, 'message': 'No stock changes selected'})
            
            # Restore selected stock changes
            count = StockChanges.objects.filter(id__in=stock_change_ids, is_archived=True).update(is_archived=False)
            
            return JsonResponse({'success': True, 'count': count, 'message': f'{count} stock change(s) restored successfully!'})
        except Exception as e:
            return JsonResponse({'success': False, 'message': str(e)})


class StockChangesArchiveOldView(View):
    def post(self, request):
        from datetime import timedelta
        one_year_ago = timezone.now() - timedelta(days=365)
        archived_count = StockChanges.objects.filter(is_archived=False, date__lt=one_year_ago).update(is_archived=True)
        messages.success(request, f"📦 {archived_count} stock change(s) older than 1 year have been archived.")
        return redirect('stock-changes')

def mask_email(email):
    """Mask email address for privacy: john@example.com -> j***@example.com"""
    if not email or '@' not in email:
        return email
    
    local, domain = email.split('@', 1)
    if len(local) <= 1:
        masked_local = local + '*'
    else:
        masked_local = local[0] + '*'
    
    return f"{masked_local}@{domain}"

def get_device_fingerprint(request):
    """Create unique device ID from browser characteristics"""
    import hashlib
    
    user_agent = request.META.get('HTTP_USER_AGENT', '')
    accept_language = request.META.get('HTTP_ACCEPT_LANGUAGE', '')
    accept_encoding = request.META.get('HTTP_ACCEPT_ENCODING', '')
    
    fingerprint_string = f"{user_agent}{accept_language}{accept_encoding}"
    return hashlib.sha256(fingerprint_string.encode()).hexdigest()


def get_device_info(request):
    """Extract human-readable device details"""
    user_agent = request.META.get('HTTP_USER_AGENT', '')
    
    # Detect browser
    if 'Chrome' in user_agent and 'Edg' not in user_agent:
        browser = 'Chrome'
    elif 'Firefox' in user_agent:
        browser = 'Firefox'
    elif 'Safari' in user_agent and 'Chrome' not in user_agent:
        browser = 'Safari'
    elif 'Edg' in user_agent:
        browser = 'Edge'
    else:
        browser = 'Unknown'
    
    # Detect OS
    if 'Windows' in user_agent:
        os = 'Windows'
    elif 'Mac' in user_agent:
        os = 'macOS'
    elif 'Linux' in user_agent:
        os = 'Linux'
    elif 'Android' in user_agent:
        os = 'Android'
    elif 'iPhone' in user_agent or 'iPad' in user_agent:
        os = 'iOS'
    else:
        os = 'Unknown'
    
    return {
        'browser': browser,
        'os': os,
        'device_name': f"{os} - {browser}"
    }


def send_login_notification(user, device_info, ip_address, is_new_device=False):
    """Send email notification about login"""
    from django.core.mail import send_mail
    from django.conf import settings
    from django.utils import timezone
    
    if is_new_device:
        subject = '🔐 New Device Verified - Real\'s Food Products'
        message = f'''Hello {user.username},

A new device has been verified for your account.

Device: {device_info['device_name']}
IP Address: {ip_address}
Time: {timezone.now().strftime('%B %d, %Y at %I:%M %p')}

This device is now trusted and will not require OTP for future logins.

If this wasn't you, please secure your account immediately.

Real's Food Products Security Team'''
    else:
        subject = '✅ Login Notification - Real\'s Food Products'
        message = f'''Hello {user.username},

You recently logged in to your account.

Device: {device_info['device_name']}
IP Address: {ip_address}
Time: {timezone.now().strftime('%B %d, %Y at %I:%M %p')}

This login was from a trusted device.

If this wasn't you, please secure your account immediately.

Real's Food Products Security Team'''
    
    try:
        send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            fail_silently=True,
        )
    except Exception as e:
        pass

def login_view(request):
    if request.method == 'POST':
        if 'otp_code' in request.POST:
            user_id = request.session.get('2fa_user_id')
            if not user_id:
                messages.error(request, "Session expired. Please login again.")
                return redirect('login')
            
            from realsproj.models import UserOTP, User2FASettings, TrustedDevice, LoginAttempt
            from django.utils import timezone
            from datetime import timedelta
            
            try:
                user = User.objects.get(id=user_id)
                otp_code = request.POST.get('otp_code', '').strip()
                
                # Clean up expired OTPs first
                UserOTP.objects.filter(
                    user=user,
                    expires_at__lt=timezone.now()
                ).delete()
                
                otp = UserOTP.objects.filter(
                    user=user,
                    otp_code=otp_code,
                    is_used=False,
                    expires_at__gt=timezone.now()
                ).first()
                
                if otp:
                    otp.is_used = True
                    otp.save()
                    
                    device_fingerprint = get_device_fingerprint(request)
                    device_info = get_device_info(request)
                    ip_address = request.META.get('REMOTE_ADDR', '0.0.0.0')
                    
                    TrustedDevice.objects.get_or_create(
                        user=user,
                        device_fingerprint=device_fingerprint,
                        defaults={
                            'device_name': device_info['device_name'],
                            'browser': device_info['browser'],
                            'os': device_info['os'],
                            'ip_address': ip_address,
                        }
                    )
                    
                    LoginAttempt.objects.create(
                        user=user,
                        username=user.username,
                        ip_address=ip_address,
                        device_fingerprint=device_fingerprint,
                        browser=device_info['browser'],
                        os=device_info['os'],
                        success=True,
                        required_otp=True,
                        is_trusted_device=True
                    )
                    
                    send_login_notification(user, device_info, ip_address, is_new_device=True)
                    
                    # Get remember me setting from session
                    remember_me = request.session.get('remember_me', False)
                    del request.session['2fa_user_id']
                    if 'remember_me' in request.session:
                        del request.session['remember_me']
                    
                    login(request, user)
                    
                    # Set session expiry based on remember me
                    if remember_me:
                        request.session.set_expiry(2592000)  # 30 days in seconds
                    else:
                        request.session.set_expiry(0)  # Expire on browser close
                    
                    messages.success(request, "✅ Successfully logged in! This device is now trusted.")
                    return redirect('home')
                else:
                    messages.error(request, "❌ Invalid or expired OTP code.")
                    return render(request, '2fa_verify.html', {'user_email': user.email})
            except Exception as e:
                messages.error(request, f"An error occurred: {str(e)}")
                return render(request, '2fa_verify.html')
        
        username = request.POST.get('username', '')
        password = request.POST.get('password', '')
                
        # Check for login lockout
        from realsproj.models import LoginAttempt
        from django.utils import timezone
        from datetime import timedelta
        
        ip_address = request.META.get('REMOTE_ADDR', '0.0.0.0')
        lockout_duration = timedelta(minutes=5)
        max_attempts = 5
        
        # Check failed attempts in the last 5 minutes from this IP address (regardless of username)
        # This prevents someone from trying random usernames
        recent_failed_attempts = LoginAttempt.objects.filter(
            ip_address=ip_address,
            success=False,
            timestamp__gte=timezone.now() - lockout_duration
        ).count()
        
        if recent_failed_attempts >= max_attempts:
            # Get the time of the last failed attempt (reuse the same query)
            last_attempt = LoginAttempt.objects.filter(
                ip_address=ip_address,
                success=False,
                timestamp__gte=timezone.now() - lockout_duration
            ).order_by('-timestamp').first()
            
            if last_attempt:
                time_remaining = (last_attempt.timestamp + lockout_duration) - timezone.now()
                minutes_remaining = int(time_remaining.total_seconds() / 60)
                seconds_remaining = int(time_remaining.total_seconds() % 60)
                
                if minutes_remaining > 0:
                    messages.error(request, f"🔒 Too many failed login attempts. Please try again in {minutes_remaining} minute(s) and {seconds_remaining} second(s).")
                else:
                    messages.error(request, f"🔒 Too many failed login attempts. Please try again in {seconds_remaining} second(s).")
                return render(request, 'login.html')
        
        user = authenticate(request, username=username, password=password)

        if user is not None:
            if user.is_active:
                from realsproj.models import UserOTP, TrustedDevice, LoginAttempt
                import random
                from datetime import timedelta
                from django.utils import timezone
                from django.core.mail import send_mail
                from django.conf import settings
                
                device_fingerprint = get_device_fingerprint(request)
                device_info = get_device_info(request)
                ip_address = request.META.get('REMOTE_ADDR', '0.0.0.0')
                
                # Check if this is a trusted device (for ALL users, not just 2FA enabled)
                trusted_device = TrustedDevice.objects.filter(
                    user=user,
                    device_fingerprint=device_fingerprint,
                    is_active=True
                ).first()
                                
                if trusted_device:
                    # Trusted device - login directly
                    trusted_device.last_used = timezone.now()
                    trusted_device.save()
                    
                    LoginAttempt.objects.create(
                        user=user,
                        username=user.username,
                        ip_address=ip_address,
                        device_fingerprint=device_fingerprint,
                        browser=device_info['browser'],
                        os=device_info['os'],
                        success=True,
                        required_otp=False,
                        is_trusted_device=True
                    )
                    
                    # Send login notification asynchronously to avoid blocking login
                    try:
                        from threading import Thread
                        Thread(target=send_login_notification, args=(user, device_info, ip_address, False)).start()
                    except Exception:
                        pass  # Don't block login if notification fails
                    
                    login(request, user)
                    
                    remember_me = request.POST.get('remember', False)
                    if remember_me:
                        request.session.set_expiry(2592000)  
                    else:
                        request.session.set_expiry(0)  
                    
                    messages.success(request, f" Welcome back! Logged in from trusted device.")
                    return redirect('home')
                else:
                    # New device - require OTP for account confirmation
                    otp_code = str(random.randint(100000, 999999))
                    
                    UserOTP.objects.create(
                        user=user,
                        otp_code=otp_code,
                        expires_at=timezone.now() + timedelta(minutes=10),  # Extended to 10 minutes
                        ip_address=ip_address
                    )
                    
                    # Send OTP email asynchronously to avoid blocking login
                    def send_otp_email():
                        try:
                            send_mail(
                                subject='🔐 Account Confirmation Required - Real\'s Food Products',
                                message=f'Hello {user.username},\n\nWe need to confirm your account for security purposes.\n\nYour confirmation code is: {otp_code}\n\nThis code will expire in 10 minutes.\n\nPlease enter this code to complete your login.\n\nReal\'s Food Products Security Team',
                                from_email=settings.DEFAULT_FROM_EMAIL,
                                recipient_list=[user.email],
                                fail_silently=False,
                            )
                            print(f"[OTP EMAIL] Successfully sent OTP to {user.email}")
                        except Exception as e:
                            print(f"[OTP EMAIL ERROR] Failed to send OTP email: {str(e)}")
                    
                    # Send email in background thread
                    try:
                        from threading import Thread
                        Thread(target=send_otp_email).start()
                    except Exception as e:
                        print(f"[THREAD ERROR] Failed to start email thread: {str(e)}")
                        messages.error(request, "Failed to send confirmation email. Please contact support.")  

                    LoginAttempt.objects.create(
                        user=user,
                        username=user.username,
                        ip_address=ip_address,
                        device_fingerprint=device_fingerprint,
                        browser=device_info['browser'],
                        os=device_info['os'],
                        success=False,
                        required_otp=True,
                        is_trusted_device=False
                    )
                    
                    request.session['2fa_user_id'] = user.id
                    remember_me = request.POST.get('remember', False)
                    request.session['remember_me'] = bool(remember_me)
                    
                    masked_email = mask_email(user.email)
                    messages.info(request, f" Account confirmation required! OTP sent to {masked_email}")
                    return render(request, '2fa_verify.html', {'user_email': masked_email})
            else:
                 # Record failed attempt for inactive account
                device_info = get_device_info(request)
                LoginAttempt.objects.create(
                    user=user,
                    username=username,
                    ip_address=ip_address,
                    device_fingerprint=get_device_fingerprint(request),
                    browser=device_info['browser'],
                    os=device_info['os'],
                    success=False,
                    required_otp=False,
                    is_trusted_device=False
                )
                messages.error(request, "❌ Your account is inactive. Please contact the administrator.")
                return render(request, 'login.html')
        else:
            # Record failed login attempt
            device_info = get_device_info(request)
            LoginAttempt.objects.create(
                user=None,
                username=username,
                ip_address=ip_address,
                device_fingerprint=get_device_fingerprint(request),
                browser=device_info['browser'],
                os=device_info['os'],
                success=False,
                required_otp=False,
                is_trusted_device=False
            )
            
            # Check how many attempts remain (based on IP address only)
            attempts_count = LoginAttempt.objects.filter(
                ip_address=ip_address,
                success=False,
                timestamp__gte=timezone.now() - lockout_duration
            ).count()
            
            attempts_remaining = max_attempts - attempts_count
            
            if attempts_remaining > 0:
                messages.error(request, f"❌ Invalid username or password. {attempts_remaining} attempt(s) remaining.")
            else:
                messages.error(request, f"🔒 Too many failed login attempts. Please wait again after 5 minutes.")
            
            return render(request, 'login.html')
    return render(request, 'login.html')

def register(request):
    if request.method == 'POST':
        form = CustomUserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            
            # Send email notification to user
            from django.core.mail import send_mail
            from django.conf import settings
            
            try:
                send_mail(
                    subject='📝 Registration Pending Approval - Real\'s Food Products',
                    message=f'''Hello {user.username},

Thank you for registering at Real's Food Products Inventory System!

Your account has been created and is currently pending approval from an administrator.

Account Details:
- Username: {user.username}
- Email: {user.email}
- Name: {user.first_name} {user.last_name}

You will receive another email once your account has been approved. After approval, you can log in using your username and password.

If you have any questions, please contact the administrator.

Real's Food Products Team''',
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[user.email],
                    fail_silently=True,
                )
            except Exception as e:
                pass
            
            # Don't auto-login inactive users
            messages.success(request, 'Your account has been created successfully! Please check your email and wait for admin approval before you can log in.')
            return redirect('login')  
        # If form is invalid, just re-render with errors (no generic message needed)
    else:
        form = CustomUserCreationForm() 

    return render(request, 'registration/register.html', {'form': form})

@login_required
def user_management(request):
    """Admin page to manage pending user registrations"""
    if not request.user.is_superuser:
        messages.error(request, "You don't have permission to access this page.")
        return redirect('home')
    
    # Get all inactive users (pending approval) - exclude rejected/deleted users
    from django.db.models import Q
    from django.core.paginator import Paginator
    
    pending_users = User.objects.filter(
        is_active=False
    ).exclude(
        Q(username__startswith='rejected_user_') | Q(username__startswith='deleted_user_') | Q(username__startswith='inactive_user_')
    ).order_by('-date_joined')
    
    # Get all active users - exclude deleted/inactive users
    active_users_queryset = User.objects.filter(
        is_active=True
    ).exclude(
        Q(username__startswith='rejected_user_') | Q(username__startswith='deleted_user_') | Q(username__startswith='inactive_user_')
    ).order_by('-date_joined')
    
    # Paginate active users - 5 per page
    active_paginator = Paginator(active_users_queryset, 5)
    active_page_number = request.GET.get('page', 1)
    active_users = active_paginator.get_page(active_page_number)
    
    # Get inactive users (deactivated by admin)
    inactive_users_raw = User.objects.filter(
        username__startswith='inactive_user_'
    ).order_by('-date_joined')
    
    inactive_users = []
    for user in inactive_users_raw:
        if user.first_name and 'ORIGINAL_USERNAME:' in user.first_name:
            parts = user.first_name.split('|')
            display_username = parts[0].replace('ORIGINAL_USERNAME:', '')
        else:
            display_username = f"User ID {user.id}"
    
        if user.last_name and 'ORIGINAL_EMAIL:' in user.last_name:
            parts = user.last_name.split('|')
            display_email = parts[0].replace('ORIGINAL_EMAIL:', '')
        else:
            display_email = user.email
        
        user.display_username = display_username
        user.display_email = display_email
        inactive_users.append(user)

     # Get rejected users (rejected during registration)
    rejected_users = User.objects.filter(
        username__startswith='rejected_user_'
    ).order_by('-date_joined')
    
    # Get deleted users (soft deleted)
    deleted_users_queryset = User.objects.filter(
        username__startswith='deleted_user_'
    ).order_by('-date_joined')
    
    # Paginate deleted users - 5 per page
    deleted_paginator = Paginator(deleted_users_queryset, 5)
    deleted_page_number = request.GET.get('page', 1)
    deleted_users = deleted_paginator.get_page(deleted_page_number)
    
    context = {
        'pending_users': pending_users,
        'active_users': active_users,
        'inactive_users': inactive_users,
        'rejected_users': rejected_users,
        'deleted_users': deleted_users,
    }
    return render(request, 'user_management.html', context)

@login_required
@require_http_methods(["POST"])
def approve_user(request, user_id):
    """Approve a pending user registration"""
    if not request.user.is_superuser:
        return JsonResponse({'success': False, 'message': 'Permission denied'})
    
    try:
        user = User.objects.get(id=user_id, is_active=False)
        username = user.username
        user_email = user.email
        
        user.is_active = True
        user.save()
        
        # Send approval email to user
        from django.core.mail import send_mail
        from django.conf import settings
        
        try:
            send_mail(
                subject='✅ Account Approved - Real\'s Food Products',
                message=f'''Hello {username},

Great news! Your account has been approved by an administrator.

You can now log in to the Real's Food Products Inventory System using your credentials

Login URL: {request.build_absolute_uri('/login/')}

Welcome to the team!

Real's Food Products Team''',
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[user_email],
                fail_silently=True,
            )
        except Exception as e:
            pass
        
        return JsonResponse({'success': True, 'message': f'User {username} approved successfully'})
    except User.DoesNotExist:
        return JsonResponse({'success': False, 'message': 'User not found or already active'})
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)})

@login_required
@require_http_methods(["POST"])
def reject_user(request, user_id):
    """Reject and soft-delete a pending user registration"""
    if not request.user.is_superuser:
        return JsonResponse({'success': False, 'message': 'Permission denied'})
    
    try:
        from datetime import datetime
        user = User.objects.get(id=user_id, is_active=False)
        username = user.username
        user_email = user.email
        
        # Send rejection email before anonymizing data
        from django.core.mail import send_mail
        from django.conf import settings
        
        try:
            send_mail(
                subject='❌ Account Registration Rejected - Real\'s Food Products',
                message=f'''Hello {username},

We regret to inform you that your registration request for Real's Food Products Inventory System has been rejected by an administrator.

If you believe this was a mistake or have any questions, please contact the administrator directly.

Thank you for your interest.

Real's Food Products Team''',
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[user_email],
                fail_silently=True,
            )
            print(f"[REJECTION] Notification email sent to {user_email}")
        except Exception as e:
            print(f"[REJECTION ERROR] Failed to send email: {e}")
        
        # Soft delete: anonymize user data instead of hard delete to preserve foreign key integrity
        timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
        user.email = f"rejected_{user.id}_{timestamp}@deleted.local"
        user.username = f"rejected_user_{user.id}_{timestamp}"
        user.first_name = "Rejected"
        user.last_name = "User"
        user.set_unusable_password()
        user.is_active = False
        user.save()
        
        return JsonResponse({'success': True, 'message': f'User {username} rejected successfully'})
    except User.DoesNotExist:
        return JsonResponse({'success': False, 'message': 'User not found or already active'})
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)})

def send_role_change_email_async(username, email, new_role):
    """Send role change email in background thread"""
    from django.core.mail import send_mail
    from django.conf import settings
    
    try:
        if new_role == 'Administrator':
            subject = '🎉 Congratulations! You\'ve Been Promoted to Administrator'
            message = f'''Hello {username},

Great news! You have been promoted to Administrator by an administrator.

Your new role: Administrator
- You now have full access to all system features
- You can manage users, approve registrations, and configure system settings
- Please log out and log back in to see the updated interface

If you have any questions, please contact the system administrator.

Real's Food Products Team'''
        else:  # Demoted to Staff
            subject = '📋 Role Change: You\'ve Been Demoted to Staff'
            message = f'''Hello {username},

Your account role has been changed to Staff by an administrator.

Your new role: Staff
- You have standard user access to the system
- Please log out and log back in to see the updated interface

If you believe this was a mistake or have any questions, please contact the administrator.

Real's Food Products Team'''
        
        send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[email],
            fail_silently=True,
        )
        print(f"[ROLE CHANGE] Email sent to {email} - New role: {new_role}")
    except Exception as e:
        print(f"[ROLE CHANGE ERROR] Failed to send email: {e}")

@login_required
@require_http_methods(["POST"])
def toggle_user_role(request, user_id):
    """Toggle user between staff and administrator"""
    if not request.user.is_superuser:
        return JsonResponse({'success': False, 'message': 'Permission denied'})
    
    try:
        user = User.objects.get(id=user_id)
        
        # Prevent modifying own account
        if user.id == request.user.id:
            return JsonResponse({'success': False, 'message': 'Cannot modify your own role'})
        
        # Toggle superuser status
        if user.is_superuser:
            user.is_superuser = False
            new_role = 'Staff'
        else:
            user.is_superuser = True
            new_role = 'Administrator'
        
        user.save()
        
        # Send role change email asynchronously (non-blocking)
        email_thread = threading.Thread(
            target=send_role_change_email_async,
            args=(user.username, user.email, new_role)
        )
        email_thread.daemon = True
        email_thread.start()
        
        # Don't force logout here - let the JavaScript polling detect the role change
        # and show the appropriate modal before logging out
        
        return JsonResponse({
            'success': True, 
            'message': f'User {user.username} is now a {new_role}. They will be notified to log out.',
            'new_role': new_role
        })
    except User.DoesNotExist:
        return JsonResponse({'success': False, 'message': 'User not found'})
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)})

@login_required
@require_http_methods(["POST"])
def create_admin_user(request):
    """Admin-only: Create a new user account (Staff or Administrator) without approval"""
    if not request.user.is_superuser:
        return JsonResponse({'success': False, 'message': 'Permission denied'})
    
    try:
        username = request.POST.get('username', '').strip()
        first_name = request.POST.get('first_name', '').strip()
        last_name = request.POST.get('last_name', '').strip()
        email = request.POST.get('email', '').strip()
        password1 = request.POST.get('password1', '')
        password2 = request.POST.get('password2', '')
        user_type = request.POST.get('user_type', 'staff')
        
        # Validation
        if not all([username, first_name, last_name, email, password1, password2]):
            return JsonResponse({'success': False, 'message': 'All fields are required'})
        
        if password1 != password2:
            return JsonResponse({'success': False, 'message': 'Passwords do not match'})
        
        if User.objects.filter(username=username).exists():
            return JsonResponse({'success': False, 'message': f'Username "{username}" already exists'})
        
        if User.objects.filter(email=email).exists():
            return JsonResponse({'success': False, 'message': f'Email "{email}" is already in use'})
        
        # Check if email belongs to a deactivated user
        deactivated_user = User.objects.filter(
            last_name=f"ORIGINAL_EMAIL:{email}",
            username__startswith='inactive_user_'
        ).first()
        
        if deactivated_user:
            return JsonResponse({'success': False, 'message': f'Email "{email}" belongs to a deactivated account. Please reactivate it or use a different email.'})
        
        # Create user
        user = User.objects.create(
            username=username,
            first_name=first_name,
            last_name=last_name,
            email=email,
            is_active=True,  # Immediately active
            is_staff=True
        )
        user.set_password(password1)
        
        # Set role
        if user_type == 'superuser':
            user.is_superuser = True
            role_name = 'Administrator'
        else:
            user.is_superuser = False
            role_name = 'Staff'
        
        user.save()
        
        return JsonResponse({
            'success': True,
            'message': f'{role_name} account "{username}" created successfully and is immediately active.'
        })
    
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)})

def send_deactivation_email_async(username, email):
    """Send deactivation email in background thread"""
    from django.core.mail import send_mail
    from django.conf import settings
    
    try:
        send_mail(
            subject='⚠️ Account Deactivated - Real\'s Food Products',
            message=f'''Hello {username},

Your account at Real's Food Products Inventory System has been deactivated by an administrator.

You will no longer be able to log in until your account is reactivated.

If you believe this was a mistake or have any questions, please contact the administrator.

Real's Food Products Team''',
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[email],
            fail_silently=True,
        )
        print(f"[DEACTIVATION] Notification email sent to {email}")
    except Exception as e:
        print(f"[DEACTIVATION ERROR] Failed to send email: {e}")

def send_reactivation_email_async(username, email):
    """Send reactivation email in background thread"""
    from django.core.mail import send_mail
    from django.conf import settings
    
    try:
        send_mail(
            subject='✅ Account Reactivated - Real\'s Food Products',
            message=f'''Hello {username},

Good news! Your account at Real's Food Products Inventory System has been reactivated by an administrator.

You can now log in again using your original credentials.

Username: {username}

If you have any questions, please contact the administrator.

Real's Food Products Team''',
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[email],
            fail_silently=True,
        )
        print(f"[REACTIVATION] Notification email sent to {email}")
    except Exception as e:
        print(f"[REACTIVATION ERROR] Failed to send email: {e}")

@login_required
@require_http_methods(["POST"])
def deactivate_user(request, user_id):
    """Deactivate an active user (soft deactivation)"""
    if not request.user.is_superuser:
        return JsonResponse({'success': False, 'message': 'Permission denied'})
    
    try:
        from datetime import datetime
        user = User.objects.get(id=user_id, is_active=True)
        
        # Prevent deactivating own account
        if user.id == request.user.id:
            return JsonResponse({'success': False, 'message': 'Cannot deactivate your own account'})
        
        username = user.username
        original_email = user.email
        original_first_name = user.first_name
        original_last_name = user.last_name
        
        # Send deactivation email asynchronously (non-blocking)
        email_thread = threading.Thread(
            target=send_deactivation_email_async,
            args=(username, original_email)
        )
        email_thread.daemon = True
        email_thread.start()
        
        # Soft deactivate: mark as inactive and prefix username
        # Store original data: username, email, first_name, last_name
        timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
        user.first_name = f"ORIGINAL_USERNAME:{username}|FNAME:{original_first_name}"
        user.last_name = f"ORIGINAL_EMAIL:{original_email}|LNAME:{original_last_name}"
        user.username = f"inactive_user_{user.id}_{timestamp}"
        user.email = f"inactive_{user.id}_{timestamp}@deactivated.local"
        user.is_active = False
        user.save()
        
        # Set a flag in all user's sessions before deleting them
        # This will trigger the modal to show on their next request
        from django.contrib.sessions.models import Session
        from django.utils import timezone as tz
        
        active_sessions = Session.objects.filter(expire_date__gte=tz.now())
        for session in active_sessions:
            session_data = session.get_decoded()
            if session_data.get('_auth_user_id') == str(user.id):
                # Update session to mark as deactivated
                session_data['show_deactivated_modal'] = True
                session.session_data = Session.objects.encode(session_data)
                session.save()
        
        return JsonResponse({'success': True, 'message': f'User {username} deactivated successfully. They will be notified to log out.'})
    except User.DoesNotExist:
        return JsonResponse({'success': False, 'message': 'User not found or already inactive'})
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)})

@login_required
@require_http_methods(["POST"])
def reactivate_user(request, user_id):
    """Reactivate an inactive user"""
    if not request.user.is_superuser:
        return JsonResponse({'success': False, 'message': 'Permission denied'})
    
    try:
        user = User.objects.get(id=user_id)
        
        if not user.username.startswith('inactive_user_'):
            return JsonResponse({'success': False, 'message': 'User is not in inactive state'})
        
        # Restore original username, email, first_name, last_name from stored fields
        # Parse first_name field: "ORIGINAL_USERNAME:username|FNAME:first_name"
        if user.first_name.startswith('ORIGINAL_USERNAME:'):
            parts = user.first_name.split('|')
            original_username = parts[0].replace('ORIGINAL_USERNAME:', '')
            original_first_name = parts[1].replace('FNAME:', '') if len(parts) > 1 else ''
        else:
            original_username = f"user_{user.id}"
            original_first_name = ''
        
        # Parse last_name field: "ORIGINAL_EMAIL:email|LNAME:last_name"
        if user.last_name.startswith('ORIGINAL_EMAIL:'):
            parts = user.last_name.split('|')
            original_email = parts[0].replace('ORIGINAL_EMAIL:', '')
            original_last_name = parts[1].replace('LNAME:', '') if len(parts) > 1 else ''
        else:
            original_email = f"user_{user.id}@reactivated.local"
            original_last_name = ''
        
        # Check if original username is already taken by another active user
        if User.objects.filter(username=original_username, is_active=True).exclude(id=user.id).exists():
            return JsonResponse({'success': False, 'message': f'Cannot reactivate: Username "{original_username}" is already in use'})
        
        # Restore user data
        user.is_active = True
        user.username = original_username
        user.email = original_email
        user.first_name = original_first_name
        user.last_name = original_last_name
        user.save()
        
        # Send reactivation email asynchronously (non-blocking)
        email_thread = threading.Thread(
            target=send_reactivation_email_async,
            args=(original_username, original_email)
        )
        email_thread.daemon = True
        email_thread.start()
        
        return JsonResponse({'success': True, 'message': f'User {original_username} reactivated successfully'})
    except User.DoesNotExist:
        return JsonResponse({'success': False, 'message': 'User not found'})
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)})

@login_required
@require_http_methods(["POST"])
@transaction.atomic
def delete_user(request, user_id):
    """Permanently delete a user (soft delete)"""
    if not request.user.is_superuser:
        return JsonResponse({'success': False, 'message': 'Permission denied'})
    
    try:
        from datetime import datetime
        import random
        user = User.objects.get(id=user_id)
        
        # Prevent deleting own account
        if user.id == request.user.id:
            return JsonResponse({'success': False, 'message': 'Cannot delete your own account'})
        
        username = user.username
        
        # Soft delete: anonymize user data
        # Add microseconds and random suffix to ensure uniqueness
        timestamp = datetime.now().strftime('%Y%m%d%H%M%S%f')  # Added microseconds
        random_suffix = random.randint(1000, 9999)
        
        user.email = f"deleted_{user.id}_{timestamp}_{random_suffix}@deleted.local"
        user.username = f"deleted_user_{user.id}_{timestamp}_{random_suffix}"
        user.first_name = "Deleted"
        user.last_name = "User"
        user.set_unusable_password()
        user.is_active = False
        user.is_staff = False
        user.is_superuser = False
        user.save()
        
        return JsonResponse({'success': True, 'message': f'User {username} deleted successfully'})
    except User.DoesNotExist:
        return JsonResponse({'success': False, 'message': 'User not found'})
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        print(f"[DELETE USER ERROR] Full traceback:\n{error_trace}")
        return JsonResponse({'success': False, 'message': f'Error: {str(e)}'})

@login_required
def edit_profile(request):
    user = request.user

    if request.method == "POST":
        # --- General fields ---
        username = request.POST.get("username")
        first_name = request.POST.get("first_name")
        last_name = request.POST.get("last_name")
        email = request.POST.get("email")

        # --- Password fields (read early) ---
        current_password = (request.POST.get("current_password") or "").strip()
        new_password = (request.POST.get("new_password") or "").strip()
        repeat_new_password = (request.POST.get("repeat_new_password") or "").strip()

        # ===== HARD GUARDS: block partial password inputs =====
        if current_password and not (new_password or repeat_new_password):
            messages.error(request, "To change your password, please enter both New Password and Repeat New Password.")
            form = UserChangeForm(request.POST, instance=user)
            return render(request, "editprofile.html", {"form": form, "active_tab": "account-change-password"})

        if (new_password or repeat_new_password) and not current_password:
            messages.error(request, "Please enter your Current Password to change your password.")
            form = UserChangeForm(request.POST, instance=user)
            return render(request, "editprofile.html", {"form": form, "active_tab": "account-change-password"})

        if new_password and not repeat_new_password:
            messages.error(request, "Please repeat your new password.")
            form = UserChangeForm(request.POST, instance=user)
            return render(request, "editprofile.html", {"form": form, "active_tab": "account-change-password"})

        if repeat_new_password and not new_password:
            messages.error(request, "Please enter a new password.")
            form = UserChangeForm(request.POST, instance=user)
            return render(request, "editprofile.html", {"form": form, "active_tab": "account-change-password"})

        # ===== Full password change flow (all three provided) =====
        password_change_requested = False
        if current_password and new_password and repeat_new_password:
            if not user.check_password(current_password):
                messages.error(request, "Current password is incorrect.")
                form = UserChangeForm(request.POST, instance=user)
                return render(request, "editprofile.html", {"form": form, "active_tab": "account-change-password"})

            if new_password != repeat_new_password:
                messages.error(request, "New passwords do not match.")
                form = UserChangeForm(request.POST, instance=user)
                return render(request, "editprofile.html", {"form": form, "active_tab": "account-change-password"})

            try:
                validate_password(new_password, user=user)
            except ValidationError as e:
                for msg in e.messages:
                    messages.error(request, msg)
                form = UserChangeForm(request.POST, instance=user)
                return render(request, "editprofile.html", {"form": form, "active_tab": "account-change-password"})

            password_change_requested = True

        # --- Email uniqueness (exclude self) ---
        if User.objects.exclude(id=user.id).filter(email=email).exists():
            messages.error(request, "This email address is already in use by another account.")
            form = UserChangeForm(request.POST, instance=user)
            return render(request, "editprofile.html", {"form": form, "active_tab": "account-general"})

        # --- Apply profile changes ---
        user.username = username
        user.first_name = first_name
        user.last_name = last_name
        user.email = email
        user.save()

        # --- Apply password change if requested ---
        if password_change_requested:
            user.set_password(new_password)
            user.save()
            update_session_auth_hash(request, user)
            
            # Send email notification about password change
            from django.core.mail import send_mail
            from django.conf import settings
            from django.utils import timezone
            
            try:
                send_mail(
                    subject='🔐 Password Changed Successfully - Real\'s Food Products',
                    message=f'''Hello {user.username},

Your password has been changed successfully.

Change Details:
- Date & Time: {timezone.now().strftime('%B %d, %Y at %I:%M %p')}
- Account: {user.email}

If you did not make this change, please contact our support team immediately or reset your password.

For security reasons, we recommend:
- Using a strong, unique password
- Enabling two-factor authentication (2FA)
- Not sharing your password with anyone

Thank you for keeping your account secure.

Real's Food Products Security Team''',
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[user.email],
                    fail_silently=False,
                )
            except Exception as e:
                # Log the error but don't prevent the password change
                print(f"Failed to send password change email: {e}")
            
            messages.success(request, "Password updated successfully.")

        messages.success(request, "Profile updated successfully!")
        return redirect("profile")

    # GET
    form = UserChangeForm(instance=user)
    return render(request, "editprofile.html", {"form": form, "active_tab": "account-general"})

@login_required
def export_sales(request):
    # Restrict to superusers only
    if not request.user.is_superuser:
        messages.error(request, "❌ You don't have permission to export sales data.")
        return redirect('home')
    filter_type = request.GET.get('filter', 'date')
    start_date = request.GET.get('start')
    end_date = request.GET.get('end')

    qs = Sales.objects.filter(is_archived=False)

    if filter_type == "date" and start_date:
        # Parse the date string and filter by exact date
        try:
            year, month, day = start_date.split('-')
            qs = qs.filter(date__year=int(year), date__month=int(month), date__day=int(day))
        except (ValueError, AttributeError):
            pass

    elif filter_type == "month" and start_date:
        start = datetime.strptime(start_date, "%Y-%m")
        qs = qs.filter(date__year=start.year, date__month=start.month)

    elif filter_type == "year" and start_date:
        year = int(start_date)
        qs = qs.filter(date__year=year)

    elif filter_type == "range" and start_date and end_date:
        start = datetime.strptime(start_date, "%Y-%m")
        end = datetime.strptime(end_date, "%Y-%m")
        
        from calendar import monthrange
        start = start.replace(day=1)
        last_day = monthrange(end.year, end.month)[1]
        end = end.replace(day=last_day)
        qs = qs.filter(date__range=(start.date(), end.date()))

    total_sales = sum(s.amount for s in qs)

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="sales_{filter_type}.csv"'

    writer = csv.writer(response)
    writer.writerow(['Category', 'Amount', 'Date', 'Description', 'Created By'])

    for s in qs:
        writer.writerow([s.category, s.amount, s.date.strftime("%Y-%m-%d"), s.description, s.created_by_admin.username])

    writer.writerow([])
    writer.writerow(['', 'TOTAL SALES', total_sales])
    return response


@login_required
def export_product_inventory(request):
    queryset = ProductInventory.objects.select_related(
        "product",
        "product__product_type",
        "product__variant",
        "product__size",
        "product__size_unit",
    ).filter(product__is_archived=False)

    search = request.GET.get("search", "").strip()
    if search:
        queryset = queryset.filter(
            Q(product__product_type__name__icontains=search)
            | Q(product__variant__name__icontains=search)
            | Q(product__size__size_label__icontains=search)
        )

    status = request.GET.get("status", "")
    if status == "on_stock":
        queryset = queryset.filter(total_stock__gt=F("restock_threshold"))
    elif status == "low_stock":
        queryset = queryset.filter(total_stock__lt=F("restock_threshold"), total_stock__gt=0)
    elif status == "warning":
        queryset = queryset.filter(total_stock=F("restock_threshold"))
    elif status == "out_of_stock":
        queryset = queryset.filter(total_stock=0)

    # Get month parameter and filter by batch creation date
    month_param = request.GET.get("month", "").strip()
    filename_suffix = month_param if month_param else timezone.localtime().strftime("%Y-%m")
    
    # Filter by batches created in the selected month OR include all products with 0 stock
    if month_param:
        try:
            year, month = month_param.split('-')
            year = int(year)
            month = int(month)
            # Filter products that have batches created in the specified month OR have 0 stock
            from django.db.models import Q as DjangoQ
            queryset = queryset.filter(
                DjangoQ(
                    product__productbatches__batch_date__year=year,
                    product__productbatches__batch_date__month=month,
                    product__productbatches__is_archived=False
                ) | DjangoQ(total_stock=0)
            ).distinct()
        except (ValueError, AttributeError):
            pass

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="product_inventory_{filename_suffix}.csv"'

    writer = csv.writer(response)
    writer.writerow(['Exported At', timezone.now().strftime('%Y-%m-%d %H:%M:%S')])
    writer.writerow(['Month', month_param if month_param else 'Current Month'])
    writer.writerow(['Filters', f"search={search}", f"status={status}"])
    writer.writerow([])
    
    writer.writerow([
        'Product Type',
        'Variant',
        'Size',
        'Size Unit',
        'Current Stock',
        'Restock Threshold',
        'Status'
    ])

    def status_label(item):
        if item.total_stock == 0:
            return 'Out of Stock'
        if item.total_stock < item.restock_threshold:
            return 'Low Stock'
        if item.total_stock == item.restock_threshold:
            return 'Warning'
        return 'On Stock'

    queryset = queryset.order_by(
        'product__product_type__name',
        'product__variant__name',
        'product__size__size_label'
    )

    for inventory in queryset:
        product = inventory.product
        size_label = product.size.size_label if product.size else 'N/A'
        size_unit = product.size_unit.unit_name if product.size_unit else 'N/A'
        writer.writerow([
            product.product_type.name,
            product.variant.name,
            size_label,
            size_unit,
            float(inventory.total_stock),
            float(inventory.restock_threshold),
            status_label(inventory)
        ])

    total_stock = queryset.aggregate(total=Sum('total_stock'))['total'] or 0
    writer.writerow([])
    writer.writerow(['', '', 'TOTAL STOCK', '', float(total_stock), '', ''])

    return response

def export_expenses(request):
    # Restrict to superusers only
    if not request.user.is_superuser:
        messages.error(request, "❌ You don't have permission to export expenses data.")
        return redirect('home')
    filter_type = request.GET.get('filter', 'date')
    start_date = request.GET.get('start')
    end_date = request.GET.get('end')

    qs = Expenses.objects.filter(is_archived=False)

    if filter_type == "date" and start_date:
        # Parse the date string and filter by exact date
        try:
            year, month, day = start_date.split('-')
            qs = qs.filter(date__year=int(year), date__month=int(month), date__day=int(day))
        except (ValueError, AttributeError):
            pass

    elif filter_type == "month" and start_date:
        start = datetime.strptime(start_date, "%Y-%m")
        qs = qs.filter(date__year=start.year, date__month=start.month)

    elif filter_type == "year" and start_date:
        year = int(start_date)
        qs = qs.filter(date__year=year)

    elif filter_type == "range" and start_date and end_date:
        start = datetime.strptime(start_date, "%Y-%m")
        end = datetime.strptime(end_date, "%Y-%m")

        from calendar import monthrange
        start = start.replace(day=1)
        last_day = monthrange(end.year, end.month)[1]
        end = end.replace(day=last_day)
        qs = qs.filter(date__range=(start.date(), end.date()))

    total_expenses = sum(e.amount for e in qs)

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="expenses_{filter_type}.csv"'

    writer = csv.writer(response)
    writer.writerow(['Category', 'Amount', 'Date', 'Description', 'Created By'])

    for e in qs:
        writer.writerow([e.category, e.amount, e.date.strftime("%Y-%m-%d"), e.description, e.created_by_admin.username])

    writer.writerow([])
    writer.writerow(['', 'TOTAL EXPENSES', total_expenses])
    return response

class UserActivityList(ListView):
    model = User
    context_object_name = 'users'
    template_name = "user_activity_list.html"
    paginate_by = 10

    def get_queryset(self):
        from django.utils import timezone
        from datetime import timedelta
        from django.db.models import Q
        
        query = self.request.GET.get('q')
        status = self.request.GET.get('status')
        
        users = User.objects.all().select_related('useractivity').exclude(
            Q(username__startswith='deleted_user_') | 
            Q(username__startswith='rejected_user_') | 
            Q(username__startswith='inactive_user_')
        ).order_by('username')
        
        if query:
            users = users.filter(username__icontains=query)
        
        if status:
            if status == 'active':
                time_threshold = timezone.now() - timedelta(minutes=5)
                users = users.filter(
                    useractivity__active=True,
                    useractivity__last_activity__gte=time_threshold
                )
            elif status == 'inactive':
                time_threshold = timezone.now() - timedelta(minutes=5)
                users = users.filter(
                    useractivity__active=True
                ).filter(
                    Q(useractivity__last_activity__lt=time_threshold) | Q(useractivity__last_activity__isnull=True)
                )
            elif status == 'logged_out':
                users = users.filter(useractivity__active=False)
        
        return users


@receiver(user_logged_in)
def set_user_active(sender, user, request, **kwargs):
    activity, created = UserActivity.objects.get_or_create(user=user)
    activity.active = True
    activity.last_activity = timezone.now()
    activity.save()

@receiver(user_logged_out)
def set_user_inactive(sender, user, request, **kwargs):
    try:
        activity = UserActivity.objects.get(user=user)
        activity.active = False
        activity.last_logout = timezone.now()
        activity.save()
    except UserActivity.DoesNotExist:
        pass

@require_http_methods(["POST"])
def clear_deactivation_flag(request):
    """Clear the deactivation modal flag from session"""
    if 'show_deactivated_modal' in request.session:
        del request.session['show_deactivated_modal']
    return JsonResponse({'success': True})


def check_account_status(request):
    """
    API endpoint to check if the current user's account is still active.
    Returns JSON with account status.
    """
    # Check if user is authenticated
    if not request.user.is_authenticated:
        return JsonResponse({
            'is_active': False,
            'error': 'Not authenticated'
        }, status=401)
    
    # Force check the user from database to get fresh data
    from django.contrib.auth import get_user_model
    User = get_user_model()
    
    try:
        user = User.objects.get(id=request.user.id)
        is_active = user.is_active
        is_superuser = user.is_superuser
    except User.DoesNotExist:
        is_active = False
        is_superuser = False
    
    return JsonResponse({
        'is_active': is_active,
        'is_superuser': is_superuser,
        'username': request.user.username
    })

class BestSellerProductsView(LoginRequiredMixin, TemplateView):
    template_name = "bestseller_products.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        now = timezone.now()

        filter_date = self.request.GET.get('month')  
        show_all = self.request.GET.get('show_all')
        
        filter_type = None 
        
        if filter_date:
            try:
                year, month = filter_date.split('-')
                current_year = int(year)
                current_month = int(month)
                filter_month = current_month
                filter_year = current_year
                filter_type = 'month'
            except (ValueError, AttributeError):
                current_month = now.month
                current_year = now.year
                filter_month = None
                filter_year = None

        elif show_all:
            current_month = None
            current_year = None
            filter_month = None
            filter_year = None
            filter_type = 'all'

        else:
            current_month = now.month
            current_year = now.year
            filter_month = None
            filter_year = None

        filters = {
            'item_type': 'PRODUCT',
            'reason': 'SOLD',
            'is_archived': False
        }
        
        if filter_type != 'all':
            if current_year:
                filters['date__year'] = current_year
            if current_month:
                filters['date__month'] = current_month

        withdrawals = Withdrawals.objects.filter(**filters).values(
            'item_id',
            'quantity',
            'custom_price',
            'total_amount',
            'final_price_per_unit',
        )

        product_sales = {}
        for w in withdrawals:
            product_id = w['item_id']
            quantity = Decimal(w['quantity'] or 0)
            custom_price = w.get('custom_price')
            total_amount = w.get('total_amount')
            final_price_per_unit = w.get('final_price_per_unit')

            revenue = Decimal('0')
            if total_amount is not None:
                revenue = Decimal(total_amount)
            elif custom_price is not None:
                revenue = Decimal(custom_price)
            elif final_price_per_unit is not None:
                revenue = quantity * Decimal(final_price_per_unit)

            if product_id not in product_sales:
                product_sales[product_id] = {
                    'total_quantity': Decimal('0'),
                    'total_revenue': Decimal('0')
                }

            product_sales[product_id]['total_quantity'] += quantity
            product_sales[product_id]['total_revenue'] += revenue

        sold_products_list = []
        for product_id, sales_data in product_sales.items():
            try:
                product = Products.objects.select_related(
                    'product_type', 'variant', 'size', 'size_unit'
                ).get(id=product_id)
                
                sold_products_list.append({
                    'item_id': product_id,
                    'product__product_type__name': product.product_type.name,
                    'product__variant__name': product.variant.name,
                    'product__size__size_label': product.size.size_label if product.size else '',
                    'product__size_unit__unit_name': product.size_unit.unit_name,
                    'total_quantity': sales_data['total_quantity'],
                    'total_revenue': sales_data['total_revenue'],
                })
            except Products.DoesNotExist:
                continue

        sold_products_list.sort(key=lambda x: x['total_quantity'], reverse=True)
        
        best_sellers = sold_products_list[:10]
        best_seller_ids = [p['item_id'] for p in best_sellers]       
        sold_product_ids = [p['item_id'] for p in sold_products_list]
        no_sales_products = Products.objects.filter(
            is_archived=False
        ).exclude(id__in=sold_product_ids).select_related(
            'product_type', 'variant', 'size', 'size_unit'
        )
        
        low_sellers_list = []

        if len(sold_products_list) > 10:
            non_best_sellers = [p for p in sold_products_list if p['item_id'] not in best_seller_ids]
            low_sellers_from_sold = sorted(non_best_sellers, key=lambda x: x['total_quantity'])[:10]
            low_sellers_list.extend(low_sellers_from_sold)
        else:
            non_best_sellers = [p for p in sold_products_list if p['item_id'] not in best_seller_ids]
            low_sellers_list.extend(sorted(non_best_sellers, key=lambda x: x['total_quantity']))

        remaining_slots = 10 - len(low_sellers_list)
        if remaining_slots > 0:
            for product in no_sales_products[:remaining_slots]:
                low_sellers_list.append({
                    'item_id': product.id,
                    'product__product_type__name': product.product_type.name,
                    'product__variant__name': product.variant.name,
                    'product__size__size_label': product.size.size_label if product.size else '',
                    'product__size_unit__unit_name': product.size_unit.unit_name,
                    'total_quantity': Decimal('0'),
                    'total_revenue': Decimal('0'),
                })
        
        low_sellers = low_sellers_list[:10]
        total_quantity = sum(p['total_quantity'] for p in sold_products_list)
        total_revenue = sum(p['total_revenue'] for p in sold_products_list)
        total_products = len(sold_products_list)
        average_revenue = total_revenue / total_products if total_products > 0 else Decimal('0')
        available_years = Withdrawals.objects.filter(
            item_type='PRODUCT',
            reason='SOLD',
            is_archived=False
        ).dates('date', 'year', order='DESC')
        
        context['best_sellers'] = best_sellers
        context['low_sellers'] = low_sellers
        context['total_products'] = total_products
        context['total_quantity'] = total_quantity
        context['total_revenue'] = total_revenue
        context['average_revenue'] = average_revenue
        context['no_sales_products'] = no_sales_products
        context['current_month'] = current_month
        context['current_year'] = current_year
        context['filter_month'] = filter_month
        context['filter_year'] = filter_year
        context['filter_type'] = filter_type
        
        context['current_month_value'] = now.strftime("%Y-%m")
        
        if filter_type == 'all':
            context['current_month_name'] = None
            context['current_year'] = None
            context['filter_month_name'] = None
            context['filter_month_value'] = ''
        elif current_month and current_year:
            context['current_month_name'] = datetime(current_year, current_month, 1).strftime('%B')
            context['filter_month_name'] = datetime(current_year, current_month, 1).strftime('%B')
            context['filter_month_value'] = f"{current_year}-{current_month:02d}"
        else:
            context['current_month_name'] = None
            context['filter_month_name'] = None
            context['filter_month_value'] = ''
        
        context['available_years'] = [d.year for d in available_years]
        context['months'] = [
            (1, 'January'), (2, 'February'), (3, 'March'), (4, 'April'),
            (5, 'May'), (6, 'June'), (7, 'July'), (8, 'August'),
            (9, 'September'), (10, 'October'), (11, 'November'), (12, 'December')
        ]
        
        return context

def export_bestseller_report(request):
    """Export Best Seller analytics as CSV using the same month/show_all filters."""
    now = timezone.now()

    filter_month_param = request.GET.get('month')
    show_all = request.GET.get('show_all')
    include_no_sales = request.GET.get('include_no_sales', '').strip()

    # Determine current_year/current_month and filter scope following the view logic
    current_year = None
    current_month = None
    filter_type = None
    if filter_month_param:
        try:
            year_str, month_str = filter_month_param.split('-')
            current_year = int(year_str)
            current_month = int(month_str)
            filter_type = 'month'
        except (ValueError, AttributeError):
            current_year = now.year
            current_month = now.month
            filter_type = 'month'
    elif show_all:
        filter_type = 'all'
    else:
        current_year = now.year
        current_month = now.month
        filter_type = 'month'

    filters = {
        'item_type': 'PRODUCT',
        'reason': 'SOLD',
        'is_archived': False,
    }

    if filter_type != 'all':
        if current_year:
            filters['date__year'] = current_year
        if current_month:
            filters['date__month'] = current_month

    withdrawals = Withdrawals.objects.filter(**filters).values(
        'item_id',
        'quantity',
        'custom_price',
        'total_amount',
        'final_price_per_unit',
    )

    # Aggregate by product
    product_sales = {}
    for w in withdrawals:
        pid = w['item_id']
        qty = Decimal(w['quantity'] or 0)
        custom_price = w.get('custom_price')
        total_amount = w.get('total_amount')
        final_price_per_unit = w.get('final_price_per_unit')

        revenue = Decimal('0')
        if total_amount is not None:
            revenue = Decimal(total_amount)
        elif custom_price is not None:
            revenue = Decimal(custom_price)
        elif final_price_per_unit is not None:
            revenue = qty * Decimal(final_price_per_unit)

        if pid not in product_sales:
            product_sales[pid] = {
                'total_quantity': Decimal('0'),
                'total_revenue': Decimal('0')
            }
        product_sales[pid]['total_quantity'] += qty
        product_sales[pid]['total_revenue'] += revenue

    # Build detailed list with product fields
    sold_products_list = []
    for pid, data in product_sales.items():
        try:
            product = Products.objects.select_related('product_type', 'variant', 'size', 'size_unit').get(id=pid)
            sold_products_list.append({
                'item_id': pid,
                'product__product_type__name': product.product_type.name,
                'product__variant__name': product.variant.name,
                'product__size__size_label': product.size.size_label if product.size else '',
                'product__size_unit__unit_name': product.size_unit.unit_name,
                'total_quantity': data['total_quantity'],
                'total_revenue': data['total_revenue'],
            })
        except Products.DoesNotExist:
            continue

    sold_products_list.sort(key=lambda x: x['total_quantity'], reverse=True)
    best_sellers = sold_products_list[:10]
    best_ids = [p['item_id'] for p in best_sellers]

    sold_ids = [p['item_id'] for p in sold_products_list]
    no_sales_products_qs = Products.objects.filter(is_archived=False).exclude(id__in=sold_ids).select_related('product_type', 'variant', 'size', 'size_unit')

    low_sellers_list = []
    if len(sold_products_list) > 10:
        non_best = [p for p in sold_products_list if p['item_id'] not in best_ids]
        low_sellers_list.extend(sorted(non_best, key=lambda x: x['total_quantity'])[:10])
    else:
        non_best = [p for p in sold_products_list if p['item_id'] not in best_ids]
        low_sellers_list.extend(sorted(non_best, key=lambda x: x['total_quantity']))

    remaining = 10 - len(low_sellers_list)
    if remaining > 0 and include_no_sales:
        for prod in no_sales_products_qs[:remaining]:
            low_sellers_list.append({
                'item_id': prod.id,
                'product__product_type__name': prod.product_type.name,
                'product__variant__name': prod.variant.name,
                'product__size__size_label': prod.size.size_label if prod.size else '',
                'product__size_unit__unit_name': prod.size_unit.unit_name,
                'total_quantity': 0,
                'total_revenue': 0,
            })

    low_sellers = low_sellers_list[:10]

    total_quantity = sum(p['total_quantity'] for p in sold_products_list)
    total_revenue = sum(p['total_revenue'] for p in sold_products_list)
    total_products = len(sold_products_list)
    average_revenue = (total_revenue / total_products) if total_products > 0 else Decimal('0')

    # Prepare CSV response
    response = HttpResponse(content_type='text/csv')
    period_suffix = 'all' if filter_type == 'all' else f"{current_year}-{current_month:02d}"
    response['Content-Disposition'] = f'attachment; filename="best_seller_analytics_{period_suffix}.csv"'
    # Add BOM for Excel compatibility
    response.write('\ufeff'.encode('utf8'))

    writer = csv.writer(response)
    # Header / Summary
    writer.writerow(['Best Seller Analytics Report'])
    period_label = 'All Time' if filter_type == 'all' else datetime(current_year, current_month, 1).strftime('%B %Y')
    writer.writerow(['Period', period_label])
    writer.writerow([])
    writer.writerow(['Summary'])
    writer.writerow(['Products Analyzed', total_products])
    writer.writerow(['Units Sold', f"{total_quantity:.0f}"])
    writer.writerow(['Total Revenue', f"{total_revenue:.2f}"])
    writer.writerow(['Avg Revenue / Product', f"{average_revenue:.2f}"])
    writer.writerow([])

    # Top Sellers section
    writer.writerow(['Top Selling Products'])
    writer.writerow(['Rank', 'Product', 'Variant', 'Size', 'Unit', 'Total Sold', 'Total Revenue'])
    for idx, p in enumerate(best_sellers, start=1):
        writer.writerow([
            f"#{idx}",
            p['product__product_type__name'],
            p['product__variant__name'],
            p['product__size__size_label'],
            p['product__size_unit__unit_name'],
            f"{p['total_quantity']:.0f}",
            f"{p['total_revenue']:.2f}",
        ])
    writer.writerow([])

    # Low Sellers section
    writer.writerow(['Low Selling / At-Risk Products'])
    writer.writerow(['Rank', 'Product', 'Variant', 'Size', 'Unit', 'Total Sold', 'Total Revenue'])
    for idx, p in enumerate(low_sellers, start=1):
        writer.writerow([
            f"#{idx}",
            p['product__product_type__name'],
            p['product__variant__name'],
            p['product__size__size_label'],
            p['product__size_unit__unit_name'],
            f"{p['total_quantity']:.0f}",
            f"{p['total_revenue']:.2f}",
        ])
    writer.writerow([])

    # No-sales summary only (count)
    writer.writerow(['Products with Zero Sales', no_sales_products_qs.count()])

    return response

@login_required
def database_backup(request):
    """
    Generate and download a Django JSON fixture backup
    Only administrator can access this feature
    """
    from django.http import HttpResponse, HttpResponseForbidden
    from django.core import serializers
    from django.apps import apps
    from datetime import datetime
    import json

    if not request.user.is_superuser:
        return HttpResponseForbidden("Access denied. Only administrators can backup the database.")
    
    if request.method == 'POST':
        try:
            # Create filename with timestamp
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f'reals_backup_{timestamp}.json'
            
            # Get all models from realsproj app (including managed=False)
            app_models = apps.get_app_config('realsproj').get_models()
            
            # Serialize all data
            all_data = []
            for model in app_models:
                try:
                    # Get all objects from this model
                    queryset = model.objects.all()
                    if queryset.exists():
                        model_data = serializers.serialize('json', queryset)
                        all_data.extend(json.loads(model_data))
                except Exception as e:
                    # Skip models that can't be serialized
                    print(f"Skipping {model.__name__}: {e}")
                    continue
            
            # Convert to JSON string with pretty formatting
            json_content = json.dumps(all_data, indent=2, ensure_ascii=False)
            
            # Create JSON response
            response = HttpResponse(
                json_content,
                content_type='application/json'
            )
            response['Content-Disposition'] = f'attachment; filename="{filename}"'
            
            response.write(u'\ufeff'.encode('utf8'))
            
            # Log the backup action
            auth_user = AuthUser.objects.get(id=request.user.id)
            
            # Get or create HistoryLogTypes for backup
            log_type, created = HistoryLogTypes.objects.get_or_create(
                category='Database Backup',
                defaults={'created_by_admin': auth_user}
            )
            
            HistoryLog.objects.create(
                admin_id=auth_user.id,
                log_type_id=log_type.id,
                log_date=timezone.now(),
                entity_type='system',
                entity_id=0
            )
            
            messages.success(request, '✅ Database backup created successfully!')
            return response
            
        except Exception as e:
            messages.error(request, f'❌ Backup error: {e}')
@login_required
def financial_loss(request):

    # Restrict to superusers only
    if not request.user.is_superuser:
        messages.error(request, "❌ You don't have permission to access financial loss reports.")
        return redirect('home')
    
    """View for displaying financial losses from expired and damaged items"""
    from django.core.paginator import Paginator


    product_date_filter = request.GET.get('product_date_filter', '').strip()
    product_show_all = request.GET.get('product_show_all', '').strip()
    raw_material_date_filter = request.GET.get('raw_material_date_filter', '').strip()
    raw_material_show_all = request.GET.get('raw_material_show_all', '').strip()
    today = timezone.now()

    # Product withdrawals with separate filter
    product_withdrawals = Withdrawals.objects.filter(
        item_type='PRODUCT',
        reason__in=['EXPIRED', 'DAMAGED', 'REPLACEMENT_FOR_RETURNED'],
        is_archived=False
    ).select_related('created_by_admin').order_by('-date')

    if product_show_all:
        # Show all product data
        pass
    elif product_date_filter:
        try:
            year_str, month_str = product_date_filter.split('-')
            year = int(year_str)
            month_num = int(month_str.lstrip('0'))
            product_withdrawals = product_withdrawals.filter(date__year=year, date__month=month_num)
        except ValueError:
            pass
    else:
        # Default to current month
        product_withdrawals = product_withdrawals.filter(date__year=today.year, date__month=today.month)

    # Raw material withdrawals with separate filter
    raw_material_withdrawals = Withdrawals.objects.filter(
        item_type='RAW_MATERIAL',
        reason__in=['EXPIRED', 'DAMAGED', 'REPLACEMENT_FOR_RETURNED'],
        is_archived=False
    ).select_related('created_by_admin').order_by('-date')

    if raw_material_show_all:
        # Show all raw material data
        pass
    elif raw_material_date_filter:
        try:
            year_str, month_str = raw_material_date_filter.split('-')
            year = int(year_str)
            month_num = int(month_str.lstrip('0'))
            raw_material_withdrawals = raw_material_withdrawals.filter(date__year=year, date__month=month_num)
        except ValueError:
            pass
    else:

        raw_material_withdrawals = raw_material_withdrawals.filter(date__year=today.year, date__month=today.month)

    product_loss_data = []
    total_product_loss = Decimal('0.00')
    
    for withdrawal in product_withdrawals:
        try:
            product = Products.objects.select_related(
                'product_type', 'variant', 'size', 'size_unit', 'unit_price'
            ).get(id=withdrawal.item_id)
            
            loss_amount = Decimal(withdrawal.quantity) * product.unit_price.unit_price
            total_product_loss += loss_amount
            
            product_loss_data.append({
                'date': withdrawal.date,
                'product_name': str(product),
                'quantity': withdrawal.quantity,
                'unit_price': product.unit_price.unit_price,
                'reason': withdrawal.reason,
                'get_reason_display': withdrawal.get_reason_display(),
                'loss_amount': loss_amount
            })
        except Products.DoesNotExist:
            continue

    raw_material_loss_data = []
    total_raw_material_loss = Decimal('0.00')
    
    for withdrawal in raw_material_withdrawals:
        try:
            material = RawMaterials.objects.select_related('unit').get(id=withdrawal.item_id)
            
            loss_amount = Decimal(withdrawal.quantity) * material.price_per_unit
            total_raw_material_loss += loss_amount
            
            raw_material_loss_data.append({
                'date': withdrawal.date,
                'material_name': material.name,
                'quantity': withdrawal.quantity,
                'unit_name': material.unit.unit_name,
                'price_per_unit': material.price_per_unit,
                'reason': withdrawal.reason,
                'get_reason_display': withdrawal.get_reason_display(),
                'loss_amount': loss_amount
            })
        except RawMaterials.DoesNotExist:
            continue
    
    total_loss = total_product_loss + total_raw_material_loss
    
    # Calculate monthly sales for the current month (or filtered month)
    # Determine which month to calculate sales for
    if product_date_filter:
        try:
            year_str, month_str = product_date_filter.split('-')
            sales_year = int(year_str)
            sales_month = int(month_str.lstrip('0'))
        except ValueError:
            sales_year = today.year
            sales_month = today.month
    else:
        sales_year = today.year
        sales_month = today.month
    
    # Get monthly sales (only if not showing all data)
    monthly_sales = Decimal('0.00')
    if not product_show_all:
        monthly_sales_qs = Sales.objects.filter(
            date__year=sales_year,
            date__month=sales_month,
            is_archived=False
        ).aggregate(total=models.Sum('amount'))
        monthly_sales = monthly_sales_qs['total'] or Decimal('0.00')
    
    # Calculate net sales (sales - financial loss)
    net_sales = monthly_sales - total_loss
    
    product_page = request.GET.get('product_page', 1)
    product_paginator = Paginator(product_loss_data, 10)
    product_page_obj = product_paginator.get_page(product_page)
    
    raw_material_page = request.GET.get('raw_material_page', 1)
    raw_material_paginator = Paginator(raw_material_loss_data, 10)
    raw_material_page_obj = raw_material_paginator.get_page(raw_material_page)
    
    context = {
        'product_withdrawals': product_page_obj,
        'product_paginator': product_paginator,
        'product_page_obj': product_page_obj,
        'product_is_paginated': product_paginator.num_pages > 1,
        'raw_material_withdrawals': raw_material_page_obj,
        'raw_material_paginator': raw_material_paginator,
        'raw_material_page_obj': raw_material_page_obj,
        'raw_material_is_paginated': raw_material_paginator.num_pages > 1,
        'product_loss': total_product_loss,
        'raw_material_loss': total_raw_material_loss,
        'total_loss': total_loss,
        'monthly_sales': monthly_sales,
        'net_sales': net_sales,
        'current_month_value': today.strftime("%Y-%m"),
    }
    
    return render(request, 'financial_loss.html', context)


@login_required
def financial_loss_export(request):
    """Export financial loss data to CSV"""
    filter_type = request.GET.get('filter', 'date')
    start_date = request.GET.get('start')
    end_date = request.GET.get('end')

    product_qs = Withdrawals.objects.filter(
        item_type='PRODUCT',
        reason__in=['EXPIRED', 'DAMAGED', 'REPLACEMENT_FOR_RETURNED'],
        is_archived=False
    )

    raw_material_qs = Withdrawals.objects.filter(
        item_type='RAW_MATERIAL',
        reason__in=['EXPIRED', 'DAMAGED', 'REPLACEMENT_FOR_RETURNED'],
        is_archived=False
    )

    if filter_type == "date" and start_date:
        try:
            year, month, day = start_date.split('-')
            product_qs = product_qs.filter(date__year=int(year), date__month=int(month), date__day=int(day))
            raw_material_qs = raw_material_qs.filter(date__year=int(year), date__month=int(month), date__day=int(day))
        except (ValueError, AttributeError):
            pass
    
    elif filter_type == "month" and start_date:
        start = datetime.strptime(start_date, "%Y-%m")
        product_qs = product_qs.filter(date__year=start.year, date__month=start.month)
        raw_material_qs = raw_material_qs.filter(date__year=start.year, date__month=start.month)
    
    elif filter_type == "year" and start_date:
        year = int(start_date)
        product_qs = product_qs.filter(date__year=year)
        raw_material_qs = raw_material_qs.filter(date__year=year)
    
    elif filter_type == "range" and start_date and end_date:
        start = datetime.strptime(start_date, "%Y-%m")
        end = datetime.strptime(end_date, "%Y-%m")
        
        from calendar import monthrange
        start = start.replace(day=1)
        last_day = monthrange(end.year, end.month)[1]
        end = end.replace(day=last_day)
        product_qs = product_qs.filter(date__range=(start.date(), end.date()))
        raw_material_qs = raw_material_qs.filter(date__range=(start.date(), end.date()))

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="financial_loss_{filter_type}.csv"'
    response.write(u'\ufeff'.encode('utf8'))
    
    writer = csv.writer(response)

    writer.writerow(['PRODUCTS - EXPIRED & DAMAGED'])
    writer.writerow(['Date', 'Product', 'Quantity', 'Unit Price', 'Reason', 'Financial Loss'])
    
    total_product_loss = Decimal('0.00')
    for withdrawal in product_qs:
        try:
            product = Products.objects.select_related(
                'product_type', 'variant', 'size', 'size_unit', 'unit_price'
            ).get(id=withdrawal.item_id)
            
            loss_amount = Decimal(withdrawal.quantity) * product.unit_price.unit_price
            total_product_loss += loss_amount
            
            writer.writerow([
                withdrawal.date.strftime("%Y-%m-%d %H:%M"),
                str(product),
                withdrawal.quantity,
                product.unit_price.unit_price,
                withdrawal.get_reason_display(),
                f"{loss_amount:.2f}"
            ])
        except Products.DoesNotExist:
            continue
    
    writer.writerow([])
    writer.writerow(['', '', '', '', 'TOTAL PRODUCT LOSS', f"₱{total_product_loss:.2f}"])
    writer.writerow([])

    writer.writerow(['RAW MATERIALS - EXPIRED & DAMAGED'])
    writer.writerow(['Date', 'Raw Material', 'Quantity', 'Price per Unit', 'Reason', 'Financial Loss'])
    
    total_raw_material_loss = Decimal('0.00')
    for withdrawal in raw_material_qs:
        try:
            material = RawMaterials.objects.select_related('unit').get(id=withdrawal.item_id)
            
            loss_amount = Decimal(withdrawal.quantity) * material.price_per_unit
            total_raw_material_loss += loss_amount
            
            writer.writerow([
                withdrawal.date.strftime("%Y-%m-%d %H:%M"),
                f"{material.name} ({material.unit.unit_name})",
                withdrawal.quantity,
                material.price_per_unit,
                withdrawal.get_reason_display(),
                f"{loss_amount:.2f}"
            ])
        except RawMaterials.DoesNotExist:
            continue
    
    writer.writerow([])
    writer.writerow(['', '', '', '', 'TOTAL RAW MATERIAL LOSS', f"₱{total_raw_material_loss:.2f}"])
    writer.writerow([])

    total_loss = total_product_loss + total_raw_material_loss
    writer.writerow(['', '', '', '', 'TOTAL FINANCIAL LOSS', f"₱{total_loss:.2f}"])
    
    return response

@login_required
def setup_2fa(request):
    """Enable 2FA for the current user - with email verification"""
    from realsproj.models import User2FASettings, UserOTP
    from django.core.mail import send_mail
    from django.conf import settings as django_settings
    import random
    from datetime import timedelta
    
    if request.method == 'POST':
        if 'verification_code' in request.POST:
            verification_code = request.POST.get('verification_code', '').strip()
            backup_email = request.session.get('2fa_setup_backup_email', '')

            otp = UserOTP.objects.filter(
                user=request.user,
                otp_code=verification_code,
                is_used=False,
                expires_at__gt=timezone.now()
            ).first()
            
            if otp:
                otp.is_used = True
                otp.save()

                settings, created = User2FASettings.objects.get_or_create(
                    user=request.user,
                    defaults={
                        'is_enabled': True,
                        'method': 'email',
                        'backup_email': backup_email if backup_email else None
                    }
                )
                
                if not created:
                    settings.is_enabled = True
                    settings.backup_email = backup_email if backup_email else None
                    settings.save()

                try:
                    email_to = backup_email if backup_email else request.user.email
                    send_mail(
                        subject='🔐 Two-Factor Authentication Enabled - Real\'s Food Products',
                        message=f'''Hello {request.user.username},

Two-Factor Authentication has been successfully enabled for your account.

Primary Email: {request.user.email}
{'Backup Email: ' + backup_email if backup_email else ''}

From now on, you will receive a one-time password (OTP) when logging in from a new device.

If you did not enable this feature, please contact support immediately.

Thank you for keeping your account secure!

Real's Food Products Security Team''',
                        from_email=django_settings.DEFAULT_FROM_EMAIL,
                        recipient_list=[email_to],
                        fail_silently=True,
                    )
                    print(f"[2FA SETUP] Confirmation email sent to {email_to}")
                except Exception as e:
                    print(f"[2FA SETUP ERROR] Failed to send confirmation email: {e}")

                if '2fa_setup_backup_email' in request.session:
                    del request.session['2fa_setup_backup_email']
                
                messages.success(request, "✅ Two-Factor Authentication has been enabled! A confirmation email has been sent.")
                return redirect('profile')
            else:
                messages.error(request, "❌ Invalid or expired verification code. Please try again.")
                return redirect('profile')
        
        backup_email = request.POST.get('backup_email', '').strip()
        email_to = backup_email if backup_email else request.user.email

        verification_code = str(random.randint(100000, 999999))

        UserOTP.objects.create(
            user=request.user,
            otp_code=verification_code,
            expires_at=timezone.now() + timedelta(minutes=5),
            ip_address=request.META.get('REMOTE_ADDR', '0.0.0.0')
        )
        
        request.session['2fa_setup_backup_email'] = backup_email

        try:
            send_mail(
                subject='🔐 Verify Your Email - Enable 2FA',
                message=f'''Hello {request.user.username},

You are enabling Two-Factor Authentication for your account.

Your verification code is: {verification_code}

This code will expire in 5 minutes.

If you did not request this, please ignore this email.

Real's Food Products Security Team''',
                from_email=django_settings.DEFAULT_FROM_EMAIL,
                recipient_list=[email_to],
                fail_silently=False,
            )
            print(f"[2FA SETUP] Verification code sent to {email_to}")
            messages.success(request, f"📧 Verification code sent to {mask_email(email_to)}. Please check your email.")
        except Exception as e:
            print(f"[2FA SETUP ERROR] Failed to send verification email: {e}")
            messages.error(request, "❌ Failed to send verification email. Please try again.")
        
        return redirect('profile')
    
    # GET request - show setup form
    try:
        twofa_settings = User2FASettings.objects.get(user=request.user)
    except User2FASettings.DoesNotExist:
        twofa_settings = None
    
    return render(request, '2fa_setup.html', {
        'user_email': request.user.email,
        'twofa_settings': twofa_settings
    })

@login_required
def disable_2fa(request):
    """Disable 2FA for the current user"""
    from realsproj.models import User2FASettings
    
    if request.method == 'POST':
        password = request.POST.get('password', '')
        
        # Verify password before disabling
        if not request.user.check_password(password):
            messages.error(request, "❌ Incorrect password. Cannot disable 2FA.")
            return redirect('profile')
        
        try:
            settings = User2FASettings.objects.get(user=request.user)
            settings.is_enabled = False
            settings.save()
            messages.success(request, "✅ Two-Factor Authentication has been disabled.")
        except User2FASettings.DoesNotExist:
            messages.info(request, "2FA was not enabled.")
        
        return redirect('profile')
    
    return redirect('profile')

@login_required
def delete_account(request):
    """Soft delete user account - deactivates instead of deleting to preserve database integrity"""
    from django.contrib.auth import logout
    from realsproj.models import User2FASettings, UserOTP, TrustedDevice
    
    if request.method == 'POST':
        password = request.POST.get('password', '')
        confirm_text = request.POST.get('confirm_text', '')
        
        # Verify password
        if not request.user.check_password(password):
            messages.error(request, "❌ Incorrect password. Account deletion cancelled.")
            return redirect('delete_account')
        
        # Verify confirmation text
        if confirm_text != 'DELETE':
            messages.error(request, "❌ Please type 'DELETE' to confirm account deletion.")
            return redirect('delete_account')

        try:
            user = request.user
            
            # Generate unique timestamp-based identifier
            from datetime import datetime
            timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
            
            # Soft delete: Deactivate account and anonymize email/username to prevent conflicts
            user.is_active = False
            user.email = f"deleted_{user.id}_{timestamp}@deleted.local"
            user.username = f"deleted_user_{user.id}_{timestamp}"
            user.first_name = "Deleted"
            user.last_name = "User"
            user.set_unusable_password()
            user.save()
            
            # Clean up 2FA and security data
            User2FASettings.objects.filter(user=user).delete()
            UserOTP.objects.filter(user=user).delete()
            TrustedDevice.objects.filter(user=user).delete()
            
            # Log the user out
            logout(request)
            
            messages.success(request, "✅ Your account has been successfully deactivated. All your data has been preserved for record-keeping purposes.")
            return redirect('home')
            
        except Exception as e:
            messages.error(request, f"❌ An error occurred while deleting your account: {str(e)}")
            return redirect('delete_account')
    
    # GET request - show confirmation page
    return render(request, 'delete_account_confirm.html')

@login_required
def direct_password_reset(request):
    """Direct password reset for logged-in users who forgot their current password"""
    if request.method == 'POST':
        new_password = request.POST.get('new_password1', '').strip()
        confirm_password = request.POST.get('new_password2', '').strip()
        
        # Validate passwords match
        if new_password != confirm_password:
            messages.error(request, "Passwords do not match.")
            return render(request, 'direct_password_reset.html')
        
        # Validate password requirements
        try:
            validate_password(new_password, user=request.user)
        except ValidationError as e:
            for msg in e.messages:
                messages.error(request, msg)
            return render(request, 'direct_password_reset.html')
        
        # Set new password
        request.user.set_password(new_password)
        request.user.save()
        update_session_auth_hash(request, request.user)
        
        # Send email notification
        from django.core.mail import send_mail
        from django.conf import settings
        from django.utils import timezone
        
        try:
            send_mail(
                subject='🔐 Password Reset Successfully - Real\'s Food Products',
                message=f'''Hello {request.user.username},

Your password has been reset successfully.

Reset Details:
- Date & Time: {timezone.now().strftime('%B %d, %Y at %I:%M %p')}
- Account: {request.user.email}

If you did not make this change, please contact our support team immediately.

For security reasons, we recommend:
✓ Using a strong, unique password
✓ Enabling two-factor authentication
✓ Never sharing your password with anyone

Thank you,
Real's Food Products Team''',
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[request.user.email],
                fail_silently=True,
            )
        except Exception:
            pass
        
        messages.success(request, "✅ Your password has been reset successfully!")
        return redirect('profile')
    
    return render(request, 'direct_password_reset.html')

def privacy_policy(request):
    return render(request, 'privacy_policy.html')

def terms_of_use(request):
    """Display the terms of use page"""
    return render(request, 'terms_of_use.html')

class PriceHistoryList(ListView):
    """View for displaying price change history"""
    model = PriceHistory
    context_object_name = 'price_changes'
    template_name = "price_history.html"
    paginate_by = 10
    
    def get_queryset(self):
        from datetime import datetime
        qs = PriceHistory.objects.all().select_related('product', 'changed_by_admin')
        
        product_id = self.request.GET.get('product_id')
        if product_id:
            qs = qs.filter(product_id=product_id)
    
        price_type = self.request.GET.get('price_type')
        if price_type:
            qs = qs.filter(price_type=price_type)
        
        date_from = self.request.GET.get('date_from')
        date_to = self.request.GET.get('date_to')
        if date_from:
            qs = qs.filter(changed_at__gte=date_from)
        if date_to:
            qs = qs.filter(changed_at__lte=date_to)

        show_all = self.request.GET.get('show_all')
        date_created = self.request.GET.get('date_created')
        
        # If show_all is not set, apply date filtering
        if not show_all:
            if date_created:
                # User selected a specific month
                try:
                    parsed_date = datetime.strptime(date_created, "%Y-%m")
                    qs = qs.filter(
                        changed_at__year=parsed_date.year,
                        changed_at__month=parsed_date.month
                    )
                except ValueError:
                    pass
            else:
                # Default to current month if no date selected
                now = datetime.now()
                qs = qs.filter(
                    changed_at__year=now.year,
                    changed_at__month=now.month
                )
        
        search = self.request.GET.get('search')
        if search:
            qs = qs.filter(
                Q(product__product_type__name__icontains=search) |
                Q(product__variant__name__icontains=search) |
                Q(product__size__size_label__icontains=search)
            )
        
        return qs.order_by('-changed_at')
    
    def get_context_data(self, **kwargs):
        from datetime import datetime
        context = super().get_context_data(**kwargs)
        context['products'] = Products.objects.all().order_by('product_type__name', 'variant__name')
        context['price_types'] = PriceHistory.PRICE_TYPE_CHOICES
        
        now = datetime.now()
        context['current_month_value'] = now.strftime('%Y-%m')

        query_params = self.request.GET.copy()
        if 'page' in query_params:
            query_params.pop('page')
        context['query_params'] = query_params.urlencode()
        
        return context

def export_price_history(request):
    """Export Price History to CSV using the same month/show_all filters as the list view."""
    # Base queryset
    qs = PriceHistory.objects.all().select_related('product', 'changed_by_admin')

    # Optional additional filters (keep behavior close to list view)
    price_type = request.GET.get('price_type', '').strip()
    if price_type:
        qs = qs.filter(price_type=price_type)

    # Month filter logic (reuse list behavior)
    show_all = request.GET.get('show_all', '').strip()
    date_created = request.GET.get('date_created', '').strip()

    from datetime import datetime
    if not show_all:
        if date_created:
            try:
                parsed_date = datetime.strptime(date_created, "%Y-%m")
                qs = qs.filter(
                    changed_at__year=parsed_date.year,
                    changed_at__month=parsed_date.month,
                )
            except ValueError:
                pass
        else:
            now = datetime.now()
            qs = qs.filter(changed_at__year=now.year, changed_at__month=now.month)

    # Order by latest changes first
    qs = qs.order_by('-changed_at')

    # Prepare CSV response
    response = HttpResponse(content_type='text/csv')
    filename_suffix = date_created if date_created else ('all' if show_all else datetime.now().strftime('%Y-%m'))
    response['Content-Disposition'] = f'attachment; filename="price_history_{filename_suffix}.csv"'

    writer = csv.writer(response)
    writer.writerow([
        'Date & Time',
        'Product',
        'Price Type',
        'Old Price',
        'New Price',
        'Change Amount',
        'Change Percent',
        'By',
    ])

    for ph in qs:
        # Product string
        product_str = str(ph.product) if getattr(ph, 'product', None) else ''

        # Price type display
        try:
            price_type_display = ph.get_price_type_display()
        except Exception:
            price_type_display = ph.price_type

        # Old/New price
        old_price = ph.old_price if ph.old_price is not None else ''
        new_price = ph.new_price

        # Compute change
        change_amount = ''
        change_percent = ''
        try:
            if ph.old_price is not None and ph.old_price != 0:
                change_amount_val = ph.new_price - ph.old_price
                change_amount = f"{change_amount_val:.2f}"
                change_percent_val = ((ph.new_price - ph.old_price) / ph.old_price) * 100
                change_percent = f"{change_percent_val:.2f}%"
        except Exception:
            pass

        # Changed by
        changed_by = ph.changed_by_admin.username if getattr(ph, 'changed_by_admin', None) else 'System'

        writer.writerow([
            ph.changed_at.strftime('%Y-%m-%d %H:%M:%S'),
            product_str,
            price_type_display,
            old_price,
            f"{new_price:.2f}",
            change_amount,
            change_percent,
            changed_by,
        ])
    
    return response


@login_required
def check_product_batches(request):
    """API endpoint to check if products already have batches with the same quantity."""
    product_data = request.GET.get('product_data', '[]')

    try:
        import json
        products_list = json.loads(product_data)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'duplicates': []})

    today = timezone.localdate()
    duplicates = []
    for item in products_list:
        try:
            product_id = item.get('id')
            quantity = float(item.get('qty', 0))
            
            if quantity <= 0:
                continue
            
            product = Products.objects.get(id=product_id)

            # Check if there's an existing batch with the same quantity
            batch_exists = ProductBatches.objects.filter(
                product=product,
                quantity=quantity,
                is_archived=False,
                batch_date=today
            ).exists()

            if batch_exists:
                duplicates.append(f"{product.product_type.name} - {product.variant.name} ({product.size.size_label})")
        except (Products.DoesNotExist, ValueError, KeyError):
            pass

    return JsonResponse({'duplicates': duplicates})


@login_required
def check_rawmaterial_batches(request):
    """API endpoint to check if raw materials already have batches with the same quantity."""
    material_data = request.GET.get('material_data', '[]')
    
    try:
        import json
        materials_list = json.loads(material_data)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'duplicates': []})

    today = timezone.localdate()
    duplicates = []
    for item in materials_list:
        try:
            material_id = item.get('id')
            quantity = float(item.get('qty', 0))
            
            if quantity <= 0:
                continue
            
            material = RawMaterials.objects.get(id=material_id)

            # Check if there's an existing batch with the same quantity
            batch_exists = RawMaterialBatches.objects.filter(
                material=material,
                quantity=quantity,
                is_archived=False,
                batch_date=today
            ).exists()

            if batch_exists:
                duplicates.append(f"{material.name}")
        except (RawMaterials.DoesNotExist, ValueError, KeyError):
            pass

    return JsonResponse({'duplicates': duplicates})


@login_required
def check_rawmaterial_duplicates(request):
    """API endpoint to check if a raw material with the same details already exists."""
    import json
    
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'duplicate': False})
    
    name = data.get('name', '').strip()
    size = data.get('size', '')
    unit = data.get('unit', '').strip()
    price_per_unit = data.get('price_per_unit', '')
    
    if not name or not size or not unit or not price_per_unit:
        return JsonResponse({'duplicate': False})
    
    try:
        size = str(size).strip()
        price_per_unit = float(price_per_unit)
    except (ValueError, TypeError):
        return JsonResponse({'duplicate': False})
    
    # Check for exact match (same name, size, unit, and price_per_unit)
    duplicate_exists = RawMaterials.objects.filter(
        name__iexact=name,
        size__iexact=size,
        unit__unit_name__iexact=unit,
        price_per_unit=price_per_unit,
        is_archived=False
    ).exists()
    
    return JsonResponse({'duplicate': duplicate_exists})


@login_required
def check_sales_duplicates(request):
    """API endpoint to check if a sales entry with the same details already exists."""
    import json
    
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'duplicate': False})
    
    category = data.get('category', '').strip()
    amount = data.get('amount', '')
    date = data.get('date', '')
    description = data.get('description', '').strip()
    
    if not category or not amount or not date:
        return JsonResponse({'duplicate': False})
    
    try:
        amount = float(amount)
    except (ValueError, TypeError):
        return JsonResponse({'duplicate': False})
    
    # Check for exact match (same category, amount, date, and description)
    duplicate_exists = Sales.objects.filter(
        category=category,
        amount=amount,
        date=date,
        description=description,
        is_archived=False
    ).exists()
    
    return JsonResponse({'duplicate': duplicate_exists})


@login_required
def check_expenses_duplicates(request):
    """API endpoint to check if an expenses entry with the same details already exists."""
    import json
    
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'duplicate': False})
    
    category = data.get('category', '').strip()
    amount = data.get('amount', '')
    date = data.get('date', '')
    description = data.get('description', '').strip()
    
    if not category or not amount or not date:
        return JsonResponse({'duplicate': False})
    
    try:
        amount = float(amount)
    except (ValueError, TypeError):
        return JsonResponse({'duplicate': False})
    
    # Check for exact match (same category, amount, date, and description)
    duplicate_exists = Expenses.objects.filter(
        category=category,
        amount=amount,
        date=date,
        description=description,
        is_archived=False
    ).exists()
    
    return JsonResponse({'duplicate': duplicate_exists})


@login_required
def check_withdrawal_duplicates(request):
    """API endpoint to check if a withdrawal entry with the same details already exists."""
    import json
    
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'duplicate': False})
    
    item_type = data.get('item_type', '').strip()
    item_id = data.get('item_id', '')
    quantity = data.get('quantity', '')
    reason = data.get('reason', '').strip()
    
    if not item_type or not item_id or not quantity or not reason:
        return JsonResponse({'duplicate': False})
    
    try:
        item_id = int(item_id)
        quantity = float(quantity)
    except (ValueError, TypeError):
        return JsonResponse({'duplicate': False})
    
    today = timezone.localdate()
    # Check for exact match (same item_type, item_id, quantity, and reason)
    duplicate_exists = Withdrawals.objects.filter(
        item_type=item_type,
        item_id=item_id,
        quantity=quantity,
        reason=reason,
        is_archived=False,
        date__date=today
    ).exists()

    return JsonResponse({'duplicate': duplicate_exists})