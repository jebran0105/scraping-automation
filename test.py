import asyncio
from pydoll.browser.chromium import Chrome
from pydoll.browser.options import Options

async def main():
    options = Options()
    options.add_argument('--user-data-dir=PASTE_PROFILE_PATH_HERE')
    options.add_argument('--profile-directory=Default')

    async with Chrome(options=options) as browser:
        tab = await browser.start()
        await tab.go_to('https://vcheck.ttc.lacounty.gov')
        await asyncio.sleep(3)

        submit_button = await tab.find(
            id='next',
            timeout=10,
            raise_exc=False
        )

        if not submit_button:
            print("Button not found")
            return

        print("Found button, clicking...")
        await submit_button.click()
        await asyncio.sleep(5)

        input("Press Enter to close...")

asyncio.run(main())
