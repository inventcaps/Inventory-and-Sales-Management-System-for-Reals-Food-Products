from django.views.generic import View
from django.shortcuts import redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
from decimal import Decimal, InvalidOperation

@method_decorator(login_required, name='dispatch')
class ProductTypeAddView(View):
    def post(self, request):
        from realsproj.models import ProductTypes, AuthUser
        name = request.POST.get('name', '').strip()
        
        if not name:
            messages.error(request, '❌ Please enter a product type name!')
            return redirect('product-attributes')
        
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
        from realsproj.models import ProductTypes
        product_type = get_object_or_404(ProductTypes, pk=pk)
        name = request.POST.get('name', '').strip()
        
        if name and name != product_type.name:
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
        from realsproj.models import ProductTypes, Products
        from django.db import IntegrityError
        
        product_type = get_object_or_404(ProductTypes, pk=pk)
        
        # Check if being used by products
        products_using = Products.objects.filter(product_type_id=pk, is_archived=False)
        if products_using.exists():
            count = products_using.count()
            messages.error(request, f'❌ Cannot delete this Product Type because it is being used by {count} product(s).')
            return redirect('product-attributes')
        
        try:
            product_type.delete()
            messages.success(request, '✅ Product Type deleted successfully!')
        except IntegrityError:
            messages.error(request, '❌ Cannot delete this Product Type because it is being used by existing products.')
        except Exception as e:
            messages.error(request, f'❌ Error deleting Product Type: {str(e)}')
        
        return redirect('product-attributes')

@method_decorator(login_required, name='dispatch')
class ProductVariantAddView(View):
    def post(self, request):
        from realsproj.models import ProductVariants, AuthUser
        name = request.POST.get('name', '').strip()
        
        if not name:
            messages.error(request, '❌ Please enter a variant name!')
            return redirect('product-attributes')
        
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
        from realsproj.models import ProductVariants
        variant = get_object_or_404(ProductVariants, pk=pk)
        name = request.POST.get('name', '').strip()
        
        if name and name != variant.name:
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
        from realsproj.models import ProductVariants, Products
        from django.db import IntegrityError
        
        variant = get_object_or_404(ProductVariants, pk=pk)
        
        products_using = Products.objects.filter(variant_id=pk, is_archived=False)
        if products_using.exists():
            count = products_using.count()
            messages.error(request, f'❌ Cannot delete this Variant because it is being used by {count} product(s).')
            return redirect('product-attributes')
        
        try:
            variant.delete()
            messages.success(request, '✅ Variant deleted successfully!')
        except IntegrityError:
            messages.error(request, '❌ Cannot delete this Variant because it is being used by existing products.')
        except Exception as e:
            messages.error(request, f'❌ Error deleting Variant: {str(e)}')
        
        return redirect('product-attributes')

@method_decorator(login_required, name='dispatch')
class SizeAddView(View):
    def post(self, request):
        from realsproj.models import Sizes, AuthUser
        size_label = request.POST.get('size_label', '').strip()
        
        if not size_label:
            messages.error(request, '❌ Please enter a size label!')
            return redirect('product-attributes')
        
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
        from realsproj.models import Sizes
        size = get_object_or_404(Sizes, pk=pk)
        size_label = request.POST.get('size_label', '').strip()
        
        if size_label and size_label != size.size_label:
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
        from realsproj.models import Sizes, Products
        from django.db import IntegrityError
        
        size = get_object_or_404(Sizes, pk=pk)
        
        products_using = Products.objects.filter(size_id=pk, is_archived=False)
        if products_using.exists():
            count = products_using.count()
            messages.error(request, f'❌ Cannot delete this Size because it is being used by {count} product(s).')
            return redirect('product-attributes')
        
        try:
            size.delete()
            messages.success(request, '✅ Size deleted successfully!')
        except IntegrityError:
            messages.error(request, '❌ Cannot delete this Size because it is being used by existing products.')
        except Exception as e:
            messages.error(request, f'❌ Error deleting Size: {str(e)}')
        
        return redirect('product-attributes')

@method_decorator(login_required, name='dispatch')
class SizeUnitAddView(View):
    def post(self, request):
        from realsproj.models import SizeUnits, AuthUser
        unit_name = request.POST.get('unit_name', '').strip()
        
        if not unit_name:
            messages.error(request, '❌ Please enter a unit name!')
            return redirect('product-attributes')
        
        if SizeUnits.objects.filter(unit_name__iexact=unit_name).exists():
            messages.error(request, f'❌ Size Unit "{unit_name}" already exists!')
            return redirect('product-attributes')
        
        try:
            auth_user = AuthUser.objects.get(id=request.user.id)
            SizeUnits.objects.create(unit_name=unit_name, created_by_admin=auth_user)
            messages.success(request, f'✅ Size Unit "{unit_name}" added successfully!')
        except Exception as e:
            messages.error(request, f'❌ Error adding Size Unit. Please try again.')
        
        return redirect('product-attributes')

@method_decorator(login_required, name='dispatch')
class SizeUnitEditView(View):
    def post(self, request, pk):
        from realsproj.models import SizeUnits
        size_unit = get_object_or_404(SizeUnits, pk=pk)
        unit_name = request.POST.get('unit_name', '').strip()
        
        if unit_name and unit_name != size_unit.unit_name:
            if SizeUnits.objects.filter(unit_name__iexact=unit_name).exclude(pk=pk).exists():
                messages.error(request, f'❌ Size Unit "{unit_name}" already exists!')
                return redirect('product-attributes')
            
            size_unit.unit_name = unit_name
            size_unit.save()
            messages.success(request, '✅ Size Unit updated successfully!')
        
        return redirect('product-attributes')

@method_decorator(login_required, name='dispatch')
class SizeUnitDeleteView(View):
    def post(self, request, pk):
        from realsproj.models import SizeUnits, Products
        from django.db import IntegrityError
        
        size_unit = get_object_or_404(SizeUnits, pk=pk)
        
        products_using = Products.objects.filter(size_unit_id=pk, is_archived=False)
        if products_using.exists():
            count = products_using.count()
            messages.error(request, f'❌ Cannot delete this Size Unit because it is being used by {count} product(s).')
            return redirect('product-attributes')
        
        try:
            size_unit.delete()
            messages.success(request, '✅ Size Unit deleted successfully!')
        except IntegrityError:
            messages.error(request, '❌ Cannot delete this Size Unit because it is being used by existing products.')
        except Exception as e:
            messages.error(request, f'❌ Error deleting Size Unit: {str(e)}')
        
        return redirect('product-attributes')

@method_decorator(login_required, name='dispatch')
class UnitPriceAddView(View):
    def post(self, request):
        from realsproj.models import UnitPrices, AuthUser
        from django.db import IntegrityError
        unit_price = request.POST.get('unit_price', '').strip()
        
        if not unit_price:
            messages.error(request, '❌ Please enter a price!')
            return redirect('product-attributes')
        
        try:
            price_value = Decimal(unit_price)
            if price_value <= 0:
                messages.error(request, '❌ Price must be greater than zero!')
                return redirect('product-attributes')
        except (InvalidOperation, ValueError):
            messages.error(request, '❌ Invalid price format! Please enter a valid number.')
            return redirect('product-attributes')
        
        if UnitPrices.objects.filter(unit_price=price_value).exists():
            messages.error(request, f'❌ Unit Price ₱{price_value} already exists!')
            return redirect('product-attributes')
        
        try:
            auth_user = AuthUser.objects.get(id=request.user.id)
            UnitPrices.objects.create(unit_price=price_value, created_by_admin=auth_user)
            messages.success(request, f'✅ Unit Price ₱{price_value} added successfully!')
        except IntegrityError:
            messages.error(request, f'❌ This Unit Price already exists!')
        except Exception as e:
            messages.error(request, f'❌ Error adding Unit Price. Please try again.')
        
        return redirect('product-attributes')

@method_decorator(login_required, name='dispatch')
class UnitPriceEditView(View):
    def post(self, request, pk):
        from realsproj.models import UnitPrices
        from django.db import IntegrityError
        unit_price_obj = get_object_or_404(UnitPrices, pk=pk)
        unit_price = request.POST.get('unit_price', '').strip()
        if unit_price:
            try:
                price_value = Decimal(unit_price)
                
                if price_value <= 0:
                    messages.error(request, '❌ Price must be greater than zero!')
                    return redirect('product-attributes')
                
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
        from realsproj.models import UnitPrices, Products
        from django.db import IntegrityError
        unit_price = get_object_or_404(UnitPrices, pk=pk)
        
        products_using = Products.objects.filter(unit_price_id=pk, is_archived=False)
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

@method_decorator(login_required, name='dispatch')
class SrpPriceAddView(View):
    def post(self, request):
        from realsproj.models import SrpPrices, AuthUser
        from django.db import IntegrityError
        srp_price = request.POST.get('srp_price', '').strip()
        
        if not srp_price:
            messages.error(request, '❌ Please enter a price!')
            return redirect('product-attributes')
        
        try:
            price_value = Decimal(srp_price)
            
            if price_value <= 0:
                messages.error(request, '❌ Price must be greater than zero!')
                return redirect('product-attributes')
            
        except (InvalidOperation, ValueError):
            messages.error(request, '❌ Invalid price format! Please enter a valid number.')
            return redirect('product-attributes')
        
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
        from realsproj.models import SrpPrices
        from django.db import IntegrityError
        srp_price_obj = get_object_or_404(SrpPrices, pk=pk)
        srp_price = request.POST.get('srp_price', '').strip()
        if srp_price:
            try:
                price_value = Decimal(srp_price)
                
                if price_value <= 0:
                    messages.error(request, '❌ Price must be greater than zero!')
                    return redirect('product-attributes')
                
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
        from realsproj.models import SrpPrices, Products
        from django.db import IntegrityError, connection
        srp_price = get_object_or_404(SrpPrices, pk=pk)
        
        products_using = Products.objects.filter(srp_price_id=pk, is_archived=False)
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
