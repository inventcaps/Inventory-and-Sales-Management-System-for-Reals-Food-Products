from datetime import date, timedelta
from decimal import Decimal
from django.db.models import Sum
from django.utils import timezone
from realsproj.models import Products, ProductBatches


def get_product_display_name(product) -> str:
    parts = [product.product_type.name, product.variant.name]
    if product.size and product.size_unit:
        parts.append(f"({product.size.size_label} {product.size_unit.unit_name})")
    return " ".join(parts)


def is_batch_expired(batch, reference_date=None) -> bool:
    if reference_date is None:
        reference_date = timezone.localdate()
    if batch.expiration_date is None:
        return False
    return batch.expiration_date < reference_date


def compute_available_stock(product) -> Decimal:
    today = timezone.localdate()
    result = ProductBatches.objects.filter(
        product=product,
        is_archived=False,
        quantity__gt=0,
    ).exclude(
        expiration_date__lt=today
    ).aggregate(total=Sum('quantity'))
    return result['total'] or Decimal('0')


def compute_expiring_stock(product, days_ahead=30) -> Decimal:
    today = timezone.localdate()
    cutoff = today + timedelta(days=days_ahead)
    result = ProductBatches.objects.filter(
        product=product,
        is_archived=False,
        quantity__gt=0,
        expiration_date__gte=today,
        expiration_date__lte=cutoff,
    ).aggregate(total=Sum('quantity'))
    return result['total'] or Decimal('0')
