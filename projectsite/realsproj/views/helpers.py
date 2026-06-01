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
import logging

logger = logging.getLogger(__name__)
import json
import hashlib
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

# get_or_create_auth_user
def get_or_create_auth_user(user):
    """
    Get or create AuthUser record from Django User.
    This handles database sync issues when switching between databases.
    """
    try:
        return AuthUser.objects.get(id=user.id)
    except AuthUser.DoesNotExist:

        return AuthUser.objects.create(
            id=user.id,
            password=user.password,
            last_login=user.last_login,
            is_superuser=user.is_superuser,
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name,
            email=user.email,
            is_staff=user.is_staff,
            is_active=user.is_active,
            date_joined=user.date_joined
        )

# create_history_log
def create_history_log(admin, log_category, entity_type, entity_id, before=None, after=None):
    """
    Create a history log entry.
    
    Args:
        admin: User instance who performed the action
        log_category: String category (e.g., "Withdrawal Edited", "Withdrawal Deleted")
        entity_type: String entity type (e.g., "withdrawal")
        entity_id: ID of the entity
        before: Dict of values before change (for updates)
        after: Dict of values after change (for creates/updates)
    """
    try:
        # Get or create log type
        log_type, _ = HistoryLogTypes.objects.get_or_create(
            category=log_category,
            defaults={'created_by_admin_id': admin.id}
        )
        
        # Build details
        details = {}
        if before:
            details['before'] = before
        if after:
            details['after'] = after
        
        # Create log entry
        HistoryLog.objects.create(
            admin_id=admin.id,
            log_type_id=log_type.id,
            log_date=timezone.now(),
            entity_type=entity_type,
            entity_id=entity_id,
            details=details if details else None,
            is_archived=False
        )
    except Exception as e:
        logger.exception("Failed to create history log for %s #%s", entity_type, entity_id)

# mask_email
def mask_email(email):
    """Mask email address for privacy: john@example.com -> j***@example.com"""
    if not email or '@' not in email:
        return email
    
    local, domain = email.split('@', 1)
    if len(local) <= 1:
        masked_local = local + '*'
    else:
        masked_local = local[0] + '*'
    
    return f"{masked_local}@{domain}"

# get_client_ip
def get_client_ip(request):
    """Return the real client IP, honouring X-Forwarded-For from trusted proxies."""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        return x_forwarded_for.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR', '0.0.0.0')

# get_device_fingerprint
def get_device_fingerprint(request):
    """Create unique device ID from browser characteristics"""
    user_agent = request.META.get('HTTP_USER_AGENT', '')
    accept_language = request.META.get('HTTP_ACCEPT_LANGUAGE', '')
    accept_encoding = request.META.get('HTTP_ACCEPT_ENCODING', '')
    
    fingerprint_string = f"{user_agent}{accept_language}{accept_encoding}"
    return hashlib.sha256(fingerprint_string.encode()).hexdigest()

# get_device_info
def get_device_info(request):
    """Extract human-readable device details"""
    user_agent = request.META.get('HTTP_USER_AGENT', '')
    
    # Detect browser
    if 'Chrome' in user_agent and 'Edg' not in user_agent:
        browser = 'Chrome'
    elif 'Firefox' in user_agent:
        browser = 'Firefox'
    elif 'Safari' in user_agent and 'Chrome' not in user_agent:
        browser = 'Safari'
    elif 'Edg' in user_agent:
        browser = 'Edge'
    else:
        browser = 'Unknown'
    
    # Detect OS
    if 'Windows' in user_agent:
        os = 'Windows'
    elif 'Mac' in user_agent:
        os = 'macOS'
    elif 'Linux' in user_agent:
        os = 'Linux'
    elif 'Android' in user_agent:
        os = 'Android'
    elif 'iPhone' in user_agent or 'iPad' in user_agent:
        os = 'iOS'
    else:
        os = 'Unknown'
    
    return {
        'browser': browser,
        'os': os,
        'device_name': f"{os} - {browser}"
    }
