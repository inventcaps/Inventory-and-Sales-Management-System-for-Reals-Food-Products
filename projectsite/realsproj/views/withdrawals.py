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
from itertools import islice
from datetime import datetime, timedelta, date
from django.db.models.signals import pre_save, post_delete
from django.dispatch import receiver
from django.utils import timezone
from django.db.models import Q, F, CharField
import re
import logging

logger = logging.getLogger(__name__)

# WithdrawSuccessView
class WithdrawSuccessView(LoginRequiredMixin, ListView):
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
        
        # Batch-load Products and RawMaterials to fix N+1
        product_ids = set()
        material_ids = set()
        for w in all_withdrawals:
            if w.item_type == 'PRODUCT':
                product_ids.add(w.item_id)
            elif w.item_type == 'RAW_MATERIAL':
                material_ids.add(w.item_id)

        products_map = {}
        materials_map = {}
        if product_ids:
            products_map = {
                p.id: p for p in Products.objects.select_related(
                    'product_type', 'variant', 'size', 'size_unit'
                ).filter(id__in=product_ids)
            }
        if material_ids:
            materials_map = {
                m.id: m for m in RawMaterials.objects.select_related('unit').filter(id__in=material_ids)
            }

        for withdrawal in all_withdrawals:
            if withdrawal.item_type == 'PRODUCT':
                product = products_map.get(withdrawal.item_id)
                withdrawal.item_display_cache = str(product) if product else f"Unknown Product (ID {withdrawal.item_id})"
            else:
                material = RawMaterials.objects.filter(id=withdrawal.item_id).first()
                withdrawal.item_display_cache = str(material) if material else f"Unknown Material (ID {withdrawal.item_id})"

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

# export_withdrawals
@require_GET
@login_required
def export_withdrawals(request):
    import csv
    from django.http import HttpResponse
    from django.template.loader import render_to_string
    from xhtml2pdf import pisa
    from io import BytesIO
    from datetime import datetime

    format_type = request.GET.get('format', 'csv').lower()
    
    qs = Withdrawals.objects.filter(is_archived=False).select_related('created_by_admin').order_by('-date')
    
    show_all = request.GET.get('show_all', '').strip()
    date_filter = request.GET.get('date_filter', '').strip()
    item_type = request.GET.get('item_type', '').strip()
    reason = request.GET.get('reason', '').strip()
    
    # Build filter info for display
    filter_info_parts = []
    if show_all:
        filter_info_parts.append('All Data')
    elif date_filter:
        filter_info_parts.append(f'Month: {date_filter}')
    else:
        today = timezone.now()
        filter_info_parts.append(f'Month: {today.strftime("%Y-%m")}')
    
    if item_type:
        filter_info_parts.append(f'Item Type: {item_type}')
    
    if reason:
        filter_info_parts.append(f'Reason: {reason}')
    
    filter_info = ' | '.join(filter_info_parts) if filter_info_parts else 'All Data'
    
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
    
    try:
        # Export based on format
        if format_type == 'pdf':
            # Calculate summary data
            total_withdrawals = sum(w.quantity for w in qs)
            
            product_withdrawals = [w for w in qs if w.item_type == 'PRODUCT']
            raw_material_withdrawals = [w for w in qs if w.item_type == 'RAW_MATERIAL']
            
            product_withdrawals_count = len(product_withdrawals)
            product_withdrawals_qty = sum(w.quantity for w in product_withdrawals)
            
            rawmat_withdrawals_count = len(raw_material_withdrawals)
            rawmat_withdrawals_qty = sum(w.quantity for w in raw_material_withdrawals)
            
            # Prepare context for template
            context = {
                'withdrawals': qs,
                'total_withdrawals': total_withdrawals,
                'product_withdrawals_count': product_withdrawals_count,
                'product_withdrawals_qty': product_withdrawals_qty,
                'rawmat_withdrawals_count': rawmat_withdrawals_count,
                'rawmat_withdrawals_qty': rawmat_withdrawals_qty,
                'filter_info': filter_info,
                'generated_date': timezone.now().strftime('%B %d, %Y at %I:%M %p'),
                'current_year': timezone.now().year,
                'logo_url': None,
            }
            
            # Render HTML template
            html = render_to_string('exports/withdrawals_pdf.html', context)
            
            # Generate PDF
            pdf_buffer = BytesIO()
            pisa_status = pisa.CreatePDF(html, dest=pdf_buffer)
            
            if not pisa_status.err:
                response = HttpResponse(pdf_buffer.getvalue(), content_type='application/pdf')
                response['Content-Disposition'] = 'attachment; filename="withdrawals.pdf"'
                return response
            else:
                raise Exception('PDF generation failed')
        
        else:  # CSV format
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
            CHUNK_SIZE = 1000
            total = qs.count()
            for offset in range(0, total, CHUNK_SIZE):
                chunk = qs[offset:offset + CHUNK_SIZE]
                for withdrawal in chunk:
                    writer.writerow([
                        withdrawal.date.strftime('%Y-%m-%d %H:%M:%S'),
                        withdrawal.get_item_type_display(),
                        withdrawal.get_reason_display(),
                        withdrawal.get_item_display(),
                        f"{withdrawal.quantity:.2f}",
                        withdrawal.created_by_admin.username,
                    ])
            
            return response
    
    except Exception as e:
        logger.exception("Withdrawals export failed")
        if format_type == 'pdf':
            response = HttpResponse(content_type='text/plain')
            response['Content-Disposition'] = 'attachment; filename="withdrawals_error.txt"'
            response.write(f'An error occurred: {str(e)}')
        else:
            response = HttpResponse(content_type='text/csv')
            response['Content-Disposition'] = 'attachment; filename="withdrawals_error.csv"'
            writer = csv.writer(response)
            writer.writerow(['Error'])
            writer.writerow([f'An error occurred: {str(e)}'])
        return response

# WithdrawItemView
class WithdrawItemView(LoginRequiredMixin, View):
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
            # Get batches with packaging information, grouped by packaging type
            batches = ProductBatches.objects.filter(
                product=product,
                is_archived=False,
                packaging__isnull=False
            ).select_related('packaging', 'packaging__unit', 'packaging__rawmaterialinventory')

            # Group batches by packaging type
            from collections import defaultdict
            packaging_groups = defaultdict(lambda: {
                'batches': [],
                'total_quantity': 0,
                'expiring_quantity': 0,
                'oldest_expiry': None,
                'newest_expiry': None,
                'packaging': None
            })

            for batch in batches:
                packaging = batch.packaging
                if not packaging:
                    continue
                    
                group_key = packaging.id
                pg = packaging_groups[group_key]
                pg['packaging'] = packaging
                pg['batches'].append(batch)
                pg['total_quantity'] += batch.quantity
                
                # Track expiry info
                if batch.expiration_date:
                    if (batch.expiration_date <= expiration_cutoff and
                        batch.expiration_date >= today and
                        batch.quantity > 0):
                        pg['expiring_quantity'] += batch.quantity
                    
                    # Track oldest expiry (FIFO priority)
                    if pg['oldest_expiry'] is None or batch.expiration_date < pg['oldest_expiry']:
                        pg['oldest_expiry'] = batch.expiration_date
                    
                    # Track newest expiry (for display)
                    if pg['newest_expiry'] is None or batch.expiration_date > pg['newest_expiry']:
                        pg['newest_expiry'] = batch.expiration_date

            # Build packaging options from groups
            packaging_options = []
            for packaging_id, pg in packaging_groups.items():
                packaging = pg['packaging']
                packaging_name = f"{packaging.name}"
                if packaging.size and packaging.unit:
                    unit_name = packaging.unit.unit_name if hasattr(packaging.unit, 'unit_name') else str(packaging.unit)
                    packaging_name = f"{packaging_name} ({packaging.size} {unit_name})"

                # Format dates
                oldest_exp_str = pg['oldest_expiry'].strftime('%Y-%m-%d') if pg['oldest_expiry'] else 'No Date'
                newest_exp_str = pg['newest_expiry'].strftime('%Y-%m-%d') if pg['newest_expiry'] else 'No Date'
                
                expiry_display = oldest_exp_str
                if oldest_exp_str != newest_exp_str:
                    expiry_display = f"{oldest_exp_str} to {newest_exp_str}"

                packaging_options.append({
                    'packaging_id': packaging_id,  # Use packaging ID for selection
                    'name': packaging_name,
                    'quantity': pg['total_quantity'],
                    'expiring': pg['expiring_quantity'],
                    'batch_count': len(pg['batches']),
                    'oldest_expiry': oldest_exp_str,
                    'expiry_range': expiry_display,
                    'packaging_obj': packaging
                })

            # Sort by oldest expiry date (FIFO) then by packaging name
            product.packaging_options = sorted(
                packaging_options, 
                key=lambda x: (x['oldest_expiry'] if x['oldest_expiry'] != 'No Date' else '9999-12-31', x['name'])
            )

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

                        # Get selected packaging type from form (now packaging_id instead of batch_id)
                        packaging_id = request.POST.get(f"packaging_{product_id}")
                        selected_packaging = None

                        if packaging_id:
                            try:
                                selected_packaging = RawMaterials.objects.get(id=packaging_id, category='PACKAGING')
                            except RawMaterials.DoesNotExist:
                                messages.error(request, f"Invalid packaging type selected for {product}")
                                continue

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

                        # =====================================
                        # FIFO AUTO-SELECTION LOGIC
                        # =====================================
                        remaining = quantity
                        batches_consumed = []

                        if selected_packaging:
                            # Get batches for this product and packaging, ordered by FIFO (oldest first)
                            fifo_batches = ProductBatches.objects.filter(
                                product=product,
                                packaging=selected_packaging,
                                is_archived=False,
                                quantity__gt=0
                            ).order_by('expiration_date', 'id')  # FIFO: oldest expiry first

                            for batch in fifo_batches:
                                if remaining <= 0:
                                    break
                                
                                deduct_amount = min(remaining, batch.quantity)
                                batches_consumed.append({
                                    'batch': batch,
                                    'quantity': deduct_amount,
                                    'packaging': selected_packaging
                                })
                                remaining -= deduct_amount
                        else:
                            # No packaging selected - get all batches FIFO
                            fifo_batches = ProductBatches.objects.filter(
                                product=product,
                                is_archived=False,
                                quantity__gt=0
                            ).order_by('expiration_date', 'id')

                            for batch in fifo_batches:
                                if remaining <= 0:
                                    break
                                
                                deduct_amount = min(remaining, batch.quantity)
                                batches_consumed.append({
                                    'batch': batch,
                                    'quantity': deduct_amount,
                                    'packaging': batch.packaging
                                })
                                remaining -= deduct_amount

                        if remaining > 0:
                            messages.error(request, f"⚠️ Insufficient stock for {product}. Could not fulfill full quantity of {quantity}.")
                            continue

                        # Create one Withdrawal record per batch consumed
                        # This enables accurate restoration later
                        for i, consumed in enumerate(batches_consumed):
                            batch = consumed['batch']
                            batch_qty = consumed['quantity']
                            packaging = consumed['packaging']
                            
                            # For multi-batch withdrawals, only the first gets price/discount info
                            # Others get quantity only (they're part of the same order)
                            is_first_batch = (i == 0)
                            
                            withdrawal = Withdrawals.objects.create(
                                item_id=product.id,
                                item_type="PRODUCT",
                                quantity=batch_qty,
                                reason=reason,
                                date=timezone.now(),
                                created_by_admin=request.user,
                                sales_channel=sales_channel if reason == "SOLD" else None,
                                price_type=price_type if reason == "SOLD" and payment_status == "PAID" and is_first_batch else None,
                                custom_price=custom_price if custom_price and is_first_batch else None,
                                discount_id=discount_obj.id if discount_obj and is_first_batch else None,
                                custom_discount_value=custom_value if is_first_batch else None,
                                customer_name=customer_name if sales_channel in ['ORDER', 'CONSIGNMENT', 'RESELLER'] else None,
                                payment_status=payment_status if sales_channel in ['ORDER', 'CONSIGNMENT', 'RESELLER'] else 'PAID',
                                paid_amount=paid_amount if payment_status == 'PARTIAL' and is_first_batch else None,
                                order_group_id=order_group_id,
                                packaging=packaging,
                                batch=batch,
                                actual_unit_price=actual_unit_price if is_first_batch else None,
                                actual_discount_percent=actual_discount_percent if is_first_batch else None,
                                actual_discount_amount=actual_discount_amount if is_first_batch else None,
                                final_price_per_unit=final_price_per_unit if is_first_batch else None,
                                total_amount=total_amount if is_first_batch else None,
                            )

                        count += 1
                    except (Products.DoesNotExist, ValueError, Decimal.InvalidOperation) as e:
                        messages.error(request, f"❌ Error withdrawing product: {str(e)}")
                        continue
                    except Exception as e:
                        logger.exception("Unexpected error withdrawing product")
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
                    except (RawMaterials.DoesNotExist, ValueError, Decimal.InvalidOperation) as e:
                        messages.error(request, f"❌ Error withdrawing raw material: {str(e)}")
                        continue
                    except Exception as e:
                        logger.exception("Unexpected error withdrawing raw material")
                        messages.error(request, f"❌ Error withdrawing raw material: {str(e)}")
                        continue

        if count > 0:
            # Trigger trg_withdrawal_sales_func creates per-item Sales records for SOLD withdrawals
            messages.success(request, f"✅ Success! {count} item(s) withdrawn. Inventory updated!")
        else:
            messages.warning(request, "⚠️ No items withdrawn. Please enter quantity for at least one item.")

        return redirect("withdrawals")

# WithdrawalsArchiveView
class WithdrawalsArchiveView(LoginRequiredMixin, View):
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

# ArchivedWithdrawalsListView
class ArchivedWithdrawalsListView(ListView):
    model = Withdrawals
    template_name = 'archived_withdrawals.html'
    context_object_name = 'object_list'
    paginate_by = 10

    def get_queryset(self):
        return Withdrawals.objects.filter(is_archived=True).order_by('-date')

# WithdrawalsUnarchiveView
class WithdrawalsUnarchiveView(LoginRequiredMixin, View):
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

# WithdrawalBulkRestoreView
class WithdrawalBulkRestoreView(LoginRequiredMixin, View):
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
            logger.exception("Withdrawal bulk restore failed")
            return JsonResponse({'success': False, 'message': str(e)})

# WithdrawalBulkDeleteView
# WithdrawalsArchiveOldView
class WithdrawalsArchiveOldView(LoginRequiredMixin, View):
    def post(self, request):
        from datetime import timedelta
        one_year_ago = timezone.now() - timedelta(days=365)
        archived_count = Withdrawals.objects.filter(is_archived=False, date__lt=one_year_ago).update(is_archived=True)
        messages.success(request, f"📦 {archived_count} withdrawal(s) older than 1 year have been archived.")
        return redirect('withdrawals')

# withdrawals_bulk_delete
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
        logger.exception("Withdrawals bulk delete failed")
        return JsonResponse({'success': False, 'message': str(e)})

# withdrawals_bulk_archive
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
        logger.exception("Withdrawals bulk archive failed")
        return JsonResponse({'success': False, 'message': str(e)})

# WithdrawUpdateView
class WithdrawUpdateView(LoginRequiredMixin, UpdateView):
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

            except (Products.DoesNotExist, RawMaterials.DoesNotExist) as e:
                messages.error(self.request, f"❌ Item not found: {str(e)}")
                return redirect(self.get_success_url())
            except Exception as e:
                logger.exception("Error validating withdrawal stock")
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

        # If reason changed from SOLD to non-SOLD, remove trigger-created Sales records
        if before['reason'] == 'SOLD' and self.object.reason != 'SOLD':
            Sales.objects.filter(withdrawal=self.object).delete()
            logger.info(
                "Deleted trigger-created Sales records for withdrawal %s "
                "because reason changed from SOLD to %s",
                self.object.pk, self.object.reason
            )

        if inventory_changed:
            messages.success(self.request,
                "✅ Withdrawal updated successfully! Inventory has been adjusted.")

        withdrawal.refresh_from_db()

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

                sales_entry = Sales.objects.filter(withdrawal=withdrawal).first()

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

# WithdrawDeleteView
class WithdrawDeleteView(LoginRequiredMixin, DeleteView):
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
        
        # Delete trigger-created Sales records before deleting the withdrawal
        Sales.objects.filter(withdrawal=withdrawal).delete()

        # Call parent delete
        response = super().post(request, *args, **kwargs)
        
        # History logging is now handled by PostgreSQL triggers
        # Removed manual create_history_log call to prevent double logging
        
        # Per-item Sales record was already deleted above (line 1085).
        # Remaining withdrawals each have their own correct per-item Sales records.
        if (reason == 'SOLD' and 
            sales_channel in ['ORDER', 'CONSIGNMENT', 'RESELLER'] and
            payment_status in ['PAID', 'PARTIAL'] and
            order_group_id):
            
            remaining = Withdrawals.objects.filter(order_group_id=order_group_id)
            if remaining.exists():
                messages.success(request, f"🗑️ Withdrawal deleted. Remaining item(s) still in order #{order_group_id}.")
            else:
                messages.success(request, "🗑️ Withdrawal and sales entry deleted successfully.")
        
        return response

    def get_success_url(self):
        return reverse_lazy('withdrawals')

# WithdrawalGroupArchiveView
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

# WithdrawalGroupDeleteView
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
            
            # Delete all Sales records linked to the deleted withdrawals
            if should_delete_sales:
                deleted_count = Sales.objects.filter(
                    withdrawal__order_group_id=order_group_id
                ).delete()[0]
                if deleted_count > 0:
                    messages.success(request, f"🗑️ Deleted {count} withdrawal(s) and {deleted_count} sales entry(ies) from Order #{order_group_id}")
                else:
                    messages.success(request, f"🗑️ Deleted {count} withdrawal(s) from Order #{order_group_id}")
            else:
                messages.success(request, f"🗑️ Deleted {count} withdrawal(s) from Order #{order_group_id}")
        else:
            messages.warning(request, "No withdrawals found to delete.")
        
        return redirect('withdrawals')

# WithdrawalGroupEditView
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
                except (InvalidOperation, ValueError, TypeError):
                    pass
            
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
            
            # Handle sales entries based on payment status
            if (reason == 'SOLD' and
                sales_channel in ['ORDER', 'CONSIGNMENT', 'RESELLER']):

                if payment_status == 'UNPAID':
                    deleted = Sales.objects.filter(
                        withdrawal__order_group_id=order_group_id
                    ).delete()[0]
                    msg = f"✅ Updated {updated_count} withdrawal(s)"
                    if deleted_count > 0:
                        msg += f", deleted {deleted_count} item(s)"
                    if deleted > 0:
                        msg += f". Sales entry(ies) removed (UNPAID)"
                    messages.success(request, msg)

                elif payment_status in ['PAID', 'PARTIAL']:
                    # Update each withdrawal's Sales record via FK
                    updated_sales = 0
                    for w in withdrawals:
                        if w.reason == 'SOLD':
                            sales_entry = Sales.objects.filter(withdrawal=w).first()
                            if sales_entry and w.total_amount is not None:
                                sales_entry.amount = w.total_amount
                                sales_entry.save()
                                updated_sales += 1

                    msg = f"✅ Updated {updated_count} withdrawal(s)"
                    if deleted_count > 0:
                        msg += f", deleted {deleted_count} item(s)"
                    if updated_sales > 0:
                        msg += f". {updated_sales} sales entry(ies) updated"
                    messages.success(request, msg)
            else:
                msg = f"✅ Updated {updated_count} withdrawal(s)"
                if deleted_count > 0:
                    msg += f", deleted {deleted_count} item(s)"
                messages.success(request, msg)
            
        except (ValueError, Decimal.InvalidOperation) as e:
            messages.error(request, f"❌ Invalid value: {str(e)}")
        except Exception as e:
            logger.exception("Withdrawal group edit failed")
            messages.error(request, f"❌ Error updating withdrawals: {str(e)}")
        
        return redirect('withdrawals')

# get_stock
@login_required
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

# StockChangesList
class StockChangesList(LoginRequiredMixin, ListView):
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

# export_stock_changes
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
    CHUNK_SIZE = 1000
    total = qs.count()
    for offset in range(0, total, CHUNK_SIZE):
        chunk = qs[offset:offset + CHUNK_SIZE]
        for item in chunk:
            writer.writerow([
                item.item_type,
                item.item_id,
                item.item_display,
                f"{item.quantity_change:.2f}",
                item.category,
                item.date.strftime('%Y-%m-%d %H:%M:%S'),
            ])
    
    return response

# StockChangesArchiveView
class StockChangesArchiveView(LoginRequiredMixin, View):
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

# stock_changes_bulk_archive
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
        logger.exception("Stock changes bulk archive failed")
        return JsonResponse({'success': False, 'message': str(e)})

# ArchivedStockChangesListView
class ArchivedStockChangesListView(LoginRequiredMixin, ListView):
    model = StockChanges
    template_name = 'archived_stock_changes.html'
    context_object_name = 'object_list'
    paginate_by = 10

    def get_queryset(self):
        return StockChanges.objects.filter(is_archived=True).order_by('-date')

# StockChangesUnarchiveView
class StockChangesUnarchiveView(LoginRequiredMixin, View):
    def post(self, request, pk):
        stock_change = get_object_or_404(StockChanges, pk=pk)
        stock_change.is_archived = False
        stock_change.save()
        messages.success(request, "✅ Stock change restored successfully.")
        return redirect('stock-changes-archived-list')

# StockChangesBulkRestoreView
class StockChangesBulkRestoreView(LoginRequiredMixin, View):
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
            logger.exception("Stock changes bulk restore failed")
            return JsonResponse({'success': False, 'message': str(e)})

# StockChangesArchiveOldView
class StockChangesArchiveOldView(LoginRequiredMixin, View):
    def post(self, request):
        from datetime import timedelta
        one_year_ago = timezone.now() - timedelta(days=365)
        archived_count = StockChanges.objects.filter(is_archived=False, date__lt=one_year_ago).update(is_archived=True)
        messages.success(request, f"📦 {archived_count} stock change(s) older than 1 year have been archived.")
        return redirect('stock-changes')

# check_withdrawal_duplicates
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
