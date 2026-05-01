import asyncio
import random
from pathlib import Path
from patchright.async_api import async_playwright

PROFILE_DIR = Path(__file__).parent / ".chrome-profile"
PROFILE_DIR.mkdir(exist_ok=True)

async def check_property_tax():
    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR),
            channel="chrome",
            headless=False,
            no_viewport=True,
            locale="en-US",
            timezone_id="America/Los_Angeles",
            args=["--disable-blink-features=AutomationControlled"],
            ignore_default_args=["--enable-automation"],
        )

        page = context.pages[0] if context.pages else await context.new_page()

        # Inject Imperva cookies before navigating
        await context.add_cookies([
            {
                "name": "incap_ses_1814_2175966",
                "value": "VMyyFHTLKXAJVWMDF6AsGZqe9GkAAAAANPMFUFsEC3OdQOHRuNapUA==",
                "domain": ".ttc.lacounty.gov",
                "path": "/",
            },
            {
                "name": "visid_incap_2175966",
                "value": "2poQ1v4kS5u6DQJWnhl6l5me9GkAAAAAQUIPAAAAAAB/k48Ct1y9EqWbUppWy3eM",
                "domain": ".ttc.lacounty.gov",
                "path": "/",
            }
        ])

        # Warm up
        await page.goto("https://ttc.lacounty.gov/", wait_until="domcontentloaded")
        await page.wait_for_timeout(2000 + int(random.random() * 2000))

        await page.mouse.move(200 + random.random() * 300, 300 + random.random() * 200, steps=15)
        await page.wait_for_timeout(400 + int(random.random() * 600))

        await page.goto("https://vcheck.ttc.lacounty.gov/", wait_until="domcontentloaded")
        await page.wait_for_timeout(5000 + int(random.random() * 3000))

        await page.screenshot(path="result.png", full_page=True)
        print(f"URL: {page.url}")
        print(f"Title: {await page.title()}")

        if "404.html" in page.url or "vchecktst" in page.url:
            print("Still blocked")
            await context.close()
            return

        # Click submit
        submit_btn = page.locator("#next")
        await submit_btn.wait_for(state="visible", timeout=10000)
        await submit_btn.scroll_into_view_if_needed()
        await page.wait_for_timeout(500 + int(random.random() * 500))
        await submit_btn.click()

        await page.wait_for_timeout(8000)
        await page.screenshot(path="result.png", full_page=True)
        print(f"After click URL: {page.url}")

        await context.close()

asyncio.run(check_property_tax())
