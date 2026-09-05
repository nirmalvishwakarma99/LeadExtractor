import re
from typing import Tuple
from models import BusinessRecord

class DataValidator:
    @staticmethod
    def validate_record(record: BusinessRecord) -> Tuple[bool, str]:
        # Rule 1: Business name must exist and not be a placeholder
        name = record.business_name.strip()
        if not name or len(name) < 2 or name.lower() in ["unknown", "n/a", "google maps"]:
            return False, "Invalid business name"

        # Rule 2: Google Maps URL must be authentic
        if not record.google_maps_url or "google.com/maps" not in record.google_maps_url:
            return False, "Invalid Google Maps URL"

        # Rule 3: Address must not be pure garbage
        if record.business_address and len(record.business_address) > 500:
            record.business_address = record.business_address[:500]

        # Rule 4: Clean website URL
        if record.website:
            low_web = record.website.lower()
            if any(p in low_web for p in ["facebook.com", "instagram.com", "twitter.com", "wa.me"]):
                record.website = ""

        return True, "Valid"