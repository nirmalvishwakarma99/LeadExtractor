from variants.base import BaseScraper
from models import BusinessRecord

class ImageDetectionScraper(BaseScraper):
    """
    Variant B — Image Detection & Signboard Verification Scraper.
    Reserved for Phase 2 implementation.
    """
    def __init__(self, *args, **kwargs):
        pass

    async def process_place(self, place_url: str) -> BusinessRecord:
        raise NotImplementedError("Variant B (Image Detection) will be implemented in Phase 2.")

    async def run(self):
        raise NotImplementedError("Variant B (Image Detection) will be implemented in Phase 2.")