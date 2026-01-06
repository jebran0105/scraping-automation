"""
Configuration management for Browser Automation with LLM.

Loads settings from environment variables and provides defaults.
"""

import os
from pathlib import Path
from typing import Optional
from pydantic import BaseModel, Field
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


class BrowserConfig(BaseModel):
    """Browser-related configuration."""
    headless: bool = Field(default=True, description="Run browser in headless mode")
    viewport_width: int = Field(default=1280, description="Browser viewport width")
    viewport_height: int = Field(default=720, description="Browser viewport height")
    user_agent: Optional[str] = Field(default=None, description="Custom user agent")
    timeout: int = Field(default=30000, description="Default timeout in ms")
    slow_mo: int = Field(default=0, description="Slow down actions by ms")


class ProxyConfig(BaseModel):
    """Proxy configuration."""
    url: Optional[str] = Field(default=None, description="Proxy URL")
    username: Optional[str] = Field(default=None, description="Proxy username")
    password: Optional[str] = Field(default=None, description="Proxy password")


class LLMConfig(BaseModel):
    """LLM-related configuration."""
    api_key: str = Field(description="Gemini API key")
    model: str = Field(default="gemini-2.5-flash", description="Model to use")
    max_tokens: int = Field(default=4096, description="Max response tokens")
    temperature: float = Field(default=0.1, description="Response temperature")
    include_screenshot: bool = Field(default=True, description="Include screenshots")
    max_history: int = Field(default=10, description="Max history items for context")


class RateLimitConfig(BaseModel):
    """Rate limiting configuration."""
    requests_per_minute: int = Field(default=30, description="Max requests per minute")
    action_delay_ms: int = Field(default=500, description="Delay between actions")


class OutputConfig(BaseModel):
    """Output configuration."""
    output_dir: Path = Field(default=Path("./output"), description="Output directory")
    screenshot_on_error: bool = Field(default=True, description="Screenshot on errors")
    save_screenshots: bool = Field(default=False, description="Save all screenshots")


class Config(BaseModel):
    """Main configuration container."""
    browser: BrowserConfig = Field(default_factory=BrowserConfig)
    proxy: ProxyConfig = Field(default_factory=ProxyConfig)
    llm: LLMConfig
    rate_limit: RateLimitConfig = Field(default_factory=RateLimitConfig)
    output: OutputConfig = Field(default_factory=OutputConfig)
    log_level: str = Field(default="INFO", description="Logging level")
    
    @classmethod
    def from_env(cls) -> "Config":
        """Load configuration from environment variables."""
        # Get API key (required)
        api_key = os.getenv("GEMINI_API_KEY", "")
        if not api_key:
            raise ValueError("GEMINI_API_KEY environment variable is required")
        
        # Browser config
        browser = BrowserConfig(
            headless=os.getenv("HEADLESS", "true").lower() == "true",
            viewport_width=int(os.getenv("VIEWPORT_WIDTH", "1280")),
            viewport_height=int(os.getenv("VIEWPORT_HEIGHT", "720")),
            user_agent=os.getenv("USER_AGENT"),
            timeout=int(os.getenv("BROWSER_TIMEOUT", "30000")),
            slow_mo=int(os.getenv("SLOW_MO", "0")),
        )
        
        # Proxy config
        proxy = ProxyConfig(
            url=os.getenv("PROXY_URL"),
            username=os.getenv("PROXY_USERNAME"),
            password=os.getenv("PROXY_PASSWORD"),
        )
        
        # LLM config
        llm = LLMConfig(
            api_key=api_key,
            model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
            max_tokens=int(os.getenv("MAX_TOKENS", "4096")),
            temperature=float(os.getenv("TEMPERATURE", "0.1")),
            include_screenshot=os.getenv("INCLUDE_SCREENSHOT", "true").lower() == "true",
            max_history=int(os.getenv("MAX_HISTORY", "10")),
        )
        
        # Rate limit config
        rate_limit = RateLimitConfig(
            requests_per_minute=int(os.getenv("REQUESTS_PER_MINUTE", "30")),
            action_delay_ms=int(os.getenv("ACTION_DELAY_MS", "500")),
        )
        
        # Output config
        output = OutputConfig(
            output_dir=Path(os.getenv("OUTPUT_DIR", "./output")),
            screenshot_on_error=os.getenv("SCREENSHOT_ON_ERROR", "true").lower() == "true",
            save_screenshots=os.getenv("SAVE_SCREENSHOTS", "false").lower() == "true",
        )
        
        return cls(
            browser=browser,
            proxy=proxy,
            llm=llm,
            rate_limit=rate_limit,
            output=output,
            log_level=os.getenv("LOG_LEVEL", "INFO"),
        )


def get_config() -> Config:
    """Get the configuration singleton."""
    return Config.from_env()

