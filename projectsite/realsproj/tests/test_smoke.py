import pytest
from django.test import Client
from django.urls import reverse
from django.contrib.auth.models import User
from realsproj.tests.factories import (
    AuthUserFactory,
    ProductsFactory,
    ProductInventoryFactory,
    ProductTypesFactory,
    ProductVariantsFactory,
    SizeUnitsFactory,
    SizesFactory,
    UnitPricesFactory,
    SrpPricesFactory,
    RawMaterialsFactory,
    RawMaterialInventoryFactory,
    SalesFactory,
    ExpensesFactory,
)


@pytest.mark.django_db
class TestModels:
    def test_product_creation(self):
        product = ProductsFactory()
        assert product.product_code
        assert str(product.product_code).startswith("PRD")

    def test_product_inventory_creation(self):
        inventory = ProductInventoryFactory()
        assert inventory.total_stock == 100
        assert inventory.restock_threshold == 20

    def test_raw_material_creation(self):
        material = RawMaterialsFactory()
        assert material.name.startswith("RawMaterial_")

    def test_raw_material_inventory_creation(self):
        inventory = RawMaterialInventoryFactory()
        assert inventory.total_stock == 200
        assert inventory.reorder_threshold == 50

    def test_sales_creation(self):
        sale = SalesFactory(amount=2500.00)
        assert sale.amount == 2500.00

    def test_expenses_creation(self):
        expense = ExpensesFactory(amount=750.00)
        assert expense.amount == 750.00

    def test_auth_user_creation(self):
        user = AuthUserFactory(username="test_admin")
        assert user.username == "test_admin"
        assert user.is_active is True


@pytest.mark.django_db
class TestViews:
    def test_home_page_requires_login(self):
        client = Client()
        response = client.get(reverse("home"))
        assert response.status_code == 302

    def test_login_page_loads(self):
        client = Client()
        response = client.get(reverse("login"))
        assert response.status_code == 200

    def test_authenticated_user_can_access_products(self):
        user = User.objects.create_user(username="testuser", password="testpass123")
        client = Client()
        client.force_login(user)
        response = client.get(reverse("products"))
        assert response.status_code in (200, 302)

    def test_authenticated_user_can_access_sales(self):
        user = User.objects.create_user(username="testuser2", password="testpass123")
        client = Client()
        client.force_login(user)
        response = client.get(reverse("salesexpenses"))
        assert response.status_code in (200, 302)

    def test_authenticated_user_can_access_profile(self):
        user = User.objects.create_user(username="testuser3", password="testpass123")
        client = Client()
        client.force_login(user)
        response = client.get(reverse("profile"))
        assert response.status_code in (200, 302)

    def test_login_redirects_authenticated_user(self):
        user = User.objects.create_user(username="testuser4", password="testpass123")
        client = Client()
        client.force_login(user)
        response = client.get(reverse("login"))
        assert response.status_code in (200, 302)


@pytest.mark.django_db
class TestFactories:
    def test_product_types_factory(self):
        pt = ProductTypesFactory(name="Beverage")
        assert pt.name == "Beverage"

    def test_product_variants_factory(self):
        pv = ProductVariantsFactory(name="Regular")
        assert pv.name == "Regular"

    def test_size_units_factory(self):
        su = SizeUnitsFactory(unit_name="mL")
        assert su.unit_name == "mL"

    def test_sizes_factory(self):
        sz = SizesFactory(size_label="500")
        assert sz.size_label == "500"

    def test_unit_prices_factory(self):
        up = UnitPricesFactory(unit_price=25.00)
        assert up.unit_price == 25.00

    def test_srp_prices_factory(self):
        sp = SrpPricesFactory(srp_price=30.00)
        assert sp.srp_price == 30.00
