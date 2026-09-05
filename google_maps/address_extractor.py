import re
import random
import asyncio
from playwright.async_api import Page
from deep_translator import GoogleTranslator

class AddressExtractor:
    def __init__(self):
        self.translator = GoogleTranslator(source="auto", target="en")

    async def check_for_captcha(self, page: Page) -> bool:
        """Checks if Google has presented a CAPTCHA or blocking wall."""
        try:
            content = (await page.content()).lower()
            triggers = ["unusual traffic", "recaptcha", "prove you're not a robot", "sorry/index"]
            return any(t in content for t in triggers)
        except Exception:
            return False

    async def extract_address_and_status(self, page: Page):
        """
        Extracts address and operational status based on the updated Gemini.py pipeline.
        Returns: (extracted_address, business_status)
        """
        extracted_address = "N/A"
        business_status = "Operational"

        try:
            # Human-like random delay to avoid bot detection
            await asyncio.sleep(random.uniform(0.5, 1.5))

            # Circuit-breaker check
            if await self.check_for_captcha(page):
                return "BLOCKED", "BLOCKED"

            # Dismiss background popups/overlays
            await page.keyboard.press("Escape")
            await asyncio.sleep(0.5)

            # 1. Operational Status Verification
            try:
                if await page.locator('text="Permanently closed"').count() > 0:
                    business_status = "Permanently closed"
                elif await page.locator('text="Temporarily closed"').count() > 0:
                    business_status = "Temporarily closed"
            except Exception:
                pass

            # 2. Robust Address Extraction
            raw_address = None
            address_btn = page.locator('button[data-item-id="address"]').first
            if await address_btn.count() > 0:
                raw_address = await address_btn.inner_text()

            if not raw_address:
                alt_btn = page.locator('[aria-label^="Address: "]').first
                if await alt_btn.count() > 0:
                    raw_address = await alt_btn.get_attribute("aria-label")
                    if raw_address:
                        raw_address = raw_address.replace("Address: ", "")

            if raw_address:
                clean_address = raw_address.replace("\n", ", ").replace("Address: ", "").strip()
                clean_address = re.sub(r"[^\x00-\x7F]+", "", clean_address).strip(" ,")

                if len(clean_address) > 3:
                    if not clean_address.isascii():
                        try:
                            translated = await asyncio.to_thread(
                                self.translator.translate, clean_address
                            )
                            extracted_address = translated if translated else clean_address
                        except Exception:
                            extracted_address = clean_address
                    else:
                        extracted_address = clean_address

        except Exception as e:
            if "Timeout" not in str(e):
                print(f"[Address Extractor Error]: {e}")

        return extracted_address, business_status