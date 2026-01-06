"""
Test fixtures for Browser Automation with LLM.
"""

import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path

from src.config import Config, BrowserConfig, LLMConfig, RateLimitConfig, OutputConfig
from src.models import PageState, ActionableElement, ElementType, Instruction, ActionType


@pytest.fixture
def mock_config():
    """Create a mock configuration for testing."""
    return Config(
        browser=BrowserConfig(
            headless=True,
            viewport_width=1280,
            viewport_height=720,
            timeout=5000
        ),
        llm=LLMConfig(
            api_key="test_api_key",
            model="gemini-2.5-flash",
            include_screenshot=False
        ),
        rate_limit=RateLimitConfig(
            requests_per_minute=60,
            action_delay_ms=100
        ),
        output=OutputConfig(
            output_dir=Path("./test_output")
        )
    )


@pytest.fixture
def sample_page_state():
    """Create a sample page state for testing."""
    return PageState(
        url="https://example.com",
        title="Example Domain",
        actionable_elements=[
            ActionableElement(
                selector="#submit-btn",
                element_type=ElementType.BUTTON,
                label="Submit",
                visible=True,
                enabled=True
            ),
            ActionableElement(
                selector="input[name='email']",
                element_type=ElementType.INPUT,
                label="Email",
                placeholder="Enter your email",
                visible=True,
                enabled=True
            ),
            ActionableElement(
                selector="a.nav-link",
                element_type=ElementType.LINK,
                label="Home",
                visible=True,
                enabled=True
            )
        ],
        text_content="Welcome to Example Domain. This is for examples.",
        forms=[
            {
                "id": "contact-form",
                "action": "/submit",
                "method": "post",
                "inputs": [
                    {"name": "email", "type": "email", "label": "Email", "required": True},
                    {"name": "message", "type": "textarea", "label": "Message", "required": False}
                ]
            }
        ]
    )


@pytest.fixture
def sample_instruction():
    """Create a sample instruction for testing."""
    return Instruction(
        action=ActionType.CLICK,
        selector="#submit-btn",
        reasoning="Clicking the submit button to submit the form"
    )


@pytest.fixture
def mock_browser_page():
    """Create a mock Playwright page."""
    page = AsyncMock()
    page.url = "https://example.com"
    page.title = AsyncMock(return_value="Example Domain")
    page.goto = AsyncMock()
    page.click = AsyncMock()
    page.fill = AsyncMock()
    page.evaluate = AsyncMock(return_value=[])
    page.screenshot = AsyncMock(return_value=b"fake_screenshot")
    page.wait_for_selector = AsyncMock()
    page.wait_for_load_state = AsyncMock()
    page.locator = MagicMock()
    page.locator.return_value.count = AsyncMock(return_value=1)
    page.locator.return_value.clear = AsyncMock()
    page.locator.return_value.fill = AsyncMock()
    return page


@pytest.fixture
def mock_browser_context():
    """Create a mock Playwright browser context."""
    context = AsyncMock()
    context.new_page = AsyncMock()
    context.cookies = AsyncMock(return_value=[])
    context.add_cookies = AsyncMock()
    return context


@pytest.fixture
def mock_browser():
    """Create a mock Playwright browser."""
    browser = AsyncMock()
    browser.new_context = AsyncMock()
    browser.close = AsyncMock()
    return browser


@pytest_asyncio.fixture
async def mock_playwright():
    """Create a mock Playwright instance."""
    playwright = AsyncMock()
    playwright.chromium.launch = AsyncMock()
    playwright.stop = AsyncMock()
    return playwright

