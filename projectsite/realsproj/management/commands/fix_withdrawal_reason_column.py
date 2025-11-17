from django.core.management.base import BaseCommand
from django.db import connection

class Command(BaseCommand):
    help = 'Fix withdrawal reason column length to support REPLACEMENT_FOR_RETURNED'

    def handle(self, *args, **options):
        try:
            with connection.cursor() as cursor:
             
                cursor.execute("""
                    SELECT column_name, data_type, character_maximum_length 
                    FROM information_schema.columns 
                    WHERE table_name = 'withdrawals' AND column_name = 'reason';
                """)
                result = cursor.fetchone()
                
                if result:
                    column_name, data_type, max_length = result
                    self.stdout.write(f'Current column: {column_name}, type: {data_type}, max_length: {max_length}')
                    
                    if max_length and max_length < 30:
                        self.stdout.write('Updating column length to 30 characters...')
                     
                        cursor.execute("ALTER TABLE withdrawals ALTER COLUMN reason TYPE character varying(30);")
                        
                        cursor.execute("ALTER TABLE withdrawals DROP CONSTRAINT IF EXISTS withdrawals_reason_check;")
                        
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
                        
                        self.stdout.write(self.style.SUCCESS('✅ Column length and constraint updated successfully!'))
                    else:
                        self.stdout.write('Column length is already sufficient.')
                else:
                    self.stdout.write(self.style.ERROR('Could not find reason column in withdrawals table.'))
                    
        except Exception as e:
            import traceback
            self.stdout.write(self.style.ERROR(f'Error: {str(e)}'))
            self.stdout.write(self.style.ERROR(f'Traceback: {traceback.format_exc()}'))
