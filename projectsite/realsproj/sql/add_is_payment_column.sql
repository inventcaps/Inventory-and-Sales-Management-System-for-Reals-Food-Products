-- Add is_payment column and backfill old payment entries
-- Run this on PRODUCTION PostgreSQL before deploying the updated code

BEGIN;

-- Add is_payment column (if not already added)
ALTER TABLE sales ADD COLUMN IF NOT EXISTS is_payment boolean DEFAULT false;

-- Backfill old payment entries: link them to a withdrawal and mark as payment
UPDATE sales s
SET is_payment = true,
    withdrawal_id = w.id
FROM withdrawals w
WHERE s.is_payment = false
  AND s.withdrawal_id IS NULL
  AND w.order_group_id IS NOT NULL
  AND s.description ILIKE '%' || w.order_group_id || '%'
  AND (s.description ILIKE '%payment%' OR s.description ILIKE '%Payment%');

-- Verify: should show only manual sales with NULL withdrawal
SELECT COUNT(*) AS remaining_unlinked_payments
FROM sales
WHERE is_payment = false
  AND withdrawal_id IS NULL
  AND description ILIKE '%order #%';

COMMIT;
