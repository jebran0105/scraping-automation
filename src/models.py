"""
Data models for Browser Automation with LLM.

Defines PageState, Instruction, and ExecutionContext using Pydantic.
"""

from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel, Field


class ActionType(str, Enum):
    """Supported action types for browser automation."""
    CLICK = "click"
    TYPE = "type"
    NAVIGATE = "navigate"
    EXTRACT = "extract"
    DONE = "done"
    WAIT = "wait"
    BACK = "back"
    SCROLL = "scroll"
    SELECT = "select"
    HOVER = "hover"
    PRESS = "press"
    ASK_USER = "ask_user"  # Ask user for clarification or choice


class ElementType(str, Enum):
    """Types of actionable elements on a page."""
    BUTTON = "button"
    LINK = "link"
    INPUT = "input"
    SELECT = "select"
    TEXTAREA = "textarea"
    CHECKBOX = "checkbox"
    RADIO = "radio"
    FILE = "file"
    SUBMIT = "submit"
    OTHER = "other"


class ActionableElement(BaseModel):
    """Represents an actionable element on the page."""
    selector: str = Field(description="CSS selector or unique identifier")
    element_type: ElementType = Field(description="Type of the element")
    label: str = Field(default="", description="Visible label or text")
    value: str = Field(default="", description="Current value (for inputs)")
    placeholder: str = Field(default="", description="Placeholder text")
    aria_label: str = Field(default="", description="ARIA label for accessibility")
    position: dict = Field(default_factory=dict, description="Position on page {x, y}")
    visible: bool = Field(default=True, description="Whether element is visible")
    enabled: bool = Field(default=True, description="Whether element is enabled")
    attributes: dict = Field(default_factory=dict, description="Additional attributes")


class PageState(BaseModel):
    """Represents the current state of a webpage."""
    url: str = Field(description="Current page URL")
    title: str = Field(default="", description="Page title")
    actionable_elements: list[ActionableElement] = Field(
        default_factory=list,
        description="List of actionable elements on the page"
    )
    text_content: str = Field(default="", description="Main text content")
    screenshot: Optional[bytes] = Field(default=None, description="Screenshot as bytes")
    metadata: dict = Field(default_factory=dict, description="Additional metadata")
    forms: list[dict] = Field(default_factory=list, description="Detected forms")
    
    class Config:
        arbitrary_types_allowed = True


class Instruction(BaseModel):
    """Represents an instruction from the LLM."""
    action: ActionType = Field(description="Action to perform")
    selector: Optional[str] = Field(default=None, description="Target element selector")
    value: Optional[str] = Field(default=None, description="Value for type/extract")
    url: Optional[str] = Field(default=None, description="URL for navigate")
    reasoning: str = Field(default="", description="LLM's reasoning for this action")
    timeout: int = Field(default=30000, description="Timeout in milliseconds")
    retry: bool = Field(default=True, description="Whether to retry on failure")
    extraction_schema: Optional[dict] = Field(
        default=None,
        description="Schema for structured data extraction"
    )
    key: Optional[str] = Field(default=None, description="Key to press for press action")
    direction: Optional[str] = Field(default=None, description="Scroll direction")
    extracted_data: Optional[Any] = Field(default=None, description="Extracted data")
    # For ask_user action
    question: Optional[str] = Field(default=None, description="Question to ask the user")
    options: Optional[list[str]] = Field(default=None, description="Numbered options for user to choose from")


class ActionResult(BaseModel):
    """Result of executing an action."""
    success: bool = Field(description="Whether action succeeded")
    action: ActionType = Field(description="Action that was executed")
    selector: Optional[str] = Field(default=None, description="Target selector")
    error: Optional[str] = Field(default=None, description="Error message if failed")
    duration_ms: int = Field(default=0, description="Execution time in ms")
    screenshot_after: Optional[bytes] = Field(default=None, description="Screenshot after action")
    
    class Config:
        arbitrary_types_allowed = True


class ExecutionContext(BaseModel):
    """Maintains context across the automation session."""
    history: list[ActionResult] = Field(
        default_factory=list,
        description="History of executed actions"
    )
    extracted_data: list[Any] = Field(
        default_factory=list,
        description="Accumulated extracted data"
    )
    stats: dict = Field(
        default_factory=lambda: {
            "total_actions": 0,
            "successful_actions": 0,
            "failed_actions": 0,
            "total_duration_ms": 0,
            "pages_visited": 0,
            "extractions": 0
        },
        description="Performance metrics"
    )
    errors: list[str] = Field(default_factory=list, description="Error log")
    current_url: str = Field(default="", description="Current page URL")
    start_time: Optional[float] = Field(default=None, description="Session start time")
    
    class Config:
        arbitrary_types_allowed = True
    
    def add_result(self, result: ActionResult) -> None:
        """Add an action result to history and update stats."""
        self.history.append(result)
        self.stats["total_actions"] += 1
        self.stats["total_duration_ms"] += result.duration_ms
        
        if result.success:
            self.stats["successful_actions"] += 1
        else:
            self.stats["failed_actions"] += 1
            if result.error:
                self.errors.append(result.error)
    
    def get_history_summary(self, last_n: int = 10) -> str:
        """Get a summary of recent actions for LLM context."""
        recent = self.history[-last_n:] if len(self.history) > last_n else self.history
        summary_parts = []
        
        for i, result in enumerate(recent, 1):
            status = "SUCCESS" if result.success else "FAILED"
            action_desc = f"{i}. {result.action.value}"
            if result.selector:
                action_desc += f" on '{result.selector}'"
            action_desc += f" [{status}]"
            if result.error:
                action_desc += f" - {result.error}"
            summary_parts.append(action_desc)
        
        return "\n".join(summary_parts) if summary_parts else "No actions yet."

