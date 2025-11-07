"""
URL configuration for projectsite project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path
from realsproj import views as a
from django.contrib.auth import views as auth_views
from django.urls import path, re_path, include
from django.contrib.auth.forms import AuthenticationForm
from django.conf import settings
from django.conf.urls.static import static





urlpatterns = [
    path("admin/", admin.site.urls),
    path('', a.HomePageView.as_view(), name='home'),
    re_path(r'^logout/$', auth_views.LogoutView.as_view(), name='logout'),

    path('products/', a.ProductsList.as_view(), name='products'),
    path('products/add', a.ProductCreateView.as_view(), name='product-add'),
    path('products/<pk>', a.ProductsUpdateView.as_view(), name='product-edit'),
    path('products/<pk>/delete', a.ProductsDeleteView.as_view(), name='product-delete'),
    path("products/scan-phone/", a.product_scan_phone, name="product-scan-phone"),
    path("api/check-barcode/", a.check_barcode_availability, name="check-barcode"),

    path('rawmaterials/', a.RawMaterialsList.as_view(), name='rawmaterials-list'),
    path('rawmaterials/', a.RawMaterialsList.as_view(), name='rawmaterials'),
    path('rawmaterials/add', a.RawMaterialsCreateView.as_view(), name='rawmaterials-add'),
    path('rawmaterials/<pk>', a.RawMaterialsUpdateView.as_view(), name='rawmaterials-edit'),
    path('rawmaterials/<pk>/delete', a.RawMaterialsDeleteView.as_view(), name='rawmaterials-delete'),
    path('rawmaterials/<int:pk>/archive/', a.RawMaterialArchiveView.as_view(), name='rawmaterials-archive'),
    path('rawmaterials/archive-old/', a.RawMaterialArchiveOldView.as_view(), name='rawmaterials-archive-old'),
    path('rawmaterials/archived/', a.ArchivedRawMaterialsListView.as_view(), name='rawmaterials-archived-list'),
    path('rawmaterials/<int:pk>/unarchive/', a.RawMaterialUnarchiveView.as_view(), name='rawmaterials-unarchive'),
    path('rawmaterials/bulk-delete/', a.rawmaterial_bulk_delete, name='rawmaterial-bulk-delete'),
    path('rawmaterials/bulk-archive/', a.rawmaterial_bulk_archive, name='rawmaterial-bulk-archive'),
    path('rawmaterials/bulk-restore/', a.rawmaterial_bulk_restore, name='rawmaterials-bulk-restore'),

    path('historylog/', a.HistoryLogList.as_view(), name='historylog'),
    path('history/', a.HistoryLogList.as_view(), name='history_log'),  

    path('salesexpenses/', a.SalesExpensesList.as_view(), name='salesexpenses'),
    path('sales/add', a.SalesCreateView.as_view(), name='sales-add'),
    path('sales/expenses/add', a.SalesExpensesCreateView.as_view(), name='sales-expenses-add'),
    path('sales/<pk>', a.SalesUpdateView.as_view(), name='sales-edit'),
    path('sales/<pk>/delete', a.SalesDeleteView.as_view(), name='sales-delete'),
    path('sales/<int:pk>/archive/', a.SaleArchiveView.as_view(), name='sales-archive'),
    path('sales/archive-old/', a.SaleArchiveOldView.as_view(), name='sales-archive-old'),
    path('sales/bulk-delete-new/', a.sales_bulk_delete, name='sales-bulk-delete-new'),
    path('sales/bulk-archive/', a.sales_bulk_archive, name='sales-bulk-archive'),
    path('sales/archived/', a.ArchivedSalesListView.as_view(), name='sales-archived-list'),
    path('sales/<int:pk>/unarchive/', a.SaleUnarchiveView.as_view(), name='sales-unarchive'),
    path('sales/bulk-restore/', a.SaleBulkRestoreView.as_view(), name='sales-bulk-restore'),
    path('sales/bulk-delete/', a.SaleBulkDeleteView.as_view(), name='sales-bulk-delete'),
    path('salesexpenses/archive/', a.ArchivedSalesExpensesCombinedView.as_view(), name='salesexpense-archive'),

    path('expenses/add', a.ExpensesCreateView.as_view(), name='expenses-add'),
    path('expenses/<pk>', a.ExpensesUpdateView.as_view(), name='expenses-edit'),
    path('expenses/<pk>/delete', a.ExpensesDeleteView.as_view(), name='expenses-delete'),
    path('expenses/<int:pk>/archive/', a.ExpenseArchiveView.as_view(), name='expenses-archive'),
    path('expenses/archive-old/', a.ExpenseArchiveOldView.as_view(), name='expenses-archive-old'),
    path('expenses/archived/', a.ArchivedExpensesListView.as_view(), name='expenses-archived-list'),
    path('expenses/<int:pk>/unarchive/', a.ExpenseUnarchiveView.as_view(), name='expenses-unarchive'),
    path('expenses/bulk-delete/', a.expenses_bulk_delete, name='expenses-bulk-delete'),
    path('expenses/bulk-archive/', a.expenses_bulk_archive, name='expenses-bulk-archive'),

    path('prodbatch/', a.ProductBatchList.as_view(), name='product-batch'),
    path('prodbatch/add', a.BulkProductBatchCreateView.as_view(), name='product-batch-add'),
    path('prodbatch/<pk>', a.ProductBatchUpdateView.as_view(), name='product-batch-edit'),
    path('prodbatch/<pk>/delete', a.ProductBatchDeleteView.as_view(), name='product-batch-delete'),
    path('prodbatch/<int:pk>/archive/', a.ProductBatchArchiveView.as_view(), name='product-batch-archive'),
    path('prodbatch/archived/', a.ArchivedProductBatchListView.as_view(), name='product-batch-archived-list'),
    path('prodbatch/<int:pk>/unarchive/', a.ProductBatchUnarchiveView.as_view(), name='product-batch-unarchive'),
    path('prodbatch/archive-old/', a.ProductBatchArchiveOldView.as_view(), name='product-batch-archive-old'),
    path('prodbatch/bulk-delete/', a.product_batch_bulk_delete, name='product-batch-bulk-delete'),
    path('prodbatch/bulk-archive/', a.product_batch_bulk_archive, name='product-batch-bulk-archive'),
    path('prodbatch/bulk-restore/', a.product_batch_bulk_restore, name='product-batch-bulk-restore'),
    path('prodbatch/', a.ProductBatchList.as_view(), name='product-batch-list'),

    path('product-inventory/', a.ProductInventoryList.as_view(), name='product-inventory'),
    path('best-seller-products/', a.BestSellerProductsView.as_view(), name='best-seller-products'),

    path('rawmatbatch/', a.RawMaterialBatchList.as_view(), name='rawmaterial-batch'),
    path('rawmatbatch/add', a.BulkRawMaterialBatchCreateView.as_view(), name='rawmaterial-batch-add'),
    path('rawmatbatch/<pk>', a.RawMaterialBatchUpdateView.as_view(), name='rawmaterial-batch-edit'),
    path('rawmatbatch/<pk>/delete', a.RawMaterialBatchDeleteView.as_view(), name='rawmaterial-batch-delete'),
    path('rawmatbatch/<int:pk>/archive/', a.RawMaterialBatchArchiveView.as_view(), name='rawmaterial-batch-archive'),
    path('rawmatbatch/archived/', a.ArchivedRawMaterialBatchListView.as_view(), name='rawmaterial-batch-archived-list'),
    path('rawmatbatch/<int:pk>/unarchive/', a.RawMaterialBatchUnarchiveView.as_view(), name='rawmaterial-batch-unarchive'),
    path('rawmatbatch/archive-old/', a.RawMaterialBatchArchiveOldView.as_view(), name='rawmaterial-batch-archive-old'),
    path('rawmatbatch/bulk-delete/', a.rawmaterial_batch_bulk_delete, name='rawmaterial-batch-bulk-delete'),
    path('rawmatbatch/bulk-archive/', a.rawmaterial_batch_bulk_archive, name='rawmaterial-batch-bulk-archive'),

    path('rawmaterial-inventory/', a.RawMaterialInventoryList.as_view(), name='rawmaterial-inventory'),

    path('producttypes/add', a.ProductTypeCreateView.as_view(), name='product-types-add'),
    path('productvariants/add', a.ProductVariantCreateView.as_view(), name='product-variants-add'),
    path('sizes/add', a.SizesCreateView.as_view(), name='sizes-add'),
    path('sizeunits/add', a.SizeUnitsCreateView.as_view(), name='size-units-add'),
    path('unirprices/add', a.UnitPricesCreateView.as_view(), name='unit-prices-add'),
    path('srpprices/add', a.SrpPricesCreateView.as_view(), name='srp-prices-add'),

    # Product Attributes Management
    path('product-attributes/', a.ProductAttributesView.as_view(), name='product-attributes'),
    
    # Product Type CRUD
    path('product-attributes/product-type/add/', a.ProductTypeAddView.as_view(), name='product-type-add'),
    path('product-attributes/product-type/<int:pk>/edit/', a.ProductTypeEditView.as_view(), name='product-type-edit'),
    path('product-attributes/product-type/<int:pk>/delete/', a.ProductTypeDeleteView.as_view(), name='product-type-delete'),
    
    # Product Variant CRUD
    path('product-attributes/product-variant/add/', a.ProductVariantAddView.as_view(), name='product-variant-add'),
    path('product-attributes/product-variant/<int:pk>/edit/', a.ProductVariantEditView.as_view(), name='product-variant-edit'),
    path('product-attributes/product-variant/<int:pk>/delete/', a.ProductVariantDeleteView.as_view(), name='product-variant-delete'),
    
    # Size CRUD
    path('product-attributes/size/add/', a.SizeAddView.as_view(), name='size-add'),
    path('product-attributes/size/<int:pk>/edit/', a.SizeEditView.as_view(), name='size-edit'),
    path('product-attributes/size/<int:pk>/delete/', a.SizeDeleteView.as_view(), name='size-delete'),
    
    # Size Unit CRUD
    path('product-attributes/size-unit/add/', a.SizeUnitAddView.as_view(), name='size-unit-add'),
    path('product-attributes/size-unit/<int:pk>/edit/', a.SizeUnitEditView.as_view(), name='size-unit-edit'),
    path('product-attributes/size-unit/<int:pk>/delete/', a.SizeUnitDeleteView.as_view(), name='size-unit-delete'),
    
    # Unit Price CRUD
    path('product-attributes/unit-price/add/', a.UnitPriceAddView.as_view(), name='unit-price-add'),
    path('product-attributes/unit-price/<int:pk>/edit/', a.UnitPriceEditView.as_view(), name='unit-price-edit'),
    path('product-attributes/unit-price/<int:pk>/delete/', a.UnitPriceDeleteView.as_view(), name='unit-price-delete'),
    
    # SRP Price CRUD
    path('product-attributes/srp-price/add/', a.SrpPriceAddView.as_view(), name='srp-price-add'),
    path('product-attributes/srp-price/<int:pk>/edit/', a.SrpPriceEditView.as_view(), name='srp-price-edit'),
    path('product-attributes/srp-price/<int:pk>/delete/', a.SrpPriceDeleteView.as_view(), name='srp-price-delete'),

    path('withdrawalsales/', a.WithdrawalSalesList.as_view(), name='withdrawalSales'),
    path('withdrawals/', a.WithdrawSuccessView.as_view(), name='withdrawals'),
    path('withdraw/<int:pk>/edit/', a.WithdrawUpdateView.as_view(), name='withdraw-edit'),
    path("withdraw-item/<pk>/delete", a.WithdrawDeleteView.as_view(), name="withdraw-delete"),
    path("withdraw-item/", a.WithdrawItemView.as_view(), name="withdraw-item"),
    path('withdrawals/<int:pk>/archive/', a.WithdrawalsArchiveView.as_view(), name='withdrawals-archive'),
    path('withdrawals/archived/', a.ArchivedWithdrawalsListView.as_view(), name='withdrawals-archived-list'),
    path('withdrawals/<int:pk>/unarchive/', a.WithdrawalsUnarchiveView.as_view(), name='withdrawals-unarchive'),
    path('withdrawals/archive-old/', a.WithdrawalsArchiveOldView.as_view(), name='withdrawals-archive-old'),
    path('withdrawal-order/<int:order_group_id>/', a.WithdrawalOrderDetailView.as_view(), name='withdrawal-order-detail'),
    path('withdrawal-order/<int:order_group_id>/update-payment/', a.WithdrawalOrderUpdatePaymentView.as_view(), name='withdrawal-order-update-payment'),
    path('withdrawal-group/<int:order_group_id>/', a.WithdrawalOrderDetailView.as_view(), name='withdrawal-group-detail'),
    path('withdrawal-group/<int:order_group_id>/edit/', a.WithdrawalGroupEditView.as_view(), name='withdrawal-group-edit'),
    path('withdrawal-group/<int:order_group_id>/archive/', a.WithdrawalGroupArchiveView.as_view(), name='withdrawal-group-archive'),
    path('withdrawal-group/<int:order_group_id>/delete/', a.WithdrawalGroupDeleteView.as_view(), name='withdrawal-group-delete'),

    path('withdrawals/bulk-delete/', a.withdrawals_bulk_delete, name='withdrawals-bulk-delete'),
    path('withdrawals/bulk-archive/', a.withdrawals_bulk_archive, name='withdrawals-bulk-archive'),
    path("api/get-stock/", a.get_stock, name="get-stock"),

    path("login/", a.login_view, name="login"),

    path('password_reset/', 
         auth_views.PasswordResetView.as_view(template_name="password_reset.html"), 
         name='password_reset'),
    path('password_reset/done/', 
         auth_views.PasswordResetDoneView.as_view(), 
         name='password_reset_done'),
    path('reset/<uidb64>/<token>/', 
         auth_views.PasswordResetConfirmView.as_view(), 
         name='password_reset_confirm'),
    path('reset/done/', 
         auth_views.PasswordResetCompleteView.as_view(), 
         name='password_reset_complete'),
    
    path("api/sales-vs-expenses/", a.sales_vs_expenses, name="sales-vs-expenses"),

    path('notifications/', a.NotificationsList.as_view(), name='notifications'),
    path('notifications/<pk>/delete/', a.NotificationsDeleteView.as_view(), name='notification-delete'),

    path("register/", a.register, name="register"),

    path("api/revenue-change/", a.revenue_change_api, name="revenue-change"),

    path("api/best-sellers/", a.best_sellers_api, name="best_sellers_api"),

    path('notifications/<int:pk>/read/', a.mark_notification_read, name='notification_read'),

    path('stock-changes/', a.StockChangesList.as_view(), name='stock-changes'),
    path('stock-changes/<int:pk>/archive/', a.StockChangesArchiveView.as_view(), name='stock-changes-archive'),
    path('stock-changes/archived/', a.ArchivedStockChangesListView.as_view(), name='stock-changes-archived-list'),
    path('stock-changes/<int:pk>/unarchive/', a.StockChangesUnarchiveView.as_view(), name='stock-changes-unarchive'),
    path('stock-changes/archive-old/', a.StockChangesArchiveOldView.as_view(), name='stock-changes-archive-old'),

    path("revenue-x-recent_sales", a.HomePageView.as_view(), name="home"),
    path("product-inventory/", a.ProductInventoryList.as_view(), name="product_inventory_list"),    

    path('profile/', a.profile_view, name='profile'),
    path('profile/edit/', a.edit_profile, name='edit_profile'),

    # User Management
    path('user-management/', a.user_management, name='user-management'),
    path('user/create-admin/', a.create_admin_user, name='create-admin-user'),
    path('user/<int:user_id>/approve/', a.approve_user, name='approve-user'),
    path('user/<int:user_id>/reject/', a.reject_user, name='reject-user'),
    path('user/<int:user_id>/toggle-role/', a.toggle_user_role, name='toggle-user-role'),
    path('user/<int:user_id>/deactivate/', a.deactivate_user, name='deactivate-user'),
    path('user/<int:user_id>/reactivate/', a.reactivate_user, name='reactivate-user'),
    path('user/<int:user_id>/delete/', a.delete_user, name='delete-user'),

    path('products/', a.ProductsList.as_view(), name='product-list'),
    path('products/<int:pk>/archive/', a.ProductArchiveView.as_view(), name='product-archive'),
    path('products/archived/', a.ArchivedProductsListView.as_view(), name='products-archived-list'),
    path('products/<int:pk>/unarchive/', a.ProductUnarchiveView.as_view(), name='product-unarchive'),
    path('products/archive-old/', a.ProductArchiveOldView.as_view(), name='products-archive-old'),
    path('products/bulk-delete/', a.product_bulk_delete, name='product-bulk-delete'),
    path('products/bulk-archive/', a.product_bulk_archive, name='product-bulk-archive'),
    path('products/bulk-restore/', a.product_bulk_restore, name='products-bulk-restore'),
    path("products/<int:product_id>/recipes/", a.ProductRecipeListView.as_view(), name="recipe-list"),
    path("products/<int:product_id>/recipes/add/", a.ProductRecipeBulkCreateView.as_view(), name="recipe-add"),
    path("recipes/<int:pk>/edit/", a.ProductRecipeUpdateView.as_view(), name="recipe-edit"),
    path("recipes/<int:pk>/delete/", a.ProductRecipeDeleteView.as_view(), name="recipe-delete"),
    path("report/", a.monthly_report, name="monthly-report"),
    path("report/export/", a.monthly_report_export, name="monthly-report-export"),

    path('export-sales/', a.export_sales, name='export_sales'),
    path('export-expenses/', a.export_expenses, name='export_expenses'),
    
    path('financial-loss/', a.financial_loss, name='financial-loss'),
    path('financial-loss/export/', a.financial_loss_export, name='financial-loss-export'),

    path('user-activity/', a.UserActivityList.as_view(), name='user-activity'),

    path('database-backup/', a.database_backup, name='database-backup'),

    path('2fa-setup/', a.setup_2fa, name='2fa_setup'),
    path('2fa-disable/', a.disable_2fa, name='2fa_disable'),
    path('account/delete/', a.delete_account, name='delete_account'),

] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)