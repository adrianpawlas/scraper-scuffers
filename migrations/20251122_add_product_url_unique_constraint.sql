-- Migration to add unique constraint on (source, product_url)
-- This ensures we can upsert products based on their source and URL

-- First, add the constraint if it doesn't exist
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'products_source_product_url_key'
        AND conrelid = 'products'::regclass
    ) THEN
        -- Add unique constraint if it doesn't exist
        ALTER TABLE products
        ADD CONSTRAINT products_source_product_url_key
        UNIQUE (source, product_url);
        
        RAISE NOTICE 'Added unique constraint on (source, product_url)';
    ELSE
        RAISE NOTICE 'Unique constraint on (source, product_url) already exists';
    END IF;
END $$;

-- Create index for performance (if not exists)
CREATE INDEX IF NOT EXISTS idx_products_source_product_url
ON products(source, product_url);

