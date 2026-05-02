-- Fix for trigger restoration bug
-- Removes AND is_archived = FALSE condition that silently skips restoration
-- Also adds un-archiving capability when batch is restored

CREATE OR REPLACE FUNCTION public.trg_withdrawals_stock_handler()
 RETURNS trigger
 LANGUAGE plpgsql
AS $function$
DECLARE
    v_remaining NUMERIC(10,2);
    v_deduct NUMERIC(10,2);
    v_batch_id INTEGER;
    v_batch_qty NUMERIC(10,2);
BEGIN
    -- INSERT: Deduct from batches
    IF TG_OP = 'INSERT' THEN
        v_remaining := NEW.quantity;
        
        IF NEW.item_type = 'PRODUCT' THEN
            -- If batch_id is NULL, skip (no stock deduction needed)
            IF NEW.batch_id IS NULL THEN
                RETURN NEW;
            END IF;
            
            -- Set flag to skip packaging trigger
            PERFORM set_config('app.skip_packaging_trigger', 'true', false);
            
            -- Deduct from the specific batch
            SELECT quantity INTO v_deduct
            FROM product_batches
            WHERE id = NEW.batch_id AND is_archived = FALSE;
            
            IF v_deduct IS NULL THEN
                PERFORM set_config('app.skip_packaging_trigger', 'false', false);
                RAISE EXCEPTION 'Batch % not found', NEW.batch_id;
            END IF;
            
            IF v_deduct < v_remaining THEN
                PERFORM set_config('app.skip_packaging_trigger', 'false', false);
                RAISE EXCEPTION 'Insufficient stock in batch % (has %, needs %)', 
                    NEW.batch_id, v_deduct, v_remaining;
            END IF;
            
            UPDATE product_batches
            SET quantity = quantity - v_remaining
            WHERE id = NEW.batch_id;
            
            -- Clear the flag
            PERFORM set_config('app.skip_packaging_trigger', 'false', false);
            
            -- Update inventory total
            UPDATE product_inventory
            SET total_stock = (
                SELECT COALESCE(SUM(quantity),0)
                FROM product_batches
                WHERE product_id = NEW.item_id AND is_archived = FALSE
            )
            WHERE product_id = NEW.item_id;
            
        ELSIF NEW.item_type = 'RAW_MATERIAL' THEN
            FOR v_batch_id, v_batch_qty IN
                SELECT id, quantity
                FROM raw_material_batches
                WHERE material_id = NEW.item_id
                  AND is_archived = FALSE
                  AND quantity > 0
                ORDER BY expiration_date ASC NULLS LAST, id ASC
            LOOP
                EXIT WHEN v_remaining <= 0;
                
                v_deduct := LEAST(v_batch_qty, v_remaining);
                UPDATE raw_material_batches
                SET quantity = quantity - v_deduct
                WHERE id = v_batch_id;
                v_remaining := v_remaining - v_deduct;
            END LOOP;
            
            IF v_remaining > 0 THEN
                RAISE EXCEPTION 'Insufficient stock for material %', NEW.item_id;
            END IF;
            
            UPDATE raw_material_inventory
            SET total_stock = (
                SELECT COALESCE(SUM(quantity),0)
                FROM raw_material_batches
                WHERE material_id = NEW.item_id AND is_archived = FALSE
            )
            WHERE material_id = NEW.item_id;
        END IF;
        
        RETURN NEW;
    END IF;
    
    -- DELETE: Restore to batches (FIXED: removed AND is_archived = FALSE)
    IF TG_OP = 'DELETE' THEN
        v_remaining := OLD.quantity;
        
        IF OLD.item_type = 'PRODUCT' THEN
            -- If batch_id is NULL, skip (no stock restoration needed)
            IF OLD.batch_id IS NULL THEN
                RETURN OLD;
            END IF;
            
            -- Set flag to skip packaging trigger
            PERFORM set_config('app.skip_packaging_trigger', 'true', false);
            
            -- Restore to the specific batch (FIXED: removed is_archived check, added un-archive)
            UPDATE product_batches
            SET quantity = quantity + v_remaining,
                is_archived = FALSE  -- Un-archive if it was archived
            WHERE id = OLD.batch_id;
            
            -- Clear the flag
            PERFORM set_config('app.skip_packaging_trigger', 'false', false);
            
            UPDATE product_inventory
            SET total_stock = (
                SELECT COALESCE(SUM(quantity),0)
                FROM product_batches
                WHERE product_id = OLD.item_id AND is_archived = FALSE
            )
            WHERE product_id = OLD.item_id;
            
        ELSIF OLD.item_type = 'RAW_MATERIAL' THEN
            FOR v_batch_id IN
                SELECT id
                FROM raw_material_batches
                WHERE material_id = OLD.item_id
                  AND is_archived = FALSE
                ORDER BY expiration_date DESC NULLS LAST, id DESC
            LOOP
                EXIT WHEN v_remaining <= 0;
                
                UPDATE raw_material_batches
                SET quantity = quantity + v_remaining
                WHERE id = v_batch_id;
                v_remaining := 0;
            END LOOP;
            
            UPDATE raw_material_inventory
            SET total_stock = (
                SELECT COALESCE(SUM(quantity),0)
                FROM raw_material_batches
                WHERE material_id = OLD.item_id AND is_archived = FALSE
            )
            WHERE material_id = OLD.item_id;
        END IF;
        
        RETURN OLD;
    END IF;
    
    -- UPDATE: Restore old, then apply new (FIXED: removed AND is_archived = FALSE in restore)
    IF TG_OP = 'UPDATE' THEN
        -- Skip if nothing changed
        IF OLD.item_id = NEW.item_id AND OLD.quantity = NEW.quantity AND OLD.reason = NEW.reason THEN
            RETURN NEW;
        END IF;
        
        -- Restore old (FIXED: removed is_archived check, added un-archive)
        IF OLD.item_type = 'PRODUCT' THEN
            IF OLD.batch_id IS NULL THEN
                -- Skip restoration if no batch
            ELSE
                PERFORM set_config('app.skip_packaging_trigger', 'true', false);
                
                UPDATE product_batches
                SET quantity = quantity + OLD.quantity,
                    is_archived = FALSE  -- Un-archive if it was archived
                WHERE id = OLD.batch_id;
                
                PERFORM set_config('app.skip_packaging_trigger', 'false', false);
            END IF;
        END IF;
        
        -- Apply new
        v_remaining := NEW.quantity;
        
        IF NEW.item_type = 'PRODUCT' THEN
            IF NEW.batch_id IS NULL THEN
                -- Skip deduction if no batch
            ELSE
                PERFORM set_config('app.skip_packaging_trigger', 'true', false);
                
                SELECT quantity INTO v_deduct
                FROM product_batches
                WHERE id = NEW.batch_id AND is_archived = FALSE;
                
                IF v_deduct IS NULL OR v_deduct < v_remaining THEN
                    PERFORM set_config('app.skip_packaging_trigger', 'false', false);
                    RAISE EXCEPTION 'Insufficient stock in batch %', NEW.batch_id;
                END IF;
                
                UPDATE product_batches
                SET quantity = quantity - v_remaining
                WHERE id = NEW.batch_id;
                
                PERFORM set_config('app.skip_packaging_trigger', 'false', false);
            END IF;
            
            -- Update inventory totals
            IF OLD.item_id = NEW.item_id THEN
                UPDATE product_inventory
                SET total_stock = (
                    SELECT COALESCE(SUM(quantity),0)
                    FROM product_batches
                    WHERE product_id = NEW.item_id AND is_archived = FALSE
                )
                WHERE product_id = NEW.item_id;
            ELSE
                UPDATE product_inventory
                SET total_stock = (
                    SELECT COALESCE(SUM(quantity),0)
                    FROM product_batches
                    WHERE product_id = OLD.item_id AND is_archived = FALSE
                )
                WHERE product_id = OLD.item_id;
                
                UPDATE product_inventory
                SET total_stock = (
                    SELECT COALESCE(SUM(quantity),0)
                    FROM product_batches
                    WHERE product_id = NEW.item_id AND is_archived = FALSE
                )
                WHERE product_id = NEW.item_id;
            END IF;
        END IF;
        
        RETURN NEW;
    END IF;
    
    RETURN COALESCE(NEW, OLD);
END;
$function$
