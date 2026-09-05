import re
from typing import Set
from urllib.parse import urlparse
from rapidfuzz import fuzz

class Deduplicator:
    def __init__(self):
        self.seen_urls: Set[str] = set()
        self.seen_cids: Set[str] = set()
        self.seen_name_phones: Set[str] = set()
        self.seen_name_addresses: Set[str] = set()

    def normalize_str(self, val: str) -> str:
        return re.sub(r'[^a-zA-Z0-9]', '', str(val).lower())

    def extract_cid_or_place_id(self, url: str) -> str:
        if not url:
            return ""
        # Match CID in hex or decimal format
        cid_match = re.search(r'0x[0-9a-fA-F]+:0x([0-9a-fA-F]+)', url)
        if cid_match:
            return cid_match.group(1).lower()
        place_match = re.search(r'/place/([^/]+)/', url)
        if place_match:
            return place_match.group(1).lower()
        return url.split("?")[0]

    def is_duplicate(self, record) -> bool:
        # Check 1: Google Maps Identity
        if record.google_maps_url:
            cid = self.extract_cid_or_place_id(record.google_maps_url)
            if cid and cid in self.seen_cids:
                return True
            if record.google_maps_url in self.seen_urls:
                return True

        norm_name = self.normalize_str(record.business_name)

        # Check 2: Name + Mobile Number
        primary_phone = re.sub(r'\D', '', record.mobile_number)
        if norm_name and len(primary_phone) == 10:
            key = f"{norm_name}_{primary_phone}"
            if key in self.seen_name_phones:
                return True

        # Check 3: Name + Address Key
        norm_addr = self.normalize_str(record.business_address)[:30]
        if norm_name and norm_addr:
            key = f"{norm_name}_{norm_addr}"
            if key in self.seen_name_addresses:
                return True

        return False

    def register(self, record):
        if record.google_maps_url:
            self.seen_urls.add(record.google_maps_url)
            cid = self.extract_cid_or_place_id(record.google_maps_url)
            if cid:
                self.seen_cids.add(cid)

        norm_name = self.normalize_str(record.business_name)
        primary_phone = re.sub(r'\D', '', record.mobile_number)
        if norm_name and len(primary_phone) == 10:
            self.seen_name_phones.add(f"{norm_name}_{primary_phone}")

        norm_addr = self.normalize_str(record.business_address)[:30]
        if norm_name and norm_addr:
            self.seen_name_addresses.add(f"{norm_name}_{norm_addr}")