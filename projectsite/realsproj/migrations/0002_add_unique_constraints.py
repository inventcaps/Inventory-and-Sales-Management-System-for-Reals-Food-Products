from django.db import migrations


class Migration(migrations.Migration):
    atomic = False

    dependencies = [
        ("realsproj", "0001_initial"),
    ]

    operations = [
        migrations.RunSQL(
            "CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS idx_products_code_unique ON products (product_code) WHERE is_archived = FALSE;",
            "DROP INDEX IF EXISTS idx_products_code_unique;",
        ),
        migrations.RunSQL(
            "CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS idx_products_barcode_unique ON products (barcode) WHERE barcode IS NOT NULL AND is_archived = FALSE;",
            "DROP INDEX IF EXISTS idx_products_barcode_unique;",
        ),
        migrations.RunSQL(
            "CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS idx_withdrawals_receipt_unique ON withdrawals (receipt_number) WHERE receipt_number IS NOT NULL;",
            "DROP INDEX IF EXISTS idx_withdrawals_receipt_unique;",
        ),
        migrations.RunSQL(
            "ALTER TABLE withdrawals ADD CONSTRAINT IF NOT EXISTS withdrawals_receipt_number_key UNIQUE (receipt_number);",
            "ALTER TABLE withdrawals DROP CONSTRAINT IF EXISTS withdrawals_receipt_number_key;",
        ),
    ]
