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
import logging

logger = logging.getLogger(__name__)
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
    PriceHistory,
    FinancialLoss,
)

from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.db.models.functions import TruncMonth, TruncDay
from django.db.models.functions import Cast
from django.contrib.auth.models import User
from django.http import HttpResponse
import csv
from itertools import islice
from datetime import datetime, timedelta
from django.db.models.signals import pre_save, post_delete
from django.dispatch import receiver
from django.utils import timezone
from django.db.models import Q, F, CharField
import re

# HomePageView
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

        context['recent_sales'] = Withdrawals.objects.filter(
            item_type="PRODUCT", reason="SOLD"
        ).order_by('-date')[:6]

        context['is_superuser'] = self.request.user.is_superuser

        if self.request.user.is_superuser:
            now = timezone.now()
            cy, cm = now.year, now.month
            py, pm = (cy - 1, 12) if cm == 1 else (cy, cm - 1)

            def _s(y, m):
                return float(Sales.objects.filter(date__year=y, date__month=m).aggregate(t=Sum('amount'))['t'] or 0)

            def _e(y, m):
                return float(Expenses.objects.filter(date__year=y, date__month=m).aggregate(t=Sum('amount'))['t'] or 0)

            cur_sales, prev_sales = _s(cy, cm), _s(py, pm)
            cur_exp, prev_exp = _e(cy, cm), _e(py, pm)
            cur_profit = cur_sales - cur_exp
            prev_profit = prev_sales - prev_exp

            def _badge(cur, prev, invert=False):
                if prev <= 0:
                    return None
                pct = round((cur - prev) / prev * 100, 1)
                prefix = '+' if pct >= 0 else ''
                up = (pct >= 0) if not invert else (pct < 0)
                return {'text': f'{prefix}{pct}%', 'up': up}

            context['profit_badge'] = _badge(cur_profit, prev_profit)
            context['revenue_badge'] = _badge(cur_sales, prev_sales)
            context['expenses_badge'] = _badge(cur_exp, prev_exp, invert=True)
            context['cur_sales'] = cur_sales
            context['prev_sales'] = prev_sales
            context['cur_profit'] = cur_profit
            context['prev_profit'] = prev_profit
            context['cur_expenses'] = cur_exp
            context['prev_expenses'] = prev_exp

        import json
        context['total_products'] = Products.objects.filter(is_archived=False).count()
        all_inv = list(
            ProductInventory.objects.filter(product__is_archived=False).select_related(
                'product', 'product__product_type', 'product__variant',
                'product__size', 'product__size_unit'
            ).order_by('-total_stock')
        )
        context['total_stocks'] = sum(inv.total_stock for inv in all_inv)
        context['low_stock_count'] = sum(
            1 for inv in all_inv if 0 < inv.total_stock <= inv.restock_threshold
        )
        context['out_of_stock_count'] = sum(
            1 for inv in all_inv if inv.total_stock <= 0
        )
        context['healthy_stock_count'] = sum(
            1 for inv in all_inv if inv.total_stock > inv.restock_threshold
        )

        if not self.request.user.is_superuser:
            inv_labels, inv_stocks, inv_colors = [], [], []
            for inv in all_inv[:15]:
                label = str(inv.product)
                if len(label) > 25:
                    label = label[:22] + '...'
                inv_labels.append(label)
                inv_stocks.append(float(inv.total_stock))
                if inv.total_stock <= 0:
                    inv_colors.append('#ef4444')
                elif inv.total_stock <= inv.restock_threshold:
                    inv_colors.append('#f59e0b')
                else:
                    inv_colors.append('#22c55e')
            context['inv_labels'] = json.dumps(inv_labels)
            context['inv_stocks'] = json.dumps(inv_stocks)
            context['inv_colors'] = json.dumps(inv_colors)
            return context

        # ===== Superuser-only: extended dashboard data =====
        today = timezone.localdate()
        now = timezone.now()
        cy, cm = now.year, now.month
        py, pm = (cy - 1, 12) if cm == 1 else (cy, cm - 1)

        # --- Units Sold MTD (with prev-month comparison) ---
        def _units(y, m):
            return float(Withdrawals.objects.filter(
                reason='SOLD', item_type='PRODUCT',
                date__year=y, date__month=m
            ).aggregate(t=Sum('quantity'))['t'] or 0)
        cur_units = _units(cy, cm)
        prev_units = _units(py, pm)
        context['cur_units'] = cur_units
        context['prev_units'] = prev_units
        if prev_units > 0:
            pct = round((cur_units - prev_units) / prev_units * 100, 1)
            context['units_badge'] = {'text': f"{'+' if pct >= 0 else ''}{pct}%", 'up': pct >= 0}
        else:
            context['units_badge'] = None

        # --- Sales vs Expenses: last 12 months (combo chart) ---
        months_labels = []
        months_sales = []
        months_expenses = []
        months_profit = []
        for i in range(11, -1, -1):
            yy = cy
            mm = cm - i
            while mm <= 0:
                mm += 12
                yy -= 1
            s = float(Sales.objects.filter(date__year=yy, date__month=mm).aggregate(t=Sum('amount'))['t'] or 0)
            e = float(Expenses.objects.filter(date__year=yy, date__month=mm).aggregate(t=Sum('amount'))['t'] or 0)
            months_labels.append(f"{yy}-{mm:02d}")
            months_sales.append(s)
            months_expenses.append(e)
            months_profit.append(s - e)
        context['chart_12mo_labels'] = json.dumps(months_labels)
        context['chart_12mo_sales'] = json.dumps(months_sales)
        context['chart_12mo_expenses'] = json.dumps(months_expenses)
        context['chart_12mo_profit'] = json.dumps(months_profit)

        # --- Stock Health doughnut (already have counts above) ---
        context['stock_health_json'] = json.dumps([
            context['healthy_stock_count'],
            context['low_stock_count'],
            context['out_of_stock_count'],
        ])

        # --- Expiring Soon (<=7 days) ---
        cutoff = today + timedelta(days=7)
        expiring_batches = list(ProductBatches.objects.filter(
            is_archived=False,
            quantity__gt=0,
            expiration_date__isnull=False,
            expiration_date__lte=cutoff,
            expiration_date__gte=today,
        ).exclude(is_expired=True).select_related('product', 'product__product_type', 'product__variant').order_by('expiration_date')[:8])
        expiring_list = []
        for b in expiring_batches:
            try:
                days_left = (b.expiration_date - today).days
            except TypeError:
                days_left = 0
            expiring_list.append({
                'label': str(b.product),
                'qty': float(b.quantity),
                'days_left': days_left,
                'exp_date': b.expiration_date.strftime('%b %d') if b.expiration_date else '',
            })
        context['expiring_soon'] = expiring_list
        context['expiring_count'] = ProductBatches.objects.filter(
            is_archived=False, quantity__gt=0,
            expiration_date__isnull=False,
            expiration_date__lte=cutoff, expiration_date__gte=today,
        ).exclude(is_expired=True).count()

        # --- Revenue Trend last 30 days + 7-day MA ---
        start_30 = today - timedelta(days=29)
        daily_rev_qs = (
            Withdrawals.objects.filter(
                reason='SOLD', date__date__gte=start_30, date__date__lte=today
            )
            .annotate(day=TruncDay('date'))
            .values('day')
            .annotate(total=Sum('total_amount'))
        )
        daily_map = {row['day'].date().isoformat(): float(row['total'] or 0) for row in daily_rev_qs if row['day']}
        rev_labels = []
        rev_values = []
        for i in range(30):
            d = start_30 + timedelta(days=i)
            rev_labels.append(d.strftime('%b %d'))
            rev_values.append(daily_map.get(d.isoformat(), 0.0))
        ma7 = []
        for i in range(len(rev_values)):
            lo = max(0, i - 6)
            window = rev_values[lo:i+1]
            ma7.append(round(sum(window) / len(window), 2))
        context['rev30_labels'] = json.dumps(rev_labels)
        context['rev30_values'] = json.dumps(rev_values)
        context['rev30_ma7'] = json.dumps(ma7)

        # --- Top 10 Best Sellers (this month, by revenue) ---
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        top_qs = (
            Withdrawals.objects.filter(
                reason='SOLD', item_type='PRODUCT', date__gte=month_start
            )
            .values('item_id')
            .annotate(qty=Sum('quantity'), revenue=Sum('total_amount'))
            .order_by('-revenue')[:10]
        )
        top_list = list(top_qs)
        product_ids = [r['item_id'] for r in top_list]
        prod_map = {p.id: str(p) for p in Products.objects.filter(id__in=product_ids).select_related('product_type', 'variant', 'size', 'size_unit')}
        best_labels = []
        best_revenue = []
        best_qty = []
        for r in top_list:
            name = prod_map.get(r['item_id'], f"Product #{r['item_id']}")
            if len(name) > 28:
                name = name[:25] + '...'
            best_labels.append(name)
            best_revenue.append(float(r['revenue'] or 0))
            best_qty.append(float(r['qty'] or 0))
        context['best_labels'] = json.dumps(best_labels)
        context['best_revenue'] = json.dumps(best_revenue)
        context['best_qty'] = json.dumps(best_qty)

        # --- Sales Channel breakdown (SOLD, all-time or MTD?) -> MTD ---
        channel_qs = (
            Withdrawals.objects.filter(reason='SOLD', date__gte=month_start)
            .values('sales_channel')
            .annotate(total=Sum('total_amount'))
        )
        channel_labels_map = dict(Withdrawals.SALES_CHANNEL_CHOICES)
        ch_labels = []
        ch_values = []
        for row in channel_qs:
            key = row['sales_channel'] or 'UNSPECIFIED'
            ch_labels.append(channel_labels_map.get(key, key.title()))
            ch_values.append(float(row['total'] or 0))
        context['channel_labels'] = json.dumps(ch_labels)
        context['channel_values'] = json.dumps(ch_values)

        # --- Withdrawal Reasons stacked (last 6 months, by qty) ---
        reason_labels_map = dict(Withdrawals.REASON_CHOICES)
        reason_months = []
        for i in range(5, -1, -1):
            yy = cy
            mm = cm - i
            while mm <= 0:
                mm += 12
                yy -= 1
            reason_months.append((yy, mm))
        reason_data = {key: [0] * 6 for key, _ in Withdrawals.REASON_CHOICES}
        for idx, (yy, mm) in enumerate(reason_months):
            rows = (
                Withdrawals.objects.filter(date__year=yy, date__month=mm)
                .values('reason')
                .annotate(q=Sum('quantity'))
            )
            for r in rows:
                if r['reason'] in reason_data:
                    reason_data[r['reason']][idx] = float(r['q'] or 0)
        context['reason_labels'] = json.dumps([f"{yy}-{mm:02d}" for yy, mm in reason_months])
        context['reason_datasets'] = json.dumps([
            {'label': reason_labels_map.get(k, k), 'key': k, 'data': v}
            for k, v in reason_data.items()
        ])

        # --- Expenses by Category (MTD) ---
        exp_cat_qs = (
            Expenses.objects.filter(date__year=cy, date__month=cm, is_archived=False)
            .values('category')
            .annotate(t=Sum('amount'))
            .order_by('-t')
        )
        context['exp_cat_labels'] = json.dumps([r['category'] for r in exp_cat_qs])
        context['exp_cat_values'] = json.dumps([float(r['t'] or 0) for r in exp_cat_qs])

        # --- Payment Status (MTD) ---
        pay_qs = (
            Withdrawals.objects.filter(reason='SOLD', date__gte=month_start)
            .values('payment_status')
            .annotate(total=Sum('total_amount'), paid=Sum('paid_amount'))
        )
        pay_map = {'PAID': 0.0, 'UNPAID': 0.0, 'PARTIAL': 0.0}
        outstanding = 0.0
        for row in pay_qs:
            key = row['payment_status'] or 'PAID'
            amt = float(row['total'] or 0)
            paid = float(row['paid'] or 0)
            pay_map[key] = pay_map.get(key, 0.0) + amt
            if key == 'UNPAID':
                outstanding += amt
            elif key == 'PARTIAL':
                outstanding += max(0.0, amt - paid)
        context['pay_labels'] = json.dumps(['Paid', 'Partial', 'Unpaid'])
        context['pay_values'] = json.dumps([pay_map.get('PAID', 0), pay_map.get('PARTIAL', 0), pay_map.get('UNPAID', 0)])
        context['pay_outstanding'] = outstanding

        # --- Low-Stock Watchlist (top 10 closest to/below threshold) ---
        watchlist = sorted(
            [inv for inv in all_inv if inv.total_stock <= inv.restock_threshold * Decimal('1.5')],
            key=lambda x: float(x.total_stock) - float(x.restock_threshold)
        )[:10]
        wl_labels, wl_stock, wl_threshold, wl_colors = [], [], [], []
        for inv in watchlist:
            name = str(inv.product)
            if len(name) > 30:
                name = name[:27] + '...'
            wl_labels.append(name)
            wl_stock.append(float(inv.total_stock))
            wl_threshold.append(float(inv.restock_threshold))
            if inv.total_stock <= 0:
                wl_colors.append('#ef4444')
            elif inv.total_stock <= inv.restock_threshold:
                wl_colors.append('#f59e0b')
            else:
                wl_colors.append('#22c55e')
        context['wl_labels'] = json.dumps(wl_labels)
        context['wl_stock'] = json.dumps(wl_stock)
        context['wl_threshold'] = json.dumps(wl_threshold)
        context['wl_colors'] = json.dumps(wl_colors)

        # --- Raw Materials / Packaging Stock ---
        rm_inv = list(
            RawMaterialInventory.objects.select_related('material').order_by('-total_stock')[:12]
        )
        rm_labels, rm_stock, rm_colors = [], [], []
        for inv in rm_inv:
            name = inv.material.name if hasattr(inv.material, 'name') else str(inv.material)
            if len(name) > 28:
                name = name[:25] + '...'
            rm_labels.append(name)
            rm_stock.append(float(inv.total_stock))
            cat = (getattr(inv.material, 'category', '') or '').upper()
            rm_colors.append('#8b5cf6' if cat == 'PACKAGING' else '#0ea5e9')
        context['rm_labels'] = json.dumps(rm_labels)
        context['rm_stock'] = json.dumps(rm_stock)
        context['rm_colors'] = json.dumps(rm_colors)

        return context

# monthly_report
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

    # Calculate financial loss per month from trigger-maintained financial_loss table
    financial_loss_qs = FinancialLoss.objects.filter(is_archived=False).annotate(
        month=TruncMonth("loss_date")
    ).values("month").annotate(total_loss=Sum("loss_amount"))

    # Normalize all dictionaries to use date objects as keys
    def normalize_date(dt):
        if hasattr(dt, 'date'):
            return dt.date()
        return dt

    expenses_dict = {normalize_date(e["month"]): e["total_expenses"] for e in expenses}
    sales_dict = {normalize_date(s["month"]): s["total_sales"] for s in sales}
    financial_loss_dict = {normalize_date(fl["month"]): fl["total_loss"] for fl in financial_loss_qs}

    # Get all unique months from sales, expenses, and financial loss
    all_months = set()
    all_months.update(sales_dict.keys())
    all_months.update(expenses_dict.keys())
    all_months.update(financial_loss_dict.keys())
    
    # Sort months chronologically
    all_months = sorted(all_months)

    report = []
    prev = None

    for month in all_months:
        gross_revenue = sales_dict.get(month, 0) or 0
        financial_loss = financial_loss_dict.get(month, 0) or 0
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
        "title": "Monthly Report",
    })

# monthly_report_export
@require_GET
@login_required
def monthly_report_export(request):
    import csv
    from django.http import HttpResponse
    from django.template.loader import render_to_string
    from xhtml2pdf import pisa
    from io import BytesIO
    from datetime import datetime

    if not request.user.is_superuser:
        messages.error(request, "❌ You don't have permission to export financial reports.")
        return redirect('home')

    format_type = request.GET.get('format', 'csv').lower()

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
    
    # Calculate financial loss per month from trigger-maintained financial_loss table
    financial_loss_qs = FinancialLoss.objects.filter(is_archived=False).annotate(
        month=TruncMonth("loss_date")
    ).values("month").annotate(total_loss=Sum("loss_amount"))

    def normalize_date(dt):
        if hasattr(dt, 'date'):
            return dt.date()
        return dt

    sales_dict = {normalize_date(s["month"]): Decimal(s["total_sales"] or 0) for s in sales}
    expenses_dict = {normalize_date(e["month"]): Decimal(e["total_expenses"] or 0) for e in expenses}
    normalized_financial_loss_dict = {normalize_date(fl["month"]): fl["total_loss"] for fl in financial_loss_qs}
    
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

    # Calculate changes and trends
    for i in range(len(report)):
        if i > 0: 
            older = report[i - 1]
            rc = report[i]["revenue"] - older["revenue"]
            pc = report[i]["profit"] - older["profit"]

            report[i]["revenue_change"] = rc
            report[i]["profit_change"] = pc

            if rc > 0 and pc > 0:
                report[i]["trend"] = "Revenue & Profit Increased"
            elif rc > 0 and pc < 0:
                report[i]["trend"] = "Revenue Increased, Profit Decreased"
            elif rc < 0 and pc > 0:
                report[i]["trend"] = "Revenue Decreased, Profit Increased"
            elif rc == 0 and pc == 0:
                report[i]["trend"] = "No Change"
            else:
                report[i]["trend"] = "Revenue & Profit Decreased"
        else:
            report[i]["revenue_change"] = None
            report[i]["profit_change"] = None
            report[i]["trend"] = "-"

    try:
        # Export based on format
        if format_type == 'pdf':
            # Calculate summary data
            total_revenue = sum(row["revenue"] for row in report)
            total_financial_loss = sum(row["financial_loss"] for row in report)
            total_profit = sum(row["profit"] for row in report)
            average_profit = total_profit / len(report) if report else Decimal(0)

            # Prepare context for template
            context = {
                'report': report,
                'summary': {
                    'total_revenue': total_revenue,
                    'total_financial_loss': total_financial_loss,
                    'total_profit': total_profit,
                    'average_profit': average_profit,
                },
                'generated_date': timezone.now().strftime('%B %d, %Y at %I:%M %p'),
                'current_year': timezone.now().year,
                'logo_url': None,
            }

            # Render HTML template
            html = render_to_string('exports/monthly_report_pdf.html', context)

            # Generate PDF
            pdf_buffer = BytesIO()
            pisa_status = pisa.CreatePDF(html, dest=pdf_buffer)

            if not pisa_status.err:
                response = HttpResponse(pdf_buffer.getvalue(), content_type='application/pdf')
                response['Content-Disposition'] = 'attachment; filename="monthly_report.pdf"'
                return response
            else:
                raise Exception('PDF generation failed')

        else:  # CSV format
            response = HttpResponse(content_type="text/csv")
            response["Content-Disposition"] = 'attachment; filename="financial_report.csv"'
            response.write(u'\ufeff'.encode('utf8'))
            writer = csv.writer(response)
            writer.writerow(["Month", "Revenue", "Financial Loss", "Expenses", "Profit", "Revenue Change", "Profit Change", "Trend"])

            for i in range(len(report)):
                row = report[i]
                rev_change = f"↑ ₱{row['revenue_change']:,.2f}" if row['revenue_change'] and row['revenue_change'] > 0 else f"↓ ₱{abs(row['revenue_change']):,.2f}" if row['revenue_change'] and row['revenue_change'] < 0 else "₱0.00" if row['revenue_change'] == 0 else "-"
                prof_change = f"↑ ₱{row['profit_change']:,.2f}" if row['profit_change'] and row['profit_change'] > 0 else f"↓ ₱{abs(row['profit_change']):,.2f}" if row['profit_change'] and row['profit_change'] < 0 else "₱0.00" if row['profit_change'] == 0 else "-"

                writer.writerow([
                    row["month"].strftime("%B %Y"),
                    f"₱{row['revenue']:,.2f}",
                    f"₱{row['financial_loss']:,.2f}",
                    f"₱{row['expenses']:,.2f}",
                    f"₱{row['profit']:,.2f}",
                    rev_change,
                    prof_change,
                    row["trend"],
                ])

            return response

    except Exception as e:
        logger.exception("Monthly report export failed")
        # Handle errors gracefully
        if format_type == 'pdf':
            response = HttpResponse(content_type='text/plain')
            response['Content-Disposition'] = 'attachment; filename="monthly_report_error.txt"'
            response.write(f'An error occurred: {str(e)}')
        else:
            response = HttpResponse(content_type='text/csv')
            response['Content-Disposition'] = 'attachment; filename="monthly_report_error.csv"'
            writer = csv.writer(response)
            writer.writerow(['Error'])
            writer.writerow([f'An error occurred: {str(e)}'])
        return response

# HistoryLogList
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
            except (ValueError, OverflowError):
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

# NotificationsList
class NotificationsList(LoginRequiredMixin, ListView):
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
        from django.core.paginator import EmptyPage, PageNotAnInteger
        try:
            return super().get(request, *args, **kwargs)
        except (PageNotAnInteger, EmptyPage):
            # Preserve all query parameters except page
            from django.shortcuts import redirect
            params = request.GET.copy()
            params['page'] = '1'
            return redirect(f"{request.path}?{params.urlencode()}")

# best_sellers_api
@login_required
def best_sellers_api(request):
    from datetime import datetime
    TOP_N = 5
    
    year = request.GET.get('year')
    month = request.GET.get('month')

    now = timezone.now()
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

# mark_notification_read
@login_required
def mark_notification_read(request, pk):
    notif = get_object_or_404(Notifications, pk=pk)
    notif.is_read = True
    notif.save()
    return redirect('notifications')

# database_backup
@login_required
def database_backup(request):
    from django.conf import settings
    from django.apps import apps
    from django.core import serializers as dj_serializers
    import datetime as dt

    if not request.user.is_superuser:
        messages.error(request, "You don't have permission to access this page.")
        return redirect('home')

    backup_dir = os.path.join(settings.BASE_DIR, 'backups')

    if request.method == 'POST':
        try:
            os.makedirs(backup_dir, exist_ok=True)
            timestamp = timezone.now().strftime('%Y%m%d_%H%M%S')
            filename = f"reals_backup_{timestamp}.json"
            backup_path = os.path.join(backup_dir, filename)

            app_models = apps.get_app_config('realsproj').get_models()
            backup_data = {}
            total_records = 0

            for model in app_models:
                model_name = model._meta.label
                try:
                    queryset = model.objects.all()
                    count = queryset.count()
                    if count > 0:
                        serialized_data = dj_serializers.serialize('json', queryset)
                        backup_data[model_name] = {
                            'count': count,
                            'data': json.loads(serialized_data),
                        }
                        total_records += count
                except Exception:
                    logger.exception("Failed to serialize model %s", model_name)

            backup_data['_metadata'] = {
                'created_at': timezone.now().isoformat(),
                'total_records': total_records,
                'backup_type': 'python_serialization',
            }

            content = json.dumps(backup_data, indent=2, ensure_ascii=False)

            with open(backup_path, 'w', encoding='utf-8') as f:
                f.write(content)

            response = HttpResponse(content, content_type='application/json')
            response['Content-Disposition'] = f'attachment; filename="{filename}"'
            return response

        except Exception as e:
            logger.exception("Backup creation failed")
            messages.error(request, f"Backup failed: {str(e)}")
            return redirect('home')

    # GET: list existing backups
    backups = []
    if os.path.exists(backup_dir):
        for fname in sorted(os.listdir(backup_dir), reverse=True):
            if fname.startswith('reals_backup_') and (fname.endswith('.json') or fname.endswith('.sql')):
                fpath = os.path.join(backup_dir, fname)
                fstats = os.stat(fpath)
                backups.append({
                    'filename': fname,
                    'size_kb': round(fstats.st_size / 1024, 1),
                    'created_at': dt.datetime.fromtimestamp(fstats.st_ctime).strftime('%b %d, %Y %I:%M %p'),
                })

    return render(request, 'database_backup.html', {'backups': backups})

# BestSellerProductsView
class BestSellerProductsView(LoginRequiredMixin, TemplateView):
    template_name = 'bestseller_products.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        from django.db.models import Sum, Count, Avg

        request = self.request
        show_all = request.GET.get('show_all', '').lower() == 'true'
        month_param = request.GET.get('month', '').strip()

        now = timezone.now()
        current_month_value = now.strftime('%Y-%m')

        base_qs = Withdrawals.objects.filter(
            item_type='PRODUCT',
            reason='SOLD',
            is_archived=False,
        )

        if not show_all:
            if month_param:
                try:
                    year_str, month_str = month_param.split('-')
                    base_qs = base_qs.filter(date__year=int(year_str), date__month=int(month_str))
                except (ValueError, IndexError):
                    base_qs = base_qs.filter(date__year=now.year, date__month=now.month)
            else:
                base_qs = base_qs.filter(date__year=now.year, date__month=now.month)

        sales_qs = base_qs.values('item_id').annotate(
            total_quantity=Sum('quantity'),
            total_revenue=Sum('total_amount'),
        )

        all_totals = sales_qs.aggregate(
            grand_total_quantity=Sum('total_quantity'),
            grand_total_revenue=Sum('total_revenue'),
        )
        total_quantity = all_totals['grand_total_quantity'] or 0
        total_revenue = all_totals['grand_total_revenue'] or 0
        total_products = sales_qs.count()
        average_revenue = (Decimal(str(total_revenue)) / total_products) if total_products else 0

        sorted_asc = list(sales_qs.filter(total_quantity__gt=0).order_by('total_quantity')[:20])
        sorted_desc = list(sales_qs.order_by('-total_quantity')[:20])

        all_item_ids = set(e['item_id'] for e in sorted_desc + sorted_asc)
        products_map = {
            p.id: p
            for p in Products.objects.select_related(
                'product_type', 'variant', 'size', 'size_unit'
            ).filter(id__in=all_item_ids)
        }

        def build_row(entry):
            p = products_map.get(entry['item_id'])
            return {
                'product__product_type__name': p.product_type.name if p and p.product_type else '',
                'product__variant__name': p.variant.name if p and p.variant else '',
                'product__size__size_label': str(p.size) if p and p.size else '',
                'product__size_unit__unit_name': p.size_unit.unit_name if p and p.size_unit else '',
                'total_quantity': entry['total_quantity'],
                'total_revenue': entry['total_revenue'] or 0,
            }

        best_sellers = [build_row(e) for e in sorted_desc]
        low_sellers = [build_row(e) for e in sorted_asc]

        context['best_sellers'] = best_sellers
        context['low_sellers'] = low_sellers
        context['total_quantity'] = total_quantity
        context['total_revenue'] = total_revenue
        context['total_products'] = total_products
        context['average_revenue'] = average_revenue
        context['current_month_value'] = current_month_value
        return context

# export_bestseller_report
@login_required
def export_bestseller_report(request):
    import csv
    from django.http import HttpResponse
    from django.db.models import Sum, Count
    from django.template.loader import render_to_string
    from xhtml2pdf import pisa
    from io import BytesIO
    from datetime import datetime

    format_type = request.GET.get('format', 'csv').lower()
    show_all = request.GET.get('show_all', '').lower() == 'true'
    include_no_sales = request.GET.get('include_no_sales', '').lower() == 'true'
    month = request.GET.get('month', '').strip()

    try:
        # Build base queryset
        queryset = Withdrawals.objects.filter(
            item_type='PRODUCT',
            reason='SOLD'
        )

        # Apply month filter if not showing all
        if not show_all and month:
            try:
                year, month_num = month.split('-')
                queryset = queryset.filter(
                    date__year=year,
                    date__month=month_num
                )
            except (ValueError, IndexError):
                pass  # Invalid month format, ignore filter

        # Get sales data
        sales_by_item = queryset.values('item_id').annotate(
            total_quantity=Sum('quantity'),
            total_transactions=Count('id')
        ).order_by('-total_quantity')[:50]

        # Export based on format
        if format_type == 'pdf':
            # Prepare data for PDF template
            bestseller_items = []
            total_sold = 0
            total_transactions = 0

            for entry in sales_by_item:
                try:
                    product = Products.objects.select_related('product_type', 'variant', 'size', 'size_unit').get(id=entry['item_id'])
                    product_name = str(product)
                    product_type = product.product_type.name if product.product_type else ''
                    variant = product.variant.name if product.variant else ''
                except Products.DoesNotExist:
                    product_name = f'Unknown (ID {entry["item_id"]})'
                    product_type = ''
                    variant = ''

                bestseller_items.append({
                    'product_name': product_name,
                    'product_type': product_type,
                    'variant': variant,
                    'total_quantity': entry.get('total_quantity', 0),
                    'total_transactions': entry.get('total_transactions', 0),
                })

                total_sold += entry.get('total_quantity', 0)
                total_transactions += entry.get('total_transactions', 0)

            # Prepare context for template
            context = {
                'bestseller_items': bestseller_items,
                'total_products': len(bestseller_items),
                'total_sold': total_sold,
                'total_transactions': total_transactions,
                'generated_date': timezone.now().strftime('%B %d, %Y at %I:%M %p'),
                'current_year': timezone.now().year,
                'logo_url': None,
                'filters': {
                    'month': month if month and not show_all else None,
                    'show_all': show_all if show_all else None
                }
            }

            # Render HTML template
            html = render_to_string('exports/bestseller_pdf.html', context)

            # Generate PDF
            pdf_buffer = BytesIO()
            pisa_status = pisa.CreatePDF(html, dest=pdf_buffer)

            if not pisa_status.err:
                response = HttpResponse(pdf_buffer.getvalue(), content_type='application/pdf')
                response['Content-Disposition'] = 'attachment; filename="bestseller_report.pdf"'
                return response
            else:
                raise Exception('PDF generation failed')

        else:  # CSV format
            response = HttpResponse(content_type='text/csv')
            response['Content-Disposition'] = 'attachment; filename="bestseller_report.csv"'
            writer = csv.writer(response)
            writer.writerow(['Product', 'Product Type', 'Variant', 'Total Sold', 'Transactions'])

            for entry in sales_by_item:
                try:
                    product = Products.objects.select_related('product_type', 'variant').get(id=entry['item_id'])
                    product_name = str(product)
                    product_type = product.product_type.name if product.product_type else ''
                    variant = product.variant.name if product.variant else ''
                except Products.DoesNotExist:
                    product_name = f'Unknown (ID {entry["item_id"]})'
                    product_type = ''
                    variant = ''
                writer.writerow([
                    product_name,
                    product_type,
                    variant,
                    entry.get('total_quantity', 0),
                    entry.get('total_transactions', 0),
                ])
            return response

    except Exception as e:
        logger.exception("Best seller export failed")
        # Handle errors gracefully
        if format_type == 'pdf':
            response = HttpResponse(content_type='text/plain')
            response['Content-Disposition'] = 'attachment; filename="bestseller_error.txt"'
            response.write(f'An error occurred: {str(e)}')
        else:
            response = HttpResponse(content_type='text/csv')
            response['Content-Disposition'] = 'attachment; filename="bestseller_error.csv"'
            writer = csv.writer(response)
            writer.writerow(['Error'])
            writer.writerow([f'An error occurred: {str(e)}'])
        return response

# financial_loss
@login_required
def financial_loss(request):
    if not request.user.is_superuser:
        messages.error(request, "You don't have permission to access this page.")
        return redirect('home')
    
    from django.core.paginator import Paginator
    from datetime import datetime
    import calendar
    
    loss_reasons = ['EXPIRED', 'DAMAGED', 'SPOILED', 'WASTED', 'LOSS']
    
    # Get current month value for default filter
    current_month = timezone.now().strftime('%Y-%m')
    current_month_value = current_month
    
    # Product withdrawals with loss reasons
    product_withdrawals_qs = Withdrawals.objects.filter(
        item_type='PRODUCT',
        reason__in=loss_reasons,
        is_archived=False
    ).order_by('-date')
    
    # Apply product date filter
    product_date_filter = request.GET.get('product_date_filter')
    product_show_all = request.GET.get('product_show_all')
    
    if product_show_all:
        # Show all data
        pass
    elif product_date_filter:
        try:
            _pd = datetime.strptime(product_date_filter, '%Y-%m')
            product_withdrawals_qs = product_withdrawals_qs.filter(date__year=_pd.year, date__month=_pd.month)
        except ValueError:
            pass
    else:
        _now = timezone.now()
        product_withdrawals_qs = product_withdrawals_qs.filter(date__year=_now.year, date__month=_now.month)
    
    # Calculate product loss and prepare withdrawal data
    product_loss = 0
    product_withdrawals_data = []
    for w in product_withdrawals_qs:
        try:
            product = Products.objects.get(id=w.item_id)
            unit_price = 0
            if hasattr(product, 'unit_price') and product.unit_price:
                unit_price = float(product.unit_price.unit_price) if hasattr(product.unit_price, 'unit_price') else float(product.unit_price)
            elif hasattr(product, 'srp_price') and product.srp_price:
                unit_price = float(product.srp_price.srp_price) if hasattr(product.srp_price, 'srp_price') else float(product.srp_price)
            
            loss_amount = float(w.quantity or 0) * unit_price
            product_loss += loss_amount
            
            product_withdrawals_data.append({
                'date': w.date,
                'product_name': str(product),
                'quantity': w.quantity,
                'unit_price': unit_price,
                'reason': w.reason,
                'get_reason_display': w.get_reason_display if hasattr(w, 'get_reason_display') else w.reason,
                'loss_amount': loss_amount,
            })
        except Products.DoesNotExist:
            product_withdrawals_data.append({
                'date': w.date,
                'product_name': f'Unknown (ID {w.item_id})',
                'quantity': w.quantity,
                'unit_price': 0,
                'reason': w.reason,
                'get_reason_display': w.reason,
                'loss_amount': 0,
            })
    
    # Raw material withdrawals with loss reasons
    raw_material_withdrawals_qs = Withdrawals.objects.filter(
        item_type='RAW_MATERIAL',
        reason__in=loss_reasons,
        is_archived=False
    ).order_by('-date')
    
    # Apply raw material date filter
    raw_material_date_filter = request.GET.get('raw_material_date_filter')
    raw_material_show_all = request.GET.get('raw_material_show_all')
    
    if raw_material_show_all:
        # Show all data
        pass
    elif raw_material_date_filter:
        try:
            _rd = datetime.strptime(raw_material_date_filter, '%Y-%m')
            raw_material_withdrawals_qs = raw_material_withdrawals_qs.filter(date__year=_rd.year, date__month=_rd.month)
        except ValueError:
            pass
    else:
        _now2 = timezone.now()
        raw_material_withdrawals_qs = raw_material_withdrawals_qs.filter(date__year=_now2.year, date__month=_now2.month)
    
    # Calculate raw material loss and prepare withdrawal data
    raw_material_loss = 0
    raw_material_withdrawals_data = []
    for w in raw_material_withdrawals_qs:
        try:
            material = RawMaterials.objects.get(id=w.item_id)
            price_per_unit = 0
            if hasattr(material, 'price_per_unit') and material.price_per_unit:
                price_per_unit = float(material.price_per_unit)
            
            loss_amount = float(w.quantity or 0) * price_per_unit
            raw_material_loss += loss_amount
            
            unit_name = ''
            if hasattr(material, 'unit') and material.unit:
                unit_name = material.unit.unit_name if hasattr(material.unit, 'unit_name') else str(material.unit)
            
            raw_material_withdrawals_data.append({
                'date': w.date,
                'material_name': str(material),
                'quantity': w.quantity,
                'unit_name': unit_name,
                'price_per_unit': price_per_unit,
                'reason': w.reason,
                'get_reason_display': w.get_reason_display if hasattr(w, 'get_reason_display') else w.reason,
                'loss_amount': loss_amount,
            })
        except RawMaterials.DoesNotExist:
            raw_material_withdrawals_data.append({
                'date': w.date,
                'material_name': f'Unknown (ID {w.item_id})',
                'quantity': w.quantity,
                'unit_name': '',
                'price_per_unit': 0,
                'reason': w.reason,
                'get_reason_display': w.reason,
                'loss_amount': 0,
            })
    
    # Paginate product withdrawals
    product_paginator = Paginator(product_withdrawals_data, 10)
    product_page_number = request.GET.get('product_page', 1)
    product_page_obj = product_paginator.get_page(product_page_number)
    product_is_paginated = product_paginator.num_pages > 1
    
    # Paginate raw material withdrawals
    raw_material_paginator = Paginator(raw_material_withdrawals_data, 10)
    raw_material_page_number = request.GET.get('raw_material_page', 1)
    raw_material_page_obj = raw_material_paginator.get_page(raw_material_page_number)
    raw_material_is_paginated = raw_material_paginator.num_pages > 1
    
    return render(request, 'financial_loss.html', {
        'product_loss': product_loss,
        'raw_material_loss': raw_material_loss,
        'product_withdrawals': product_page_obj,
        'raw_material_withdrawals': raw_material_page_obj,
        'product_paginator': product_paginator,
        'raw_material_paginator': raw_material_paginator,
        'product_page_obj': product_page_obj,
        'raw_material_page_obj': raw_material_page_obj,
        'product_is_paginated': product_is_paginated,
        'raw_material_is_paginated': raw_material_is_paginated,
        'current_month_value': current_month_value,
    })

# financial_loss_export
@login_required
def financial_loss_export(request):
    import csv
    from django.http import HttpResponse
    from django.template.loader import render_to_string
    from xhtml2pdf import pisa
    from io import BytesIO
    from datetime import datetime

    format_type = request.GET.get('format', 'csv').lower()
    filter_type = request.GET.get('filter', 'date')
    start = request.GET.get('start', '')
    end = request.GET.get('end', '')

    loss_reasons = ['EXPIRED', 'DAMAGED', 'SPOILED', 'WASTED', 'LOSS']

    # Build base queryset
    withdrawals = Withdrawals.objects.filter(
        reason__in=loss_reasons,
        is_archived=False
    ).order_by('-date')

    # Apply date filters
    filter_info = 'All Data'
    if filter_type == 'date' and start:
        withdrawals = withdrawals.filter(date__date=start)
        filter_info = f'Date: {start}'
    elif filter_type == 'month' and start:
        try:
            year, month = start.split('-')
            withdrawals = withdrawals.filter(date__year=year, date__month=month)
            filter_info = f'Month: {start}'
        except ValueError:
            pass
    elif filter_type == 'year' and start:
        withdrawals = withdrawals.filter(date__year=start)
        filter_info = f'Year: {start}'
    elif filter_type == 'range' and start and end:
        withdrawals = withdrawals.filter(date__date__range=[start, end])
        filter_info = f'Range: {start} to {end}'

    # Separate by item type (chunked to avoid memory exhaustion)
    product_withdrawals = []
    raw_material_withdrawals = []

    CHUNK_SIZE = 1000
    total_withdrawals = withdrawals.count()
    for offset in range(0, total_withdrawals, CHUNK_SIZE):
        chunk = withdrawals[offset:offset + CHUNK_SIZE]
        for w in chunk:
            if w.item_type == 'PRODUCT':
                try:
                    product = Products.objects.select_related('unit_price').get(id=w.item_id)
                    unit_price = product.unit_price.unit_price if product.unit_price else Decimal('0.00')
                    loss_amount = Decimal(w.quantity) * unit_price
                    product_withdrawals.append({
                        'date': w.date,
                        'product_name': str(product),
                        'quantity': w.quantity,
                        'unit_price': unit_price,
                        'reason': w.reason,
                        'get_reason_display': w.get_reason_display(),
                        'loss_amount': loss_amount,
                    })
                except Products.DoesNotExist:
                    continue
            elif w.item_type == 'RAW_MATERIAL':
                try:
                    material = RawMaterials.objects.get(id=w.item_id)
                    loss_amount = Decimal(w.quantity) * material.price_per_unit
                    raw_material_withdrawals.append({
                        'date': w.date,
                        'material_name': material.name,
                        'quantity': w.quantity,
                        'unit_name': material.unit_name,
                        'price_per_unit': material.price_per_unit,
                        'reason': w.reason,
                        'get_reason_display': w.get_reason_display(),
                        'loss_amount': loss_amount,
                    })
                except RawMaterials.DoesNotExist:
                    continue

    # Calculate totals
    product_loss = sum(item['loss_amount'] for item in product_withdrawals)
    raw_material_loss = sum(item['loss_amount'] for item in raw_material_withdrawals)
    total_loss = product_loss + raw_material_loss

    try:
        # Export based on format
        if format_type == 'pdf':
            # Prepare context for template
            context = {
                'product_withdrawals': product_withdrawals,
                'raw_material_withdrawals': raw_material_withdrawals,
                'product_loss': product_loss,
                'raw_material_loss': raw_material_loss,
                'total_loss': total_loss,
                'filter_info': filter_info,
                'generated_date': timezone.now().strftime('%B %d, %Y at %I:%M %p'),
                'current_year': timezone.now().year,
                'logo_url': None,
            }

            # Render HTML template
            html = render_to_string('exports/financial_loss_pdf.html', context)

            # Generate PDF
            pdf_buffer = BytesIO()
            pisa_status = pisa.CreatePDF(html, dest=pdf_buffer)

            if not pisa_status.err:
                response = HttpResponse(pdf_buffer.getvalue(), content_type='application/pdf')
                response['Content-Disposition'] = 'attachment; filename="financial_loss.pdf"'
                return response
            else:
                raise Exception('PDF generation failed')

        else:  # CSV format
            response = HttpResponse(content_type='text/csv')
            response['Content-Disposition'] = 'attachment; filename="financial_loss.csv"'
            response.write(u'\ufeff'.encode('utf8'))
            writer = csv.writer(response)
            writer.writerow(['Type', 'Date', 'Item', 'Quantity', 'Reason', 'Financial Loss'])

            # Write product losses
            for item in product_withdrawals:
                writer.writerow([
                    'Product',
                    item['date'].strftime('%Y-%m-%d %H:%M:%S'),
                    item['product_name'],
                    item['quantity'],
                    item['get_reason_display'],
                    f"₱{item['loss_amount']:,.2f}",
                ])

            # Write raw material losses
            for item in raw_material_withdrawals:
                writer.writerow([
                    'Packaging Material',
                    item['date'].strftime('%Y-%m-%d %H:%M:%S'),
                    item['material_name'],
                    f"{item['quantity']} {item['unit_name']}",
                    item['get_reason_display'],
                    f"₱{item['loss_amount']:,.2f}",
                ])

            return response

    except Exception as e:
        logger.exception("Financial loss export failed")
        # Handle errors gracefully
        if format_type == 'pdf':
            response = HttpResponse(content_type='text/plain')
            response['Content-Disposition'] = 'attachment; filename="financial_loss_error.txt"'
            response.write(f'An error occurred: {str(e)}')
        else:
            response = HttpResponse(content_type='text/csv')
            response['Content-Disposition'] = 'attachment; filename="financial_loss_error.csv"'
            writer = csv.writer(response)
            writer.writerow(['Error'])
            writer.writerow([f'An error occurred: {str(e)}'])
        return response
