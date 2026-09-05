import asyncio
from typing import List
from playwright.async_api import Page
from monitoring.alerts import trigger_alert
from google_maps.browser import detect_captcha

class GoogleMapsSearcher:
    def __init__(self, page: Page, logger, circuit_breaker_event: asyncio.Event):
        self.page = page
        self.logger = logger
        self.circuit_breaker_event = circuit_breaker_event

    async def search_and_scroll_feed(self, search_query: str) -> List[str]:
        target_url = f"https://www.google.com/maps/search/{search_query.replace(' ', '+')}"
        self.logger.info(f"Opening query: {search_query}")
        
        await self.page.goto(target_url, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(2.0)

        if await detect_captcha(self.page):
            await self._handle_block()

        feed_selector = 'div[role="feed"]'
        try:
            await self.page.wait_for_selector(feed_selector, timeout=10000)
        except Exception:
            # If a single exact result loaded directly, return current URL
            current_url = self.page.url
            if "/maps/place/" in current_url:
                return [current_url]
            return []

        links = set()
        scroll_attempts = 0
        max_attempts = 35

        while scroll_attempts < max_attempts:
            if await detect_captcha(self.page):
                await self._handle_block()

            # Harvest all business cards currently visible
            elements = await self.page.locator('div[role="feed"] a[href*="/maps/place/"]').all()
            for el in elements:
                href = await el.get_attribute('href')
                if href:
                    links.add(href.split("?")[0])

            # End of list indicator check
            end_elem = self.page.locator("text=\"You've reached the end of the list.\"")
            if await end_elem.count() > 0:
                break

            # Scroll downward on the feed container
            feed = self.page.locator(feed_selector).first
            await feed.evaluate('(el) => el.scrollTop = el.scrollHeight')
            await asyncio.sleep(1.2)
            scroll_attempts += 1

        self.logger.info(f"Discovered {len(links)} unique listings for: {search_query}")
        return list(links)

    async def _handle_block(self):
        self.logger.warning("🚨 [CIRCUIT BREAKER] Google Bot Detection triggered!")
        self.circuit_breaker_event.clear()
        trigger_alert("Google Maps CAPTCHA Detected", "Solve the verification challenge in the browser window, then press ENTER in the terminal.")
        print("\n" + "="*70)
        print("⚠️ ACTION REQUIRED: Google Maps displayed a CAPTCHA or blocking screen.")
        print("Switch to the open browser window and complete the challenge manually.")
        input("Press [ENTER] in this console after you have resolved the verification...")
        print("Resuming extraction pipeline...\n" + "="*70)
        self.circuit_breaker_event.set()
        await asyncio.sleep(2.0)