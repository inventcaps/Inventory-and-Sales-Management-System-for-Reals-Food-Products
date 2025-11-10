# Generated manually to fix duplicate history log entries

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('realsproj', '0012_add_withdrawals_price_fields'),
    ]

    operations = [
        # Drop products update trigger and function
        migrations.RunSQL(
            sql="""
            DROP TRIGGER IF EXISTS products_after_update ON products;
            DROP FUNCTION IF EXISTS log_products_update() CASCADE;
            """,
            reverse_sql="SELECT 1;"
        ),
        
        # Drop sales update trigger and function
        migrations.RunSQL(
            sql="""
            DROP TRIGGER IF EXISTS sales_after_update ON sales;
            DROP FUNCTION IF EXISTS log_sales_update() CASCADE;
            """,
            reverse_sql="SELECT 1;"
        ),
        
        # Drop expenses update trigger and function
        migrations.RunSQL(
            sql="""
            DROP TRIGGER IF EXISTS expenses_after_update ON expenses;
            DROP FUNCTION IF EXISTS log_expenses_update() CASCADE;
            """,
            reverse_sql="SELECT 1;"
        ),
    ]
