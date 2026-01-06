"""
LLM Client for Browser Automation with LLM.

Interfaces with Google Gemini Chat API for interactive navigation instructions.
"""

import json
from typing import Optional
from google import genai
from google.genai import types
from loguru import logger

from .models import Instruction, ActionType, PageState, ExecutionContext
from .config import LLMConfig
from .utils import extract_json_from_text, RateLimiter


# System instruction for the LLM
SYSTEM_INSTRUCTION = """You are an interactive browser automation assistant. You help users navigate websites and extract information through a conversational interface.

You receive:
1. The current page state with a LIST OF ACTIONABLE ELEMENTS - each has a "selector" field
2. Optionally, a screenshot of the page
3. The user's goal or instructions
4. History of previous actions

You must respond with a JSON object containing the next action:

{
    "action": "click" | "type" | "navigate" | "extract" | "wait" | "back" | "scroll" | "select" | "press" | "ask_user",
    "selector": "MUST be copied EXACTLY from the actionable elements list",
    "value": "text to type (for type action)",
    "url": "URL to navigate to (for navigate action)",
    "key": "keyboard key to press (for press action, e.g., 'Enter', 'Tab')",
    "direction": "scroll direction: 'up', 'down', 'top', 'bottom' (for scroll action)",
    "reasoning": "brief explanation of why you chose this action",
    "extracted_data": "structured data when action is 'extract'",
    "question": "question to ask the user (for ask_user action)",
    "options": ["option 1", "option 2", "option 3"] // optional numbered choices for ask_user
}

CRITICAL SELECTOR RULES:
1. ONLY use selectors that appear EXACTLY in the "Actionable Elements" list
2. NEVER invent, modify, or construct your own CSS selectors
3. Copy the selector string EXACTLY as shown - do not add nth-child, nth-of-type, or other modifiers
4. If you can't find a matching selector in the list, use "ask_user" to ask for help
5. If an action fails, use "scroll" to reveal more elements or "ask_user" for guidance

CRITICAL BEHAVIOR RULES:
1. NEVER use "done" action - only the USER decides when the session ends
2. After completing a task or finding results, ALWAYS use "ask_user" to ask what to do next
3. When you see search results or a list of items, use "ask_user" to let the user choose
4. When an action fails repeatedly, use "ask_user" to get user guidance - don't keep retrying

ALWAYS use "ask_user" when:
- You've found search results - ask which one to explore
- You've completed extracting data - ask what to do next
- Multiple options/paths exist - let user choose
- You're uncertain about what to do
- An action has failed - ask for help
- You can't find the right selector

When using ask_user:
- Describe what you see on the page
- List the available clickable elements by their labels
- Ask what the user wants to do next

IMPORTANT: Respond ONLY with valid JSON, no markdown or extra text."""


class LLMClient:
    """
    Client for Google Gemini Chat API.
    
    Uses multi-turn chat for interactive browser automation with user feedback.
    """
    
    def __init__(self, config: LLMConfig):
        """
        Initialize the LLM client.
        
        Args:
            config: LLM configuration
        """
        self.config = config
        self.client = genai.Client(api_key=config.api_key)
        self.rate_limiter = RateLimiter(requests_per_minute=30)
        self.chat = None
        self._initialize_chat()
    
    def _initialize_chat(self) -> None:
        """Initialize a new chat session."""
        self.chat = self.client.chats.create(
            model=self.config.model,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_INSTRUCTION,
                temperature=self.config.temperature,
                max_output_tokens=self.config.max_tokens,
            )
        )
        logger.debug("Chat session initialized")
    
    async def get_instruction(
        self,
        page_state: PageState,
        goal: str,
        context: Optional[ExecutionContext] = None,
        page_state_text: Optional[str] = None,
        user_response: Optional[str] = None
    ) -> Instruction:
        """
        Get the next instruction from the LLM.
        
        Args:
            page_state: Current page state
            goal: User's goal for the automation
            context: Execution context with history
            page_state_text: Pre-formatted page state text
            user_response: User's response to a previous question
        
        Returns:
            Instruction object with the next action
        """
        # Rate limiting
        await self.rate_limiter.acquire()
        
        # Build the message content
        contents = []
        
        # Add screenshot if available
        if page_state.screenshot and self.config.include_screenshot:
            contents.append(
                types.Part.from_bytes(
                    data=page_state.screenshot,
                    mime_type="image/png"
                )
            )
        
        # Build text prompt
        prompt = self._build_prompt(page_state, goal, context, page_state_text, user_response)
        contents.append(prompt)
        
        logger.debug(f"Sending message to Gemini chat ({self.config.model})...")
        
        try:
            # Send message in the chat
            response = self.chat.send_message(contents)
            
            # Parse the response
            instruction = self._parse_response(response.text)
            
            logger.debug(f"LLM instruction: {instruction.action.value} - {instruction.reasoning[:50]}")
            return instruction
            
        except Exception as e:
            logger.error(f"LLM request failed: {e}")
            # Return a wait instruction on error
            return Instruction(
                action=ActionType.ASK_USER,
                question=f"I encountered an error: {str(e)}. How would you like me to proceed?",
                reasoning=f"Error occurred: {str(e)}"
            )
    
    async def send_user_response(self, user_response: str) -> Instruction:
        """
        Send a user response to the ongoing chat.
        
        Args:
            user_response: The user's text response
        
        Returns:
            Next instruction from the LLM
        """
        await self.rate_limiter.acquire()
        
        logger.debug(f"Sending user response: {user_response[:50]}...")
        
        try:
            response = self.chat.send_message(f"User response: {user_response}")
            instruction = self._parse_response(response.text)
            return instruction
            
        except Exception as e:
            logger.error(f"Failed to process user response: {e}")
            return Instruction(
                action=ActionType.WAIT,
                reasoning=f"Error processing response: {str(e)}"
            )
    
    def _build_prompt(
        self,
        page_state: PageState,
        goal: str,
        context: Optional[ExecutionContext],
        page_state_text: Optional[str],
        user_response: Optional[str]
    ) -> str:
        """Build the prompt for the LLM."""
        parts = [
            f"GOAL: {goal}",
            ""
        ]
        
        # Add user response if provided
        if user_response:
            parts.append(f"USER RESPONSE: {user_response}")
            parts.append("")
        
        # Add execution history if available
        if context and context.history:
            parts.append("PREVIOUS ACTIONS:")
            parts.append(context.get_history_summary(last_n=5))
            parts.append("")
        
        # Add current page state
        parts.append("CURRENT PAGE STATE:")
        if page_state_text:
            parts.append(page_state_text)
        else:
            parts.append(f"URL: {page_state.url}")
            parts.append(f"Title: {page_state.title}")
            parts.append("")
            
            # Add elements
            parts.append("Actionable Elements:")
            for i, el in enumerate(page_state.actionable_elements[:30], 1):
                label = el.label or el.placeholder or el.aria_label or "(no label)"
                parts.append(
                    f"{i}. [{el.element_type.value}] "
                    f'selector="{el.selector}" '
                    f'label="{label[:40]}"'
                )
            
            # Add text excerpt
            if page_state.text_content:
                parts.append("")
                parts.append("Page text excerpt:")
                parts.append(page_state.text_content[:1500])
        
        parts.append("")
        parts.append("What is the next action to achieve the goal? Respond with JSON only.")
        
        return "\n".join(parts)
    
    def _parse_response(self, response_text: str) -> Instruction:
        """Parse the LLM response into an Instruction."""
        # Try to extract JSON from the response
        data = extract_json_from_text(response_text)
        
        if not data:
            logger.warning(f"Could not parse JSON from response: {response_text[:200]}")
            return Instruction(
                action=ActionType.ASK_USER,
                question="I had trouble understanding the page. Could you provide more guidance?",
                reasoning="Failed to parse LLM response"
            )
        
        try:
            # Map action string to ActionType
            action_str = data.get("action", "wait").lower()
            try:
                action = ActionType(action_str)
            except ValueError:
                logger.warning(f"Unknown action type: {action_str}")
                action = ActionType.ASK_USER
            
            # Handle extracted_data - convert to string if it's a dict/list
            extracted_data = data.get("extracted_data")
            value = data.get("value")
            
            # If value is a dict/list, convert to JSON string
            if isinstance(value, (dict, list)):
                value = json.dumps(value)
            
            return Instruction(
                action=action,
                selector=data.get("selector"),
                value=value,
                url=data.get("url"),
                key=data.get("key"),
                direction=data.get("direction"),
                reasoning=data.get("reasoning", ""),
                extracted_data=extracted_data,
                timeout=data.get("timeout", 30000),
                retry=data.get("retry", True),
                question=data.get("question"),
                options=data.get("options"),
            )
            
        except Exception as e:
            logger.error(f"Error creating instruction: {e}")
            return Instruction(
                action=ActionType.ASK_USER,
                question=f"I encountered an error parsing the response. How should I proceed?",
                reasoning=f"Error parsing instruction: {str(e)}"
            )
    
    def reset_chat(self) -> None:
        """Reset the chat session for a new automation task."""
        self._initialize_chat()
        logger.debug("Chat session reset")
    
    def get_history(self) -> list:
        """Get the chat history."""
        if self.chat:
            return list(self.chat.get_history())
        return []
