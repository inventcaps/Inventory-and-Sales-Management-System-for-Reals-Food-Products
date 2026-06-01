from django.shortcuts import render, redirect, get_object_or_404
from django.views.generic import (
    ListView, CreateView, UpdateView, DeleteView, TemplateView, View
)
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.http import require_GET
from django.db import transaction, models
from django.utils.decorators import method_decorator
from django.contrib.auth.decorators import login_required
from decimal import Decimal, InvalidOperation
from django.urls import reverse, reverse_lazy
from django.contrib.auth import login, authenticate, update_session_auth_hash
from django.contrib.auth import get_user_model
from django.db.models import Avg, Count, Sum
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.views.decorators.http import require_http_methods
import threading
import os
import json
from realsproj.forms import (
    ProductsForm,
    RawMaterialsForm,
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
    BulkProductBatchForm,
    BulkRawMaterialBatchForm,
    CustomUserCreationForm,
    WithdrawEditForm,
    UserEditForm
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

from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.db.models.functions import TruncMonth, TruncDay
from django.db.models.functions import Cast
from django.contrib.auth.models import User
from django.http import HttpResponse
import csv
from datetime import datetime, timedelta, date
from django.db.models.signals import pre_save, post_delete
from django.dispatch import receiver
from django.utils import timezone
from django.db.models import Q, F, CharField
import re
import logging

logger = logging.getLogger(__name__)

# sales_vs_expenses
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

# revenue_change_api
@login_required
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

# SaleArchiveView
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

# SaleArchiveOldView
class SaleArchiveOldView(View):
    def post(self, request):
        one_year_ago = timezone.now() - timedelta(days=365)
        Sales.objects.filter(is_archived=False, date__lt=one_year_ago).update(is_archived=True)
        return redirect('salesexpenses')

# ArchivedSalesListView
class ArchivedSalesListView(ListView):
    model = Sales
    template_name = 'archived_sales.html'
    context_object_name = 'object_list'
    paginate_by = 10

    def get_queryset(self):
        return Sales.objects.filter(is_archived=True).order_by('-date')

# ArchivedSalesExpensesCombinedView
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

# SaleUnarchiveView
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

# sales_bulk_delete
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
        logger.exception("Sales bulk delete failed")
        return JsonResponse({'success': False, 'message': str(e)})

# sales_bulk_archive
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
        logger.exception("Sales bulk archive failed")
        return JsonResponse({'success': False, 'message': str(e)})

# SaleBulkRestoreView
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
            logger.exception("Sale bulk restore failed")
            return JsonResponse({'success': False, 'message': str(e)})

# SaleBulkDeleteView
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
            logger.exception("Sale bulk delete failed")
            return JsonResponse({'success': False, 'message': str(e)})

# SalesExpensesList
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

# SalesCreateView
class SalesCreateView(CreateView):
    model = Sales
    form_class = SalesForm
    template_name = 'sales_add.html'
    success_url = reverse_lazy('salesexpenses')

    @transaction.atomic
    def form_valid(self, form):
        try:
            from django.db import IntegrityError
            auth_user = AuthUser.objects.get(id=self.request.user.id)
            form.instance.created_by_admin = auth_user
            self.object = form.save()
        except (ValidationError, IntegrityError) as e:
            transaction.set_rollback(True)
            messages.error(self.request, f"Sale creation failed: {e}")
            return redirect(self.request.path)
        messages.success(self.request, "✅ Sale recorded successfully.")
        return redirect(self.success_url)

    def form_invalid(self, form):
        messages.error(self.request, "Please complete all required fields. The form was reset.")
        return redirect(self.request.path) 

# SalesUpdateView
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

# SalesDeleteView
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

# WithdrawalOrderDetailView
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

# WithdrawalOrderUpdatePaymentView
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

# ExpenseArchiveView
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

# ExpenseArchiveOldView
class ExpenseArchiveOldView(View):
    def post(self, request):
        one_year_ago = timezone.now() - timedelta(days=365)
        Expenses.objects.filter(is_archived=False, date__lt=one_year_ago).update(is_archived=True)
        messages.success(request, " Old expenses archived successfully.")
        return redirect('salesexpenses')

# expenses_bulk_delete
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
        logger.exception("Expenses bulk delete failed")
        return JsonResponse({'success': False, 'message': str(e)})

# expenses_bulk_archive
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
        logger.exception("Expenses bulk archive failed")
        return JsonResponse({'success': False, 'message': str(e)})

# ArchivedExpensesListView
class ArchivedExpensesListView(ListView):
    model = Expenses
    template_name = 'archived_expenses.html'
    context_object_name = 'object_list'
    paginate_by = 10

    def get_queryset(self):
        return Expenses.objects.filter(is_archived=True).order_by('-date')

# ExpenseUnarchiveView
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

# ExpenseBulkRestoreView
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
            logger.exception("Expense bulk restore failed")
            return JsonResponse({'success': False, 'message': str(e)})

# ExpenseBulkDeleteView
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
            logger.exception("Expense bulk delete failed")
            return JsonResponse({'success': False, 'message': str(e)})

# ExpensesCreateView
class ExpensesCreateView(CreateView):
    model = Expenses
    form_class = ExpensesForm
    template_name = 'expenses_add.html'
    success_url = reverse_lazy('salesexpenses')

    @transaction.atomic
    def form_valid(self, form):
        try:
            from django.db import IntegrityError
            auth_user = AuthUser.objects.get(id=self.request.user.id)
            form.instance.created_by_admin = auth_user
            self.object = form.save()
        except (ValidationError, IntegrityError) as e:
            transaction.set_rollback(True)
            messages.error(self.request, f"Expense creation failed: {e}")
            return redirect(self.request.path)  # reset form
        messages.success(self.request, "✅ Expense recorded successfully.")
        return redirect(self.success_url)

    def form_invalid(self, form):
        messages.error(self.request, "Please complete all required fields. The form was reset.")
        return redirect(self.request.path)  # reset form

# ExpensesUpdateView
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

# ExpensesDeleteView
class ExpensesDeleteView(LoginRequiredMixin, DeleteView):
    model = Expenses
    success_url = reverse_lazy('salesexpenses')

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_superuser:
            messages.error(request, "❌ You don't have permission to delete expense records.")
            return redirect('salesexpenses')
        return super().dispatch(request, *args, **kwargs)


    def get_success_url(self):
        messages.success(self.request, "🗑️ Expense deleted successfully.")
        return super().get_success_url()

# SalesExpensesCreateView
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
                from django.db import IntegrityError
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
                
            except (ValidationError, IntegrityError) as e:
                messages.error(request, f"Failed to create sales & expenses: {e}")
                return render(request, self.template_name, {'form': form})
        else:
            messages.error(request, "Please correct the errors below.")
            return render(request, self.template_name, {'form': form})

# get_total_revenue
def get_total_revenue():
    withdrawals = Withdrawals.objects.filter(item_type="PRODUCT", reason="SOLD")
    total = 0
    for w in withdrawals:
        total += w.compute_revenue()
    return total

# export_sales
@login_required
def export_sales(request):
    if not request.user.is_superuser:
        return HttpResponse("Permission denied", status=403)
    import csv
    from django.template.loader import render_to_string
    from xhtml2pdf import pisa
    from io import BytesIO
    from datetime import datetime

    format_type = request.GET.get('format', 'csv').lower()
    filter_type = request.GET.get('filter', 'date')
    start = request.GET.get('start', '')
    end = request.GET.get('end', '')

    qs = Sales.objects.filter(is_archived=False).order_by('-date')

    filter_info = 'All Data'
    if filter_type == 'date' and start:
        qs = qs.filter(date=start)
        filter_info = f'Date: {start}'
    elif filter_type == 'month' and start:
        try:
            year, month = start.split('-')
            qs = qs.filter(date__year=year, date__month=month)
            filter_info = f'Month: {start}'
        except ValueError:
            pass
    elif filter_type == 'year' and start:
        qs = qs.filter(date__year=start)
        filter_info = f'Year: {start}'
    elif filter_type == 'range' and start and end:
        qs = qs.filter(date__range=[start, end])
        filter_info = f'Range: {start} to {end}'

    try:
        if format_type == 'pdf':
            from decimal import Decimal
            total_amount = sum(s.amount for s in qs) or Decimal('0.00')
            context = {
                'sales': qs,
                'total_amount': total_amount,
                'filter_info': filter_info,
                'generated_date': datetime.now().strftime('%B %d, %Y at %I:%M %p'),
                'current_year': datetime.now().year,
            }
            html = render_to_string('exports/sales_pdf.html', context)
            pdf_buffer = BytesIO()
            pisa_status = pisa.CreatePDF(html, dest=pdf_buffer)
            if not pisa_status.err:
                response = HttpResponse(pdf_buffer.getvalue(), content_type='application/pdf')
                response['Content-Disposition'] = 'attachment; filename="sales_export.pdf"'
                return response
            raise Exception('PDF generation failed')
        else:
            response = HttpResponse(content_type='text/csv')
            response['Content-Disposition'] = 'attachment; filename="sales_export.csv"'
            writer = csv.writer(response)
            writer.writerow(['Date', 'Category', 'Amount', 'Description'])
            for sale in qs:
                writer.writerow([
                    sale.date,
                    getattr(sale, 'category', ''),
                    sale.amount,
                    getattr(sale, 'description', ''),
                ])
            return response
    except Exception as e:
        logger.exception("Sales export failed")
        if format_type == 'pdf':
            resp = HttpResponse(content_type='text/plain')
            resp['Content-Disposition'] = 'attachment; filename="sales_error.txt"'
            resp.write(f'An error occurred: {str(e)}')
        else:
            resp = HttpResponse(content_type='text/csv')
            resp['Content-Disposition'] = 'attachment; filename="sales_error.csv"'
            writer = csv.writer(resp)
            writer.writerow(['Error'])
            writer.writerow([str(e)])
        return resp

# export_expenses
@login_required
def export_expenses(request):
    if not request.user.is_superuser:
        return HttpResponse("Permission denied", status=403)
    import csv
    from django.template.loader import render_to_string
    from xhtml2pdf import pisa
    from io import BytesIO
    from datetime import datetime

    format_type = request.GET.get('format', 'csv').lower()
    filter_type = request.GET.get('filter', 'date')
    start = request.GET.get('start', '')
    end = request.GET.get('end', '')

    qs = Expenses.objects.filter(is_archived=False).order_by('-date')

    filter_info = 'All Data'
    if filter_type == 'date' and start:
        qs = qs.filter(date=start)
        filter_info = f'Date: {start}'
    elif filter_type == 'month' and start:
        try:
            year, month = start.split('-')
            qs = qs.filter(date__year=year, date__month=month)
            filter_info = f'Month: {start}'
        except ValueError:
            pass
    elif filter_type == 'year' and start:
        qs = qs.filter(date__year=start)
        filter_info = f'Year: {start}'
    elif filter_type == 'range' and start and end:
        qs = qs.filter(date__range=[start, end])
        filter_info = f'Range: {start} to {end}'

    try:
        if format_type == 'pdf':
            from decimal import Decimal
            total_amount = sum(e.amount for e in qs) or Decimal('0.00')
            context = {
                'expenses': qs,
                'total_amount': total_amount,
                'filter_info': filter_info,
                'generated_date': datetime.now().strftime('%B %d, %Y at %I:%M %p'),
                'current_year': datetime.now().year,
            }
            html = render_to_string('exports/expenses_pdf.html', context)
            pdf_buffer = BytesIO()
            pisa_status = pisa.CreatePDF(html, dest=pdf_buffer)
            if not pisa_status.err:
                response = HttpResponse(pdf_buffer.getvalue(), content_type='application/pdf')
                response['Content-Disposition'] = 'attachment; filename="expenses_export.pdf"'
                return response
            raise Exception('PDF generation failed')
        else:
            response = HttpResponse(content_type='text/csv')
            response['Content-Disposition'] = 'attachment; filename="expenses_export.csv"'
            writer = csv.writer(response)
            writer.writerow(['Date', 'Category', 'Amount', 'Description'])
            for expense in qs:
                writer.writerow([
                    expense.date,
                    getattr(expense, 'category', ''),
                    expense.amount,
                    getattr(expense, 'description', ''),
                ])
            return response
    except Exception as e:
        logger.exception("Expenses export failed")
        if format_type == 'pdf':
            resp = HttpResponse(content_type='text/plain')
            resp['Content-Disposition'] = 'attachment; filename="expenses_error.txt"'
            resp.write(f'An error occurred: {str(e)}')
        else:
            resp = HttpResponse(content_type='text/csv')
            resp['Content-Disposition'] = 'attachment; filename="expenses_error.csv"'
            writer = csv.writer(resp)
            writer.writerow(['Error'])
            writer.writerow([str(e)])
        return resp

# check_sales_duplicates
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

# check_expenses_duplicates
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
