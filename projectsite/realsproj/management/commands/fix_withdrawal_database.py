from django.core.management.base import BaseCommand
from django.db import connection

class Command(BaseCommand):
    help = 'Fix withdrawal reason database issues step by step'

    def handle(self, *args, **options):
        try:
            with connection.cursor() as cursor:
              
                self.stdout.write('Step 1: Checking current data...')
                cursor.execute("SELECT DISTINCT reason FROM withdrawals;")
                reasons = cursor.fetchall()
                self.stdout.write(f'Current reasons in database: {[r[0] for r in reasons]}')
                
                self.stdout.write('Step 2: Dropping existing constraint...')
                cursor.execute("ALTER TABLE withdrawals DROP CONSTRAINT IF EXISTS withdrawals_reason_check;")
                
                self.stdout.write('Step 3: Updating column length...')
                cursor.execute("ALTER TABLE withdrawals ALTER COLUMN reason TYPE character varying(30);")
                
                self.stdout.write('Step 4: Updating old reason values...')
                cursor.execute("""
                    UPDATE withdrawals 
                    SET reason = 'REPLACEMENT_FOR_RETURNED' 
                    WHERE reason IN ('RETURNED', 'REPLACEMENT');
                """)
                updated_rows = cursor.rowcount
                self.stdout.write(f'Updated {updated_rows} rows with old reason values')
                
                self.stdout.write('Step 5: Checking for invalid reasons...')
                cursor.execute("""
                    SELECT DISTINCT reason FROM withdrawals 
                    WHERE reason NOT IN ('SOLD', 'EXPIRED', 'DAMAGED', 'REPLACEMENT_FOR_RETURNED', 'OTHERS');
                """)
                invalid_reasons = cursor.fetchall()
                
                if invalid_reasons:
                    self.stdout.write(f'Found invalid reasons: {[r[0] for r in invalid_reasons]}')
                
                    cursor.execute("""
                        UPDATE withdrawals 
                        SET reason = 'OTHERS' 
                        WHERE reason NOT IN ('SOLD', 'EXPIRED', 'DAMAGED', 'REPLACEMENT_FOR_RETURNED', 'OTHERS');
                    """)
                    fixed_rows = cursor.rowcount
                    self.stdout.write(f'Fixed {fixed_rows} rows with invalid reasons')
                
                self.stdout.write('Step 6: Adding new constraint...')
                cursor.execute("""
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
                """)
                
                self.stdout.write('Step 7: Verifying final state...')
                cursor.execute("SELECT DISTINCT reason FROM withdrawals ORDER BY reason;")
                final_reasons = cursor.fetchall()
                self.stdout.write(f'Final reasons in database: {[r[0] for r in final_reasons]}')
                
                cursor.execute("""
                    SELECT column_name, data_type, character_maximum_length 
                    FROM information_schema.columns 
                    WHERE table_name = 'withdrawals' AND column_name = 'reason';
                """)
                column_info = cursor.fetchone()
                if column_info:
                    self.stdout.write(f'Column info: {column_info}')
                
                self.stdout.write(self.style.SUCCESS('✅ Database fix completed successfully!'))
                    
        except Exception as e:
            import traceback
            self.stdout.write(self.style.ERROR(f'Error: {str(e)}'))
            self.stdout.write(self.style.ERROR(f'Traceback: {traceback.format_exc()}'))
