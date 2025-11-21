# Generated manually to update withdrawal reason constraint

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('realsproj', '0013_disable_duplicate_update_triggers'),
        ('realsproj', '0013_fix_price_history_cascade'),
    ]

    operations = [
        migrations.RunSQL(
            # First, alter the column length to accommodate longer reason values
            sql="""
                ALTER TABLE withdrawals 
                ALTER COLUMN reason TYPE character varying(30);
            """,
            reverse_sql="""
                ALTER TABLE withdrawals 
                ALTER COLUMN reason TYPE character varying(20);
            """
        ),
        migrations.RunSQL(
            # Drop old constraint and add new one with updated values
            sql="""
                -- Drop the old constraint
                ALTER TABLE withdrawals 
                DROP CONSTRAINT IF EXISTS withdrawals_reason_check;
                
                -- Add new constraint with REPLACEMENT_FOR_RETURNED instead of RETURNED and REPLACEMENT
                ALTER TABLE withdrawals 
                ADD CONSTRAINT withdrawals_reason_check 
                CHECK (
                    reason::text = ANY (ARRAY[
                        'SOLD'::character varying::text,
                        'EXPIRED'::character varying::text,
                        'DAMAGED'::character varying::text,
                        'REPLACEMENT_FOR_RETURNED'::character varying::text,
                        'OTHERS'::character varying::text
                    ])
                );
            """,
            reverse_sql="""
                -- Revert back to old constraint
                ALTER TABLE withdrawals 
                DROP CONSTRAINT IF EXISTS withdrawals_reason_check;
                
                ALTER TABLE withdrawals 
                ADD CONSTRAINT withdrawals_reason_check 
                CHECK (
                    reason::text = ANY (ARRAY[
                        'SOLD'::character varying::text,
                        'EXPIRED'::character varying::text,
                        'DAMAGED'::character varying::text,
                        'RETURNED'::character varying::text,
                        'REPLACEMENT'::character varying::text,
                        'OTHERS'::character varying::text
                    ])
                );
            """
        ),
        migrations.RunSQL(
            # Update existing RETURNED and REPLACEMENT records to REPLACEMENT_FOR_RETURNED
            sql="""
                UPDATE withdrawals 
                SET reason = 'REPLACEMENT_FOR_RETURNED' 
                WHERE reason IN ('RETURNED', 'REPLACEMENT');
            """,
            reverse_sql=migrations.RunSQL.noop
        ),
    ]
