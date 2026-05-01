import asyncio
import os
import random
from pathlib import Path

from patchright.async_api import async_playwright


# Persistent profile dir so Imperva's incap_ses_* / visid_incap_* cookies
# survive between runs once we've passed the initial JS challenge.
PROFILE_DIR = Path(__file__).parent / ".chrome-profile"
PROFILE_DIR.mkdir(exist_ok=True)


async def check_property_tax():
    async with async_playwright() as p:
        # Key choices for beating Imperva (Error 15):
        # 1. launch_persistent_context (NOT launch + new_context) — patchright's
        #    stealth patches only kick in fully on persistent contexts.
        # 2. channel="chrome" — use the real Google Chrome binary, not bundled
        #    Chromium. Imperva fingerprints chrome.app / chrome.csi /
        #    chrome.loadTimes, and bundled Chromium has visible gaps.
        # 3. NO --no-sandbox, NO --disable-blink-features=AutomationControlled,
        #    NO --disable-web-security. These are all detection signals.
        # 4. headless=False until we confirm the site lets us in; many sites
        #    fingerprint the headless shell separately even with stealth.
        context = await p.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR),
            channel="chrome",
            headless=False,
            no_viewport=True,
            locale="en-US",
            timezone_id="America/Los_Angeles",
            args=[
                "--disable-blink-features=AutomationControlled",
            ],
            ignore_default_args=[
                "--enable-automation",
            ],
        )

        page = context.pages[0] if context.pages else await context.new_page()

        # Warm up with a "normal" referrer page first. Hitting the target
        # cold from about:blank is itself a signal — a real user usually
        # arrives via a search engine or the parent county site.
        await page.goto("https://ttc.lacounty.gov/", wait_until="domcontentloaded")
        await page.wait_for_timeout(2000 + int(random.random() * 2000))

        # Some human-ish mouse motion
        await page.mouse.move(
            200 + random.random() * 300,
            300 + random.random() * 200,
            steps=15,
        )
        await page.wait_for_timeout(400 + int(random.random() * 600))

        # Now navigate to the actual target.
        response = await page.goto(
            "https://vcheck.ttc.lacounty.gov/",
            wait_until="domcontentloaded",
        )
        # Give Imperva's JS challenge time to run and set its session cookies.
        await page.wait_for_timeout(5000 + int(random.random() * 3000))

        try:
            await page.wait_for_load_state("networkidle", timeout=15000)
        except Exception:
            pass

        # Save the landing state so we can see what came back.
        await page.screenshot(path="result.png", full_page=True)
        print(f"Status: {response.status if response else 'no response'}")
        print(f"Current URL: {page.url}")
        print(f"Title: {await page.title()}")

        # If we got blocked again, bail out with the cookies dumped so we
        # can inspect what (if any) Imperva tokens were set.
        if "404.html" in page.url or "vchecktst" in page.url:
            cookies = await context.cookies()
            print("\n=== STILL BLOCKED ===")
            for c in cookies:
                if "incap" in c["name"].lower() or "visid" in c["name"].lower():
                    print(f"  {c['name']}={c['value'][:40]}...")
            await context.close()
            return

        # We're past the challenge — proceed with the real flow.
        submit_btn = page.locator("#next")
        await submit_btn.wait_for(state="visible", timeout=10000)
        await submit_btn.scroll_into_view_if_needed()
        await page.wait_for_timeout(500 + int(random.random() * 500))
        await submit_btn.click()

        await page.wait_for_timeout(8000)
        await page.screenshot(path="result.png", full_page=True)
        print(f"After click URL: {page.url}")

        fp = await page.evaluate("""() => ({
            ua: navigator.userAgent,
            platform: navigator.platform,
            cores: navigator.hardwareConcurrency,
            mem: navigator.deviceMemory,
            screen: [screen.width, screen.height],
            inner: [innerWidth, innerHeight],
            webgl: (() => {
                const c = document.createElement('canvas').getContext('webgl');
                const d = c && c.getExtension('WEBGL_debug_renderer_info');
                return d ? [c.getParameter(d.UNMASKED_VENDOR_WEBGL), c.getParameter(d.UNMASKED_RENDERER_WEBGL)] : null;
            })(),
            tz: Intl.DateTimeFormat().resolvedOptions().timeZone,
            langs: navigator.languages,
        })""")
        print(fp)

        await context.close()


if __name__ == "__main__":
    asyncio.run(check_property_tax())
