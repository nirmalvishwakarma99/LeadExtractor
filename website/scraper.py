import re
import asyncio
from typing import Dict, Any, List
from playwright.async_api import BrowserContext, Page

# ============================================================================
# EXTRACTION PATTERNS & JUNK FILTERS (from real_estate_contact_scraper.py)
# ============================================================================
EMAIL_PATTERN = re.compile(r'[a-zA-Z0-9_.+-]+\s*@\s*[a-zA-Z0-9-]+\s*\.\s*[a-zA-Z0-9-.]+')
PHONE_PATTERN = re.compile(r'(\+?\d[\d\-\s()]{7,14}\d)')
PINCODE_PATTERN = re.compile(r'\b\d{6}\b')

JUNK_EMAIL_DOMAINS = {
    "example.com", "yourdomain.com", "domain.com", "email.com", "test.com",
    "yourname.com", "sentry.io", "wixpress.com", "godaddy.com", "schema.org",
    "w3.org", "placeholder.com", "site.com", "company.com"
}
JUNK_EMAIL_EXTENSIONS = (".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".bmp")

IGNORED_URL_PATTERNS = [
    "whatsapp.com", "wa.me", "maps.google", "goo.gl/maps",
    "facebook.com", "fb.com", "instagram.com", "linkedin.com",
    "twitter.com", "x.com", "youtube.com", "youtu.be",
    "pinterest.com", "telegram.me", "t.me", "tel:", "mailto:"
]

def extract_emails(text: str) -> List[str]:
    if not text:
        return []
    found = EMAIL_PATTERN.findall(text)
    return [re.sub(r'\s+', '', e) for e in found]

def clean_emails(raw_emails: List[str]) -> List[str]:
    cleaned, seen = [], set()
    for e in raw_emails:
        e = e.strip().strip(".,;:").lower()
        if "@" not in e or e in seen:
            continue
        if e.endswith(JUNK_EMAIL_EXTENSIONS):
            continue
        domain = e.split("@")[-1]
        if domain in JUNK_EMAIL_DOMAINS:
            continue
        seen.add(e)
        cleaned.append(e)
    return cleaned

def extract_phones(text: str) -> List[str]:
    if not text:
        return []
    return PHONE_PATTERN.findall(text)

def classify_phone(raw: str):
    digits = re.sub(r'\D', '', raw)
    if len(digits) < 8:
        return None

    # Toll-free
    if digits.startswith("1800") or digits.startswith("1900") or digits.startswith("01800"):
        return ("tollfree", digits)

    # Country code cleanup
    if len(digits) > 11 and digits.startswith("0091"):
        digits = digits[4:]
    elif len(digits) > 11 and digits.startswith("91"):
        digits = digits[2:]

    # Trunk 0 cleanup
    if len(digits) == 11 and digits[0] == "0" and digits[1] in "6789":
        digits = digits[1:]

    if len(digits) == 10 and digits[0] in "6789":
        return ("mobile", digits)
    if 8 <= len(digits) <= 11:
        return ("landline", digits)
    return None

def distribute_phones(raw_phones: List[str]) -> Dict[str, str]:
    mobiles, landlines, tollfree = [], [], []
    seen = set()
    for raw in raw_phones:
        result = classify_phone(raw)
        if not result:
            continue
        kind, num = result
        if num in seen:
            continue
        seen.add(num)
        if kind == "mobile":
            mobiles.append(num)
        elif kind == "landline":
            landlines.append(num)
        else:
            tollfree.append(num)

    return {
        "Site Mobile Number": mobiles[0] if len(mobiles) > 0 else "",
        "Site Mobile Number 2": mobiles[1] if len(mobiles) > 1 else "",
        "Site Mobile Number 3": mobiles[2] if len(mobiles) > 2 else "",
        "Site Extra Mobile Number": ", ".join(mobiles[3:]),
        "Site Landline": ", ".join(landlines),
        "Site Toll Free": ", ".join(tollfree),
    }

def distribute_emails(raw_emails: List[str]) -> Dict[str, str]:
    emails = clean_emails(raw_emails)
    return {
        "Site Email 1": emails[0] if len(emails) > 0 else "",
        "Site Email 2": emails[1] if len(emails) > 1 else "",
        "Site Email 3": emails[2] if len(emails) > 2 else "",
        "Site Extra Email": ", ".join(emails[3:]),
    }

def extract_name(text: str) -> str:
    if not text:
        return ""
    for pat in (
        r'(?i)Contact Person\s*[\n\r]*[:\-]?\s*([A-Za-z\s]{3,35})',
        r'(?i)Owner Name\s*[\n\r]*[:\-]?\s*([A-Za-z\s]{3,35})',
        r'(?i)Proprietor\s*[\n\r]*[:\-]?\s*([A-Za-z\s]{3,35})'
    ):
        m = re.search(pat, text)
        if m:
            name = m.group(1).split("\n")[0].strip()
            if len(name) > 2:
                return name
    return ""

def extract_address(text: str) -> str:
    if not text:
        return ""
    m = re.search(
        r'(?i)Address\s*[\n\r]*[:\-]?\s*(.*?)(?:\n\s*\n|Call Us|Email|Web Address|Pincode|$)',
        text, re.DOTALL
    )
    if m:
        addr = re.sub(r'\s+', ' ', m.group(1).replace("\n", ", ")).strip()
        if len(addr) > 5:
            return addr
    return ""

def extract_rera(text: str) -> str:
    if not text:
        return ""
    m = re.search(r'(?i)(RERA(?:[\s\w]*No)?[.:\-\s]*[A-Z0-9]{8,15})', text)
    return m.group(1).strip() if m else ""

# ============================================================================
# ASYNCHRONOUS PLAYWRIGHT WEBSITE SCRAPER
# ============================================================================
class WebsiteScraper:
    def __init__(self, context: BrowserContext):
        self.context = context

    async def close_popups(self, page: Page):
        popup_selectors = [
            "text='X'", "text='x'", "text='×'", "text='Close'",
            "[aria-label='Close']", "[aria-label='close']",
            "button:has-text('Accept')", "button:has-text('Got it')"
        ]
        for sel in popup_selectors:
            try:
                el = page.locator(sel).first
                if await el.is_visible():
                    await el.click(timeout=300)
            except Exception:
                pass

    async def extract_hidden_attributes(self, page: Page) -> List[str]:
        hidden = []
        try:
            elements = await page.locator("[data-mobile], [data-phone], [data-number]").all()
            for el in elements:
                for attr in ("data-mobile", "data-phone", "data-number"):
                    val = await el.get_attribute(attr)
                    if val and val.strip():
                        hidden.append(val.strip())
        except Exception:
            pass
        return hidden

    async def extract_from_links(self, page: Page):
        emails, phones = [], []
        try:
            links = await page.locator("a[href^='mailto:'], a[href^='tel:']").all()
            for a in links:
                href = (await a.get_attribute("href") or "").strip()
                low = href.lower()
                if low.startswith("mailto:"):
                    emails.append(href.split(":", 1)[1].split("?")[0])
                elif low.startswith("tel:"):
                    phones.append(href.split(":", 1)[1])
        except Exception:
            pass
        return emails, phones

    async def interact_with_reveal_elements(self, page: Page):
        keywords = ["view mobile", "view number", "show number", "get number", "+91", "contact"]
        for kw in keywords:
            try:
                btn = page.locator(f"text=/{kw}/i").first
                if await btn.is_visible():
                    await btn.click(timeout=500)
                    await asyncio.sleep(0.3)
            except Exception:
                pass

    async def scrape_site(self, url: str) -> Dict[str, Any]:
        """Navigates to business website and pulls complete contact intelligence."""
        result = {
            "Site Email 1": "", "Site Email 2": "", "Site Email 3": "", "Site Extra Email": "",
            "Site Mobile Number": "", "Site Mobile Number 2": "", "Site Mobile Number 3": "",
            "Site Extra Mobile Number": "", "Site Landline": "", "Site Toll Free": "",
            "Owner Name (scraped)": "", "Address (scraped)": "", "Pincodes (scraped)": "",
            "RERA No (scraped)": "", "Scraping Status": "Pending"
        }

        if not url or any(ign in url.lower() for ign in IGNORED_URL_PATTERNS):
            result["Scraping Status"] = "Skipped (Invalid/Social)"
            return result

        page = await self.context.new_page()
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=20000)
            await self.close_popups(page)
            await self.interact_with_reveal_elements(page)

            link_emails, link_phones = await self.extract_from_links(page)
            attr_phones = await self.extract_hidden_attributes(page)

            body_text = await page.inner_text("body")

            emails = extract_emails(body_text) + link_emails
            phones = extract_phones(body_text) + link_phones + attr_phones

            # Deep search contact page if primary page lacked sufficient contact data
            if not clean_emails(emails) or not [p for p in phones if classify_phone(p)]:
                contact_link = page.locator(
                    "a:has-text('Contact'), a:has-text('Contact Us'), a[href*='contact']"
                ).first
                if await contact_link.count() > 0:
                    href = await contact_link.get_attribute("href")
                    if href and not any(ign in href.lower() for ign in IGNORED_URL_PATTERNS):
                        try:
                            await page.goto(href, wait_until="domcontentloaded", timeout=15000)
                            await self.close_popups(page)
                            await self.interact_with_reveal_elements(page)
                            
                            c_emails, c_phones = await self.extract_from_links(page)
                            c_attrs = await self.extract_hidden_attributes(page)
                            c_body = await page.inner_text("body")

                            body_text += "\n" + c_body
                            emails += extract_emails(c_body) + c_emails
                            phones += extract_phones(c_body) + c_phones + c_attrs
                        except Exception:
                            pass

            # Classify & distribute
            result.update(distribute_emails(emails))
            result.update(distribute_phones(phones))
            result["Owner Name (scraped)"] = extract_name(body_text)
            result["Address (scraped)"] = extract_address(body_text)
            pincodes = list(dict.fromkeys(PINCODE_PATTERN.findall(body_text)))
            result["Pincodes (scraped)"] = ", ".join(pincodes)
            result["RERA No (scraped)"] = extract_rera(body_text)
            result["Scraping Status"] = "Success"

        except Exception as e:
            result["Scraping Status"] = f"Error: {str(e)[:60]}"
        finally:
            await page.close()

        return result