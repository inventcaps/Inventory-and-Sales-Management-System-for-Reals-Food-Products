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

# RawMaterialsList
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

# RawMaterialArchiveView
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

# RawMaterialArchiveOldView
class RawMaterialArchiveOldView(View):
    def post(self, request):
        one_year_ago = timezone.now() - timedelta(days=365)
        RawMaterials.objects.filter(is_archived=False, date_created__lt=one_year_ago).update(is_archived=True)
        return redirect('rawmaterials-list')

# rawmaterial_bulk_delete
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

# rawmaterial_bulk_archive
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

# rawmaterial_bulk_restore
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

# ArchivedRawMaterialsListView
class ArchivedRawMaterialsListView(ListView):
    model = RawMaterials
    template_name = 'archived_rawmaterials.html'
    context_object_name = 'object_list'
    paginate_by = 10

    def get_queryset(self):
        return RawMaterials.objects.filter(is_archived=True).order_by('-date_created')

# ArchivedPackagingMaterialsListView
class ArchivedPackagingMaterialsListView(ArchivedRawMaterialsListView):
    template_name = 'archived_packaging.html'

    def get_queryset(self):
        return (super().get_queryset()
                .filter(category__iexact='PACKAGING'))

# RawMaterialUnarchiveView
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

# RawMaterialsCreateView
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
            form.instance.category = 'PACKAGING'
            self.object = form.save()
        except Exception as e:
            transaction.set_rollback(True)
            messages.error(self.request, f"Raw material creation failed: {e}")
            return redirect(self.request.path)
        messages.success(self.request, "Packaging material created successfully.")
        return redirect(self.success_url)

    def form_invalid(self, form):
        messages.error(self.request, "Please complete all required fields. The form was reset.")
        return redirect(self.request.path)  

# RawMaterialsUpdateView
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

# RawMaterialsDeleteView
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

# CategoryFilteredRawMaterialsList
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

# CategoryRawMaterialsCreateView
class CategoryRawMaterialsCreateView(RawMaterialsCreateView):
    category_value = None

    def form_valid(self, form):
        if self.category_value:
            form.instance.category = self.category_value
        return super().form_valid(form)

# CategoryRawMaterialsUpdateView
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

# PackagingMaterialsList
class PackagingMaterialsList(CategoryFilteredRawMaterialsList):
    category_value = 'PACKAGING'
    template_name = 'packaging_list.html'

# PackagingMaterialsCreateView
class PackagingMaterialsCreateView(CategoryRawMaterialsCreateView):
    template_name = 'packaging_add.html'
    success_url = reverse_lazy('packaging-materials')
    category_value = 'PACKAGING'

# PackagingMaterialsUpdateView
class PackagingMaterialsUpdateView(CategoryRawMaterialsUpdateView):
    template_name = 'packaging_edit.html'
    success_url = reverse_lazy('packaging-materials')
    category_value = 'PACKAGING'

# RawMaterialBatchList
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

# RawMaterialBatchCreateView
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

# RawMaterialBatchUpdateView
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

# RawMaterialBatchDeleteView
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

# RawMaterialBatchArchiveView
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

# ArchivedRawMaterialBatchListView
class ArchivedRawMaterialBatchListView(ListView):
    model = RawMaterialBatches
    template_name = 'archived_rawmaterial_batch.html'
    context_object_name = 'object_list'
    paginate_by = 10

    def get_queryset(self):
        return RawMaterialBatches.objects.filter(is_archived=True).select_related('material', 'created_by_admin').order_by('-batch_date')

# RawMaterialBatchUnarchiveView
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

# RawMaterialBatchBulkRestoreView
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

# RawMaterialBatchBulkDeleteView
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

# RawMaterialBatchArchiveOldView
class RawMaterialBatchArchiveOldView(View):
    def post(self, request):
        from datetime import timedelta
        one_year_ago = timezone.now() - timedelta(days=365)
        archived_count = RawMaterialBatches.objects.filter(is_archived=False, batch_date__lt=one_year_ago).update(is_archived=True)
        messages.success(request, f"📦 {archived_count} raw material batch(es) older than 1 year have been archived.")
        return redirect('rawmaterial-batch')

# rawmaterial_batch_bulk_delete
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

# rawmaterial_batch_bulk_archive
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

# RawMaterialInventoryList
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

# export_rawmaterial_inventory
@require_GET
@login_required
def export_rawmaterial_inventory(request):
    import csv
    from django.http import HttpResponse
    from django.template.loader import render_to_string
    from xhtml2pdf import pisa
    from io import BytesIO
    from datetime import datetime

    format_type = request.GET.get('format', 'csv').lower()

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

    try:
        # Export based on format
        if format_type == 'pdf':
            # Prepare data for PDF template
            inventory_items = []
            total_stock = 0
            low_stock_count = 0

            for item in qs:
                mat = item.material
                unit_obj = getattr(mat, 'unit', None)
                unit_name = getattr(unit_obj, 'unit_name', str(unit_obj)) if unit_obj is not None else ''
                
                # Handle unit size - convert to float for formatting if possible
                try:
                    if mat.size is not None:
                        unit_size = float(mat.size)
                    else:
                        unit_size = 0
                except (ValueError, TypeError):
                    unit_size = 0
                
                price = mat.price_per_unit if mat.price_per_unit is not None else 0
                
                status_label = (
                    'Out of Stock' if item.total_stock == 0 else
                    'Low Stock' if item.total_stock < item.reorder_threshold else
                    'Warning' if item.total_stock == item.reorder_threshold else
                    'On Stock'
                )

                if status_label == 'Low Stock':
                    low_stock_count += 1

                inventory_items.append({
                    'material_name': mat.name,
                    'unit_size': unit_size,
                    'unit_name': unit_name,
                    'price_per_unit': price,
                    'category': mat.category or '',
                    'current_stock': item.total_stock,
                    'reorder_threshold': item.reorder_threshold,
                    'status': status_label,
                })

                total_stock += item.total_stock

            # Prepare context for template
            context = {
                'inventory_items': inventory_items,
                'total_materials': len(inventory_items),
                'total_stock': total_stock,
                'low_stock_count': low_stock_count,
                'generated_date': timezone.now().strftime('%B %d, %Y at %I:%M %p'),
                'current_year': timezone.now().year,
                'logo_url': None,
                'filters': {
                    'search': q if q else None,
                    'status': status.replace('_', ' ') if status else None,
                    'category': category if category else None
                }
            }

            # Render HTML template
            html = render_to_string('exports/raw_material_inventory_pdf.html', context)

            # Generate PDF
            pdf_buffer = BytesIO()
            pisa_status = pisa.CreatePDF(html, dest=pdf_buffer)

            if not pisa_status.err:
                response = HttpResponse(pdf_buffer.getvalue(), content_type='application/pdf')
                response['Content-Disposition'] = 'attachment; filename="raw_material_inventory.pdf"'
                return response
            else:
                raise Exception('PDF generation failed')

        else:  # CSV format
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

    except Exception as e:
        # Handle errors gracefully
        if format_type == 'pdf':
            response = HttpResponse(content_type='text/plain')
            response['Content-Disposition'] = 'attachment; filename="raw_material_inventory_error.txt"'
            response.write(f'An error occurred: {str(e)}')
        else:
            response = HttpResponse(content_type='text/csv')
            response['Content-Disposition'] = 'attachment; filename="raw_material_inventory_error.csv"'
            writer = csv.writer(response)
            writer.writerow(['Error'])
            writer.writerow([f'An error occurred: {str(e)}'])
        return response

# BulkRawMaterialBatchCreateView
class BulkRawMaterialBatchCreateView(LoginRequiredMixin, View):
    template_name = "rawmatbatch_add.html"

    def get(self, request):
        category = request.GET.get('category', 'PACKAGING')
        form = BulkRawMaterialBatchForm(initial={'category': category})
        return render(request, self.template_name, {'form': form, 'raw_materials': form.rawmaterials})

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

# check_rawmaterial_batches
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

# check_rawmaterial_duplicates
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
