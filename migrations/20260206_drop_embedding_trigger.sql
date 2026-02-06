-- Fix: "record \"new\" has no field \"embedding\"" on products insert/update.
-- A trigger on products references the removed column "embedding". Drop all user-defined
-- triggers on products so inserts/updates succeed. Re-add only updated_at if your table has that column.

-- Drop every user-defined trigger on public.products (removes any that reference NEW.embedding)
DO $$
DECLARE
  r RECORD;
BEGIN
  FOR r IN
    SELECT tgname
    FROM pg_trigger
    WHERE tgrelid = 'public.products'::regclass
      AND NOT tgisinternal
  LOOP
    EXECUTE format('DROP TRIGGER IF EXISTS %I ON public.products', r.tgname);
  END LOOP;
END $$;

-- Optional: if your table has updated_at and you want it auto-updated, run this after the block above:
-- CREATE OR REPLACE FUNCTION update_updated_at_column()
-- RETURNS TRIGGER AS $$ BEGIN NEW.updated_at = NOW(); RETURN NEW; END; $$ LANGUAGE plpgsql;
-- CREATE TRIGGER update_products_updated_at BEFORE UPDATE ON public.products
--   FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
