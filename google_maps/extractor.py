import re
from playwright.async_api import Page
from models import BusinessRecord
from processing.translator import MultilingualHandler

class BusinessDetailExtractor:
    def __init__(self, translator: MultilingualHandler):
        self.translator = translator

    async def extract_sidebar_details(self, page: Page, profile_url: str) -> BusinessRecord:
        record = BusinessRecord(google_maps_url=profile_url)

        # Title / Business Name
        # Title / Business Name Extraction
        try:
            # Wait briefly for header rendering instead of failing immediately
            title_locator = page.locator('h1.DUwDvf, h1.fontHeadlineLarge, div[role="main"] h1').first
            await title_locator.wait_for(state="attached", timeout=4000)
            raw_title = await title_locator.inner_text()
            if raw_title and raw_title.strip():
                record.business_name = raw_title.strip()
        except Exception:
            pass

        # Fallback: Extract title directly from Google Maps URL slug if DOM lagged
        if not record.business_name and "/place/" in profile_url:
            try:
                import urllib.parse
                slug = profile_url.split("/place/")[1].split("/")[0]
                slug_clean = urllib.parse.unquote_plus(slug).replace("+", " ").strip()
                if len(slug_clean) >= 2:
                    record.business_name = slug_clean
            except Exception:
                pass
        # Category
        try:
            cat_el = page.locator('button.DkEaL').first
            if await cat_el.count() > 0:
                raw_cat = (await cat_el.inner_text()).strip()
                record.category = self.translator.translate_text(raw_cat)
        except Exception:
            pass

        # Rating and Reviews Count
        try:
            rating_el = page.locator('div.F7nice span[aria-hidden="true"]').first
            if await rating_el.count() > 0:
                record.rating = (await rating_el.inner_text()).strip()

            reviews_el = page.locator('div.F7nice span[aria-label*="reviews"]').first
            if await reviews_el.count() > 0:
                raw_rev = await reviews_el.get_attribute('aria-label')
                match = re.search(r'([\d,]+)', raw_rev or "")
                if match:
                    record.reviews_count = match.group(1).replace(",", "")
        except Exception:
            pass

        # Phone Number from Maps Listing
        try:
            phone_btn = page.locator('button[data-item-id^="phone:tel:"]').first
            if await phone_btn.count() > 0:
                raw_phone = await phone_btn.get_attribute('data-item-id')
                record.raw_extracted_phones = raw_phone.replace("phone:tel:", "").strip()
            else:
                alt_phone = page.locator('button[aria-label^="Phone: "]').first
                if await alt_phone.count() > 0:
                    aria_p = await alt_phone.get_attribute('aria-label')
                    record.raw_extracted_phones = aria_p.replace("Phone: ", "").strip()
        except Exception:
            pass

        # Official Website Link
        try:
            web_btn = page.locator('a[data-item-id="authority"]').first
            if await web_btn.count() > 0:
                href = await web_btn.get_attribute('href')
                if href and "google.com" not in href:
                    record.website = href.strip()
        except Exception:
            pass

        return record