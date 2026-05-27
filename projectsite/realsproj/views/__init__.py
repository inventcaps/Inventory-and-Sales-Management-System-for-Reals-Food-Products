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

from realsproj.views.helpers import *
from realsproj.views.products import *
from realsproj.views.materials import *
from realsproj.views.sales import *
from realsproj.views.withdrawals import *
from realsproj.views.users import *
from realsproj.views.reports import *
# Helper function for creating history logs
# Withdrawal Order Views
# Product Attributes Management View
# Product Type CRUD
# Product Variant CRUD
# Size CRUD
# Size Unit CRUD
# Unit Price CRUD
# SRP Price CRUD
# Withdrawal Group Actions
# NotificationsDeleteView removed - notifications should not be deleted