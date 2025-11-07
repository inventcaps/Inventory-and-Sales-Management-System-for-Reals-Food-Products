from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('realsproj', '0009_merge_20251101_1012'),
    ]

    operations = [
        # Fix unit_prices delete trigger
        migrations.RunSQL(
            sql="""
            CREATE OR REPLACE FUNCTION log_unit_prices_delete()
            RETURNS TRIGGER AS $$
            BEGIN
                INSERT INTO history_log (admin_id, log_type_id, log_date, entity_type, entity_id, details)
                VALUES (
                    OLD.created_by_admin_id,
                    (SELECT id FROM history_log_types WHERE category = 'Unit Price Deleted' LIMIT 1),
                    NOW(),
                    'unit_price',
                    OLD.id,
                    jsonb_build_object('before', row_to_json(OLD))
                );
                RETURN OLD;
            END;
            $$ LANGUAGE plpgsql SECURITY DEFINER SET search_path TO 'public', 'pg_temp';
            """,
            reverse_sql="""
            CREATE OR REPLACE FUNCTION log_unit_prices_delete()
            RETURNS TRIGGER AS $$
            BEGIN
                INSERT INTO history_log (admin_id, log_type_id, log_date)
                VALUES (
                    OLD.created_by_admin_id,
                    (SELECT id FROM history_log_types WHERE category = 'Unit Price Deleted' LIMIT 1),
                    NOW()
                );
                RETURN OLD;
            END;
            $$ LANGUAGE plpgsql SECURITY DEFINER SET search_path TO 'public', 'pg_temp';
            """
        ),
        
        # Fix srp_prices delete trigger
        migrations.RunSQL(
            sql="""
            CREATE OR REPLACE FUNCTION log_srp_prices_delete()
            RETURNS TRIGGER AS $$
            BEGIN
                INSERT INTO history_log (admin_id, log_type_id, log_date, entity_type, entity_id, details)
                VALUES (
                    OLD.created_by_admin_id,
                    (SELECT id FROM history_log_types WHERE category = 'SRP Price Deleted' LIMIT 1),
                    NOW(),
                    'srp_price',
                    OLD.id,
                    jsonb_build_object('before', row_to_json(OLD))
                );
                RETURN OLD;
            END;
            $$ LANGUAGE plpgsql SECURITY DEFINER SET search_path TO 'public', 'pg_temp';
            """,
            reverse_sql="""
            CREATE OR REPLACE FUNCTION log_srp_prices_delete()
            RETURNS TRIGGER AS $$
            BEGIN
                INSERT INTO history_log (admin_id, log_type_id, log_date)
                VALUES (
                    OLD.created_by_admin_id,
                    (SELECT id FROM history_log_types WHERE category = 'SRP Price Deleted' LIMIT 1),
                    NOW()
                );
                RETURN OLD;
            END;
            $$ LANGUAGE plpgsql SECURITY DEFINER SET search_path TO 'public', 'pg_temp';
            """
        ),
        
        # Fix product_types delete trigger
        migrations.RunSQL(
            sql="""
            CREATE OR REPLACE FUNCTION log_product_types_delete()
            RETURNS TRIGGER AS $$
            BEGIN
                INSERT INTO history_log (admin_id, log_type_id, log_date, entity_type, entity_id, details)
                VALUES (
                    OLD.created_by_admin_id,
                    (SELECT id FROM history_log_types WHERE category = 'Product Type Deleted' LIMIT 1),
                    NOW(),
                    'product_type',
                    OLD.id,
                    jsonb_build_object('before', row_to_json(OLD))
                );
                RETURN OLD;
            END;
            $$ LANGUAGE plpgsql SECURITY DEFINER SET search_path TO 'public', 'pg_temp';
            """,
            reverse_sql="SELECT 1;"  # No reverse needed
        ),
        
        # Fix product_variants delete trigger
        migrations.RunSQL(
            sql="""
            CREATE OR REPLACE FUNCTION log_product_variants_delete()
            RETURNS TRIGGER AS $$
            BEGIN
                INSERT INTO history_log (admin_id, log_type_id, log_date, entity_type, entity_id, details)
                VALUES (
                    OLD.created_by_admin_id,
                    (SELECT id FROM history_log_types WHERE category = 'Product Variant Deleted' LIMIT 1),
                    NOW(),
                    'product_variant',
                    OLD.id,
                    jsonb_build_object('before', row_to_json(OLD))
                );
                RETURN OLD;
            END;
            $$ LANGUAGE plpgsql SECURITY DEFINER SET search_path TO 'public', 'pg_temp';
            """,
            reverse_sql="SELECT 1;"
        ),
        
        # Fix sizes delete trigger
        migrations.RunSQL(
            sql="""
            CREATE OR REPLACE FUNCTION log_sizes_delete()
            RETURNS TRIGGER AS $$
            BEGIN
                INSERT INTO history_log (admin_id, log_type_id, log_date, entity_type, entity_id, details)
                VALUES (
                    OLD.created_by_admin_id,
                    (SELECT id FROM history_log_types WHERE category = 'Size Deleted' LIMIT 1),
                    NOW(),
                    'size',
                    OLD.id,
                    jsonb_build_object('before', row_to_json(OLD))
                );
                RETURN OLD;
            END;
            $$ LANGUAGE plpgsql SECURITY DEFINER SET search_path TO 'public', 'pg_temp';
            """,
            reverse_sql="SELECT 1;"
        ),
        
        # Fix size_units delete trigger
        migrations.RunSQL(
            sql="""
            CREATE OR REPLACE FUNCTION log_size_units_delete()
            RETURNS TRIGGER AS $$
            BEGIN
                INSERT INTO history_log (admin_id, log_type_id, log_date, entity_type, entity_id, details)
                VALUES (
                    OLD.created_by_admin_id,
                    (SELECT id FROM history_log_types WHERE category = 'Size Unit Deleted' LIMIT 1),
                    NOW(),
                    'size_unit',
                    OLD.id,
                    jsonb_build_object('before', row_to_json(OLD))
                );
                RETURN OLD;
            END;
            $$ LANGUAGE plpgsql SECURITY DEFINER SET search_path TO 'public', 'pg_temp';
            """,
            reverse_sql="SELECT 1;"
        ),
    ]
