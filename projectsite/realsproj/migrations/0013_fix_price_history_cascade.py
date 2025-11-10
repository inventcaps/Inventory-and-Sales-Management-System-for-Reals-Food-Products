# Generated manually to fix foreign key constraint

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('realsproj', '0012_add_withdrawals_price_fields'),
    ]

    operations = [
        migrations.RunSQL(
            # Drop the existing foreign key constraint
            sql="""
                ALTER TABLE price_history 
                DROP CONSTRAINT IF EXISTS price_history_product_id_fkey;
            """,
            reverse_sql="""
                ALTER TABLE price_history 
                ADD CONSTRAINT price_history_product_id_fkey 
                FOREIGN KEY (product_id) REFERENCES products(id);
            """
        ),
        migrations.RunSQL(
            # Add the foreign key constraint with CASCADE delete
            sql="""
                ALTER TABLE price_history 
                ADD CONSTRAINT price_history_product_id_fkey 
                FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE;
            """,
            reverse_sql="""
                ALTER TABLE price_history 
                DROP CONSTRAINT IF EXISTS price_history_product_id_fkey;
            """
        ),
    ]
