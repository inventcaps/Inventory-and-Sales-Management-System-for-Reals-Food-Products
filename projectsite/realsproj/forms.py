from decimal import Decimal, InvalidOperation
from django.forms import ModelForm
from django import forms
from datetime import timedelta
from calendar import monthrange

from django.utils import timezone

from .models import Expenses, Products, RawMaterials, HistoryLog, Sales, ProductBatches, ProductInventory, RawMaterialBatches, RawMaterialInventory, ProductTypes, ProductVariants, Sizes, SizeUnits, UnitPrices, SrpPrices, Notifications, StockChanges, Discounts, ProductRecipes, Withdrawals
from django.contrib.auth.models import User
from django.contrib.auth.forms import UserCreationForm, UserChangeForm
from django.core.exceptions import ValidationError
from django.forms import inlineformset_factory

# ... (rest of the code remains the same)

class ProductsForm(forms.ModelForm):
    # ADD THIS - Barcode field
    barcode = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Scan or enter barcode',
            'id': 'barcode-input'
        })
    )

    product_code = forms.CharField(
        max_length=10,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter product code'
        })
    )

    product_type = forms.CharField(
        widget=forms.TextInput(attrs={'list': 'product_type-options'}))
    variant = forms.CharField(
        widget=forms.TextInput(attrs={'list': 'variant-options'}))
    size = forms.CharField(
        widget=forms.TextInput(attrs={'list': 'size-options'}), required=False)
    size_unit = forms.ModelChoiceField(
        queryset=SizeUnits.objects.all(), empty_label="Select unit")
    unit_price = forms.CharField(
        widget=forms.TextInput(attrs={'list': 'unit_price-options'}))
    srp_price = forms.CharField(
        widget=forms.TextInput(attrs={'list': 'srp_price-options'}))
    description = forms.CharField(widget=forms.Textarea, required=False)

    class Meta:
        model = Products
        exclude = ['created_by_admin', 'date_created']
        widgets = {
            'size_unit': forms.Select(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        self.created_by_admin = kwargs.pop('created_by_admin', None)
        super().__init__(*args, **kwargs)

        if self.instance.pk:
            self.fields['product_type'].initial = self.instance.product_type.name
            self.fields['variant'].initial = self.instance.variant.name
            self.fields['size'].initial = self.instance.size.size_label if self.instance.size else ''
            self.fields['unit_price'].initial = self.instance.unit_price.unit_price
            self.fields['srp_price'].initial = self.instance.srp_price.srp_price
            self.fields['barcode'].initial = self.instance.barcode
            self.fields['product_code'].initial = self.instance.product_code

            self.initial['product_type'] = self.fields['product_type'].initial
            self.initial['variant'] = self.fields['variant'].initial
            self.initial['size'] = self.fields['size'].initial
            self.initial['unit_price'] = self.fields['unit_price'].initial
            self.initial['srp_price'] = self.fields['srp_price'].initial
            self.initial['barcode'] = self.fields['barcode'].initial
            self.initial['product_code'] = self.fields['product_code'].initial

    def clean_barcode(self):
        barcode = self.cleaned_data.get('barcode', '').strip()

        if not barcode:
            if self.instance and self.instance.pk:
                return self.instance.barcode
            return barcode

        qs = Products.objects.filter(barcode=barcode)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)

        if qs.exists():
            raise forms.ValidationError(
                f"Barcode '{barcode}' is already used by another product."
            )

        return barcode

    def clean_product_code(self):
        code = self.cleaned_data.get('product_code', '').strip()

        if not code:
            raise forms.ValidationError("Product code is required.")

        # Get the product type and variant from cleaned data
        product_type = self.cleaned_data.get('product_type')
        variant = self.cleaned_data.get('variant')

        # Check if product code is used with different product type or variant
        if product_type and variant:
            qs = Products.objects.filter(product_code__iexact=code).exclude(
                product_type=product_type,
                variant=variant
            )
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)

            if qs.exists():
                raise forms.ValidationError(
                    f"Product code '{code}' is already used by another product with a different type or variant. "
                    f"Product codes can only be reused for the same product type and variant."
                )

        return code.upper()

    def clean_product_type(self):
        name = self.cleaned_data['product_type'].strip()
        obj, _ = ProductTypes.objects.get_or_create(
            name=name,
            defaults={'created_by_admin': self.created_by_admin}
        )
        return obj

    def clean_variant(self):
        name = self.cleaned_data['variant'].strip()
        obj, _ = ProductVariants.objects.get_or_create(
            name=name,
            defaults={'created_by_admin': self.created_by_admin}
        )
        return obj

    def clean_size(self):
        name = self.cleaned_data['size'].strip()
        if not name:
            return None

        try:
            obj = Sizes.objects.get(size_label__iexact=name)
        except Sizes.DoesNotExist:
            obj = Sizes.objects.create(
                size_label=name,
                created_by_admin=self.created_by_admin
            )
        except Sizes.MultipleObjectsReturned:
            obj = Sizes.objects.filter(size_label__iexact=name).first()

        return obj

    def clean_unit_price(self):
        price = self.cleaned_data['unit_price'].strip()
        obj, created = UnitPrices.objects.get_or_create(
            unit_price=price,
            defaults={'created_by_admin': self.created_by_admin}
        )
        if not created and not obj.created_by_admin and self.created_by_admin:
            obj.created_by_admin = self.created_by_admin
            obj.save()
        return obj

    def clean_srp_price(self):
        price = self.cleaned_data['srp_price'].strip()
        obj, created = SrpPrices.objects.get_or_create(
            srp_price=price,
            defaults={'created_by_admin': self.created_by_admin}
        )
        if not created and not obj.created_by_admin and self.created_by_admin:
            obj.created_by_admin = self.created_by_admin
            obj.save()
        return obj

    def clean(self):
        cleaned_data = super().clean()

        if self.errors:
            return cleaned_data

        product_code = cleaned_data.get('product_code')
        product_type = cleaned_data.get('product_type')
        variant = cleaned_data.get('variant')
        size = cleaned_data.get('size')
        size_unit = cleaned_data.get('size_unit')
        unit_price = cleaned_data.get('unit_price')
        srp_price = cleaned_data.get('srp_price')

        required_fields = [product_code, product_type, variant, size_unit, unit_price, srp_price]
        if any(field is None for field in required_fields):
            return cleaned_data

        # Check for complete duplicates: same product code, type, variant, size, size_unit, unit price, and SRP
        duplicate_qs = Products.objects.filter(
            product_code__iexact=product_code,
            product_type=product_type,
            variant=variant,
            size=size,
            size_unit=size_unit,
            unit_price=unit_price,
            srp_price=srp_price,
        )

        if self.instance.pk:
            duplicate_qs = duplicate_qs.exclude(pk=self.instance.pk)

        if duplicate_qs.exists():
            raise ValidationError(
                "A product with the same code, type, variant, size, unit, unit price, and SRP already exists. "
                "This is a complete duplicate and cannot be added."
            )

        return cleaned_data


class ProductRecipeForm(forms.ModelForm):
    class Meta:
        model = ProductRecipes
        fields = ["material", "quantity_needed", "yield_factor"]


class RawMaterialsForm(ModelForm):
    CATEGORY_CHOICES = (
        ("PACKAGING", "Packaging"),
        ("RECIPE", "Recipe"),
    )

    category = forms.ChoiceField(choices=CATEGORY_CHOICES)
    field_order = ["name", "size", "unit", "price_per_unit", "category"]

    class Meta:
        model = RawMaterials
        field_order = ["name", "size", "unit", "price_per_unit", "category"]
        exclude = ['created_by_admin', 'date_created', 'is_archived']
        widgets = {
            'expiration_date': forms.DateInput(attrs={'type': 'date'}),
        }

    def clean_category(self):
        value = self.cleaned_data.get('category', 'PACKAGING')
        return (value or 'PACKAGING').upper()

    def clean(self):
        cleaned_data = super().clean()

        if self.errors:
            return cleaned_data

        name = cleaned_data.get('name')
        size = cleaned_data.get('size')
        unit = cleaned_data.get('unit')
        price_per_unit = cleaned_data.get('price_per_unit')

        # Check if all required fields are present
        required_fields = [name, size, unit, price_per_unit]
        if any(field is None for field in required_fields):
            return cleaned_data

        # Check for complete duplicates: same name, size, unit, and price_per_unit
        duplicate_qs = RawMaterials.objects.filter(
            name__iexact=name,
            size=size,
            unit=unit,
            price_per_unit=price_per_unit,
        )

        if self.instance.pk:
            duplicate_qs = duplicate_qs.exclude(pk=self.instance.pk)

        if duplicate_qs.exists():
            raise ValidationError(
                "A raw material with the same name, size, unit, and price per unit already exists. "
                "This is a complete duplicate and cannot be added."
            )

        return cleaned_data


class HistoryLogForm(ModelForm):
    class Meta:
        model = HistoryLog
        fields = "__all__"


class SalesForm(ModelForm):
    class Meta:
        model = Sales
        exclude = ['created_by_admin', 'is_archived']
        fields = ['category', 'amount', 'date', 'description']
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date'}),
        }


class ExpensesForm(ModelForm):
    class Meta:
        model = Expenses
        exclude = ['created_by_admin', 'is_archived']
        fields = ['category', 'amount', 'date', 'description']
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date'}),
        }


class SalesExpensesForm(forms.Form):
    sales_category = forms.CharField(
        max_length=255,
        label='Sales Category',
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Enter Sales Category'})
    )
    sales_amount = forms.DecimalField(
        max_digits=10,
        decimal_places=2,
        label='Sales Amount',
        widget=forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Enter Sales Amount'})
    )
    date = forms.DateField(
        label='Date',
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'})
    )
    sales_description = forms.CharField(
        required=False,
        label='Sales Description',
        widget=forms.Textarea(attrs={'class': 'form-control', 'placeholder': 'Enter Sales Description', 'rows': 3})
    )

    total_expenses = forms.DecimalField(
        max_digits=10,
        decimal_places=2,
        label='Total Expenses',
        widget=forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Enter Total Expenses'})
    )
    expenses_description = forms.CharField(
        required=False,
        label='Expenses Description',
        widget=forms.Textarea(attrs={'class': 'form-control', 'placeholder': 'Enter Expenses Description (Optional)', 'rows': 3})
    )

    def clean(self):
        cleaned_data = super().clean()
        sales_amount = cleaned_data.get('sales_amount')
        total_expenses = cleaned_data.get('total_expenses')

        if sales_amount and total_expenses and total_expenses > sales_amount:
            self.add_error('total_expenses', 'Expenses cannot exceed sales amount.')

        return cleaned_data


class ProductBatchForm(ModelForm):

    class Meta:
        model = ProductBatches
        fields = [
            'product',
            'quantity',
            'batch_date',
            'manufactured_date',
            'expiration_date',
            'batch_code',
        ]
        widgets = {
            'product': forms.Select(attrs={'class': 'form-control'}),
            'batch_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'manufactured_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'expiration_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'quantity': forms.NumberInput(attrs={'class': 'form-control'}),
            'batch_code': forms.TextInput(attrs={'class': 'form-control', 'readonly': 'readonly', 'placeholder': 'Auto-generated (MMDDYY + Product Code)'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['product'].queryset = Products.objects.filter(is_archived=False)
        self.fields['batch_code'].required = False
        self.fields['batch_code'].disabled = True

    def save(self, commit=True):
        instance = super().save(commit=False)
        manufactured_date = instance.manufactured_date or timezone.localdate()
        product_code = (instance.product.product_code or '').upper()
        instance.batch_code = f"{manufactured_date.strftime('%m%d%y')}{product_code}"
        if commit:
            instance.save()
        return instance


class ProductInventoryForm(ModelForm):
    class Meta:
        model = ProductInventory
        fields = ['product', 'total_stock', 'restock_threshold']
        widgets = {
            'total_stock': forms.NumberInput(attrs={'min': 0}),
            'restock_threshold': forms.NumberInput(attrs={'min': 0}),
        }


class RawMaterialBatchForm(ModelForm):
    class Meta:
        model = RawMaterialBatches
        fields = ['material', 'quantity', 'batch_date', 'received_date', 'expiration_date']
        widgets = {
            'material': forms.Select(attrs={'class': 'form-control'}),
            'quantity': forms.NumberInput(attrs={'class': 'form-control'}),
            'batch_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'received_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'expiration_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['material'].queryset = RawMaterials.objects.filter(is_archived=False)


class RawMaterialInventoryForm(ModelForm):
    class Meta:
        model = RawMaterialInventory
        fields = ['material', 'total_stock', 'reorder_threshold']
        widgets = {
            'total_stock': forms.NumberInput(attrs={'min': 0}),
            'reorder_threshold': forms.NumberInput(attrs={'min': 0}),
        }


class ProductTypesForm(ModelForm):
    class Meta:
        model = ProductTypes
        fields = "__all__"


class ProductVariantsForm(ModelForm):
    class Meta:
        model = ProductVariants
        fields = "__all__"


class SizesForm(ModelForm):
    class Meta:
        model = Sizes
        fields = "__all__"


class SizeUnitsForm(ModelForm):
    class Meta:
        model = SizeUnits
        fields = "__all__"


class UnitPricesForm(ModelForm):
    class Meta:
        model = UnitPrices
        fields = "__all__"


class SrpPricesForm(ModelForm):
    class Meta:
        model = SrpPrices
        fields = "__all__"


class WithdrawEditForm(forms.ModelForm):
    SALES_CHANNEL_CHOICES = [
        ('ORDER', 'Order'),
        ('CONSIGNMENT', 'Consignment'),
        ('RESELLER', 'Reseller'),
        ('PHYSICAL_STORE', 'Physical Store'),
    ]
    PRICE_TYPE_CHOICES = [
        ('UNIT', 'Unit Price'),
        ('SRP', 'Suggested Retail Price'),
    ]
    REASON_CHOICES = [
        ('SOLD', 'Sold'),
        ('EXPIRED', 'Expired'),
        ('DAMAGED', 'Damaged'),
        ('REPLACEMENT_FOR_RETURNED', 'Replacement for Returned Items'),
        ('OTHERS', 'Others'),
    ]
    PAYMENT_STATUS_CHOICES = [
        ('PAID', 'Paid'),
        ('UNPAID', 'Unpaid'),
        ('PARTIAL', 'Partial'),
    ]

    item_id = forms.ChoiceField(choices=[], required=True, label="Item")
    quantity = forms.DecimalField(min_value=0.01, required=True, decimal_places=2)
    reason = forms.ChoiceField(choices=REASON_CHOICES, required=True)
    sales_channel = forms.ChoiceField(choices=SALES_CHANNEL_CHOICES, required=False)
    customer_name = forms.CharField(
        required=False,
        label="Customer/Store Name",
        widget=forms.TextInput(attrs={"placeholder": "Enter customer or store name"})
    )
    payment_status = forms.ChoiceField(
        choices=PAYMENT_STATUS_CHOICES,
        required=False,
        initial='PAID',
        label="Payment Status"
    )
    paid_amount = forms.DecimalField(
        required=False,
        min_value=0,
        decimal_places=2,
        label="Paid Amount",
        widget=forms.NumberInput(attrs={"placeholder": "Enter amount paid"})
    )

    price_type_or_custom = forms.CharField(
        required=False,
        label="Price Type or Custom Price",
        widget=forms.TextInput(
            attrs={
                "placeholder": "Type custom price or select from dropdown",
                "list": "price_type_list"
            }
        )
    )

    discount = forms.ModelChoiceField(
        queryset=Discounts.objects.all(),
        required=False,
        empty_label="No Discount",
        label="Select Discount"
    )
    custom_discount_value = forms.DecimalField(
        required=False,
        min_value=0,
        decimal_places=2,
        label="Custom Discount (%)"
    )

    class Meta:
        model = Withdrawals
        fields = [
            'item_id', 'quantity', 'reason', 'sales_channel', 'customer_name',
            'payment_status', 'paid_amount', 'price_type_or_custom',
            'discount', 'custom_discount_value',
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if self.instance.pk:
            if self.instance.item_type == 'RAW_MATERIAL':
                materials = [(m.id, str(m)) for m in RawMaterials.objects.all()]
                self.fields['item_id'].choices = materials
                self.fields['item_id'].initial = self.instance.item_id
                self.fields['reason'].choices = [
                    ('EXPIRED', 'Expired'),
                    ('DAMAGED', 'Damaged'),
                    ('REPLACEMENT_FOR_RETURNED', 'Replacement for Returned Items'),
                    ('OTHERS', 'Others'),
                ]
                self.fields['price_type_or_custom'].required = False
                self.fields['sales_channel'].required = False
                self.fields['discount'].required = False
                self.fields['custom_discount_value'].required = False
            else:
                products = [(p.id, str(p)) for p in Products.objects.all()]
                self.fields['item_id'].choices = products
                self.fields['item_id'].initial = self.instance.item_id
        else:
            products = [(p.id, str(p)) for p in Products.objects.all()]
            materials = [(m.id, str(m)) for m in RawMaterials.objects.all()]
            self.fields['item_id'].choices = products + materials

        if self.instance.pk:
            if self.instance.price_type:
                self.fields['price_type_or_custom'].initial = self.instance.price_type
            elif self.instance.custom_price:
                self.fields['price_type_or_custom'].initial = str(self.instance.custom_price)

            if self.instance.customer_name:
                self.fields['customer_name'].initial = self.instance.customer_name
            if self.instance.payment_status:
                self.fields['payment_status'].initial = self.instance.payment_status
            if self.instance.paid_amount:
                self.fields['paid_amount'].initial = self.instance.paid_amount

    def clean(self):
        cleaned_data = super().clean()
        reason = cleaned_data.get("reason")
        sales_channel = cleaned_data.get("sales_channel")
        price_input = cleaned_data.get("price_type_or_custom")

        is_raw_material = self.instance.pk and self.instance.item_type == 'RAW_MATERIAL'
        if is_raw_material and reason == "SOLD":
            self.add_error("reason", "Raw materials cannot be marked as SOLD.")
            return cleaned_data

        if not is_raw_material:
            discount = cleaned_data.get("discount")
            custom_discount = cleaned_data.get("custom_discount_value")
            if discount and custom_discount:
                self.add_error("custom_discount_value", "You cannot select and enter a discount at the same time.")

            if reason == "SOLD":
                if not sales_channel:
                    self.add_error("sales_channel", "This field is required when reason is SOLD.")
                if not price_input:
                    self.add_error("price_type_or_custom", "Please select a price type or enter a custom price.")
                    return cleaned_data

                price_upper = str(price_input).upper().strip()

                try:
                    custom_price = Decimal(price_input)
                    cleaned_data["custom_price"] = custom_price
                    cleaned_data["price_type"] = None
                except (TypeError, ValueError, InvalidOperation):
                    if price_upper not in dict(self.PRICE_TYPE_CHOICES):
                        self.add_error("price_type_or_custom", "Enter a numeric price or select UNIT or SRP as price type.")
                    else:
                        cleaned_data["price_type"] = price_upper
                        cleaned_data["custom_price"] = None

        return cleaned_data

    def save(self, commit=True):
        instance = super().save(commit=False)

        instance.price_type = None
        instance.custom_price = None

        price_input = self.cleaned_data.get("price_type_or_custom")
        if price_input:
            try:
                custom_price = Decimal(str(price_input))
                instance.custom_price = custom_price
            except (ValueError, TypeError, InvalidOperation):
                price_upper = str(price_input).upper().strip()
                if price_upper in dict(self.PRICE_TYPE_CHOICES):
                    instance.price_type = price_upper

        discount_obj = self.cleaned_data.get("discount")
        custom_discount = self.cleaned_data.get("custom_discount_value")
        if discount_obj:
            instance.discount_id = discount_obj.id
            instance.custom_discount_value = None
        else:
            instance.discount_id = None
            instance.custom_discount_value = custom_discount

        if commit:
            instance.save()

        return instance


class UnifiedWithdrawForm(forms.Form):
    ITEM_TYPE_CHOICES = [
        ('PRODUCT', 'Product'),
        ('RAW_MATERIAL', 'Raw Material'),
    ]
    SALES_CHANNEL_CHOICES = [
        ('ORDER', 'Order'),
        ('CONSIGNMENT', 'Consignment'),
        ('RESELLER', 'Reseller'),
        ('PHYSICAL_STORE', 'Physical Store'),
    ]
    REASON_CHOICES = [
        ('SOLD', 'Sold'),
        ('EXPIRED', 'Expired'),
        ('DAMAGED', 'Damaged'),
        ('REPLACEMENT_FOR_RETURNED', 'Replacement for Returned Items'),
        ('OTHERS', 'Others'),
    ]

    item_type = forms.ChoiceField(choices=ITEM_TYPE_CHOICES, required=True)
    item = forms.ChoiceField(choices=[], required=True)
    quantity = forms.DecimalField(min_value=0.01, required=True, decimal_places=2)
    reason = forms.ChoiceField(choices=REASON_CHOICES, required=True)

    sales_channel = forms.ChoiceField(choices=SALES_CHANNEL_CHOICES, required=False)
    price_input = forms.CharField(
        required=False,
        label="Price",
        help_text="Enter custom price or select UNIT/SRP"
    )

    discount = forms.ModelChoiceField(queryset=Discounts.objects.all(), required=False)
    custom_discount_value = forms.DecimalField(
        required=False, min_value=0, decimal_places=2, label="Custom Discount"
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['item'].choices = [(p.id, str(p)) for p in Products.objects.filter(is_archived=False)]

    def clean(self):
        cleaned_data = super().clean()
        reason = cleaned_data.get("reason")
        sales_channel = cleaned_data.get("sales_channel")
        price_input = cleaned_data.get("price_input")

        if reason == "SOLD" and not sales_channel:
            self.add_error("sales_channel", "This field is required when reason is SOLD.")

        if reason == "SOLD":
            if not price_input:
                self.add_error("price_input", "This field is required for SOLD items.")
            elif price_input not in ['UNIT', 'SRP']:
                try:
                    float(price_input)
                except ValueError:
                    self.add_error("price_input", "Enter a number or select UNIT/SRP.")

        return cleaned_data


class NotificationsForm(forms.ModelForm):
    class Meta:
        model = Notifications
        fields = "__all__"


class BulkProductBatchForm(forms.Form):
    """
    Bulk product batch form.
    Handles multiple products with quantity, manufactured date, and expiration date.
    Auto-generates expiration based on product type and defaults.
    """

    manufactured_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'type': 'date'})
    )

    expiration_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'type': 'date'})
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.products = []

        # Filter out archived products
        for product in Products.objects.filter(is_archived=False).order_by('id'):

            qty_field_name = f'product_{product.id}_qty'
            manufactured_field_name = f'product_{product.id}_manufactured'
            expiration_field_name = f'product_{product.id}_expiration'
            is_yema = self._is_yema_product(product)

            # Quantity field
            self.fields[qty_field_name] = forms.DecimalField(
                required=False,
                min_value=0,
                label=str(product),
                widget=forms.NumberInput(attrs={
                    'class': 'form-control',
                    'step': '0.01',
                    'placeholder': 'Enter Quantity',
                    'data-product-id': str(product.id),
                    'data-field-type': 'quantity'
                })
            )

            # Manufactured field with default = today
            self.fields[manufactured_field_name] = forms.DateField(
                required=False,
                initial=timezone.localdate(),
                widget=forms.DateInput(attrs={
                    'type': 'date',
                    'class': 'form-control product-manufactured manufactured-input',
                    'data-product-id': str(product.id),
                    'data-field-type': 'manufactured',
                    'data-is-yema': 'true' if is_yema else 'false'
                })
            )

            # Compute default expiration
            expiration_initial = self._calculate_expiration(timezone.localdate(), is_yema)

            expiration_attrs = {
                'type': 'date',
                'class': 'form-control product-expiration expiration-input',
                'data-product-id': str(product.id),
                'data-field-type': 'expiration',
                'data-is-yema': 'true' if is_yema else 'false'
            }

            self.fields[expiration_field_name] = forms.DateField(
                required=False,
                initial=expiration_initial,
                widget=forms.DateInput(attrs=expiration_attrs)
            )

            self.products.append({
                "product": product,
                "qty_field": self[qty_field_name],
                "manufactured_field": self[manufactured_field_name],
                "expiration_field": self[expiration_field_name],
                "is_yema": is_yema,
            })

    def _is_yema_product(self, product):
        """
        Determine if product is Yema type.
        """
        product_text = " ".join(filter(None, [
            getattr(product.product_type, 'name', '') if hasattr(product, 'product_type') else '',
            getattr(product.variant, 'name', '') if hasattr(product, 'variant') else '',
            product.description or ''
        ])).lower()
        return 'yema' in product_text

    def _add_months_safe(self, date_obj, months):
        month_index = date_obj.month - 1 + months
        year = date_obj.year + month_index // 12
        month = month_index % 12 + 1
        day = min(date_obj.day, monthrange(year, month)[1])
        return date_obj.replace(year=year, month=month, day=day)

    def _calculate_expiration(self, manufactured_value, is_yema):
        months_to_add = 6 if is_yema else 12
        base_expiration = self._add_months_safe(manufactured_value, months_to_add)
        return base_expiration + timedelta(days=1)

    def clean(self):
        cleaned_data = super().clean()
        default_manufactured = cleaned_data.get('manufactured_date')
        default_expiration = cleaned_data.get('expiration_date')

        if default_manufactured:
            if default_expiration and default_expiration < default_manufactured:
                self.add_error('expiration_date', 'Expiration date cannot be before the manufactured date.')
        elif default_expiration:
            self.add_error('manufactured_date', 'Please provide a manufactured date to use as default for all products.')
        else:
            default_manufactured = timezone.localdate()

        for product_info in self.products:
            product = product_info["product"]
            qty_field_name = f'product_{product.id}_qty'
            manufactured_field_name = f'product_{product.id}_manufactured'
            expiration_field_name = f'product_{product.id}_expiration'
            is_yema = product_info['is_yema']

            # Only validate if quantity is entered
            qty = cleaned_data.get(qty_field_name)
            if not qty or float(qty) <= 0:
                continue

            manufactured_value = cleaned_data.get(manufactured_field_name) or default_manufactured or timezone.localdate()

            expiration_value = cleaned_data.get(expiration_field_name)

            if is_yema:
                expiration_value = self._calculate_expiration(manufactured_value, True)
            elif expiration_value:
                if expiration_value < manufactured_value:
                    self.add_error(expiration_field_name, 'Expiration date cannot be before the manufactured date.')
                    continue
            elif default_expiration:
                expiration_value = default_expiration
            else:
                expiration_value = self._calculate_expiration(manufactured_value, False)

            if expiration_value < manufactured_value:
                self.add_error(expiration_field_name, 'Expiration date cannot be before the manufactured date.')
                continue

            cleaned_data[manufactured_field_name] = manufactured_value
            cleaned_data[expiration_field_name] = expiration_value

        # Also ensure top-level defaults exist
        cleaned_data['manufactured_date'] = default_manufactured
        if default_expiration:
            cleaned_data['expiration_date'] = default_expiration
        elif default_manufactured:
            cleaned_data['expiration_date'] = self._calculate_expiration(default_manufactured, False)
        else:
            cleaned_data['expiration_date'] = None


# ... (rest of the code remains the same)

class BulkRawMaterialBatchForm(forms.Form):
    CATEGORY_CHOICES = (
        ('PACKAGING', 'Packaging'),
        ('RECIPE', 'Recipe'),
    )

    category = forms.ChoiceField(choices=CATEGORY_CHOICES, required=False)
    received_date = forms.DateField(widget=forms.DateInput(attrs={'type': 'date'}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.rawmaterials = []

        choice_values = {value for value, _ in self.CATEGORY_CHOICES}
        selected = (self.data.get('category') or self.initial.get('category') or 'PACKAGING').upper()
        if selected not in choice_values:
            selected = 'PACKAGING'
        self.selected_category = selected
        self.fields['category'].initial = self.selected_category

        queryset = RawMaterials.objects.filter(is_archived=False, category__iexact=self.selected_category)

        for rawmaterial in queryset.order_by('name'):
            qty_field_name = f'rawmaterial_{rawmaterial.id}_qty'
            exp_field_name = f'rawmaterial_{rawmaterial.id}_exp'

            self.fields[qty_field_name] = forms.DecimalField(
                required=False,
                min_value=0,
                label=str(rawmaterial),
                widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'placeholder': 'Enter Quantity'})
            )

            self.fields[exp_field_name] = forms.DateField(
                required=False,
                widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control', 'placeholder': 'Select Expiration Date'})
            )

            self.rawmaterials.append({
                "rawmaterial": rawmaterial,
                "qty_field": self[qty_field_name],
                "exp_field": self[exp_field_name],
            })



class StockChangesForm(ModelForm):
    class Meta:
        model = StockChanges
        fields = "__all__"

class CustomUserCreationForm(forms.ModelForm):
    password1 = forms.CharField(widget=forms.PasswordInput, label="Password")
    password2 = forms.CharField(widget=forms.PasswordInput, label="Confirm Password")
    user_type = forms.ChoiceField(
        choices=[('', 'Select User Type'), ('staff', 'Staff')],
        required=True,
        label="User Type",
        help_text="Administrator accounts can only be created by existing admins."
    )

    class Meta:
        model = User
        fields = ['username', 'first_name', 'last_name', 'email']

    def clean_email(self):
        email = self.cleaned_data.get('email')
        if User.objects.filter(email=email).exists():
            raise ValidationError("This email address is already in use.")
        
        if User.objects.filter(username=email).exists():
            raise ValidationError("This email address is already in use.")
        
        deactivated_user = User.objects.filter(
            last_name = f"ORIGINAL_EMAIL:{email}",
            username__startswith= 'inactive_user_'
        ).first()
        if deactivated_user:
            raise ValidationError("This email address is already in use.")

        return email

    def clean_password2(self):
        password1 = self.cleaned_data.get('password1')
        password2 = self.cleaned_data.get('password2')
        if password1 != password2:
            raise ValidationError("Passwords do not match.")
        return password2
    
    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data["password1"])

        user.is_active = False
        
        user_type = self.cleaned_data.get('user_type')
        if user_type == 'staff':
            user.is_staff = True
            user.is_superuser = False
        else:
            user.is_staff = False
            user.is_superuser = False

        if commit:
            user.save()
        return user