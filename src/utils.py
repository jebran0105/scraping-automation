"""
Utility functions for Browser Automation with LLM.

Provides rate limiting, retry logic, and helper functions.
"""

import asyncio
import time
import json
import re
from functools import wraps
from typing import Any, Callable, TypeVar
from loguru import logger

T = TypeVar("T")


class RateLimiter:
    """Rate limiter using token bucket algorithm."""
    
    def __init__(self, requests_per_minute: int = 30):
        self.requests_per_minute = requests_per_minute
        self.tokens = requests_per_minute
        self.last_update = time.time()
        self._lock = asyncio.Lock()
    
    async def acquire(self) -> None:
        """Acquire a token, waiting if necessary."""
        async with self._lock:
            now = time.time()
            elapsed = now - self.last_update
            
            # Replenish tokens based on elapsed time
            self.tokens = min(
                self.requests_per_minute,
                self.tokens + elapsed * (self.requests_per_minute / 60)
            )
            self.last_update = now
            
            if self.tokens < 1:
                # Wait for token to become available
                wait_time = (1 - self.tokens) * (60 / self.requests_per_minute)
                logger.debug(f"Rate limit reached, waiting {wait_time:.2f}s")
                await asyncio.sleep(wait_time)
                self.tokens = 1
            
            self.tokens -= 1


class CircuitBreaker:
    """Circuit breaker pattern for handling repeated failures."""
    
    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0,
        half_open_requests: int = 3
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_requests = half_open_requests
        
        self.failures = 0
        self.last_failure_time: float = 0
        self.state = "closed"  # closed, open, half-open
        self.half_open_successes = 0
    
    def can_execute(self) -> bool:
        """Check if execution is allowed."""
        if self.state == "closed":
            return True
        
        if self.state == "open":
            # Check if recovery timeout has passed
            if time.time() - self.last_failure_time >= self.recovery_timeout:
                self.state = "half-open"
                self.half_open_successes = 0
                logger.info("Circuit breaker entering half-open state")
                return True
            return False
        
        # half-open state
        return True
    
    def record_success(self) -> None:
        """Record a successful execution."""
        if self.state == "half-open":
            self.half_open_successes += 1
            if self.half_open_successes >= self.half_open_requests:
                self.state = "closed"
                self.failures = 0
                logger.info("Circuit breaker closed")
        else:
            self.failures = 0
    
    def record_failure(self) -> None:
        """Record a failed execution."""
        self.failures += 1
        self.last_failure_time = time.time()
        
        if self.state == "half-open":
            self.state = "open"
            logger.warning("Circuit breaker opened from half-open state")
        elif self.failures >= self.failure_threshold:
            self.state = "open"
            logger.warning(f"Circuit breaker opened after {self.failures} failures")


async def retry_with_backoff(
    func: Callable[..., T],
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    exponential_base: float = 2.0,
    exceptions: tuple = (Exception,)
) -> T:
    """
    Retry a function with exponential backoff.
    
    Args:
        func: Async function to retry
        max_retries: Maximum number of retries
        base_delay: Initial delay in seconds
        max_delay: Maximum delay in seconds
        exponential_base: Base for exponential calculation
        exceptions: Tuple of exceptions to catch and retry
    
    Returns:
        Result of the function
    
    Raises:
        Last exception if all retries fail
    """
    last_exception = None
    
    for attempt in range(max_retries + 1):
        try:
            return await func()
        except exceptions as e:
            last_exception = e
            if attempt < max_retries:
                delay = min(base_delay * (exponential_base ** attempt), max_delay)
                logger.warning(
                    f"Attempt {attempt + 1} failed: {e}. "
                    f"Retrying in {delay:.2f}s..."
                )
                await asyncio.sleep(delay)
            else:
                logger.error(f"All {max_retries + 1} attempts failed")
    
    raise last_exception


def clean_text(text: str, max_length: int = 5000) -> str:
    """
    Clean and truncate text content.
    
    Args:
        text: Raw text to clean
        max_length: Maximum length of output
    
    Returns:
        Cleaned and truncated text
    """
    if not text:
        return ""
    
    # Remove excessive whitespace
    text = re.sub(r'\s+', ' ', text)
    
    # Remove common script/style artifacts
    text = re.sub(r'<[^>]+>', '', text)
    
    # Truncate if necessary
    if len(text) > max_length:
        text = text[:max_length] + "... [truncated]"
    
    return text.strip()


def extract_json_from_text(text: str) -> dict | None:
    """
    Extract JSON from text that may contain markdown or other formatting.
    
    Args:
        text: Text possibly containing JSON
    
    Returns:
        Parsed JSON dict or None if extraction fails
    """
    # Try to find JSON in code blocks
    json_patterns = [
        r'```json\s*([\s\S]*?)\s*```',
        r'```\s*([\s\S]*?)\s*```',
        r'\{[\s\S]*\}',
    ]
    
    for pattern in json_patterns:
        matches = re.findall(pattern, text)
        for match in matches:
            try:
                # Clean the match
                clean_match = match.strip()
                if not clean_match.startswith('{'):
                    # Find the first { and last }
                    start = clean_match.find('{')
                    end = clean_match.rfind('}')
                    if start != -1 and end != -1:
                        clean_match = clean_match[start:end + 1]
                
                return json.loads(clean_match)
            except json.JSONDecodeError:
                continue
    
    # Try direct parse as last resort
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def generate_unique_selector(tag: str, attributes: dict, index: int = 0) -> str:
    """
    Generate a unique CSS selector for an element.
    
    Args:
        tag: HTML tag name
        attributes: Element attributes
        index: Element index for disambiguation
    
    Returns:
        CSS selector string
    """
    selector_parts = [tag]
    
    # Use ID if available (most specific)
    if 'id' in attributes and attributes['id']:
        return f"#{attributes['id']}"
    
    # Add class names
    if 'class' in attributes and attributes['class']:
        classes = attributes['class'].split()
        for cls in classes[:3]:  # Limit to first 3 classes
            if cls and not cls.startswith('_'):  # Skip generated classes
                selector_parts.append(f".{cls}")
    
    # Add data attributes
    for attr in ['data-testid', 'data-id', 'name', 'aria-label']:
        if attr in attributes and attributes[attr]:
            value = attributes[attr].replace('"', '\\"')
            selector_parts.append(f'[{attr}="{value}"]')
            break
    
    selector = ''.join(selector_parts)
    
    # Add nth-of-type if needed for disambiguation
    if index > 0:
        selector += f":nth-of-type({index + 1})"
    
    return selector


def truncate_for_prompt(text: str, max_tokens: int = 2000) -> str:
    """
    Truncate text to fit within token limits.
    
    Args:
        text: Text to truncate
        max_tokens: Approximate max tokens (4 chars per token estimate)
    
    Returns:
        Truncated text
    """
    max_chars = max_tokens * 4
    if len(text) <= max_chars:
        return text
    
    return text[:max_chars] + "\n... [content truncated for length]"


async def wait_for_stable_dom(page, timeout: int = 5000, check_interval: int = 100) -> bool:
    """
    Wait for DOM to stabilize (no new elements being added).
    
    Args:
        page: Playwright page object
        timeout: Maximum wait time in ms
        check_interval: Interval between checks in ms
    
    Returns:
        True if DOM stabilized, False if timeout
    """
    start_time = time.time() * 1000
    last_element_count = 0
    stable_checks = 0
    required_stable_checks = 3
    
    while (time.time() * 1000 - start_time) < timeout:
        current_count = await page.evaluate("document.querySelectorAll('*').length")
        
        if current_count == last_element_count:
            stable_checks += 1
            if stable_checks >= required_stable_checks:
                return True
        else:
            stable_checks = 0
            last_element_count = current_count
        
        await asyncio.sleep(check_interval / 1000)
    
    return False

