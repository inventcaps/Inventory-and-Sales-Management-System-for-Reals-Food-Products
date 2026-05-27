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

# profile_view
@login_required
def profile_view(request):
    return render(request, "profile.html")

# download_my_data
@login_required
def download_my_data(request):
    """
    Generate and download a CSV file containing all user data
    """
    import csv
    from io import StringIO
    
    user = request.user
    # Convert Django User to AuthUser for querying
    auth_user = AuthUser.objects.get(id=user.id)
    
    # Create CSV in memory
    output = StringIO()
    writer = csv.writer(output)
    
    # Write header
    writer.writerow(['=== MY DATA EXPORT ==='])
    writer.writerow([f'Generated: {timezone.now().strftime("%B %d, %Y at %I:%M %p")}'])
    writer.writerow([])
    
    # Account Information Section
    writer.writerow(['ACCOUNT INFORMATION'])
    writer.writerow(['Field', 'Value'])
    writer.writerow(['Username', user.username])
    writer.writerow(['Email', user.email])
    writer.writerow(['First Name', user.first_name or 'Not set'])
    writer.writerow(['Last Name', user.last_name or 'Not set'])
    writer.writerow(['Staff Status', 'Yes' if user.is_staff else 'No'])
    writer.writerow(['Administrator', 'Yes' if user.is_superuser else 'No'])
    writer.writerow(['Account Active', 'Yes' if user.is_active else 'No'])
    writer.writerow(['Date Joined', user.date_joined.strftime('%B %d, %Y') if user.date_joined else 'N/A'])
    writer.writerow(['Last Login', user.last_login.strftime('%B %d, %Y at %I:%M %p') if user.last_login else 'Never'])
    writer.writerow([])
    
    # Two-Factor Authentication Section
    writer.writerow(['TWO-FACTOR AUTHENTICATION'])
    writer.writerow(['Field', 'Value'])
    try:
        if hasattr(user, 'twofa_settings'):
            writer.writerow(['2FA Enabled', 'Yes' if user.twofa_settings.is_enabled else 'No'])
            writer.writerow(['Method', user.twofa_settings.method or 'N/A'])
            writer.writerow(['Backup Email', user.twofa_settings.backup_email or 'Not set'])
        else:
            writer.writerow(['2FA Enabled', 'No'])
    except:
        writer.writerow(['2FA Enabled', 'No'])
    writer.writerow([])
    
    # User Activity Section
    writer.writerow(['USER ACTIVITY'])
    writer.writerow(['Field', 'Value'])
    try:
        if hasattr(user, 'useractivity'):
            writer.writerow(['Last Logout', user.useractivity.last_logout.strftime('%B %d, %Y at %I:%M %p') if user.useractivity.last_logout else 'N/A'])
            writer.writerow(['Currently Active', 'Yes' if user.useractivity.active else 'No'])
        else:
            writer.writerow(['Activity Tracking', 'Not available'])
    except:
        writer.writerow(['Activity Tracking', 'Not available'])
    writer.writerow([])
    
    # Products Created
    writer.writerow(['PRODUCTS CREATED'])
    try:
        products = Products.objects.filter(created_by_admin=auth_user)
        if products.exists():
            writer.writerow(['ID', 'Name', 'Barcode', 'Created At'])
            for product in products:
                writer.writerow([
                    product.id,
                    str(product),
                    product.barcode or 'N/A',
                    product.date_created.strftime('%B %d, %Y') if hasattr(product, 'date_created') and product.date_created else 'N/A'
                ])
        else:
            writer.writerow(['No products created'])
    except Exception as e:
        writer.writerow([f'Error retrieving products: {str(e)}'])
    writer.writerow([])
    
    # Raw Materials Created
    writer.writerow(['RAW MATERIALS CREATED'])
    try:
        raw_materials = RawMaterials.objects.filter(created_by_admin=auth_user)
        if raw_materials.exists():
            writer.writerow(['ID', 'Name', 'Created At'])
            for rm in raw_materials:
                writer.writerow([
                    rm.id,
                    rm.name,
                    rm.date_created.strftime('%B %d, %Y') if hasattr(rm, 'date_created') and rm.date_created else 'N/A'
                ])
        else:
            writer.writerow(['No raw materials created'])
    except Exception as e:
        writer.writerow([f'Error retrieving raw materials: {str(e)}'])
    writer.writerow([])
    
    # Sales Created
    writer.writerow(['SALES RECORDS CREATED'])
    try:
        sales = Sales.objects.filter(created_by_admin=auth_user)
        if sales.exists():
            writer.writerow(['ID', 'Date', 'Amount'])
            for sale in sales:
                writer.writerow([
                    sale.id,
                    sale.date.strftime('%B %d, %Y') if sale.date else 'N/A',
                    f'₱{float(sale.amount):,.2f}' if sale.amount else '₱0.00'
                ])
        else:
            writer.writerow(['No sales records created'])
    except Exception as e:
        writer.writerow([f'Error retrieving sales: {str(e)}'])
    writer.writerow([])
    
    # Expenses Created
    writer.writerow(['EXPENSE RECORDS CREATED'])
    try:
        expenses = Expenses.objects.filter(created_by_admin=auth_user)
        if expenses.exists():
            writer.writerow(['ID', 'Date', 'Amount', 'Description'])
            for expense in expenses:
                writer.writerow([
                    expense.id,
                    expense.date.strftime('%B %d, %Y') if expense.date else 'N/A',
                    f'₱{float(expense.amount):,.2f}' if expense.amount else '₱0.00',
                    expense.description if hasattr(expense, 'description') else 'N/A'
                ])
        else:
            writer.writerow(['No expense records created'])
    except Exception as e:
        writer.writerow([f'Error retrieving expenses: {str(e)}'])
    writer.writerow([])
    
    # Withdrawals Created
    writer.writerow(['WITHDRAWAL RECORDS CREATED'])
    try:
        withdrawals = Withdrawals.objects.filter(created_by_admin=user)
        if withdrawals.exists():
            writer.writerow(['ID', 'Date', 'Item Type', 'Quantity', 'Reason'])
            for withdrawal in withdrawals:
                writer.writerow([
                    withdrawal.id,
                    withdrawal.date.strftime('%B %d, %Y at %I:%M %p') if withdrawal.date else 'N/A',
                    withdrawal.item_type,
                    float(withdrawal.quantity) if withdrawal.quantity else 0,
                    withdrawal.reason
                ])
        else:
            writer.writerow(['No withdrawal records created'])
    except Exception as e:
        writer.writerow([f'Error retrieving withdrawals: {str(e)}'])
    writer.writerow([])
    
    # Product Batches Created
    writer.writerow(['PRODUCT BATCHES CREATED'])
    try:
        product_batches = ProductBatches.objects.filter(created_by_admin=auth_user)
        if product_batches.exists():
            writer.writerow(['ID', 'Product', 'Quantity', 'Batch Date'])
            for batch in product_batches:
                writer.writerow([
                    batch.id,
                    str(batch.product) if batch.product else 'N/A',
                    batch.quantity if hasattr(batch, 'quantity') else 'N/A',
                    batch.batch_date.strftime('%B %d, %Y') if hasattr(batch, 'batch_date') and batch.batch_date else 'N/A'
                ])
        else:
            writer.writerow(['No product batches created'])
    except Exception as e:
        writer.writerow([f'Error retrieving product batches: {str(e)}'])
    writer.writerow([])
    
    # Raw Material Batches Created
    writer.writerow(['RAW MATERIAL BATCHES CREATED'])
    try:
        rm_batches = RawMaterialBatches.objects.filter(created_by_admin=auth_user)
        if rm_batches.exists():
            writer.writerow(['ID', 'Material', 'Quantity', 'Batch Date'])
            for batch in rm_batches:
                writer.writerow([
                    batch.id,
                    str(batch.material) if batch.material else 'N/A',
                    batch.quantity if hasattr(batch, 'quantity') else 'N/A',
                    batch.batch_date.strftime('%B %d, %Y') if hasattr(batch, 'batch_date') and batch.batch_date else 'N/A'
                ])
        else:
            writer.writerow(['No raw material batches created'])
    except Exception as e:
        writer.writerow([f'Error retrieving raw material batches: {str(e)}'])
    
    # Create CSV response
    response = HttpResponse(output.getvalue(), content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="my_data_{user.username}_{timezone.now().strftime("%Y%m%d_%H%M%S")}.csv"'
    
    return response

# login_view
def login_view(request):
    if request.method == 'POST':
        if 'otp_code' in request.POST:
            user_id = request.session.get('2fa_user_id')
            if not user_id:
                messages.error(request, "Session expired. Please login again.")
                return redirect('login')
            
            # OTP brute-force protection
            otp_attempts = request.session.get('otp_attempts', 0)
            max_otp_attempts = 3
            if otp_attempts >= max_otp_attempts:
                for key in ['2fa_user_id', 'remember_me', 'otp_attempts']:
                    request.session.pop(key, None)
                messages.error(request, "🔒 Too many incorrect OTP attempts. Please login again.")
                return redirect('login')
            
            from realsproj.models import UserOTP, User2FASettings, TrustedDevice, LoginAttempt
            from django.utils import timezone
            from datetime import timedelta
            
            try:
                user = User.objects.get(id=user_id)
                otp_code = request.POST.get('otp_code', '').strip()
                
                # Clean up expired OTPs first
                UserOTP.objects.filter(
                    user=user,
                    expires_at__lt=timezone.now()
                ).delete()
                
                otp = UserOTP.objects.filter(
                    user=user,
                    otp_code=otp_code,
                    is_used=False,
                    expires_at__gt=timezone.now()
                ).first()
                
                if otp:
                    otp.is_used = True
                    otp.save()
                    request.session.pop('otp_attempts', None)
                    
                    device_fingerprint = get_device_fingerprint(request)
                    device_info = get_device_info(request)
                    ip_address = get_client_ip(request)
                    
                    TrustedDevice.objects.get_or_create(
                        user=user,
                        device_fingerprint=device_fingerprint,
                        defaults={
                            'device_name': device_info['device_name'],
                            'browser': device_info['browser'],
                            'os': device_info['os'],
                            'ip_address': ip_address,
                        }
                    )
                    
                    LoginAttempt.objects.create(
                        user=user,
                        username=user.username,
                        ip_address=ip_address,
                        device_fingerprint=device_fingerprint,
                        browser=device_info['browser'],
                        os=device_info['os'],
                        success=True,
                        required_otp=True,
                        is_trusted_device=True
                    )
                    
                    send_login_notification(user, device_info, ip_address, is_new_device=True)
                    
                    # Get remember me setting from session
                    remember_me = request.session.get('remember_me', False)
                    del request.session['2fa_user_id']
                    if 'remember_me' in request.session:
                        del request.session['remember_me']
                    
                    login(request, user)
                    
                    # Set session expiry based on remember me
                    if remember_me:
                        request.session.set_expiry(2592000)  # 30 days in seconds
                    else:
                        request.session.set_expiry(0)  # Expire on browser close
                    
                    messages.success(request, "✅ Successfully logged in! This device is now trusted.")
                    return redirect('home')
                else:
                    new_attempts = otp_attempts + 1
                    request.session['otp_attempts'] = new_attempts
                    remaining = 3 - new_attempts
                    if remaining > 0:
                        messages.error(request, f"❌ Invalid or expired OTP code. {remaining} attempt(s) remaining.")
                        return render(request, '2fa_verify.html', {'user_email': user.email})
                    else:
                        for key in ['2fa_user_id', 'remember_me', 'otp_attempts']:
                            request.session.pop(key, None)
                        messages.error(request, "🔒 Too many incorrect OTP attempts. Please login again.")
                        return redirect('login')
            except Exception as e:
                messages.error(request, f"An error occurred: {str(e)}")
                return render(request, '2fa_verify.html')
        
        username = request.POST.get('username', '')
        password = request.POST.get('password', '')
                
        # Check for login lockout
        from realsproj.models import LoginAttempt
        from django.utils import timezone
        from datetime import timedelta
        
        ip_address = get_client_ip(request)
        lockout_duration = timedelta(minutes=5)
        max_attempts = 5
        
        # Check failed attempts in the last 5 minutes from this IP address for THIS username.
        # Excludes OTP-pending rows (required_otp=True) — those represent CORRECT password
        # entries that just need 2FA, not credential failures, so they must not contribute
        # to lockout. Scoping by username also prevents one user's failures from locking
        # out others sharing the same IP (e.g., office network).
        recent_failed_attempts = LoginAttempt.objects.filter(
            ip_address=ip_address,
            username=username,
            success=False,
            required_otp=False,
            timestamp__gte=timezone.now() - lockout_duration
        ).count()

        if recent_failed_attempts >= max_attempts:
            last_attempt = LoginAttempt.objects.filter(
                ip_address=ip_address,
                username=username,
                success=False,
                required_otp=False,
                timestamp__gte=timezone.now() - lockout_duration
            ).order_by('-timestamp').first()
            
            if last_attempt:
                time_remaining = (last_attempt.timestamp + lockout_duration) - timezone.now()
                minutes_remaining = int(time_remaining.total_seconds() / 60)
                seconds_remaining = int(time_remaining.total_seconds() % 60)
                
                if minutes_remaining > 0:
                    messages.error(request, f"🔒 Too many failed login attempts. Please try again in {minutes_remaining} minute(s) and {seconds_remaining} second(s).")
                else:
                    messages.error(request, f"🔒 Too many failed login attempts. Please try again in {seconds_remaining} second(s).")
                return render(request, 'login.html')
        
        user = authenticate(request, username=username, password=password)

        # Fallback: allow login by email address. Many users type their email instead of
        # their username on the login form, which previously surfaced as "Invalid
        # username or password" and inflated failure metrics.
        if user is None and '@' in username:
            try:
                candidate = User.objects.get(email__iexact=username.strip())
                user = authenticate(request, username=candidate.username, password=password)
            except (User.DoesNotExist, User.MultipleObjectsReturned):
                user = None

        if user is not None:
            if user.is_active:
                from realsproj.models import UserOTP, TrustedDevice, LoginAttempt
                import random
                from datetime import timedelta
                from django.utils import timezone
                from django.core.mail import send_mail
                from django.conf import settings

                device_fingerprint = get_device_fingerprint(request)
                device_info = get_device_info(request)
                ip_address = get_client_ip(request)
                
                trusted_device = TrustedDevice.objects.filter(
                    user=user,
                    device_fingerprint=device_fingerprint,
                    is_active=True
                ).first()
                                
                if trusted_device:
                    trusted_device.last_used = timezone.now()
                    trusted_device.save()
                    
                    LoginAttempt.objects.create(
                        user=user,
                        username=user.username,
                        ip_address=ip_address,
                        device_fingerprint=device_fingerprint,
                        browser=device_info['browser'],
                        os=device_info['os'],
                        success=True,
                        required_otp=False,
                        is_trusted_device=True
                    )
                    
                    try:
                        from threading import Thread
                        Thread(target=send_login_notification, args=(user, device_info, ip_address, False)).start()
                    except Exception:
                        pass  
                    
                    login(request, user)
                    
                    remember_me = request.POST.get('remember', False)
                    if remember_me:
                        request.session.set_expiry(2592000)  
                    else:
                        request.session.set_expiry(0)  
                    
                    messages.success(request, f" Welcome back! Logged in from trusted device.")
                    return redirect('home')
                else:
                    otp_code = str(random.randint(100000, 999999))
                    
                    UserOTP.objects.create(
                        user=user,
                        otp_code=otp_code,
                        expires_at=timezone.now() + timedelta(minutes=10),
                        ip_address=ip_address
                    )
                    
                    def send_otp_email():
                        try:
                            send_mail(
                                subject='🔐 Account Confirmation Required - Real\'s Food Products',
                                message=f'''Hello {user.username},

Thank you for logging in to Real's Food Products Inventory System!

We need to confirm your account for security purposes.

Your confirmation code is: {otp_code}

This code will expire in 10 minutes.

Please enter this code to complete your login.

Real's Food Products Security Team''',
                                from_email=settings.DEFAULT_FROM_EMAIL,
                                recipient_list=[user.email],
                                fail_silently=False,
                            )
                        except Exception as e:
                            pass
                    
                    try:
                        from threading import Thread
                        Thread(target=send_otp_email).start()
                    except Exception as e:
                        messages.error(request, "Failed to send confirmation email. Please contact support.")  

                    LoginAttempt.objects.create(
                        user=user,
                        username=user.username,
                        ip_address=ip_address,
                        device_fingerprint=device_fingerprint,
                        browser=device_info['browser'],
                        os=device_info['os'],
                        success=False,
                        required_otp=True,
                        is_trusted_device=False
                    )
                    
                    request.session['2fa_user_id'] = user.id
                    remember_me = request.POST.get('remember', False)
                    request.session['remember_me'] = bool(remember_me)
                    
                    masked_email = mask_email(user.email)
                    messages.info(request, f" Account confirmation required! OTP sent to {masked_email}")
                    return render(request, '2fa_verify.html', {'user_email': masked_email})
            else:
                device_info = get_device_info(request)
                LoginAttempt.objects.create(
                    user=user,
                    username=username,
                    ip_address=ip_address,
                    device_fingerprint=get_device_fingerprint(request),
                    browser=device_info['browser'],
                    os=device_info['os'],
                    success=False,
                    required_otp=False,
                    is_trusted_device=False
                )
                messages.error(request, "❌ Your account is inactive. Please contact the administrator.")
                return render(request, 'login.html')
        else:
            device_info = get_device_info(request)
            LoginAttempt.objects.create(
                user=None,
                username=username,
                ip_address=ip_address,
                device_fingerprint=get_device_fingerprint(request),
                browser=device_info['browser'],
                os=device_info['os'],
                success=False,
                required_otp=False,
                is_trusted_device=False
            )
            
            attempts_count = LoginAttempt.objects.filter(
                ip_address=ip_address,
                username=username,
                success=False,
                required_otp=False,
                timestamp__gte=timezone.now() - lockout_duration
            ).count()
            
            attempts_remaining = max_attempts - attempts_count

            if attempts_remaining > 0:
                messages.error(request, f"Invalid username or password. {attempts_remaining} attempt(s) remaining.")
            else:
                messages.error(request, f"Too many failed login attempts. Please wait again after 5 minutes.")

            return render(request, 'login.html')
    return render(request, 'login.html')

# register
def register(request):
    if request.method == 'POST':
        form = CustomUserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            from django.core.mail import send_mail
            from django.conf import settings
            try:
                send_mail(
                    subject='Registration Pending Approval - Real\'s Food Products',
                    message=f'Hello {user.username},\n\nThank you for registering. Your account is pending approval.\n\nReal\'s Food Products Team',
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[user.email],
                    fail_silently=True,
                )
            except Exception:
                pass
            messages.success(request, 'Your account has been created! Please wait for admin approval before logging in.')
            return redirect('login')
    else:
        form = CustomUserCreationForm()
    return render(request, 'registration/register.html', {'form': form})

# user_management
@login_required
def user_management(request):
    if not request.user.is_superuser:
        messages.error(request, "You don't have permission to access this page.")
        return redirect('home')
    from django.db.models import Q
    from django.core.paginator import Paginator
    pending_users = User.objects.filter(is_active=False).exclude(
        Q(username__startswith='rejected_user_') | Q(username__startswith='deleted_user_') | Q(username__startswith='inactive_user_')
    ).order_by('-date_joined')
    active_users_queryset = User.objects.filter(is_active=True).exclude(
        Q(username__startswith='rejected_user_') | Q(username__startswith='deleted_user_') | Q(username__startswith='inactive_user_')
    ).order_by('-date_joined')
    active_paginator = Paginator(active_users_queryset, 5)
    active_users = active_paginator.get_page(request.GET.get('page', 1))
    inactive_users_raw = User.objects.filter(username__startswith='inactive_user_').order_by('-date_joined')
    inactive_users = []
    for user in inactive_users_raw:
        if user.first_name and 'ORIGINAL_USERNAME:' in user.first_name:
            parts = user.first_name.split('|')
            user.display_username = parts[0].replace('ORIGINAL_USERNAME:', '')
        else:
            user.display_username = f"User ID {user.id}"
        if user.last_name and 'ORIGINAL_EMAIL:' in user.last_name:
            parts = user.last_name.split('|')
            user.display_email = parts[0].replace('ORIGINAL_EMAIL:', '')
        else:
            user.display_email = user.email
        inactive_users.append(user)
    rejected_users = User.objects.filter(username__startswith='rejected_user_').order_by('-date_joined')
    deleted_users_queryset = User.objects.filter(username__startswith='deleted_user_').order_by('-date_joined')
    deleted_paginator = Paginator(deleted_users_queryset, 5)
    deleted_users = deleted_paginator.get_page(request.GET.get('page', 1))
    return render(request, 'user_management.html', {
        'pending_users': pending_users,
        'active_users': active_users,
        'inactive_users': inactive_users,
        'rejected_users': rejected_users,
        'deleted_users': deleted_users,
    })

# approve_user
@login_required
@require_http_methods(["POST"])
def approve_user(request, user_id):
    if not request.user.is_superuser:
        return JsonResponse({'success': False, 'message': 'Permission denied'})
    try:
        user = User.objects.get(id=user_id, is_active=False)
        username = user.username
        user_email = user.email
        user.is_active = True
        user.save()
        from django.core.mail import send_mail
        from django.conf import settings
        try:
            send_mail(
                subject='Account Approved - Real\'s Food Products',
                message=f'Hello {username},\n\nYour account has been approved. You can now log in.\n\nReal\'s Food Products Team',
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[user_email],
                fail_silently=True,
            )
        except Exception:
            pass
        return JsonResponse({'success': True, 'message': f'User {username} approved successfully'})
    except User.DoesNotExist:
        return JsonResponse({'success': False, 'message': 'User not found or already active'})
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)})

# reject_user
@login_required
@require_http_methods(["POST"])
def reject_user(request, user_id):
    if not request.user.is_superuser:
        return JsonResponse({'success': False, 'message': 'Permission denied'})
    try:
        from datetime import datetime
        user = User.objects.get(id=user_id, is_active=False)
        username = user.username
        user_email = user.email
        from django.core.mail import send_mail
        from django.conf import settings
        try:
            send_mail(
                subject='Account Registration Rejected - Real\'s Food Products',
                message=f'Hello {username},\n\nYour registration request has been rejected.\n\nReal\'s Food Products Team',
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[user_email],
                fail_silently=True,
            )
        except Exception:
            pass
        timestamp = timezone.now().strftime('%Y%m%d%H%M%S')
        user.email = f"rejected_{user.id}_{timestamp}@deleted.local"
        user.username = f"rejected_user_{user.id}_{timestamp}"
        user.first_name = "Rejected"
        user.last_name = "User"
        user.set_unusable_password()
        user.is_active = False
        user.save()
        return JsonResponse({'success': True, 'message': f'User {username} rejected successfully'})
    except User.DoesNotExist:
        return JsonResponse({'success': False, 'message': 'User not found or already active'})
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)})

# send_role_change_email_async
def send_role_change_email_async(username, email, new_role):
    from django.core.mail import send_mail
    from django.conf import settings
    try:
        send_mail(
            subject=f'Role Change: {new_role} - Real\'s Food Products',
            message=f'Hello {username},\n\nYour role has been changed to {new_role}. Please log out and log back in.\n\nReal\'s Food Products Team',
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[email],
            fail_silently=True,
        )
    except Exception as e:
        pass

# toggle_user_role
@login_required
@require_http_methods(["POST"])
def toggle_user_role(request, user_id):
    if not request.user.is_superuser:
        return JsonResponse({'success': False, 'message': 'Permission denied'})
    try:
        user = User.objects.get(id=user_id)
        if user.id == request.user.id:
            return JsonResponse({'success': False, 'message': 'Cannot modify your own role'})
        if user.is_superuser:
            user.is_superuser = False
            new_role = 'Staff'
        else:
            user.is_superuser = True
            new_role = 'Administrator'
        user.save()
        email_thread = threading.Thread(target=send_role_change_email_async, args=(user.username, user.email, new_role))
        email_thread.daemon = True
        email_thread.start()
        return JsonResponse({'success': True, 'message': f'User {user.username} is now a {new_role}.', 'new_role': new_role})
    except User.DoesNotExist:
        return JsonResponse({'success': False, 'message': 'User not found'})
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)})

# create_admin_user
@login_required
@require_http_methods(["POST"])
def create_admin_user(request):
    """Admin-only: Create a new user account (Staff or Administrator) without approval"""
    if not request.user.is_superuser:
        return JsonResponse({'success': False, 'message': 'Permission denied'})
    
    try:
        username = request.POST.get('username', '').strip()
        first_name = request.POST.get('first_name', '').strip()
        last_name = request.POST.get('last_name', '').strip()
        email = request.POST.get('email', '').strip()
        password1 = request.POST.get('password1', '')
        password2 = request.POST.get('password2', '')
        user_type = request.POST.get('user_type', 'staff')
        
        # Validation
        if not all([username, first_name, last_name, email, password1, password2]):
            return JsonResponse({'success': False, 'message': 'All fields are required'})
        
        if password1 != password2:
            return JsonResponse({'success': False, 'message': 'Passwords do not match'})
        
        from django.contrib.auth.password_validation import validate_password
        from django.core.exceptions import ValidationError as DjangoValidationError
        try:
            validate_password(password1)
        except DjangoValidationError as e:
            return JsonResponse({'success': False, 'message': ' '.join(e.messages)})
        
        if User.objects.filter(username=username).exists():
            return JsonResponse({'success': False, 'message': f'Username "{username}" already exists'})
        
        if User.objects.filter(email=email).exists():
            return JsonResponse({'success': False, 'message': f'Email "{email}" is already in use'})
        
        # Check if email belongs to a deactivated user
        deactivated_user = User.objects.filter(
            last_name=f"ORIGINAL_EMAIL:{email}",
            username__startswith='inactive_user_'
        ).first()
        
        if deactivated_user:
            return JsonResponse({'success': False, 'message': f'Email "{email}" belongs to a deactivated account. Please reactivate it or use a different email.'})
        
        # Set role
        is_superuser = (user_type == 'superuser')
        role_name = 'Administrator' if is_superuser else 'Staff'

        # Create user with hashed password in a single save
        user = User.objects.create_user(
            username=username,
            first_name=first_name,
            last_name=last_name,
            email=email,
            password=password1,
            is_active=True,
            is_staff=True,
            is_superuser=is_superuser,
        )
        
        return JsonResponse({
            'success': True,
            'message': f'{role_name} account "{username}" created successfully and is immediately active.'
        })

    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)})

# send_deactivation_email_async
def send_deactivation_email_async(username, email):
    from django.core.mail import send_mail
    from django.conf import settings
    try:
        send_mail(
            subject='Account Deactivated - Real\'s Food Products',
            message=f'Hello {username},\n\nYour account has been deactivated.\n\nReal\'s Food Products Team',
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[email],
            fail_silently=True,
        )
    except Exception as e:
        pass

# send_reactivation_email_async
def send_reactivation_email_async(username, email):
    from django.core.mail import send_mail
    from django.conf import settings
    try:
        send_mail(
            subject='Account Reactivated - Real\'s Food Products',
            message=f'Hello {username},\n\nYour account has been reactivated. You can now log in.\n\nReal\'s Food Products Team',
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[email],
            fail_silently=True,
        )
    except Exception as e:
        pass

# deactivate_user
@login_required
@require_http_methods(["POST"])
def deactivate_user(request, user_id):
    if not request.user.is_superuser:
        return JsonResponse({'success': False, 'message': 'Permission denied'})
    try:
        from datetime import datetime
        user = User.objects.get(id=user_id, is_active=True)
        if user.id == request.user.id:
            return JsonResponse({'success': False, 'message': 'Cannot deactivate your own account'})
        username = user.username
        email = user.email
        timestamp = timezone.now().strftime('%Y%m%d%H%M%S')
        user.is_active = False
        user.first_name = f"ORIGINAL_USERNAME:{username}"
        user.last_name = f"ORIGINAL_EMAIL:{email}"
        user.email = f"inactive_{user.id}_{timestamp}@inactive.local"
        user.username = f"inactive_user_{user.id}_{timestamp}"
        user.save()
        t = threading.Thread(target=send_deactivation_email_async, args=(username, email))
        t.daemon = True
        t.start()
        return JsonResponse({'success': True, 'message': f'User {username} deactivated successfully'})
    except User.DoesNotExist:
        return JsonResponse({'success': False, 'message': 'User not found or already inactive'})
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)})

# reactivate_user
@login_required
@require_http_methods(["POST"])
def reactivate_user(request, user_id):
    if not request.user.is_superuser:
        return JsonResponse({'success': False, 'message': 'Permission denied'})
    try:
        user = User.objects.get(id=user_id)
        original_username = None
        original_email = None
        if user.first_name and 'ORIGINAL_USERNAME:' in user.first_name:
            original_username = user.first_name.replace('ORIGINAL_USERNAME:', '').split('|')[0]
        if user.last_name and 'ORIGINAL_EMAIL:' in user.last_name:
            original_email = user.last_name.replace('ORIGINAL_EMAIL:', '').split('|')[0]
        if original_username:
            user.username = original_username
        if original_email:
            user.email = original_email
        user.first_name = ''
        user.last_name = ''
        user.is_active = True
        user.save()
        if original_email:
            t = threading.Thread(target=send_reactivation_email_async, args=(original_username or user.username, original_email))
            t.daemon = True
            t.start()
        return JsonResponse({'success': True, 'message': 'User reactivated successfully'})
    except User.DoesNotExist:
        return JsonResponse({'success': False, 'message': 'User not found'})
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)})

# delete_user
@login_required
@require_http_methods(["POST"])
def delete_user(request, user_id):
    if not request.user.is_superuser:
        return JsonResponse({'success': False, 'message': 'Permission denied'})
    try:
        from datetime import datetime
        user = User.objects.get(id=user_id)
        if user.id == request.user.id:
            return JsonResponse({'success': False, 'message': 'Cannot delete your own account'})
        username = user.username
        timestamp = timezone.now().strftime('%Y%m%d%H%M%S')
        user.is_active = False
        user.email = f"deleted_{user.id}_{timestamp}@deleted.local"
        user.username = f"deleted_user_{user.id}_{timestamp}"
        user.first_name = "Deleted"
        user.last_name = "User"
        user.set_unusable_password()
        user.save()
        return JsonResponse({'success': True, 'message': f'User {username} deleted successfully'})
    except User.DoesNotExist:
        return JsonResponse({'success': False, 'message': 'User not found'})
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)})

# edit_profile
@login_required
def edit_profile(request):
    if request.method == 'POST':
        first_name = request.POST.get('first_name', '').strip()
        last_name = request.POST.get('last_name', '').strip()
        email = request.POST.get('email', '').strip()
        user = request.user
        if email and email != user.email:
            if User.objects.filter(email=email).exclude(id=user.id).exists():
                messages.error(request, 'This email is already in use.')
                return redirect('edit-profile')
            user.email = email
        if first_name:
            user.first_name = first_name
        if last_name:
            user.last_name = last_name
        user.save()
        messages.success(request, 'Profile updated successfully.')
        return redirect('profile')
    form = UserEditForm(initial={
        'username': request.user.username,
        'first_name': request.user.first_name,
        'last_name': request.user.last_name,
        'email': request.user.email,
    })
    return render(request, 'editprofile.html', {'form': form, 'active_tab': 'account-general'})

# UserActivityList
class UserActivityList(LoginRequiredMixin, ListView):
    template_name = 'user_activity_list.html'
    context_object_name = 'users'
    paginate_by = 20

    def get(self, request, *args, **kwargs):
        if not request.user.is_superuser:
            messages.error(request, "You don't have permission to access this page.")
            return redirect('home')
        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        from realsproj.models import UserActivity
        from django.db.models import Q
        qs = User.objects.prefetch_related('useractivity').filter(is_active=True).order_by('-last_login')
        q = self.request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(Q(username__icontains=q) | Q(email__icontains=q))
        status = self.request.GET.get('status', '')
        if status == 'active':
            from django.utils import timezone
            from datetime import timedelta
            cutoff = timezone.now() - timedelta(minutes=5)
            ids = UserActivity.objects.filter(active=True, last_activity__gte=cutoff).values_list('user_id', flat=True)
            qs = qs.filter(id__in=ids)
        elif status == 'inactive':
            from django.utils import timezone
            from datetime import timedelta
            cutoff = timezone.now() - timedelta(minutes=5)
            ids = UserActivity.objects.filter(active=True).exclude(last_activity__gte=cutoff).values_list('user_id', flat=True)
            qs = qs.filter(id__in=ids)
        elif status == 'logged_out':
            ids = UserActivity.objects.filter(active=False).values_list('user_id', flat=True)
            qs = qs.filter(id__in=ids)
        return qs

# check_account_status
@login_required
def check_account_status(request):
    if not request.user.is_authenticated:
        return JsonResponse({'is_active': False, 'deactivated': True})
    if not request.user.is_active:
        return JsonResponse({'is_active': False, 'deactivated': True})
    deactivated_flag = request.session.get('account_deactivated', False)
    return JsonResponse({
        'is_active': True,
        'deactivated': deactivated_flag,
        'is_superuser': request.user.is_superuser,
    })

# clear_deactivation_flag
@require_http_methods(["POST"])
def clear_deactivation_flag(request):
    request.session.pop('account_deactivated', None)
    return JsonResponse({'success': True})

# setup_2fa
@login_required
def setup_2fa(request):
    from realsproj.models import User2FASettings
    if request.method == 'POST':
        action = request.POST.get('action', '')
        if action == 'enable':
            settings_obj, _ = User2FASettings.objects.get_or_create(user=request.user)
            settings_obj.is_enabled = True
            settings_obj.save()
            messages.success(request, 'Two-Factor Authentication has been enabled.')
        elif action == 'disable':
            try:
                settings_obj = User2FASettings.objects.get(user=request.user)
                settings_obj.is_enabled = False
                settings_obj.save()
                messages.success(request, 'Two-Factor Authentication has been disabled.')
            except User2FASettings.DoesNotExist:
                pass
        return redirect('profile')
    try:
        twofa_settings = User2FASettings.objects.get(user=request.user)
    except User2FASettings.DoesNotExist:
        twofa_settings = None
    return render(request, '2fa_setup.html', {
        'user_email': request.user.email,
        'twofa_settings': twofa_settings,
    })

# send_login_notification
def send_login_notification(user, device_info, ip_address, is_new_device=False):
    """Send email notification about login"""
    from django.core.mail import send_mail
    from django.conf import settings
    from django.utils import timezone

    if is_new_device:
        subject = 'New Device Verified - Real\'s Food Products'
        message = (
            f'Hello {user.username},\n\n'
            f'A new device has been verified for your account.\n\n'
            f'Device: {device_info["device_name"]}\n'
            f'IP Address: {ip_address}\n'
            f'Time: {timezone.now().strftime("%B %d, %Y at %I:%M %p")}\n\n'
            f'This device is now trusted.\n\n'
            f'Real\'s Food Products Security Team'
        )
    else:
        subject = 'Login Notification - Real\'s Food Products'
        message = (
            f'Hello {user.username},\n\n'
            f'You recently logged in to your account.\n\n'
            f'Device: {device_info["device_name"]}\n'
            f'IP Address: {ip_address}\n'
            f'Time: {timezone.now().strftime("%B %d, %Y at %I:%M %p")}\n\n'
            f'This login was from a trusted device.\n\n'
            f'Real\'s Food Products Security Team'
        )
    try:
        send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            fail_silently=True,
        )
    except Exception as e:
        pass

# disable_2fa
@login_required
def disable_2fa(request):
    """Disable 2FA for the current user"""
    from realsproj.models import User2FASettings
    
    if request.method == 'POST':
        password = request.POST.get('password', '')
        
        # Verify password before disabling
        if not request.user.check_password(password):
            messages.error(request, "❌ Incorrect password. Cannot disable 2FA.")
            return redirect('profile')
        
        try:
            twofa_settings = User2FASettings.objects.get(user=request.user)
            twofa_settings.is_enabled = False
            twofa_settings.save()
            messages.success(request, "✅ Two-Factor Authentication has been disabled.")
        except User2FASettings.DoesNotExist:
            messages.info(request, "2FA was not enabled.")
        
        return redirect('profile')
    
    return redirect('profile')

# delete_account
@login_required
def delete_account(request):
    """Soft delete user account - deactivates instead of deleting to preserve database integrity"""
    from django.contrib.auth import logout
    from realsproj.models import User2FASettings, UserOTP, TrustedDevice
    
    if request.method == 'POST':
        password = request.POST.get('password', '')
        confirm_text = request.POST.get('confirm_text', '')
        
        # Verify password
        if not request.user.check_password(password):
            messages.error(request, "❌ Incorrect password. Account deletion cancelled.")
            return redirect('delete-account')
        
        # Verify confirmation text
        if confirm_text != 'DELETE':
            messages.error(request, "❌ Please type 'DELETE' to confirm account deletion.")
            return redirect('delete-account')

        try:
            user = request.user
            
            # Generate unique timestamp-based identifier
            from datetime import datetime
            timestamp = timezone.now().strftime('%Y%m%d%H%M%S')
            
            # Soft delete: Deactivate account and anonymize email/username to prevent conflicts
            user.is_active = False
            user.email = f"deleted_{user.id}_{timestamp}@deleted.local"
            user.username = f"deleted_user_{user.id}_{timestamp}"
            user.first_name = "Deleted"
            user.last_name = "User"
            user.set_unusable_password()
            user.save()
            
            # Clean up 2FA and security data
            User2FASettings.objects.filter(user=user).delete()
            UserOTP.objects.filter(user=user).delete()
            TrustedDevice.objects.filter(user=user).delete()
            
            # Log the user out
            logout(request)
            
            messages.success(request, "✅ Your account has been successfully deactivated. All your data has been preserved for record-keeping purposes.")
            return redirect('home')
            
        except Exception as e:
            messages.error(request, f"❌ An error occurred while deleting your account: {str(e)}")
            return redirect('delete-account')
    
    # GET request - show confirmation page
    return render(request, 'delete_account_confirm.html')

# direct_password_reset
@login_required
def direct_password_reset(request):
    """Direct password reset for logged-in users who forgot their current password"""
    if request.method == 'POST':
        new_password = request.POST.get('new_password1', '').strip()
        confirm_password = request.POST.get('new_password2', '').strip()
        
        # Validate passwords match
        if new_password != confirm_password:
            messages.error(request, "Passwords do not match.")
            return render(request, 'direct_password_reset.html')
        
        # Validate password requirements
        try:
            validate_password(new_password, user=request.user)
        except ValidationError as e:
            for msg in e.messages:
                messages.error(request, msg)
            return render(request, 'direct_password_reset.html')
        
        # Set new password
        request.user.set_password(new_password)
        request.user.save()
        update_session_auth_hash(request, request.user)
        
        # Send email notification
        from django.core.mail import send_mail
        from django.conf import settings
        from django.utils import timezone
        
        try:
            send_mail(
                subject='🔐 Password Reset Successfully - Real\'s Food Products',
                message=f'''Hello {request.user.username},

Your password has been reset successfully.

Reset Details:
- Date & Time: {timezone.now().strftime('%B %d, %Y at %I:%M %p')}
- Account: {request.user.email}

If you did not make this change, please contact our support team immediately.

For security reasons, we recommend:
✓ Using a strong, unique password
✓ Enabling two-factor authentication
✓ Never sharing your password with anyone

Thank you,
Real's Food Products Team''',
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[request.user.email],
                fail_silently=True,
            )
        except Exception:
            pass
        
        messages.success(request, "✅ Your password has been reset successfully!")
        return redirect('profile')
    
    return render(request, 'direct_password_reset.html')

# verify_current_password
@login_required
@require_http_methods(["POST"])
def verify_current_password(request):
    MAX_ATTEMPTS = 5
    SESSION_KEY = 'pw_verify_attempts'

    attempts = request.session.get(SESSION_KEY, 0)

    if attempts >= MAX_ATTEMPTS:
        return JsonResponse({'valid': False, 'locked': True, 'attempts': attempts})

    password = request.POST.get('password', '')
    if request.user.check_password(password):
        request.session[SESSION_KEY] = 0
        return JsonResponse({'valid': True, 'locked': False, 'attempts': 0})

    attempts += 1
    request.session[SESSION_KEY] = attempts
    remaining = MAX_ATTEMPTS - attempts
    return JsonResponse({'valid': False, 'locked': attempts >= MAX_ATTEMPTS, 'attempts': attempts, 'remaining': remaining})

# privacy_policy
def privacy_policy(request):
    return render(request, 'privacy_policy.html')

# terms_of_use
def terms_of_use(request):
    """Display the terms of use page"""
    return render(request, 'terms_of_use.html')
