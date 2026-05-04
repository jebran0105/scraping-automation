"""
CDP-attach mode: connect to a Chrome instance the user launched manually.

WHY: When Chrome is launched by Playwright/patchright, several detection
vectors light up regardless of stealth (CDP runtime hooks, automation flag,
parent process is Python, etc.). When Chrome is launched by the user as a
normal process and we just attach to its remote debugging port, none of
those signals exist. Imperva sees a regular user's Chrome.

PREREQUISITE — start Chrome manually with a debug port BEFORE running this.

  WINDOWS (cmd):
    "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe" ^
        --remote-debugging-port=9222 ^
        --user-data-dir="C:\\temp\\chrome-debug-profile"

  WINDOWS (PowerShell):
    & "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe" `
        --remote-debugging-port=9222 `
        --user-data-dir="C:\\temp\\chrome-debug-profile"

  macOS:
    /Applications/Google\\ Chrome.app/Contents/MacOS/Google\\ Chrome \\
        --remote-debugging-port=9222 \\
        --user-data-dir="$HOME/.chrome-debug-profile"

  Verify it's listening:
    curl http://localhost:9222/json/version

Then in that Chrome window, navigate to https://vcheck.ttc.lacounty.gov/
and let any Imperva challenge complete naturally. ONCE you can see the
real page, run this script.
"""

import asyncio
import random
import sys

from patchright.async_api import async_playwright


CDP_URL = "http://localhost:9222"


async def check_property_tax():
    async with async_playwright() as p:
        try:
            browser = await p.chromium.connect_over_cdp(CDP_URL)
        except Exception as e:
            print(f"ERROR: could not connect to Chrome at {CDP_URL}")
            print(f"       Did you launch Chrome with --remote-debugging-port=9222?")
            print(f"       Underlying error: {e}")
            sys.exit(1)

        # Reuse the existing context (the user's running session) instead of
        # making a new one — that way we inherit cookies, profile, fingerprint.
        if not browser.contexts:
            print("ERROR: no contexts available on the attached Chrome.")
            sys.exit(1)
        context = browser.contexts[0]

        # Find or open a page on the target domain. Prefer reusing an
        # existing tab if the user already navigated there.
        page = None
        for existing in context.pages:
            if "ttc.lacounty.gov" in existing.url:
                page = existing
                print(f"Reusing existing tab: {existing.url}")
                break
        if page is None:
            page = await context.new_page()
            await page.goto("https://vcheck.ttc.lacounty.gov/", wait_until="domcontentloaded")
            await page.wait_for_timeout(5000 + int(random.random() * 3000))

        # If we landed on the block page, bail loudly.
        if "404.html" in page.url or "vchecktst" in page.url:
            print(f"BLOCKED — current URL: {page.url}")
            print("Open the manually-launched Chrome and pass any Imperva")
            print("challenges by hand first, then re-run this script.")
            await browser.close()
            return

        await page.screenshot(path="result.png", full_page=True)
        print(f"URL: {page.url}")
        print(f"Title: {await page.title()}")

        # Click submit
        submit_btn = page.locator("#next")
        await submit_btn.wait_for(state="visible", timeout=10000)
        await submit_btn.scroll_into_view_if_needed()
        await page.wait_for_timeout(500 + int(random.random() * 500))
        await submit_btn.click()

        await page.wait_for_timeout(8000)
        await page.screenshot(path="result.png", full_page=True)
        print(f"After click URL: {page.url}")

        # IMPORTANT: do NOT call browser.close() — that would close the
        # user's real Chrome. Just disconnect.
        # patchright auto-disconnects on context exit.


if __name__ == "__main__":
    asyncio.run(check_property_tax())
