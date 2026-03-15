import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()

@dataclass
class Config:
    SUPABASE_URL: str = os.getenv("SUPABASE_URL", "https://yqawmzggcgpeyaaynrjk.supabase.co")
    SUPABASE_KEY: str = os.getenv("SUPABASE_KEY", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InlxYXdtemdnY2dwZXlhYXlucmprIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc1NTAxMDkyNiwiZXhwIjoyMDcwNTg2OTI2fQ.XtLpxausFriraFJeX27ZzsdQsFv3uQKXBBggoz6P4D4")
    
    BASE_URL = "https://scuffers.com"
    CATEGORIES = [
        "https://scuffers.com/collections/all",
        "https://scuffers.com/collections/woman",
        "https://scuffers.com/collections/footwear"
    ]
    
    EMBEDDING_MODEL = "google/siglip-base-patch16-384"
    EMBEDDING_DIMENSION = 768
    
    SOURCE = "scraper-scuffers"
    BRAND = "Scuffers"
    SECOND_HAND = False
    
    DELAY_BETWEEN_REQUESTS = 1.0
    MAX_RETRIES = 3
    TIMEOUT = 30

config = Config()
