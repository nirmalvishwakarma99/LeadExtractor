import asyncio
from playwright.async_api import Playwright, Browser, BrowserContext, Page

async def create_stealth_browser(p: Playwright, headless: bool) -> Browser:
    return await p.chromium.launch(
        headless=headless,
        args=[
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-web-security",
            "--disable-features=IsolateOrigins,site-per-process"
        ]
    )

async def create_stealth_context(browser: Browser) -> BrowserContext:
    context = await browser.new_context(
        viewport={"width": 1280, "height": 800},
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        locale="en-IN"
    )
    # Block heavy media resources while preserving fonts and stylesheets for selector accuracy
    await context.route("**/*", lambda route: (
        route.abort() if route.request.resource_type in ["media", "image"] else route.continue_()
    ))
    return context

async def detect_captcha(page: Page) -> bool:
    try:
        content = (await page.content()).lower()
        triggers = ["unusual traffic", "recaptcha", "prove you're not a robot", "sorry/index", "consent.google.com"]
        return any(t in content for t in triggers)
    except Exception:
        return False