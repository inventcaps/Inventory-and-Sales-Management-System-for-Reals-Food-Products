from decimal import Decimal
from collections import defaultdict
from realsproj.models import Withdrawals, Products, Discounts


def compute_withdrawal_total_amount(withdrawal) -> Decimal:
    if withdrawal.total_amount is not None:
        return withdrawal.total_amount

    if withdrawal.custom_price is not None:
        return Decimal(withdrawal.custom_price)

    if withdrawal.price_type not in ('UNIT', 'SRP'):
        return Decimal('0')

    try:
        product = Products.objects.select_related('unit_price', 'srp_price').get(id=withdrawal.item_id)
    except Products.DoesNotExist:
        return Decimal('0')

    base_price = product.unit_price.unit_price if withdrawal.price_type == 'UNIT' else product.srp_price.srp_price

    discount_percent = Decimal('0')
    if withdrawal.discount_id:
        try:
            discount = Discounts.objects.get(id=withdrawal.discount_id)
            discount_percent = Decimal(discount.value)
        except Discounts.DoesNotExist:
            pass
    elif withdrawal.custom_discount_value:
        discount_percent = Decimal(withdrawal.custom_discount_value)

    discounted_price = base_price * (1 - discount_percent / 100)
    return Decimal(withdrawal.quantity) * discounted_price


def group_withdrawals_by_order(withdrawals_qs):
    groups = defaultdict(list)
    for w in withdrawals_qs:
        key = w.order_group_id or f"single_{w.id}"
        groups[key].append(w)

    result = []
    for key, items in groups.items():
        total_items = len(items)
        total_amount = sum(compute_withdrawal_total_amount(w) for w in items)
        first = items[0]
        result.append({
            'group_key': key,
            'order_group_id': first.order_group_id,
            'is_single': first.order_group_id is None,
            'date': first.date,
            'reason': first.reason,
            'reason_display': first.get_reason_display(),
            'item_type': first.item_type,
            'item_type_display': first.get_item_type_display(),
            'sales_channel': first.sales_channel,
            'customer_name': first.customer_name,
            'created_by_admin': first.created_by_admin,
            'item_count': total_items,
            'total_amount': total_amount,
            'withdrawals': items,
        })

    result.sort(key=lambda x: x['date'], reverse=True)
    return result


def compute_payment_status(total_paid: Decimal, total_due: Decimal) -> str:
    if total_due == 0:
        return 'PAID'
    if not total_paid or total_paid <= 0:
        return 'UNPAID'
    if total_paid >= total_due:
        return 'PAID'
    return 'PARTIAL'
