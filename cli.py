"""
Command-line interface for Browser Automation with LLM.

Provides a user-friendly CLI for running automation tasks.
"""

import asyncio
import click
from pathlib import Path
from loguru import logger
from rich.console import Console

from src.config import Config, BrowserConfig, LLMConfig, RateLimitConfig, OutputConfig
from main import InteractiveBrowserAutomation

console = Console()


def setup_logging(level: str) -> None:
    """Configure logging based on level."""
    logger.remove()  # Remove default handler
    
    log_format = (
        "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
        "<level>{message}</level>"
    )
    
    logger.add(
        lambda msg: console.print(msg, end=""),
        format=log_format,
        level=level.upper(),
        colorize=True
    )


@click.group()
@click.version_option(version="0.1.0")
def cli():
    """Browser Automation with LLM - Intelligent web automation."""
    pass


@cli.command()
@click.argument("url")
@click.argument("goal")
@click.option(
    "--headless/--no-headless",
    default=True,
    help="Run browser in headless mode"
)
@click.option(
    "--screenshot/--no-screenshot",
    default=True,
    help="Include screenshots in LLM context"
)
@click.option(
    "--max-iterations",
    "-n",
    default=100,
    help="Maximum number of actions"
)
@click.option(
    "--output",
    "-o",
    type=click.Path(),
    default="./output",
    help="Output directory for results"
)
@click.option(
    "--session",
    "-s",
    default=None,
    help="Session name to save/load"
)
@click.option(
    "--delay",
    "-d",
    default=500,
    help="Delay between actions in milliseconds"
)
@click.option(
    "--log-level",
    "-l",
    type=click.Choice(["DEBUG", "INFO", "WARNING", "ERROR"]),
    default="INFO",
    help="Logging level"
)
@click.option(
    "--model",
    "-m",
    default="gemini-2.5-flash",
    help="Gemini model to use"
)
def run(
    url: str,
    goal: str,
    headless: bool,
    screenshot: bool,
    max_iterations: int,
    output: str,
    session: str,
    delay: int,
    log_level: str,
    model: str
):
    """
    Run browser automation to achieve a goal.
    
    URL: Starting URL for the automation
    
    GOAL: Description of what to achieve (e.g., "Extract all product prices")
    
    Examples:
    
        python cli.py run "https://example.com" "Find the contact email"
    
        python cli.py run "https://shop.com" "Extract all product names and prices" --no-headless
    """
    setup_logging(log_level)
    
    # Build configuration
    import os
    api_key = os.getenv("GEMINI_API_KEY", "")
    if not api_key:
        console.print("[red]Error: GEMINI_API_KEY environment variable is required[/red]")
        console.print("Set it with: export GEMINI_API_KEY=your_key_here")
        raise click.Abort()
    
    config = Config(
        browser=BrowserConfig(
            headless=headless,
            viewport_width=1280,
            viewport_height=720
        ),
        llm=LLMConfig(
            api_key=api_key,
            model=model,
            include_screenshot=screenshot
        ),
        rate_limit=RateLimitConfig(
            action_delay_ms=delay
        ),
        output=OutputConfig(
            output_dir=Path(output)
        ),
        log_level=log_level
    )
    
    # Run automation
    automation = InteractiveBrowserAutomation(config)
    
    async def execute():
        return await automation.run(
            start_url=url,
            goal=goal,
            max_iterations=max_iterations,
            session_name=session
        )
    
    try:
        results = asyncio.run(execute())
        
        if results["success"]:
            console.print("\n[green]✓ Automation completed successfully![/green]")
        else:
            console.print("\n[yellow]⚠ Automation completed with errors[/yellow]")
            
    except KeyboardInterrupt:
        console.print("\n[yellow]Automation interrupted by user[/yellow]")
    except Exception as e:
        console.print(f"\n[red]Error: {e}[/red]")
        raise click.Abort()


@cli.command()
@click.argument("url")
@click.option(
    "--headless/--no-headless",
    default=False,
    help="Run browser in headless mode"
)
@click.option(
    "--output",
    "-o",
    type=click.Path(),
    default="./output",
    help="Output directory"
)
def interactive(url: str, headless: bool, output: str):
    """
    Start an interactive browser session for manual testing.
    
    Opens a browser to the URL and waits for user input.
    
    Examples:
    
        python cli.py interactive "https://example.com" --no-headless
    """
    import os
    
    api_key = os.getenv("GEMINI_API_KEY", "")
    if not api_key:
        console.print("[red]Error: GEMINI_API_KEY environment variable is required[/red]")
        raise click.Abort()
    
    config = Config(
        browser=BrowserConfig(
            headless=headless,
            viewport_width=1280,
            viewport_height=720
        ),
        llm=LLMConfig(api_key=api_key),
        output=OutputConfig(output_dir=Path(output))
    )
    
    async def run_interactive():
        from src.browser_engine import BrowserEngine
        from src.page_extractor import PageExtractor
        
        browser = BrowserEngine(config)
        extractor = PageExtractor()
        
        try:
            await browser.start()
            await browser.navigate(url)
            
            console.print(f"\n[green]Browser opened to: {url}[/green]")
            console.print("Commands: 'extract', 'screenshot', 'quit'")
            
            while True:
                command = click.prompt("\nEnter command", default="extract")
                
                if command == "quit" or command == "q":
                    break
                
                elif command == "extract":
                    page_state = await extractor.extract(browser.page)
                    console.print(f"\n[bold]URL:[/bold] {page_state.url}")
                    console.print(f"[bold]Title:[/bold] {page_state.title}")
                    console.print(f"[bold]Elements:[/bold] {len(page_state.actionable_elements)}")
                    
                    for el in page_state.actionable_elements[:20]:
                        console.print(f"  - [{el.element_type.value}] {el.selector}: {el.label[:40]}")
                
                elif command == "screenshot":
                    screenshot = await browser.take_screenshot()
                    path = Path(output) / "screenshots" / "interactive.png"
                    path.parent.mkdir(parents=True, exist_ok=True)
                    with open(path, "wb") as f:
                        f.write(screenshot)
                    console.print(f"[green]Screenshot saved: {path}[/green]")
                
                else:
                    console.print("[yellow]Unknown command[/yellow]")
        
        finally:
            await browser.stop()
    
    asyncio.run(run_interactive())


@cli.command()
def sessions():
    """List all saved browser sessions."""
    from pathlib import Path
    
    session_dir = Path("./output/sessions")
    
    if not session_dir.exists():
        console.print("[dim]No sessions found[/dim]")
        return
    
    sessions = list(session_dir.glob("*.json"))
    
    if not sessions:
        console.print("[dim]No sessions found[/dim]")
        return
    
    console.print("[bold]Saved Sessions:[/bold]")
    for session in sessions:
        console.print(f"  - {session.stem}")


@cli.command()
@click.argument("session_name")
def delete_session(session_name: str):
    """Delete a saved browser session."""
    from pathlib import Path
    
    session_path = Path(f"./output/sessions/{session_name}.json")
    
    if not session_path.exists():
        console.print(f"[red]Session not found: {session_name}[/red]")
        return
    
    session_path.unlink()
    console.print(f"[green]Session deleted: {session_name}[/green]")


if __name__ == "__main__":
    cli()

