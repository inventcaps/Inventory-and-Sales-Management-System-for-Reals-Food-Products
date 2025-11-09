from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('realsproj', '0011_fix_attribute_update_triggers'),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
            -- Check and add columns only if they don't exist
            DO $$ 
            BEGIN
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                              WHERE table_name='withdrawals' AND column_name='actual_unit_price') THEN
                    ALTER TABLE withdrawals ADD COLUMN actual_unit_price NUMERIC(10, 2) NULL;
                END IF;
                
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                              WHERE table_name='withdrawals' AND column_name='actual_discount_percent') THEN
                    ALTER TABLE withdrawals ADD COLUMN actual_discount_percent NUMERIC(5, 2) NULL;
                END IF;
                
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                              WHERE table_name='withdrawals' AND column_name='actual_discount_amount') THEN
                    ALTER TABLE withdrawals ADD COLUMN actual_discount_amount NUMERIC(10, 2) NULL;
                END IF;
                
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                              WHERE table_name='withdrawals' AND column_name='final_price_per_unit') THEN
                    ALTER TABLE withdrawals ADD COLUMN final_price_per_unit NUMERIC(10, 2) NULL;
                END IF;
                
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                              WHERE table_name='withdrawals' AND column_name='total_amount') THEN
                    ALTER TABLE withdrawals ADD COLUMN total_amount NUMERIC(10, 2) NULL;
                END IF;
            END $$;
            
            COMMENT ON COLUMN withdrawals.actual_unit_price IS 'Base price (unit or SRP) at time of sale';
            COMMENT ON COLUMN withdrawals.actual_discount_percent IS 'Discount percentage applied';
            COMMENT ON COLUMN withdrawals.actual_discount_amount IS 'Discount amount applied';
            COMMENT ON COLUMN withdrawals.final_price_per_unit IS 'Final price per unit after discount';
            COMMENT ON COLUMN withdrawals.total_amount IS 'Total amount (quantity × final_price_per_unit)';
            """,
            reverse_sql="""
            ALTER TABLE withdrawals DROP COLUMN IF EXISTS actual_unit_price;
            ALTER TABLE withdrawals DROP COLUMN IF EXISTS actual_discount_percent;
            ALTER TABLE withdrawals DROP COLUMN IF EXISTS actual_discount_amount;
            ALTER TABLE withdrawals DROP COLUMN IF EXISTS final_price_per_unit;
            ALTER TABLE withdrawals DROP COLUMN IF EXISTS total_amount;
            """
        ),
    ]
