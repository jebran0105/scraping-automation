import asyncio
import random
from pathlib import Path

from patchright.async_api import async_playwright


PROFILE_DIR = Path(__file__).parent / ".chrome-profile"
PROFILE_DIR.mkdir(exist_ok=True)


# Anti-fingerprint init script. Runs in every page/frame BEFORE any site JS,
# so Imperva's detection code reads the spoofed values instead of the
# VM-shaped ones (WARP renderer, deviceMemory=16, etc.).
FINGERPRINT_SPOOF_JS = r"""
(() => {
    // Pretend to be a stock Windows desktop with Intel UHD Graphics 630.
    // This is the single most common Windows GPU fingerprint, so spoofing
    // to it blends into the largest cluster of real users.
    const VENDOR   = 'Google Inc. (Intel)';
    const RENDERER = 'ANGLE (Intel, Intel(R) UHD Graphics 630 (0x00003E92) Direct3D11 vs_5_0 ps_5_0, D3D11)';

    const UNMASKED_VENDOR_WEBGL   = 0x9245;
    const UNMASKED_RENDERER_WEBGL = 0x9246;
    const MAX_TEXTURE_SIZE        = 0x0D33;

    const patchGetParameter = (proto) => {
        if (!proto || !proto.getParameter) return;
        const orig = proto.getParameter;
        proto.getParameter = function (param) {
            if (param === UNMASKED_VENDOR_WEBGL)   return VENDOR;
            if (param === UNMASKED_RENDERER_WEBGL) return RENDERER;
            // Real Intel UHD reports 16384; WARP reports 8192.
            if (param === MAX_TEXTURE_SIZE)        return 16384;
            return orig.call(this, param);
        };
    };
    if (typeof WebGLRenderingContext  !== 'undefined') patchGetParameter(WebGLRenderingContext.prototype);
    if (typeof WebGL2RenderingContext !== 'undefined') patchGetParameter(WebGL2RenderingContext.prototype);

    // Canvas pixel-noise injection. Imperva renders a known shape and hashes
    // the resulting pixels. WARP's software rasterizer produces a distinctive
    // hash; perturbing one bit in every 1024th byte breaks the hash without
    // being humanly visible, and changes the result from run to run.
    const noisePixels = (data) => {
        for (let i = 0; i < data.length; i += 1024) data[i] ^= 1;
    };
    const origToDataURL = HTMLCanvasElement.prototype.toDataURL;
    HTMLCanvasElement.prototype.toDataURL = function (...args) {
        try {
            const ctx = this.getContext('2d');
            if (ctx && this.width && this.height) {
                const img = ctx.getImageData(0, 0, this.width, this.height);
                noisePixels(img.data);
                ctx.putImageData(img, 0, 0);
            }
        } catch (e) {}
        return origToDataURL.apply(this, args);
    };
    const origGetImageData = CanvasRenderingContext2D.prototype.getImageData;
    CanvasRenderingContext2D.prototype.getImageData = function (...args) {
        const out = origGetImageData.apply(this, args);
        noisePixels(out.data);
        return out;
    };

    // The VM reports navigator.deviceMemory=16, but the W3C spec caps it
    // at 8. A non-spec value is itself a bot tell — clamp it back.
    try {
        Object.defineProperty(Navigator.prototype, 'deviceMemory', {
            get: () => 8, configurable: true,
        });
    } catch (e) {}

    // Lift hardwareConcurrency from 4 (VM-typical) to 8 (desktop-typical).
    try {
        Object.defineProperty(Navigator.prototype, 'hardwareConcurrency', {
            get: () => 8, configurable: true,
        });
    } catch (e) {}
})();
"""


async def check_property_tax():
    async with async_playwright() as p:
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

        # Apply spoof BEFORE any navigation so it covers every page/frame.
        await context.add_init_script(FINGERPRINT_SPOOF_JS)

        page = context.pages[0] if context.pages else await context.new_page()

        # Sanity check: verify the spoof is active by dumping fingerprint
        # on about:blank before we hit the target. Compare to the previous
        # VM dump — webgl renderer should now claim Intel UHD, not WARP.
        await page.goto("about:blank")
        fp = await page.evaluate("""() => ({
            cores: navigator.hardwareConcurrency,
            mem:   navigator.deviceMemory,
            webgl: (() => {
                const c = document.createElement('canvas').getContext('webgl');
                const d = c && c.getExtension('WEBGL_debug_renderer_info');
                return d ? [c.getParameter(d.UNMASKED_VENDOR_WEBGL),
                            c.getParameter(d.UNMASKED_RENDERER_WEBGL)] : null;
            })(),
        })""")
        print(f"Spoofed fingerprint: {fp}")

        await page.goto("https://ttc.lacounty.gov/", wait_until="domcontentloaded")
        await page.wait_for_timeout(2000 + int(random.random() * 2000))

        await page.mouse.move(
            200 + random.random() * 300,
            300 + random.random() * 200,
            steps=15,
        )
        await page.wait_for_timeout(400 + int(random.random() * 600))

        response = await page.goto(
            "https://vcheck.ttc.lacounty.gov/",
            wait_until="domcontentloaded",
        )
        await page.wait_for_timeout(5000 + int(random.random() * 3000))

        try:
            await page.wait_for_load_state("networkidle", timeout=15000)
        except Exception:
            pass

        await page.screenshot(path="result.png", full_page=True)
        print(f"Status: {response.status if response else 'no response'}")
        print(f"Current URL: {page.url}")
        print(f"Title: {await page.title()}")

        if "404.html" in page.url or "vchecktst" in page.url:
            cookies = await context.cookies()
            print("\n=== STILL BLOCKED ===")
            for c in cookies:
                if "incap" in c["name"].lower() or "visid" in c["name"].lower():
                    print(f"  {c['name']}={c['value'][:40]}...")
            await context.close()
            return

        submit_btn = page.locator("#next")
        await submit_btn.wait_for(state="visible", timeout=10000)
        await submit_btn.scroll_into_view_if_needed()
        await page.wait_for_timeout(500 + int(random.random() * 500))
        await submit_btn.click()

        await page.wait_for_timeout(8000)
        await page.screenshot(path="result.png", full_page=True)
        print(f"After click URL: {page.url}")

        await context.close()


if __name__ == "__main__":
    asyncio.run(check_property_tax())
