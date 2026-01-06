"""
Instruction Executor for Browser Automation with LLM.

Executes instructions from the LLM on the browser.
"""

import asyncio
import time
from typing import Optional
from loguru import logger

from .models import Instruction, ActionType, ActionResult
from .browser_engine import BrowserEngine
from .config import Config


class InstructionExecutor:
    """
    Executes LLM instructions on the browser.
    
    Handles all action types and provides robust error handling.
    """
    
    def __init__(self, browser: BrowserEngine, config: Config):
        """
        Initialize the instruction executor.
        
        Args:
            browser: Browser engine instance
            config: Configuration object
        """
        self.browser = browser
        self.config = config
        self.action_delay = config.rate_limit.action_delay_ms / 1000
    
    async def execute(self, instruction: Instruction) -> ActionResult:
        """
        Execute an instruction and return the result.
        
        Args:
            instruction: Instruction to execute
        
        Returns:
            ActionResult with success status and details
        """
        start_time = time.time()
        
        logger.info(
            f"Executing: {instruction.action.value}"
            f"{' on ' + instruction.selector if instruction.selector else ''}"
            f" - {instruction.reasoning[:50] if instruction.reasoning else ''}"
        )
        
        try:
            # Add delay between actions
            await asyncio.sleep(self.action_delay)
            
            # Route to appropriate handler
            success, error = await self._execute_action(instruction)
            
            duration_ms = int((time.time() - start_time) * 1000)
            
            # Take screenshot after action if configured
            screenshot_after = None
            if self.config.output.save_screenshots:
                try:
                    screenshot_after = await self.browser.take_screenshot()
                except Exception:
                    pass
            
            result = ActionResult(
                success=success,
                action=instruction.action,
                selector=instruction.selector,
                error=error,
                duration_ms=duration_ms,
                screenshot_after=screenshot_after
            )
            
            if success:
                logger.debug(f"Action succeeded in {duration_ms}ms")
            else:
                logger.warning(f"Action failed: {error}")
            
            return result
            
        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            error_msg = str(e)
            logger.error(f"Execution error: {error_msg}")
            
            return ActionResult(
                success=False,
                action=instruction.action,
                selector=instruction.selector,
                error=error_msg,
                duration_ms=duration_ms
            )
    
    async def _execute_action(self, instruction: Instruction) -> tuple[bool, Optional[str]]:
        """
        Execute the specific action type.
        
        Returns:
            Tuple of (success, error_message)
        """
        action = instruction.action
        
        if action == ActionType.CLICK:
            return await self._execute_click(instruction)
        
        elif action == ActionType.TYPE:
            return await self._execute_type(instruction)
        
        elif action == ActionType.NAVIGATE:
            return await self._execute_navigate(instruction)
        
        elif action == ActionType.WAIT:
            return await self._execute_wait(instruction)
        
        elif action == ActionType.BACK:
            return await self._execute_back(instruction)
        
        elif action == ActionType.SCROLL:
            return await self._execute_scroll(instruction)
        
        elif action == ActionType.SELECT:
            return await self._execute_select(instruction)
        
        elif action == ActionType.HOVER:
            return await self._execute_hover(instruction)
        
        elif action == ActionType.PRESS:
            return await self._execute_press(instruction)
        
        elif action == ActionType.EXTRACT:
            # Extract is handled by the main loop
            return True, None
        
        elif action == ActionType.DONE:
            # Done is handled by the main loop
            return True, None
        
        elif action == ActionType.ASK_USER:
            # Ask user is handled by the main loop
            return True, None
        
        else:
            return False, f"Unknown action type: {action}"
    
    async def _execute_click(self, instruction: Instruction) -> tuple[bool, Optional[str]]:
        """Execute a click action."""
        if not instruction.selector:
            return False, "Click requires a selector"
        
        # First, check if selector exists
        exists = await self._check_selector_exists(instruction.selector)
        if not exists:
            return False, f"Selector not found: {instruction.selector}"
        
        success = await self.browser.click(
            instruction.selector,
            timeout=instruction.timeout
        )
        
        if success:
            return True, None
        else:
            return False, f"Click failed on: {instruction.selector}"
    
    async def _execute_type(self, instruction: Instruction) -> tuple[bool, Optional[str]]:
        """Execute a type action."""
        if not instruction.selector:
            return False, "Type requires a selector"
        
        if instruction.value is None:
            return False, "Type requires a value"
        
        # Check if selector exists
        exists = await self._check_selector_exists(instruction.selector)
        if not exists:
            return False, f"Selector not found: {instruction.selector}"
        
        success = await self.browser.type_text(
            instruction.selector,
            instruction.value,
            timeout=instruction.timeout
        )
        
        if success:
            return True, None
        else:
            return False, f"Type failed on: {instruction.selector}"
    
    async def _execute_navigate(self, instruction: Instruction) -> tuple[bool, Optional[str]]:
        """Execute a navigate action."""
        if not instruction.url:
            return False, "Navigate requires a URL"
        
        success = await self.browser.navigate(
            instruction.url,
            timeout=instruction.timeout
        )
        
        if success:
            return True, None
        else:
            return False, f"Navigation failed to: {instruction.url}"
    
    async def _execute_wait(self, instruction: Instruction) -> tuple[bool, Optional[str]]:
        """Execute a wait action."""
        # If a selector is provided, wait for it
        if instruction.selector:
            success = await self.browser.wait_for_selector(
                instruction.selector,
                timeout=instruction.timeout
            )
            if success:
                return True, None
            else:
                return False, f"Wait for selector timed out: {instruction.selector}"
        
        # Otherwise, wait for page stability
        await self.browser.wait_for_page_stable(timeout=instruction.timeout)
        return True, None
    
    async def _execute_back(self, instruction: Instruction) -> tuple[bool, Optional[str]]:
        """Execute a back navigation."""
        success = await self.browser.go_back()
        
        if success:
            return True, None
        else:
            return False, "Back navigation failed"
    
    async def _execute_scroll(self, instruction: Instruction) -> tuple[bool, Optional[str]]:
        """Execute a scroll action."""
        direction = instruction.direction or "down"
        success = await self.browser.scroll(direction=direction)
        
        if success:
            return True, None
        else:
            return False, f"Scroll {direction} failed"
    
    async def _execute_select(self, instruction: Instruction) -> tuple[bool, Optional[str]]:
        """Execute a select option action."""
        if not instruction.selector:
            return False, "Select requires a selector"
        
        if instruction.value is None:
            return False, "Select requires a value"
        
        success = await self.browser.select_option(
            instruction.selector,
            instruction.value,
            timeout=instruction.timeout
        )
        
        if success:
            return True, None
        else:
            return False, f"Select failed on: {instruction.selector}"
    
    async def _execute_hover(self, instruction: Instruction) -> tuple[bool, Optional[str]]:
        """Execute a hover action."""
        if not instruction.selector:
            return False, "Hover requires a selector"
        
        success = await self.browser.hover(
            instruction.selector,
            timeout=instruction.timeout
        )
        
        if success:
            return True, None
        else:
            return False, f"Hover failed on: {instruction.selector}"
    
    async def _execute_press(self, instruction: Instruction) -> tuple[bool, Optional[str]]:
        """Execute a key press action."""
        if not instruction.key:
            return False, "Press requires a key"
        
        success = await self.browser.press_key(
            instruction.key,
            selector=instruction.selector
        )
        
        if success:
            return True, None
        else:
            return False, f"Press key failed: {instruction.key}"
    
    async def _check_selector_exists(self, selector: str) -> bool:
        """Check if a selector exists on the page."""
        try:
            locator = self.browser.page.locator(selector)
            count = await locator.count()
            return count > 0
        except Exception as e:
            logger.debug(f"Selector check failed for '{selector}': {e}")
            return False
    
    async def retry_with_alternatives(
        self,
        instruction: Instruction,
        alternatives: list[str]
    ) -> ActionResult:
        """
        Try alternative selectors if the primary one fails.
        
        Args:
            instruction: Original instruction
            alternatives: List of alternative selectors
        
        Returns:
            ActionResult from successful alternative or final failure
        """
        # Try the original instruction first
        result = await self.execute(instruction)
        if result.success:
            return result
        
        # Try alternatives
        for alt_selector in alternatives:
            logger.debug(f"Trying alternative selector: {alt_selector}")
            alt_instruction = instruction.model_copy()
            alt_instruction.selector = alt_selector
            
            result = await self.execute(alt_instruction)
            if result.success:
                logger.info(f"Alternative selector worked: {alt_selector}")
                return result
        
        # All alternatives failed
        return result

