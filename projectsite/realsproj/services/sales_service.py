from decimal import Decimal
from django.db.models import Sum, Avg, Count, Q
from django.utils import timezone
from realsproj.models import Sales, Expenses


def get_manual_sales_queryset(filters=None):
    qs = Sales.objects.filter(is_archived=False).exclude(
        Q(description__icontains="Order #") | Q(description__icontains="order #")
    )
    return _apply_common_filters(qs, filters)


def get_withdrawal_sales_queryset(filters=None):
    qs = Sales.objects.filter(is_archived=False).filter(
        Q(description__icontains="Order #") | Q(description__icontains="order #")
    )
    return _apply_common_filters(qs, filters)


def get_expenses_queryset(filters=None):
    qs = Expenses.objects.filter(is_archived=False)
    return _apply_common_filters(qs, filters)


def _apply_common_filters(qs, filters=None):
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
        qs = qs.filter(
            Q(category__icontains=query) | Q(amount__icontains=query) | Q(date__icontains=query)
        )
    return qs


def compute_aggregate_summary(queryset):
    return queryset.aggregate(
        total=Sum("amount"),
        average=Avg("amount"),
        count=Count("id"),
    )


def get_filter_params(request):
    return {
        'month': request.GET.get('month', '').strip(),
        'category': request.GET.get('category', '').strip(),
        'query': request.GET.get('q', '').strip(),
        'show_all': request.GET.get('show_all', '').strip(),
    }


def get_expense_filter_params(request):
    return {
        'month': request.GET.get('expense_month', '').strip(),
        'category': request.GET.get('expense_category', '').strip(),
        'query': request.GET.get('q', '').strip(),
        'show_all': request.GET.get('expense_show_all', '').strip(),
    }


def get_withdrawal_filter_params(request):
    return {
        'month': request.GET.get('withdrawal_date_filter', '').strip(),
        'channel': request.GET.get('withdrawal_channel', '').strip(),
        'payment_status': request.GET.get('withdrawal_payment_status', '').strip(),
        'show_all': request.GET.get('withdrawal_show_all', '').strip(),
    }
