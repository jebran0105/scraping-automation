"""
Main entry point for Browser Automation with LLM.

Implements an interactive automation loop with user feedback.
"""

import asyncio
import json
import time
from pathlib import Path
from typing import Optional
from loguru import logger
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt, Confirm
from rich.table import Table
from rich.markdown import Markdown

from src.config import Config, get_config
from src.models import ActionType, ExecutionContext, Instruction
from src.browser_engine import BrowserEngine
from src.page_extractor import PageExtractor
from src.llm_client import LLMClient
from src.instruction_executor import InstructionExecutor
from src.session_manager import SessionManager

console = Console()


class InteractiveBrowserAutomation:
    """
    Interactive browser automation orchestrator.
    
    Coordinates the browser, page extractor, LLM client, and executor
    with user feedback at each step.
    """
    
    def __init__(self, config: Optional[Config] = None):
        """
        Initialize the automation system.
        
        Args:
            config: Optional configuration (loads from env if not provided)
        """
        self.config = config or get_config()
        
        # Initialize components
        self.browser = BrowserEngine(self.config)
        self.extractor = PageExtractor(
            include_screenshot=self.config.llm.include_screenshot
        )
        self.llm_client = LLMClient(self.config.llm)
        self.executor = InstructionExecutor(self.browser, self.config)
        self.session_manager: Optional[SessionManager] = None
        
        # Execution state
        self.context = ExecutionContext(start_time=time.time())
        self.max_iterations = 100  # Safety limit
        self.is_running = False
    
    async def start(self) -> None:
        """Start the browser and prepare for automation."""
        await self.browser.start()
        self.session_manager = SessionManager(self.config, self.browser)
        self.is_running = True
        logger.info("Browser automation started")
    
    async def stop(self) -> None:
        """Stop the browser and cleanup."""
        self.is_running = False
        await self.browser.stop()
        logger.info("Browser automation stopped")
    
    async def run(
        self,
        start_url: str,
        goal: str,
        max_iterations: Optional[int] = None,
        session_name: Optional[str] = None
    ) -> dict:
        """
        Run the interactive automation loop.
        
        Args:
            start_url: URL to start from
            goal: Description of what to achieve
            max_iterations: Maximum number of actions (default: 100)
            session_name: Optional session to load
        
        Returns:
            Dictionary with results and extracted data
        """
        if max_iterations:
            self.max_iterations = max_iterations
        
        console.print(Panel(
            f"[bold cyan]Goal:[/bold cyan] {goal}\n"
            f"[bold cyan]URL:[/bold cyan] {start_url}\n\n"
            "[dim]Actions will execute automatically. The AI will only pause to ask for your input when needed.[/dim]",
            title="[bold]Browser Automation[/bold]",
            border_style="cyan"
        ))
        
        try:
            await self.start()
            
            # Load session if specified
            if session_name and self.session_manager:
                await self.session_manager.load_session(session_name)
            
            # Navigate to start URL
            await self.browser.navigate(start_url)
            self.context.current_url = start_url
            self.context.stats["pages_visited"] += 1
            
            # Main interactive loop
            result = await self._interactive_loop(goal)
            
            # Save session if name provided
            if session_name and self.session_manager:
                await self.session_manager.save_session(session_name)
            
            return result
            
        finally:
            await self.stop()
    
    async def _interactive_loop(self, goal: str) -> dict:
        """
        Main interactive automation loop.
        
        Args:
            goal: User's goal for the automation
        
        Returns:
            Dictionary with results
        """
        iteration = 0
        extracted_data = []
        user_response = None
        
        while iteration < self.max_iterations and self.is_running:
            iteration += 1
            
            console.print(f"\n[bold cyan]─── Step {iteration} ───[/bold cyan]")
            
            try:
                # Extract current page state
                console.print("[dim]Analyzing page...[/dim]")
                page_state = await self.extractor.extract(self.browser.page)
                self.context.current_url = page_state.url
                
                # Show current URL
                console.print(f"[dim]URL: {page_state.url}[/dim]")
                
                # Format page state for LLM
                page_state_text = self.extractor.format_for_llm(page_state)
                
                # Get instruction from LLM
                console.print("[dim]Getting LLM instruction...[/dim]")
                instruction = await self.llm_client.get_instruction(
                    page_state=page_state,
                    goal=goal,
                    context=self.context,
                    page_state_text=page_state_text,
                    user_response=user_response
                )
                user_response = None  # Clear after use
                
                # Display the instruction
                self._display_instruction(instruction)
                
                # Handle ask_user action
                if instruction.action == ActionType.ASK_USER:
                    user_response = await self._handle_ask_user(instruction)
                    if user_response.lower() == 'stop':
                        console.print("[yellow]Stopping automation...[/yellow]")
                        break
                    continue
                
                # Handle extract action - but don't stop, ask user what's next
                if instruction.action == ActionType.EXTRACT:
                    # Handle extraction - display data and continue
                    if instruction.extracted_data:
                        extracted_data.append(instruction.extracted_data)
                        self.context.extracted_data.append(instruction.extracted_data)
                        self.context.stats["extractions"] += 1
                        self._display_extracted_data(instruction.extracted_data)
                    continue
                
                # Handle DONE - only if LLM mistakenly sends it, convert to ask_user
                if instruction.action == ActionType.DONE:
                    # Don't end - ask user what to do next instead
                    user_response = Prompt.ask(
                        "[cyan]Task appears complete. What would you like to do next?[/cyan]\n"
                        "(Type 'stop' to end, or give new instructions)"
                    )
                    if user_response.lower() == 'stop':
                        console.print("[bold green]✓ Session ended by user[/bold green]")
                        break
                    continue
                
                # Execute the instruction (no confirmation needed - auto-execute)
                console.print(f"[dim]Executing: {instruction.action.value}...[/dim]")
                result = await self.executor.execute(instruction)
                self.context.add_result(result)
                
                # Track page visits
                new_url = await self.browser.get_current_url()
                if new_url != self.context.current_url:
                    self.context.stats["pages_visited"] += 1
                    self.context.current_url = new_url
                
                # Report result
                if result.success:
                    console.print(f"[green]✓ Action completed[/green]")
                else:
                    console.print(f"[red]✗ Action failed: {result.error}[/red]")
                    
                    # Take error screenshot if configured
                    if self.config.output.screenshot_on_error:
                        await self._save_error_screenshot(iteration)
                    
                    # Show available elements to help user
                    console.print("\n[yellow]Available elements on this page:[/yellow]")
                    for i, el in enumerate(page_state.actionable_elements[:15], 1):
                        label = el.label or el.placeholder or el.aria_label or "(no label)"
                        console.print(f"  [cyan]{i}.[/cyan] [{el.element_type.value}] {label[:50]}")
                        console.print(f"      [dim]selector: {el.selector}[/dim]")
                    
                    if len(page_state.actionable_elements) > 15:
                        console.print(f"  [dim]... and {len(page_state.actionable_elements) - 15} more elements[/dim]")
                    
                    # Ask user what to do
                    user_response = Prompt.ask(
                        "\n[yellow]Action failed. What should I do?[/yellow]\n"
                        "(Type element # to click, 'scroll' to see more, 'elements' to see all, or give instructions)"
                    )
                    
                    if user_response.lower() == 'stop':
                        console.print("[yellow]Stopping...[/yellow]")
                        break
                    elif user_response.lower() == 'elements':
                        self._show_elements(page_state)
                        user_response = Prompt.ask("Now what should I do?")
                    
                    if user_response.isdigit():
                        idx = int(user_response) - 1
                        if 0 <= idx < len(page_state.actionable_elements):
                            el = page_state.actionable_elements[idx]
                            user_response = f"Click on the element with selector: {el.selector}"
                    
                    # Continue with user response for next iteration
                    continue
                
            except KeyboardInterrupt:
                console.print("\n[yellow]Interrupted by user[/yellow]")
                break
            except Exception as e:
                logger.error(f"Error in iteration {iteration}: {e}")
                console.print(f"[red]Error: {e}[/red]")
                
                # Ask user how to proceed
                if Confirm.ask("Continue anyway?", default=True):
                    continue
                else:
                    break
        
        # Compile results
        return self._compile_results(extracted_data, iteration)
    
    def _display_instruction(self, instruction: Instruction) -> None:
        """Display the LLM's instruction in a nice format."""
        action_colors = {
            ActionType.CLICK: "yellow",
            ActionType.TYPE: "blue",
            ActionType.NAVIGATE: "magenta",
            ActionType.EXTRACT: "green",
            ActionType.DONE: "green",
            ActionType.ASK_USER: "cyan",
            ActionType.WAIT: "dim",
            ActionType.SCROLL: "dim",
            ActionType.BACK: "dim",
        }
        
        color = action_colors.get(instruction.action, "white")
        
        console.print(f"\n[bold {color}]Action: {instruction.action.value.upper()}[/bold {color}]")
        
        if instruction.selector:
            console.print(f"  Target: [cyan]{instruction.selector}[/cyan]")
        if instruction.value:
            console.print(f"  Value: [cyan]{instruction.value[:100]}[/cyan]")
        if instruction.url:
            console.print(f"  URL: [cyan]{instruction.url}[/cyan]")
        if instruction.reasoning:
            console.print(f"  [dim]Reasoning: {instruction.reasoning}[/dim]")
    
    async def _handle_ask_user(self, instruction: Instruction) -> str:
        """Handle the ask_user action by prompting the user."""
        console.print()
        
        # Display the question
        console.print(Panel(
            instruction.question or "I need your input to proceed.",
            title="[bold cyan]AI Assistant[/bold cyan]",
            border_style="cyan"
        ))
        
        # Display options if provided
        if instruction.options:
            console.print("\n[bold]Available options:[/bold]")
            for i, option in enumerate(instruction.options, 1):
                console.print(f"  [cyan]{i}.[/cyan] {option}")
            console.print()
            console.print("[dim]Enter a number, type instructions, or 'stop' to end[/dim]")
            
            response = Prompt.ask("You")
            
            # If user entered a number, map to the option
            if response.isdigit():
                idx = int(response) - 1
                if 0 <= idx < len(instruction.options):
                    return f"I choose option {response}: {instruction.options[idx]}"
            
            return response
        else:
            console.print("[dim]Type your response, or 'stop' to end[/dim]")
            return Prompt.ask("You")
    
    async def _get_user_input(self) -> str:
        """Get user input for the next action."""
        console.print()
        response = Prompt.ask(
            "[bold]Press Enter to execute, or type command[/bold]",
            default=""
        )
        return response.strip().lower()
    
    def _show_help(self) -> None:
        """Show help for available commands."""
        console.print(Panel(
            "[bold]Available Commands:[/bold]\n\n"
            "[cyan]Enter[/cyan] - Execute the proposed action\n"
            "[cyan]auto[/cyan] - Switch to automatic mode (no confirmations)\n"
            "[cyan]skip[/cyan] - Skip this action and get a new one\n"
            "[cyan]stop[/cyan] - Stop the automation\n"
            "[cyan]say <text>[/cyan] - Send feedback/instructions to the AI\n"
            "[cyan]elements[/cyan] - Show all detected elements on the page\n"
            "[cyan]help[/cyan] - Show this help message",
            title="Help",
            border_style="blue"
        ))
    
    def _show_elements(self, page_state) -> None:
        """Show all detected elements on the page."""
        table = Table(title="Page Elements", show_lines=True)
        table.add_column("#", style="cyan", width=4)
        table.add_column("Type", style="yellow", width=10)
        table.add_column("Selector", style="green", max_width=40)
        table.add_column("Label", style="white", max_width=40)
        
        for i, el in enumerate(page_state.actionable_elements[:30], 1):
            label = el.label or el.placeholder or el.aria_label or "-"
            table.add_row(
                str(i),
                el.element_type.value,
                el.selector[:40],
                label[:40]
            )
        
        console.print(table)
    
    def _display_extracted_data(self, data) -> None:
        """Display extracted data in a nice format."""
        console.print("\n[bold green]Extracted Data:[/bold green]")
        if isinstance(data, (dict, list)):
            console.print_json(json.dumps(data, indent=2, default=str))
        else:
            console.print(f"  {data}")
    
    def _compile_results(self, extracted_data: list, iterations: int) -> dict:
        """Compile the final results."""
        duration = time.time() - (self.context.start_time or time.time())
        
        results = {
            "success": len(self.context.errors) == 0,
            "iterations": iterations,
            "duration_seconds": round(duration, 2),
            "extracted_data": extracted_data,
            "stats": self.context.stats,
            "errors": self.context.errors[-10:],
            "final_url": self.context.current_url,
        }
        
        # Save results to file
        self._save_results(results)
        
        # Print summary
        console.print("\n" + "─" * 50)
        console.print("[bold]Summary:[/bold]")
        console.print(f"  Iterations: {iterations}")
        console.print(f"  Duration: {duration:.1f}s")
        console.print(f"  Pages visited: {self.context.stats['pages_visited']}")
        console.print(f"  Extractions: {self.context.stats['extractions']}")
        console.print(f"  Success rate: {self._calculate_success_rate():.1%}")
        
        if extracted_data:
            console.print(f"\n[bold green]Extracted {len(extracted_data)} items[/bold green]")
        
        return results
    
    def _calculate_success_rate(self) -> float:
        """Calculate the success rate of actions."""
        total = self.context.stats["total_actions"]
        if total == 0:
            return 1.0
        return self.context.stats["successful_actions"] / total
    
    def _save_results(self, results: dict) -> None:
        """Save results to a JSON file."""
        output_dir = self.config.output.output_dir
        output_dir.mkdir(parents=True, exist_ok=True)
        
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        output_path = output_dir / f"results_{timestamp}.json"
        
        with open(output_path, "w") as f:
            json.dump(results, f, indent=2, default=str)
        
        console.print(f"\n[dim]Results saved to: {output_path}[/dim]")
    
    async def _save_error_screenshot(self, iteration: int) -> None:
        """Save a screenshot when an error occurs."""
        try:
            output_dir = self.config.output.output_dir / "screenshots"
            output_dir.mkdir(parents=True, exist_ok=True)
            
            screenshot = await self.browser.take_screenshot()
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            path = output_dir / f"error_{timestamp}_step{iteration}.png"
            
            with open(path, "wb") as f:
                f.write(screenshot)
            
            logger.debug(f"Error screenshot saved: {path}")
            
        except Exception as e:
            logger.debug(f"Failed to save error screenshot: {e}")


# Keep backward compatibility
BrowserAutomation = InteractiveBrowserAutomation


async def main():
    """Main entry point for command-line usage."""
    import sys
    
    if len(sys.argv) < 3:
        console.print("[red]Usage: python main.py <url> <goal>[/red]")
        console.print("Example: python main.py 'https://example.com' 'Find the contact email'")
        sys.exit(1)
    
    url = sys.argv[1]
    goal = sys.argv[2]
    
    automation = InteractiveBrowserAutomation()
    results = await automation.run(url, goal)
    
    if results["extracted_data"]:
        console.print("\n[bold green]Extracted Data:[/bold green]")
        for item in results["extracted_data"]:
            console.print(json.dumps(item, indent=2, default=str))


if __name__ == "__main__":
    asyncio.run(main())
