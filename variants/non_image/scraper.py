import asyncio
from playwright.async_api import BrowserContext
from variants.base import BaseScraper
from models import BusinessRecord
from google_maps.extractor import BusinessDetailExtractor
from google_maps.address_extractor import AddressExtractor
from website.scraper import WebsiteScraper
from processing.normalizer import (
    extract_pincode, get_company_type, extract_city,
    parse_phone_robust, extract_location_smart
)
from processing.translator import MultilingualHandler
from processing.validator import DataValidator
from processing.deduplicator import Deduplicator

class NonImageScraper(BaseScraper):
    def __init__(
        self,
        context: BrowserContext,
        translator: MultilingualHandler,
        validator: DataValidator,
        deduplicator: Deduplicator,
        logger
    ):
        self.context = context
        self.detail_extractor = BusinessDetailExtractor(translator)
        self.address_extractor = AddressExtractor()
        self.website_scraper = WebsiteScraper(context)
        self.validator = validator
        self.deduplicator = deduplicator
        self.logger = logger

    async def process_place(self, place_url: str) -> BusinessRecord:
        page = await self.context.new_page()
        try:
            await page.goto(place_url, wait_until="domcontentloaded", timeout=25000)
            await asyncio.sleep(1.0)

            # 1. Base details from Google Maps Sidebar
            record = await self.detail_extractor.extract_sidebar_details(page, place_url)

            # 2. Complete Address & Business Status
            addr, status = await self.address_extractor.extract_address_and_status(page)
            record.business_address = addr
            record.business_status = status

            # 3. Harvest External Website (if available)
            raw_website_phones = []
            website_emails = []

            if record.website:
                self.logger.info(f"Visiting external website: {record.website}")
                web_data = await self.website_scraper.scrape_site(record.website)

                # Collect all emails found on website
                for key in ["Site Email 1", "Site Email 2", "Site Email 3", "Site Extra Email"]:
                    val = web_data.get(key, "").strip()
                    if val and val not in website_emails:
                        website_emails.append(val)

                # Collect all phone candidates found on website
                for key in ["Site Mobile Number", "Site Mobile Number 2", "Site Mobile Number 3", "Site Extra Mobile Number", "Site Landline", "Site Toll Free"]:
                    val = web_data.get(key, "").strip()
                    if val:
                        raw_website_phones.append(val)

                # Preserve metadata in extra_attributes
                record.extra_attributes.update({
                    "Owner Name (scraped)": web_data.get("Owner Name (scraped)", ""),
                    "Address (scraped)": web_data.get("Address (scraped)", ""),
                    "Pincodes (scraped)": web_data.get("Pincodes (scraped)", ""),
                    "RERA No (scraped)": web_data.get("RERA No (scraped)", ""),
                })

            
            # 4. Consolidate and Distribute Emails (Up to 3, overflow to extra_email)
            all_emails = []
            if record.email:
                all_emails.append(record.email)
            all_emails.extend(website_emails)
            unique_emails = list(dict.fromkeys([e.strip() for e in all_emails if "@" in e]))

            if len(unique_emails) >= 1:
                record.email = unique_emails[0]
            if len(unique_emails) >= 2:
                record.email_2 = unique_emails[1]
            if len(unique_emails) >= 3:
                record.email_3 = unique_emails[2]
            if len(unique_emails) > 3:
                record.extra_email = ", ".join(unique_emails[3:])

            # 5. UNIFIED PHONE POOLING & DISTRIBUTION (Up to 3, 4+ separated by ' / ')
            phone_candidates = []
            if record.raw_extracted_phones:
                phone_candidates.append(record.raw_extracted_phones)
            phone_candidates.extend(raw_website_phones)

            combined_raw_phones = ", ".join(phone_candidates)
            mobiles, landlines, std_codes, toll_frees = parse_phone_robust(combined_raw_phones)
            unique_mobiles = list(dict.fromkeys(mobiles))

            if len(unique_mobiles) >= 1:
                record.mobile_number = unique_mobiles[0]
            if len(unique_mobiles) >= 2:
                record.mobile_number_2 = unique_mobiles[1]
            if len(unique_mobiles) >= 3:
                record.mobile_number_3 = unique_mobiles[2]
            if len(unique_mobiles) > 3:
                record.extra_mobile_number = " / ".join(unique_mobiles[3:])

            if landlines:
                record.landline_number = ", ".join(dict.fromkeys(landlines))
            if std_codes:
                record.std_code = ", ".join(dict.fromkeys(std_codes))
            if toll_frees:
                record.toll_free_number = ", ".join(dict.fromkeys(toll_frees))

            # 6. Geographic Normalization
            record.business_type = get_company_type(record.business_name)
            record.pincode = extract_pincode(record.business_address)
            city = extract_city(record.business_address)
            record.district_name = city
            record.location_name = extract_location_smart(record.business_address, city)

            # 7. Schema Validation
            valid, reason = self.validator.validate_record(record)
            if not valid:
                record.scraping_status = f"Filtered: {reason}"

            return record

        finally:
            await page.close()

    # async def process_place(self, place_url: str) -> BusinessRecord:
    #     page = await self.context.new_page()
    #     try:
    #         await page.goto(place_url, wait_until="domcontentloaded", timeout=25000)
    #         await asyncio.sleep(1.0)

    #         # 1. Base details from Google Maps Sidebar
    #         record = await self.detail_extractor.extract_sidebar_details(page, place_url)

    #         # 2. Complete Address & Business Status (Gemini.py logic)
    #         addr, status = await self.address_extractor.extract_address_and_status(page)
    #         record.business_address = addr
    #         record.business_status = status

    #         # 3. Parse Google Maps direct phone listing
    #         if record.raw_extracted_phones:
    #             m, l, s, t = parse_phone_robust(record.raw_extracted_phones)
    #             if m: record.mobile_number = m[0]
    #             if len(m) > 1: record.mobile_number_2 = m[1]
    #             if l: record.landline_number = ", ".join(l)
    #             if s: record.std_code = ", ".join(s)
    #             if t: record.toll_free_number = ", ".join(t)

    #         # 4. Deep Website Extraction (real_estate_contact_scraper.py logic)
    #         if record.website:
    #             web_data = await self.website_scraper.scrape_site(record.website)
                
    #             # Fill missing emails from website
    #             if not record.email and web_data.get("Site Email 1"):
    #                 record.email = web_data["Site Email 1"]

    #             # Fill fallback phones if Google Maps had none
    #             if not record.mobile_number and web_data.get("Site Mobile Number"):
    #                 record.mobile_number = web_data["Site Mobile Number"]

    #             # Store newly scraped website intelligence
    #             record.extra_attributes.update({
    #                 "Site Email 1": web_data.get("Site Email 1", ""),
    #                 "Site Email 2": web_data.get("Site Email 2", ""),
    #                 "Site Mobile Number": web_data.get("Site Mobile Number", ""),
    #                 "Site Mobile Number 2": web_data.get("Site Mobile Number 2", ""),
    #                 "Site Toll Free": web_data.get("Site Toll Free", ""),
    #                 "Site Landline": web_data.get("Site Landline", ""),
    #                 "Owner Name (scraped)": web_data.get("Owner Name (scraped)", ""),
    #                 "Address (scraped)": web_data.get("Address (scraped)", ""),
    #                 "Pincodes (scraped)": web_data.get("Pincodes (scraped)", ""),
    #                 "RERA No (scraped)": web_data.get("RERA No (scraped)", ""),
    #             })

    #         # 5. Geographic Normalization
    #         record.business_type = get_company_type(record.business_name)
    #         record.pincode = extract_pincode(record.business_address)
    #         city = extract_city(record.business_address)
    #         record.district_name = city
    #         record.location_name = extract_location_smart(record.business_address, city)

    #         # 6. Schema Validation
    #         valid, reason = self.validator.validate_record(record)
    #         if not valid:
    #             record.scraping_status = f"Filtered: {reason}"

    #         return record

    #     finally:
    #         await page.close()

    async def run(self):
        pass