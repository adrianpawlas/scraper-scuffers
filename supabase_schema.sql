-- Products table for fashion scraper
CREATE TABLE IF NOT EXISTS products (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    source TEXT NOT NULL,
    external_id TEXT NOT NULL,
    merchant_name TEXT,
    merchant_id TEXT,
    sku TEXT,
    gtin_upc_ean TEXT,
    product_url TEXT,
    affiliate_url TEXT,
    image_url TEXT,
    image_alt_urls TEXT[],
    image_width INTEGER,
    image_height INTEGER,
    image_sha256 TEXT,
    image_phash TEXT,
    brand TEXT,
    title TEXT,
    description TEXT,
    category TEXT,
    subcategory TEXT,
    gender TEXT,
    tags TEXT[],
    price DECIMAL(10,2),
    currency TEXT,
    availability TEXT DEFAULT 'unknown',
    ocr TEXT,
    color_names TEXT[],
    color_histogram JSONB,
    search_tsv TSVECTOR,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    metadata JSONB,
    size TEXT,
    country TEXT,
    name TEXT,
    embedding VECTOR(1024),
    second_hand BOOLEAN DEFAULT FALSE,
    UNIQUE(source, external_id)
);

-- Index for efficient upserts
CREATE INDEX IF NOT EXISTS idx_products_source_external_id ON products(source, external_id);

-- Index for search
CREATE INDEX IF NOT EXISTS idx_products_search_tsv ON products USING gin(search_tsv);

-- Index for embeddings (if using vector search)
CREATE INDEX IF NOT EXISTS idx_products_embedding ON products USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- Function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Trigger to automatically update updated_at
CREATE TRIGGER update_products_updated_at
    BEFORE UPDATE ON products
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();
