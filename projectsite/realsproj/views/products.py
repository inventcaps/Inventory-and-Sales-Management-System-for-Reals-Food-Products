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

# ProductsList
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

# product_scan_phone
def product_scan_phone(request):
    
    return render(request, "product_scan_phone.html")

# check_barcode_availability
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

# ProductArchiveView
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

# ArchivedProductsListView
class ArchivedProductsListView(ListView):
    model = Products
    template_name = 'archived_products.html'
    context_object_name = 'object_list'
    paginate_by = 10

    def get_queryset(self):
        return Products.objects.filter(is_archived=True).order_by('-date_created')

# ProductUnarchiveView
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

# ProductArchiveOldView
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

# product_bulk_delete
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

# product_bulk_archive
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

# product_bulk_restore
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

# ProductCreateView
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

# ProductsUpdateView
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

# delete_old_product_photo_on_change
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

# delete_product_photo_on_delete
@receiver(post_delete, sender=Products)
def delete_product_photo_on_delete(sender, instance, **kwargs):
    if instance.photo and instance.photo.name:
        try:
            instance.photo.delete(save=False)
        except Exception:
            pass

# ProductsDeleteView
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

# ProductBatchList
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
                Q(product__size__size_label__icontains=search) |
                Q(packaging__name__icontains=search)
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

# ProductBatchCreateView
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

# ProductBatchUpdateView
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

# ProductBatchDeleteView
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

# ProductBatchArchiveView
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

# ArchivedProductBatchListView
class ArchivedProductBatchListView(ListView):
    model = ProductBatches
    template_name = 'archived_product_batch.html'
    context_object_name = 'object_list'
    paginate_by = 10

    def get_queryset(self):
        return ProductBatches.objects.filter(is_archived=True).select_related('product', 'created_by_admin').order_by('-batch_date')

# ProductBatchUnarchiveView
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

# ProductBatchArchiveOldView
class ProductBatchArchiveOldView(View):
    def post(self, request):
        from datetime import timedelta
        one_year_ago = timezone.now() - timedelta(days=365)
        # Note: Database triggers will automatically create history logs
        archived_count = ProductBatches.objects.filter(is_archived=False, batch_date__lt=one_year_ago).update(is_archived=True)
        messages.success(request, f"📦 {archived_count} product batch(es) older than 1 year have been archived.")
        return redirect('product-batch')

# product_batch_bulk_delete
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

# product_batch_bulk_archive
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

# product_batch_bulk_restore
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

# ProductInventoryList
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
            inv.reorder_status = inv.get_reorder_status(days_ahead=30)
            
            # Get packaging information and stock from batches
            batches = ProductBatches.objects.filter(
                product=inv.product,
                is_archived=False,
                quantity__gt=0  # Only show batches with stock
            ).select_related('packaging').order_by('expiration_date', 'id')

            from collections import defaultdict
            packaging_groups = defaultdict(lambda: {
                'total_quantity': 0,
                'expiring_quantity': 0,
                'batch_count': 0,
                'oldest_expiry': None,
                'newest_expiry': None,
                'has_expired': False,
                'has_near_expiry': False,
            })

            from django.utils import timezone
            today = timezone.localdate()
            near_expiry_cutoff = today + timezone.timedelta(days=30)
            from datetime import date as date_type

            for batch in batches:
                if not batch.packaging:
                    continue
                    
                packaging = batch.packaging
                packaging_name = packaging.name.title()
                if packaging.size and packaging.unit:
                    unit_name = packaging.unit.unit_name if hasattr(packaging.unit, 'unit_name') else str(packaging.unit)
                    packaging_name = f"{packaging_name} ({packaging.size} {unit_name})"

                pg = packaging_groups[packaging_name]
                pg['total_quantity'] += batch.quantity
                pg['batch_count'] += 1
                
                # Track expiry dates
                if batch.expiration_date:
                    # Check for expired
                    if batch.expiration_date < today:
                        pg['has_expired'] = True
                    # Check for near expiry
                    elif batch.expiration_date <= near_expiry_cutoff:
                        pg['has_near_expiry'] = True
                        pg['expiring_quantity'] += batch.quantity
                    
                    # Track oldest and newest expiry
                    if pg['oldest_expiry'] is None or batch.expiration_date < pg['oldest_expiry']:
                        pg['oldest_expiry'] = batch.expiration_date
                    if pg['newest_expiry'] is None or batch.expiration_date > pg['newest_expiry']:
                        pg['newest_expiry'] = batch.expiration_date

            # Create formatted packaging stock breakdown (grouped by packaging type)
            packaging_breakdown = []
            packaging_list = []
            
            for packaging_name, pg in packaging_groups.items():
                # Format expiry range
                if pg['oldest_expiry'] and pg['newest_expiry']:
                    oldest_str = pg['oldest_expiry'].strftime('%Y-%m-%d')
                    newest_str = pg['newest_expiry'].strftime('%Y-%m-%d')
                    if oldest_str == newest_str:
                        expiry_display = oldest_str
                    else:
                        expiry_display = f"{oldest_str} to {newest_str}"
                elif pg['oldest_expiry']:
                    expiry_display = pg['oldest_expiry'].strftime('%Y-%m-%d')
                else:
                    expiry_display = 'No Date'
                
                # Determine overall expiry status
                if pg['has_expired']:
                    expiry_status = 'expired'
                elif pg['has_near_expiry']:
                    expiry_status = 'near_expiry'
                else:
                    expiry_status = 'normal'
                    
                packaging_breakdown.append({
                    'name': packaging_name,
                    'stock': pg['total_quantity'],
                    'expiring': pg['expiring_quantity'],
                    'batch_count': pg['batch_count'],
                    'expiration_date': expiry_display,
                    'expiry_status': expiry_status
                })
                packaging_list.append(packaging_name)

            inv.packaging_used = ', '.join(packaging_list) if packaging_list else None
            inv.packaging_stock_breakdown = packaging_breakdown
        
        # Calculate total stock across all non-archived products
        total_stock = ProductInventory.objects.filter(
            product__is_archived=False
        ).aggregate(total=Sum('total_stock'))['total'] or 0
        context['total_product_stock'] = total_stock
        return context

# ProductVariantCreateView
class ProductVariantCreateView(LoginRequiredMixin, CreateView):
    model = ProductVariants
    form_class = ProductVariantsForm
    template_name = "prodvar_add.html"
    success_url = reverse_lazy("product-add")


    def form_valid(self, form):
        auth_user = AuthUser.objects.get(id=self.request.user.id)
        form.instance.created_by_admin = auth_user
        return super().form_valid(form)

# SizesCreateView
class SizesCreateView(LoginRequiredMixin, CreateView):
    model = Sizes
    form_class = SizesForm
    template_name = "sizes_add.html"
    success_url = reverse_lazy("product-add")

    def form_valid(self, form):
        auth_user = AuthUser.objects.get(id=self.request.user.id)
        form.instance.created_by_admin = auth_user
        return super().form_valid(form)

# SizeUnitsCreateView
class SizeUnitsCreateView(LoginRequiredMixin, CreateView):
    model = SizeUnits
    form_class = SizeUnitsForm
    template_name = "sizeunits_add.html"
    success_url = reverse_lazy("product-add")

    def form_valid(self, form):
        auth_user = AuthUser.objects.get(id=self.request.user.id)
        form.instance.created_by_admin = auth_user
        return super().form_valid(form)

# UnitPricesCreateView
class UnitPricesCreateView(LoginRequiredMixin, CreateView):
    model = UnitPrices
    form_class = UnitPricesForm
    template_name = "unitprices_add.html"
    success_url = reverse_lazy("product-add")

    def form_valid(self, form):
        auth_user = AuthUser.objects.get(id=self.request.user.id)
        form.instance.created_by_admin = auth_user
        return super().form_valid(form)

# SrpPricesCreateView
class SrpPricesCreateView(LoginRequiredMixin, CreateView):
    model = SrpPrices
    form_class = SrpPricesForm
    template_name = "srpprices_add.html"
    success_url = reverse_lazy("product-add")

    def form_valid(self, form):
        auth_user = AuthUser.objects.get(id=self.request.user.id)
        form.instance.created_by_admin = auth_user
        return super().form_valid(form)

# ProductAttributesView
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

# ProductTypeAddView
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

# ProductTypeEditView
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

# ProductTypeDeleteView
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

# ProductVariantAddView
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

# ProductVariantEditView
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

# ProductVariantDeleteView
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

# SizeAddView
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

# SizeEditView
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

# SizeDeleteView
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

# SizeUnitAddView
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

# SizeUnitEditView
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

# SizeUnitDeleteView
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

# UnitPriceAddView
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

# UnitPriceEditView
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

# UnitPriceDeleteView
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

# SrpPriceAddView
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

# SrpPriceEditView
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

# SrpPriceDeleteView
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

# BulkProductBatchCreateView
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

# export_product_inventory
@login_required
def export_product_inventory(request):
    import csv
    from django.http import HttpResponse
    from django.db.models import Q
    from django.template.loader import render_to_string
    from xhtml2pdf import pisa
    from io import BytesIO
    
    format_type = request.GET.get('format', 'csv').lower()
    
    try:
        # Get base queryset with filters
        queryset = ProductInventory.objects.select_related(
            'product',
            'product__product_type',
            'product__variant',
            'product__size',
        ).filter(product__is_archived=False)
        
        # Apply search filter
        search = request.GET.get('search', '').strip()
        if search:
            queryset = queryset.filter(
                Q(product__product_type__name__icontains=search) |
                Q(product__variant__name__icontains=search) |
                Q(product__size__size_label__icontains=search)
            )
        
        # Apply status filter
        status = request.GET.get('status', '').strip()
        if status:
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
            
            queryset = queryset.filter(product_id__in=filtered_items) if filtered_items else queryset.none()
        
        # Apply month filter if provided
        month = request.GET.get('month', '').strip()
        from django.utils import timezone
        if month:
            from django.db.models import Sum
            try:
                year, month_num = month.split('-')
                # Filter batches that have activity in the specified month
                from realsproj.models import ProductBatches
                batches_in_month = ProductBatches.objects.filter(
                    batch_date__year=year,
                    batch_date__month=month_num
                ).values_list('product_id', flat=True).distinct()
                queryset = queryset.filter(product_id__in=batches_in_month)
            except (ValueError, IndexError):
                pass  # Invalid month format, ignore filter
        
        # Export based on format
        if format_type == 'pdf':
            # Prepare data for PDF template
            inventory_items = []
            total_stock = 0
            total_available = 0
            from datetime import datetime
            from django.conf import settings
            
            for inv in queryset:
                reorder_status = inv.get_reorder_status()
                available_stock = reorder_status['available_stock']
                expiring_stock = reorder_status['expiring_stock']
                
                if inv.total_stock <= 0:
                    stock_status = 'Out of Stock'
                    status_class = 'out-of-stock'
                elif inv.total_stock <= inv.restock_threshold:
                    stock_status = 'Low Stock'
                    status_class = 'low-stock'
                elif inv.total_stock == inv.restock_threshold:
                    stock_status = 'Warning'
                    status_class = 'warning'
                else:
                    stock_status = 'In Stock'
                    status_class = 'in-stock'
                
                # Get packaging information
                packaging_used = getattr(inv, 'packaging_used', None) or 'N/A'
                
                inventory_items.append({
                    'product': str(inv.product),
                    'total_stock': inv.total_stock,
                    'available_stock': available_stock,
                    'expiring_stock': expiring_stock,
                    'restock_threshold': inv.restock_threshold,
                    'status': stock_status,
                    'status_class': status_class,
                    'packaging_used': packaging_used
                })
                
                total_stock += inv.total_stock
                total_available += available_stock
            
            # Prepare context for template
            context = {
                'inventory_items': inventory_items,
                'total_products': len(inventory_items),
                'total_stock': total_stock,
                'total_available': total_available,
                'generated_date': timezone.now().strftime('%B %d, %Y at %I:%M %p'),
                'current_year': timezone.now().year,
                'logo_url': None,  # Disabled: xhtml2pdf cannot resolve relative static paths
                'filters': {
                    'month': month if month else None,
                    'search': search if search else None,
                    'status': status.replace('_', ' ') if status else None
                }
            }
            
            # Render HTML template
            html = render_to_string('exports/product_inventory_pdf.html', context)
            
            # Generate PDF
            pdf_buffer = BytesIO()
            pisa_status = pisa.CreatePDF(html, dest=pdf_buffer)
            
            if not pisa_status.err:
                response = HttpResponse(pdf_buffer.getvalue(), content_type='application/pdf')
                response['Content-Disposition'] = 'attachment; filename="product_inventory.pdf"'
                return response
            else:
                raise Exception('PDF generation failed')
        
        else:  # CSV format
            response = HttpResponse(content_type='text/csv')
            response['Content-Disposition'] = 'attachment; filename="product_inventory.csv"'
            writer = csv.writer(response)
            writer.writerow(['Product', 'Total Stock', 'Restock Threshold', 'Status'])
            
            for inv in queryset:
                if inv.total_stock <= 0:
                    stock_status = 'Out of Stock'
                elif inv.total_stock <= inv.restock_threshold:
                    stock_status = 'Low Stock'
                else:
                    stock_status = 'In Stock'
                writer.writerow([str(inv.product), inv.total_stock, inv.restock_threshold, stock_status])
            
            return response
            
    except Exception as e:
        # Handle errors gracefully
        if format_type == 'pdf':
            response = HttpResponse(content_type='text/plain')
            response['Content-Disposition'] = 'attachment; filename="product_inventory_error.txt"'
            response.write(f'An error occurred: {str(e)}')
        else:
            response = HttpResponse(content_type='text/csv')
            response['Content-Disposition'] = 'attachment; filename="product_inventory_error.csv"'
            writer = csv.writer(response)
            writer.writerow(['Error'])
            writer.writerow([f'An error occurred: {str(e)}'])
        return response

# PriceHistoryList
class PriceHistoryList(LoginRequiredMixin, ListView):
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
                now = timezone.now()
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
        
        now = timezone.now()
        context['current_month_value'] = now.strftime('%Y-%m')

        query_params = self.request.GET.copy()
        if 'page' in query_params:
            query_params.pop('page')
        context['query_params'] = query_params.urlencode()
        
        return context

# export_price_history
def export_price_history(request):
    """Export Price History to CSV or PDF using the same month/show_all filters as the list view."""
    import csv
    from django.http import HttpResponse
    from django.template.loader import render_to_string
    from xhtml2pdf import pisa
    from io import BytesIO
    from datetime import datetime

    format_type = request.GET.get('format', 'csv').lower()

    # Base queryset
    qs = PriceHistory.objects.all().select_related('product', 'changed_by_admin')

    # Optional additional filters (keep behavior close to list view)
    price_type = request.GET.get('price_type', '').strip()
    if price_type:
        qs = qs.filter(price_type=price_type)

    # Month filter logic (reuse list behavior)
    show_all = request.GET.get('show_all', '').strip()
    date_created = request.GET.get('date_created', '').strip()

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
            now = timezone.now()
            qs = qs.filter(changed_at__year=now.year, changed_at__month=now.month)

    # Order by latest changes first
    qs = qs.order_by('-changed_at')

    try:
        # Export based on format
        if format_type == 'pdf':
            # Prepare data for PDF template
            price_changes = []
            total_increases = 0
            total_decreases = 0

            for ph in qs:
                # Product string
                product_str = str(ph.product) if getattr(ph, 'product', None) else ''

                # Price type display
                try:
                    price_type_display = ph.get_price_type_display()
                except Exception:
                    price_type_display = ph.price_type

                # Old/New price
                old_price = ph.old_price if ph.old_price is not None else None
                new_price = ph.new_price

                # Compute change
                change_amount = None
                try:
                    if ph.old_price is not None and ph.old_price != 0:
                        change_amount = ph.new_price - ph.old_price
                        if change_amount > 0:
                            total_increases += 1
                        elif change_amount < 0:
                            total_decreases += 1
                except Exception:
                    pass

                # Changed by
                changed_by = ph.changed_by_admin.username if getattr(ph, 'changed_by_admin', None) else 'System'

                price_changes.append({
                    'changed_at': ph.changed_at,
                    'product': product_str,
                    'price_type': ph.price_type,
                    'get_price_type_display': price_type_display,
                    'old_price': old_price,
                    'new_price': new_price,
                    'price_change_amount': change_amount,
                    'changed_by': changed_by,
                })

            # Prepare context for template
            context = {
                'price_changes': price_changes,
                'total_changes': len(price_changes),
                'total_increases': total_increases,
                'total_decreases': total_decreases,
                'generated_date': timezone.now().strftime('%B %d, %Y at %I:%M %p'),
                'current_year': timezone.now().year,
                'logo_url': None,
                'filters': {
                    'month': date_created if date_created and not show_all else None,
                    'show_all': show_all if show_all else None,
                    'price_type': price_type if price_type else None
                }
            }

            # Render HTML template
            html = render_to_string('exports/price_history_pdf.html', context)

            # Generate PDF
            pdf_buffer = BytesIO()
            pisa_status = pisa.CreatePDF(html, dest=pdf_buffer)

            if not pisa_status.err:
                response = HttpResponse(pdf_buffer.getvalue(), content_type='application/pdf')
                response['Content-Disposition'] = 'attachment; filename="price_history.pdf"'
                return response
            else:
                raise Exception('PDF generation failed')

        else:  # CSV format
            # Prepare CSV response
            response = HttpResponse(content_type='text/csv')
            filename_suffix = date_created if date_created else ('all' if show_all else timezone.now().strftime('%Y-%m'))
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
                    ph.changed_at.strftime('%Y-%m-%d %I:%M %p') if ph.changed_at else '',
                    product_str,
                    price_type_display,
                    old_price,
                    new_price,
                    change_amount,
                    change_percent,
                    changed_by,
                ])

            return response

    except Exception as e:
        # Handle errors gracefully
        if format_type == 'pdf':
            response = HttpResponse(content_type='text/plain')
            response['Content-Disposition'] = 'attachment; filename="price_history_error.txt"'
            response.write(f'An error occurred: {str(e)}')
        else:
            response = HttpResponse(content_type='text/csv')
            response['Content-Disposition'] = 'attachment; filename="price_history_error.csv"'
            writer = csv.writer(response)
            writer.writerow(['Error'])
            writer.writerow([f'An error occurred: {str(e)}'])
        return response

# check_product_batches
@login_required
def check_product_batches(request):
    """API endpoint to check if products already have batches with the same quantity."""
    from django.utils import timezone
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
