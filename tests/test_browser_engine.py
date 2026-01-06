"""
Tests for the Browser Engine.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.browser_engine import BrowserEngine


class TestBrowserEngine:
    """Tests for BrowserEngine class."""
    
    @pytest.mark.asyncio
    async def test_start_creates_browser(self, mock_config):
        """Test that start() initializes the browser."""
        with patch("src.browser_engine.async_playwright") as mock_pw:
            # Setup mocks
            mock_playwright = AsyncMock()
            mock_browser = AsyncMock()
            mock_context = AsyncMock()
            mock_page = AsyncMock()
            
            mock_pw.return_value.start = AsyncMock(return_value=mock_playwright)
            mock_playwright.chromium.launch = AsyncMock(return_value=mock_browser)
            mock_browser.new_context = AsyncMock(return_value=mock_context)
            mock_context.new_page = AsyncMock(return_value=mock_page)
            
            engine = BrowserEngine(mock_config)
            await engine.start()
            
            # Verify browser was launched
            mock_playwright.chromium.launch.assert_called_once()
            mock_browser.new_context.assert_called_once()
            mock_context.new_page.assert_called_once()
            
            await engine.stop()
    
    @pytest.mark.asyncio
    async def test_navigate_success(self, mock_config, mock_browser_page):
        """Test successful navigation."""
        with patch("src.browser_engine.async_playwright") as mock_pw:
            mock_response = MagicMock()
            mock_response.ok = True
            mock_response.status = 200
            mock_browser_page.goto = AsyncMock(return_value=mock_response)
            
            # Setup engine with mocked page
            engine = BrowserEngine(mock_config)
            engine._page = mock_browser_page
            engine._playwright = AsyncMock()
            engine._browser = AsyncMock()
            engine._context = AsyncMock()
            
            result = await engine.navigate("https://example.com")
            
            assert result is True
            mock_browser_page.goto.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_click_success(self, mock_config, mock_browser_page):
        """Test successful click action."""
        engine = BrowserEngine(mock_config)
        engine._page = mock_browser_page
        engine._playwright = AsyncMock()
        engine._browser = AsyncMock()
        engine._context = AsyncMock()
        engine.config = mock_config
        
        result = await engine.click("#button")
        
        assert result is True
        mock_browser_page.click.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_type_text_success(self, mock_config, mock_browser_page):
        """Test successful type action."""
        engine = BrowserEngine(mock_config)
        engine._page = mock_browser_page
        engine._playwright = AsyncMock()
        engine._browser = AsyncMock()
        engine._context = AsyncMock()
        
        result = await engine.type_text("input[name='email']", "test@example.com")
        
        assert result is True
    
    @pytest.mark.asyncio
    async def test_take_screenshot(self, mock_config, mock_browser_page):
        """Test screenshot capture."""
        engine = BrowserEngine(mock_config)
        engine._page = mock_browser_page
        engine._playwright = AsyncMock()
        engine._browser = AsyncMock()
        engine._context = AsyncMock()
        
        screenshot = await engine.take_screenshot()
        
        assert screenshot == b"fake_screenshot"
        mock_browser_page.screenshot.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_scroll(self, mock_config, mock_browser_page):
        """Test scroll action."""
        engine = BrowserEngine(mock_config)
        engine._page = mock_browser_page
        engine._playwright = AsyncMock()
        engine._browser = AsyncMock()
        engine._context = AsyncMock()
        
        result = await engine.scroll("down")
        
        assert result is True
        mock_browser_page.evaluate.assert_called()
    
    @pytest.mark.asyncio
    async def test_go_back(self, mock_config, mock_browser_page):
        """Test back navigation."""
        mock_browser_page.go_back = AsyncMock()
        
        engine = BrowserEngine(mock_config)
        engine._page = mock_browser_page
        engine._playwright = AsyncMock()
        engine._browser = AsyncMock()
        engine._context = AsyncMock()
        
        result = await engine.go_back()
        
        assert result is True
        mock_browser_page.go_back.assert_called_once()

