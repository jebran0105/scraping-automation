"""
Browser Engine for Browser Automation with LLM.

Wraps Playwright for browser control with SPA-aware waiting strategies.
"""

import asyncio
from typing import Optional
from playwright.async_api import async_playwright, Browser, BrowserContext, Page, Playwright
from loguru import logger

from .config import Config, BrowserConfig, ProxyConfig


# Manual stealth scripts - more reliable than playwright-stealth library
STEALTH_SCRIPTS = """
// Overwrite the 'webdriver' property to return false
Object.defineProperty(navigator, 'webdriver', {
    get: () => false,
});

// Overwrite the 'plugins' property to return a non-empty array
Object.defineProperty(navigator, 'plugins', {
    get: () => [1, 2, 3, 4, 5],
});

// Overwrite the 'languages' property
Object.defineProperty(navigator, 'languages', {
    get: () => ['en-US', 'en'],
});

// Mock chrome runtime
window.chrome = {
    runtime: {},
};

// Mock permissions
const originalQuery = window.navigator.permissions.query;
window.navigator.permissions.query = (parameters) => (
    parameters.name === 'notifications' ?
        Promise.resolve({ state: Notification.permission }) :
        originalQuery(parameters)
);
"""


class BrowserEngine:
    """
    Manages Playwright browser lifecycle and navigation.
    
    Provides SPA-aware waiting strategies and robust page interactions.
    """
    
    def __init__(self, config: Config):
        self.config = config
        self.browser_config = config.browser
        self.proxy_config = config.proxy
        
        self._playwright: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None
    
    @property
    def page(self) -> Page:
        """Get the current page, raising if not initialized."""
        if self._page is None:
            raise RuntimeError("Browser not initialized. Call start() first.")
        return self._page
    
    @property
    def context(self) -> BrowserContext:
        """Get the browser context."""
        if self._context is None:
            raise RuntimeError("Browser not initialized. Call start() first.")
        return self._context
    
    async def start(self) -> None:
        """Initialize the browser and create a new page."""
        logger.info("Starting browser engine...")
        
        self._playwright = await async_playwright().start()
        
        # Prepare browser launch options - use args to avoid detection
        launch_options = {
            "headless": self.browser_config.headless,
            "slow_mo": self.browser_config.slow_mo,
            "args": [
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                "--no-sandbox",
                "--disable-web-security",
                "--disable-features=IsolateOrigins,site-per-process",
            ],
        }
        
        # Add proxy if configured
        if self.proxy_config.url:
            launch_options["proxy"] = {
                "server": self.proxy_config.url,
            }
            if self.proxy_config.username:
                launch_options["proxy"]["username"] = self.proxy_config.username
                launch_options["proxy"]["password"] = self.proxy_config.password
        
        self._browser = await self._playwright.chromium.launch(**launch_options)
        
        # Create context with viewport and realistic user agent
        default_user_agent = (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
        
        context_options = {
            "viewport": {
                "width": self.browser_config.viewport_width,
                "height": self.browser_config.viewport_height,
            },
            "user_agent": self.browser_config.user_agent or default_user_agent,
            "locale": "en-US",
            "timezone_id": "America/New_York",
        }
        
        self._context = await self._browser.new_context(**context_options)
        self._page = await self._context.new_page()
        
        # Apply stealth patches to avoid bot detection
        await self._apply_stealth()
        
        # Set default timeout
        self._page.set_default_timeout(self.browser_config.timeout)
        
        logger.info(
            f"Browser started: headless={self.browser_config.headless}, "
            f"viewport={self.browser_config.viewport_width}x{self.browser_config.viewport_height}, "
            "stealth=enabled"
        )
    
    async def _apply_stealth(self) -> None:
        """Apply stealth patches to avoid bot detection."""
        # Add init script that runs before any page script
        await self._context.add_init_script(STEALTH_SCRIPTS)
        logger.debug("Stealth patches applied")
    
    async def stop(self) -> None:
        """Close the browser and cleanup resources."""
        logger.info("Stopping browser engine...")
        
        if self._page:
            await self._page.close()
            self._page = None
        
        if self._context:
            await self._context.close()
            self._context = None
        
        if self._browser:
            await self._browser.close()
            self._browser = None
        
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None
        
        logger.info("Browser engine stopped")
    
    async def navigate(
        self,
        url: str,
        wait_until: str = "networkidle",
        timeout: Optional[int] = None
    ) -> bool:
        """
        Navigate to a URL and wait for page to be ready.
        
        Args:
            url: URL to navigate to
            wait_until: Wait strategy ('load', 'domcontentloaded', 'networkidle')
            timeout: Custom timeout in ms
        
        Returns:
            True if navigation succeeded
        """
        logger.info(f"Navigating to: {url}")
        
        try:
            response = await self.page.goto(
                url,
                wait_until=wait_until,
                timeout=timeout or self.browser_config.timeout
            )
            
            if response and response.ok:
                logger.debug(f"Navigation successful: {response.status}")
                # Additional wait for SPA content
                await self.wait_for_page_stable()
                return True
            else:
                status = response.status if response else "no response"
                logger.warning(f"Navigation returned status: {status}")
                return response.ok if response else False
                
        except Exception as e:
            logger.error(f"Navigation failed: {e}")
            return False
    
    async def wait_for_page_stable(
        self,
        timeout: int = 5000,
        check_interval: int = 100
    ) -> bool:
        """
        Wait for page to stabilize (DOM stops changing).
        
        Args:
            timeout: Maximum wait time in ms
            check_interval: Interval between checks in ms
        
        Returns:
            True if page stabilized within timeout
        """
        logger.debug("Waiting for page to stabilize...")
        
        start_time = asyncio.get_event_loop().time() * 1000
        last_element_count = 0
        stable_checks = 0
        required_stable_checks = 3
        
        while (asyncio.get_event_loop().time() * 1000 - start_time) < timeout:
            try:
                current_count = await self.page.evaluate(
                    "document.querySelectorAll('*').length"
                )
                
                if current_count == last_element_count:
                    stable_checks += 1
                    if stable_checks >= required_stable_checks:
                        logger.debug("Page stabilized")
                        return True
                else:
                    stable_checks = 0
                    last_element_count = current_count
                
                await asyncio.sleep(check_interval / 1000)
                
            except Exception as e:
                logger.debug(f"Stability check error: {e}")
                await asyncio.sleep(check_interval / 1000)
        
        logger.debug("Page stability timeout reached")
        return False
    
    async def wait_for_selector(
        self,
        selector: str,
        state: str = "visible",
        timeout: Optional[int] = None
    ) -> bool:
        """
        Wait for a selector to reach a specific state.
        
        Args:
            selector: CSS selector to wait for
            state: Target state ('attached', 'detached', 'visible', 'hidden')
            timeout: Custom timeout in ms
        
        Returns:
            True if selector reached state within timeout
        """
        try:
            await self.page.wait_for_selector(
                selector,
                state=state,
                timeout=timeout or self.browser_config.timeout
            )
            return True
        except Exception as e:
            logger.debug(f"Wait for selector '{selector}' failed: {e}")
            return False
    
    async def wait_for_network_idle(self, timeout: int = 5000) -> bool:
        """
        Wait for network to become idle.
        
        Args:
            timeout: Maximum wait time in ms
        
        Returns:
            True if network became idle within timeout
        """
        try:
            await self.page.wait_for_load_state("networkidle", timeout=timeout)
            return True
        except Exception:
            logger.debug("Network idle timeout reached")
            return False
    
    async def click(
        self,
        selector: str,
        timeout: Optional[int] = None,
        wait_after: bool = True
    ) -> bool:
        """
        Click on an element and optionally wait for page to stabilize.
        
        Args:
            selector: CSS selector of element to click
            timeout: Custom timeout in ms
            wait_after: Whether to wait for page stability after click
        
        Returns:
            True if click succeeded
        """
        logger.debug(f"Clicking: {selector}")
        
        try:
            await self.page.click(
                selector,
                timeout=timeout or self.browser_config.timeout
            )
            
            if wait_after:
                # Wait for any dynamic content to load
                await asyncio.sleep(self.config.rate_limit.action_delay_ms / 1000)
                await self.wait_for_page_stable()
            
            return True
            
        except Exception as e:
            logger.error(f"Click failed on '{selector}': {e}")
            return False
    
    async def type_text(
        self,
        selector: str,
        text: str,
        clear_first: bool = True,
        timeout: Optional[int] = None
    ) -> bool:
        """
        Type text into an input element.
        
        Args:
            selector: CSS selector of input element
            text: Text to type
            clear_first: Whether to clear existing content first
            timeout: Custom timeout in ms
        
        Returns:
            True if typing succeeded
        """
        logger.debug(f"Typing into: {selector}")
        
        try:
            locator = self.page.locator(selector)
            
            if clear_first:
                await locator.clear(timeout=timeout or self.browser_config.timeout)
            
            await locator.fill(text, timeout=timeout or self.browser_config.timeout)
            return True
            
        except Exception as e:
            logger.error(f"Type failed on '{selector}': {e}")
            return False
    
    async def select_option(
        self,
        selector: str,
        value: str,
        timeout: Optional[int] = None
    ) -> bool:
        """
        Select an option from a dropdown.
        
        Args:
            selector: CSS selector of select element
            value: Value to select
            timeout: Custom timeout in ms
        
        Returns:
            True if selection succeeded
        """
        logger.debug(f"Selecting '{value}' in: {selector}")
        
        try:
            await self.page.select_option(
                selector,
                value,
                timeout=timeout or self.browser_config.timeout
            )
            await self.wait_for_page_stable()
            return True
            
        except Exception as e:
            logger.error(f"Select failed on '{selector}': {e}")
            return False
    
    async def press_key(
        self,
        key: str,
        selector: Optional[str] = None
    ) -> bool:
        """
        Press a keyboard key.
        
        Args:
            key: Key to press (e.g., 'Enter', 'Tab', 'Escape')
            selector: Optional element to focus first
        
        Returns:
            True if key press succeeded
        """
        logger.debug(f"Pressing key: {key}")
        
        try:
            if selector:
                await self.page.focus(selector)
            
            await self.page.keyboard.press(key)
            return True
            
        except Exception as e:
            logger.error(f"Key press failed: {e}")
            return False
    
    async def scroll(
        self,
        direction: str = "down",
        amount: int = 500
    ) -> bool:
        """
        Scroll the page.
        
        Args:
            direction: 'up', 'down', 'top', or 'bottom'
            amount: Scroll amount in pixels (for up/down)
        
        Returns:
            True if scroll succeeded
        """
        logger.debug(f"Scrolling: {direction}")
        
        try:
            if direction == "top":
                await self.page.evaluate("window.scrollTo(0, 0)")
            elif direction == "bottom":
                await self.page.evaluate(
                    "window.scrollTo(0, document.body.scrollHeight)"
                )
            elif direction == "down":
                await self.page.evaluate(f"window.scrollBy(0, {amount})")
            elif direction == "up":
                await self.page.evaluate(f"window.scrollBy(0, -{amount})")
            
            await asyncio.sleep(0.3)  # Brief wait for lazy loading
            return True
            
        except Exception as e:
            logger.error(f"Scroll failed: {e}")
            return False
    
    async def go_back(self) -> bool:
        """
        Navigate back in browser history.
        
        Returns:
            True if navigation succeeded
        """
        logger.debug("Navigating back")
        
        try:
            await self.page.go_back(wait_until="networkidle")
            await self.wait_for_page_stable()
            return True
        except Exception as e:
            logger.error(f"Go back failed: {e}")
            return False
    
    async def take_screenshot(self, full_page: bool = False) -> bytes:
        """
        Take a screenshot of the current page.
        
        Args:
            full_page: Whether to capture the full scrollable page
        
        Returns:
            Screenshot as PNG bytes
        """
        return await self.page.screenshot(full_page=full_page, type="png")
    
    async def get_current_url(self) -> str:
        """Get the current page URL."""
        return self.page.url
    
    async def get_page_title(self) -> str:
        """Get the current page title."""
        return await self.page.title()
    
    async def evaluate(self, expression: str) -> any:
        """
        Evaluate JavaScript expression on the page.
        
        Args:
            expression: JavaScript expression to evaluate
        
        Returns:
            Result of the expression
        """
        return await self.page.evaluate(expression)
    
    async def hover(self, selector: str, timeout: Optional[int] = None) -> bool:
        """
        Hover over an element.
        
        Args:
            selector: CSS selector of element
            timeout: Custom timeout in ms
        
        Returns:
            True if hover succeeded
        """
        try:
            await self.page.hover(
                selector,
                timeout=timeout or self.browser_config.timeout
            )
            return True
        except Exception as e:
            logger.error(f"Hover failed on '{selector}': {e}")
            return False
    
    async def handle_dialog(self, accept: bool = True, prompt_text: str = "") -> None:
        """
        Set up dialog handling for alerts, confirms, and prompts.
        
        Args:
            accept: Whether to accept or dismiss the dialog
            prompt_text: Text to enter for prompt dialogs
        """
        async def handle(dialog):
            if accept:
                await dialog.accept(prompt_text)
            else:
                await dialog.dismiss()
        
        self.page.on("dialog", handle)
    
    async def get_cookies(self) -> list[dict]:
        """Get all cookies from the browser context."""
        return await self._context.cookies()
    
    async def set_cookies(self, cookies: list[dict]) -> None:
        """Set cookies in the browser context."""
        await self._context.add_cookies(cookies)

