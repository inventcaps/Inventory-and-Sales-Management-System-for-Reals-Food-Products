import factory
from django.utils import timezone
from realsproj import models


class AuthUserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = models.AuthUser

    password = "pbkdf2_sha256$..."
    last_login = None
    is_superuser = False
    username = factory.Sequence(lambda n: f"testuser_{n}")
    first_name = "Test"
    last_name = "User"
    email = factory.Sequence(lambda n: f"testuser_{n}@example.com")
    is_staff = False
    is_active = True
    date_joined = timezone.now()


class ProductTypesFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = models.ProductTypes

    name = factory.Sequence(lambda n: f"ProductType_{n}")
    created_by_admin = factory.SubFactory(AuthUserFactory)


class ProductVariantsFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = models.ProductVariants

    name = factory.Sequence(lambda n: f"Variant_{n}")
    created_by_admin = factory.SubFactory(AuthUserFactory)


class SizeUnitsFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = models.SizeUnits

    unit_name = factory.Sequence(lambda n: f"Unit_{n}")
    created_by_admin = factory.SubFactory(AuthUserFactory)


class SizesFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = models.Sizes

    size_label = factory.Sequence(lambda n: f"Size_{n}")
    created_by_admin = factory.SubFactory(AuthUserFactory)


class UnitPricesFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = models.UnitPrices

    unit_price = factory.Sequence(lambda n: n * 10.0 + 5.0)
    created_by_admin = factory.SubFactory(AuthUserFactory)


class SrpPricesFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = models.SrpPrices

    srp_price = factory.Sequence(lambda n: n * 15.0 + 10.0)
    created_by_admin = factory.SubFactory(AuthUserFactory)


class ProductsFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = models.Products

    product_type = factory.SubFactory(ProductTypesFactory)
    variant = factory.SubFactory(ProductVariantsFactory)
    size_unit = factory.SubFactory(SizeUnitsFactory)
    unit_price = factory.SubFactory(UnitPricesFactory)
    srp_price = factory.SubFactory(SrpPricesFactory)
    description = "Test product"
    created_by_admin = factory.SubFactory(AuthUserFactory)
    date_created = timezone.now()
    size = None
    photo = None
    is_archived = False
    barcode = None
    product_code = factory.Sequence(lambda n: f"PRD{n:04d}")


class ProductInventoryFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = models.ProductInventory

    product = factory.SubFactory(ProductsFactory)
    total_stock = 100
    restock_threshold = 20


class RawMaterialsFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = models.RawMaterials

    name = factory.Sequence(lambda n: f"RawMaterial_{n}")
    unit = factory.SubFactory(SizeUnitsFactory)
    price_per_unit = 50.0
    created_by_admin = factory.SubFactory(AuthUserFactory)
    size = "1"
    date_created = timezone.now()
    is_archived = False
    category = "Packaging"


class RawMaterialInventoryFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = models.RawMaterialInventory

    material = factory.SubFactory(RawMaterialsFactory)
    total_stock = 200
    reorder_threshold = 50


class SalesFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = models.Sales

    category = "Regular Sales"
    amount = 1500.00
    date = timezone.localdate()
    description = "Test sale"
    created_by_admin = factory.SubFactory(AuthUserFactory)
    is_archived = False


class ExpensesFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = models.Expenses

    category = "Utilities"
    amount = 500.00
    date = timezone.localdate()
    description = "Test expense"
    created_by_admin = factory.SubFactory(AuthUserFactory)
    is_archived = False
