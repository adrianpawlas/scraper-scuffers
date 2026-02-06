# Database Migrations

This folder contains SQL migration files for the Supabase database.

## How to Apply Migrations

### Option 1: Supabase Dashboard (Recommended)

1. Go to your Supabase project dashboard
2. Navigate to **SQL Editor**
3. Copy the contents of the migration file
4. Paste and run the SQL

### Option 2: Supabase CLI

If you have the Supabase CLI installed:

```bash
supabase db push
```

## Migration Files

### `20251122_add_product_url_unique_constraint.sql`

**Purpose**: Adds a unique constraint on `(source, product_url)` to enable proper upsert operations.

**Why needed**: The scraper uses `source` and `product_url` as the natural unique identifier for products. This constraint ensures:
- No duplicate products from the same source
- Efficient upserts (updates existing products, inserts new ones)
- Data integrity

**Safe to run**: Yes, this migration checks if the constraint already exists before adding it.

### `20260206_drop_embedding_trigger.sql`

**Purpose**: Fixes error `record "new" has no field "embedding"` on insert/update. A trigger on `products` was still referencing the removed `embedding` column. This migration drops all user-defined triggers on `public.products` so upserts succeed.

**When to run**: Run this in the Supabase SQL Editor if you see the error above when the scraper syncs products.

**Safe to run**: Yes. If you need `updated_at` auto-update, re-add that trigger after (see comments in the migration file).

### `20251003_add_unique_index.sql`

**Purpose**: Adds a unique constraint on `(source, external_id)`.

**Note**: This migration is for the older schema. If you're using the current scraper version, apply `20251122_add_product_url_unique_constraint.sql` instead.

## Current Schema Requirements

The scraper expects the following key columns in the `products` table:

- `id` (TEXT, primary key from hash of source+product_url)
- `source` (TEXT, required)
- `product_url` (TEXT, required)
- `image_url` (TEXT)
- `title` (TEXT)
- `brand` (TEXT)
- `gender` (TEXT)
- `price` (TEXT)
- `sale` (TEXT, optional)
- `size` (TEXT)
- `second_hand` (BOOLEAN)
- `image_embedding` (vector, 768-dim)
- `info_embedding` (vector, 768-dim)
- `additional_images` (TEXT, comma-separated URLs)
- `metadata` (TEXT/JSON)
- `country`, `tags`, `other` (optional)

**Unique constraint**: `(source, product_url)`

