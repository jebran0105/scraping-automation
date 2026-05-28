import asyncio
from pydoll.browser.chromium import Chrome

async def main():
    async with Chrome() as browser:
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
