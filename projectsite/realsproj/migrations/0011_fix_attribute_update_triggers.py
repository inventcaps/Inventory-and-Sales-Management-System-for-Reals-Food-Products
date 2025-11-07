from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('realsproj', '0010_fix_attribute_delete_triggers'),
    ]

    operations = [
        # Fix unit_prices update trigger
        migrations.RunSQL(
            sql="""
            CREATE OR REPLACE FUNCTION log_unit_prices_update()
            RETURNS TRIGGER AS $$
            DECLARE
                log_type_id_var INT;
            BEGIN
                -- Get the log type for 'Unit Price Updated'
                SELECT id INTO log_type_id_var
                FROM history_log_types
                WHERE category = 'Unit Price Updated'
                LIMIT 1;
                
                -- Insert into history_log with entity_type
                INSERT INTO history_log (
                    admin_id,
                    log_type_id,
                    log_date,
                    entity_type,
                    entity_id,
                    details,
                    is_archived
                )
                VALUES (
                    NEW.created_by_admin_id,
                    log_type_id_var,
                    NOW(),
                    'unit_price',
                    NEW.id,
                    jsonb_build_object(
                        'before', jsonb_build_object('unit_price', OLD.unit_price),
                        'after', jsonb_build_object('unit_price', NEW.unit_price)
                    ),
                    false
                );
                
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql SECURITY DEFINER SET search_path TO 'public', 'pg_temp';
            """,
            reverse_sql="SELECT 1;"
        ),
        
        # Fix srp_prices update trigger
        migrations.RunSQL(
            sql="""
            CREATE OR REPLACE FUNCTION log_srp_prices_update()
            RETURNS TRIGGER AS $$
            DECLARE
                log_type_id_var INT;
            BEGIN
                -- Get the log type for 'SRP Price Updated'
                SELECT id INTO log_type_id_var
                FROM history_log_types
                WHERE category = 'SRP Price Updated'
                LIMIT 1;
                
                -- Insert into history_log with entity_type
                INSERT INTO history_log (
                    admin_id,
                    log_type_id,
                    log_date,
                    entity_type,
                    entity_id,
                    details,
                    is_archived
                )
                VALUES (
                    NEW.created_by_admin_id,
                    log_type_id_var,
                    NOW(),
                    'srp_price',
                    NEW.id,
                    jsonb_build_object(
                        'before', jsonb_build_object('srp_price', OLD.srp_price),
                        'after', jsonb_build_object('srp_price', NEW.srp_price)
                    ),
                    false
                );
                
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql SECURITY DEFINER SET search_path TO 'public', 'pg_temp';
            """,
            reverse_sql="SELECT 1;"
        ),
    ]
