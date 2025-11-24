# Generated migration for adding receipt_number field to Withdrawals model

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('realsproj', '0016_auto_20251112_1606'),
    ]

    operations = [
        migrations.RunSQL(
            sql="ALTER TABLE withdrawals ADD COLUMN receipt_number VARCHAR(50) NULL UNIQUE;",
            reverse_sql="ALTER TABLE withdrawals DROP COLUMN IF EXISTS receipt_number;",
        ),
        migrations.RunSQL(
            sql="CREATE INDEX IF NOT EXISTS withdrawals_receipt_number_idx ON withdrawals(receipt_number);",
            reverse_sql="DROP INDEX IF EXISTS withdrawals_receipt_number_idx;",
        ),
    ]
