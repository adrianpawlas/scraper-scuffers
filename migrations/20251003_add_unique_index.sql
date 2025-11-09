-- Migration to add unique index on (source, external_id)
-- Run this if your table doesn't already have the unique constraint

-- First, check if the constraint exists
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'products_source_external_id_key'
        AND conrelid = 'products'::regclass
    ) THEN
        -- Add unique constraint if it doesn't exist
        ALTER TABLE products
        ADD CONSTRAINT products_source_external_id_key
        UNIQUE (source, external_id);
    END IF;
END $$;

-- Create index for performance (if not exists)
CREATE INDEX IF NOT EXISTS idx_products_source_external_id
ON products(source, external_id);
