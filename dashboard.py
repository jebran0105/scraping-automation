"""
Streamlit Dashboard for Browser Automation with LLM.

Provides a user-friendly web interface for running automation tasks.
"""

import asyncio
import os
import sys
import threading
import queue
from pathlib import Path
from typing import Optional
import streamlit as st
from loguru import logger

from src.config import Config, BrowserConfig, LLMConfig, RateLimitConfig, OutputConfig
from main import InteractiveBrowserAutomation
from src.models import Instruction, ActionType


# Page configuration
st.set_page_config(
    page_title="Browser Automation Dashboard",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded"
)


class StreamlitLogHandler:
    """Custom log handler that collects logs for Streamlit display."""
    
    def __init__(self):
        self.logs = []
        self.max_logs = 2000  # Keep last 2000 log lines
    
    def write(self, message):
        if message.strip():
            self.logs.append(message.strip())
            # Keep only last max_logs lines to avoid memory issues
            if len(self.logs) > self.max_logs:
                self.logs.pop(0)
    
    def flush(self):
        pass
    
    def get_logs(self):
        """Get all collected logs as a string."""
        return "\n".join(self.logs)
    
    def clear(self):
        """Clear all logs."""
        self.logs = []


# Global log handler instance
_log_handler = StreamlitLogHandler()


class StreamlitAutomation(InteractiveBrowserAutomation):
    """Streamlit-compatible automation that handles user prompts via session state."""
    
    def __init__(self, config, question_queue, response_queue):
        """
        Initialize Streamlit automation.
        
        Args:
            config: Configuration object
            question_queue: Queue to send questions to Streamlit
            response_queue: Queue to receive responses from Streamlit
        """
        super().__init__(config)
        self.question_queue = question_queue
        self.response_queue = response_queue
    
    async def _handle_ask_user(self, instruction: Instruction) -> str:
        """Handle the ask_user action by using queues for Streamlit communication."""
        # Store question and options for display
        question = instruction.question or "I need your input to proceed."
        options = instruction.options
        
        # Log the question
        logger.info(f"AI Assistant: {question}")
        if options:
            logger.info("Available options:")
            for i, option in enumerate(options, 1):
                logger.info(f"  {i}. {option}")
        
        # Send question to Streamlit via queue
        self.question_queue.put({
            'question': question,
            'options': options
        })
        
        # Wait for response from Streamlit
        try:
            response = self.response_queue.get(timeout=300)  # 5 minute timeout
            
            # If user entered a number and we have options, map to the option
            if response and response.strip().isdigit() and options:
                idx = int(response.strip()) - 1
                if 0 <= idx < len(options):
                    mapped_response = f"I choose option {response.strip()}: {options[idx]}"
                    logger.info(f"User response: {mapped_response}")
                    return mapped_response
            
            logger.info(f"User response: {response}")
            return response or ""
        except queue.Empty:
            logger.warning("Timeout waiting for user response")
            return "stop"


def setup_logging_for_streamlit(level: str):
    """Configure logging to collect logs for Streamlit."""
    logger.remove()
    
    log_format = (
        "{time:YYYY-MM-DD HH:mm:ss} | "
        "{level: <8} | "
        "{name}:{function}:{line} - "
        "{message}"
    )
    
    logger.add(
        _log_handler.write,
        format=log_format,
        level=level.upper(),
        colorize=False
    )
    
    # Also add console output for debugging
    logger.add(
        sys.stderr,
        format=log_format,
        level=level.upper(),
        colorize=True
    )


def run_automation_in_thread(
    url: str,
    goal: str,
    headless: bool,
    screenshot: bool,
    max_iterations: int,
    output: str,
    session: Optional[str],
    delay: int,
    log_level: str,
    model: str,
    question_queue: queue.Queue,
    response_queue: queue.Queue,
    results_container: dict
):
    """Run automation in a separate thread."""
    try:
        # Clear previous logs
        _log_handler.clear()
        
        # Setup logging
        setup_logging_for_streamlit(log_level)
        
        # Check for API key
        api_key = os.getenv("GEMINI_API_KEY", "")
        if not api_key:
            results_container['error'] = "GEMINI_API_KEY environment variable is required"
            return
        
        # Build configuration
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
        
        # Create Streamlit-compatible automation
        automation = StreamlitAutomation(config, question_queue, response_queue)
        
        async def execute():
            """Execute automation with prompt handling."""
            try:
                return await automation.run(
                    start_url=url,
                    goal=goal,
                    max_iterations=max_iterations,
                    session_name=session
                )
            except Exception as e:
                logger.error(f"Automation error: {e}")
                raise
        
        # Run async function
        results = asyncio.run(execute())
        results_container['results'] = results
        results_container['done'] = True
        
    except Exception as e:
        logger.error(f"Error: {e}")
        results_container['error'] = str(e)
        results_container['done'] = True


def main():
    """Main Streamlit app."""
    st.title("🤖 Browser Automation Dashboard")
    st.markdown("Automate web tasks using AI-powered browser automation")
    
    # Sidebar for configuration
    with st.sidebar:
        st.header("⚙️ Configuration")
        
        # Basic settings
        st.subheader("Basic Settings")
        headless = st.checkbox("Headless Mode", value=True, help="Run browser in headless mode")
        screenshot = st.checkbox("Include Screenshots", value=True, help="Include screenshots in LLM context")
        
        # Advanced settings
        with st.expander("Advanced Settings"):
            max_iterations = st.number_input(
                "Max Iterations",
                min_value=1,
                max_value=1000,
                value=100,
                help="Maximum number of actions"
            )
            
            delay = st.number_input(
                "Action Delay (ms)",
                min_value=0,
                max_value=10000,
                value=500,
                step=100,
                help="Delay between actions in milliseconds"
            )
            
            log_level = st.selectbox(
                "Log Level",
                ["DEBUG", "INFO", "WARNING", "ERROR"],
                index=1,
                help="Logging verbosity level"
            )
            
            model = st.text_input(
                "Model",
                value="gemini-2.5-flash",
                help="Gemini model to use"
            )
            
            output_dir = st.text_input(
                "Output Directory",
                value="./output",
                help="Directory for results and screenshots"
            )
            
            session_name = st.text_input(
                "Session Name (optional)",
                value="",
                help="Session name to save/load"
            )
    
    # Main content area
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.subheader("📝 Task Configuration")
        
        url = st.text_input(
            "Starting URL",
            value="",
            placeholder="https://example.com",
            help="The URL where automation should start"
        )
        
        goal = st.text_area(
            "Goal / Prompt",
            value="",
            placeholder="Describe what you want to achieve (e.g., 'Extract all product prices')",
            height=150,
            help="Detailed description of the automation goal"
        )
        
        # Run button
        run_button = st.button("🚀 Run Automation", type="primary", use_container_width=True)
    
    with col2:
        st.subheader("ℹ️ Information")
        st.info("""
        **How to use:**
        1. Enter the starting URL
        2. Describe your goal
        3. Configure options in sidebar
        4. Click Run Automation
        
        **Note:** Make sure GEMINI_API_KEY is set in your environment.
        """)
    
    # Initialize session state for automation
    if 'automation_thread' not in st.session_state:
        st.session_state.automation_thread = None
    if 'question_queue' not in st.session_state:
        st.session_state.question_queue = queue.Queue()
    if 'response_queue' not in st.session_state:
        st.session_state.response_queue = queue.Queue()
    if 'automation_results' not in st.session_state:
        st.session_state.automation_results = None
    if 'current_question' not in st.session_state:
        st.session_state.current_question = None
    if 'current_options' not in st.session_state:
        st.session_state.current_options = None
    if 'automation_config' not in st.session_state:
        st.session_state.automation_config = None
    if 'results_container' not in st.session_state:
        st.session_state.results_container = {'done': False, 'results': None, 'error': None}
    
    # Logs and results section
    if run_button:
        # Validate inputs
        if not url:
            st.error("❌ Please enter a starting URL")
            st.stop()
        
        if not goal:
            st.error("❌ Please enter a goal/prompt")
            st.stop()
        
        # Store config and start automation thread
        st.session_state.automation_config = {
            'url': url,
            'goal': goal,
            'headless': headless,
            'screenshot': screenshot,
            'max_iterations': max_iterations,
            'output': output_dir,
            'session': session_name if session_name.strip() else None,
            'delay': delay,
            'log_level': log_level,
            'model': model
        }
        st.session_state.results_container = {'done': False, 'results': None, 'error': None}
        st.session_state.current_question = None
        st.session_state.current_options = None
        
        # Start automation in a thread
        thread = threading.Thread(
            target=run_automation_in_thread,
            args=(
                url, goal, headless, screenshot, max_iterations, output_dir,
                session_name if session_name.strip() else None, delay, log_level, model,
                st.session_state.question_queue,
                st.session_state.response_queue,
                st.session_state.results_container
            ),
            daemon=True
        )
        thread.start()
        st.session_state.automation_thread = thread
    
    # Check for pending questions from automation
    if st.session_state.automation_thread and st.session_state.automation_thread.is_alive():
        # Check if there's a new question (non-blocking)
        # Keep checking until queue is empty to get the latest question
        latest_question = None
        latest_options = None
        while True:
            try:
                question_data = st.session_state.question_queue.get_nowait()
                latest_question = question_data['question']
                latest_options = question_data.get('options')
            except queue.Empty:
                break
        
        # Update session state if we got a new question
        if latest_question is not None:
            st.session_state.current_question = latest_question
            st.session_state.current_options = latest_options
    
    # Display automation UI if running or has results
    if st.session_state.automation_config or st.session_state.automation_results:
        # Create containers for logs and results
        st.divider()
        st.subheader("📊 Execution Logs")
        
        # Prompt container for ASK_USER actions
        prompt_container = st.empty()
        
        # Status indicator
        status_placeholder = st.empty()
        
        # Check if automation is still running
        is_running = (st.session_state.automation_thread and 
                     st.session_state.automation_thread.is_alive())
        
        if is_running:
            if st.session_state.current_question:
                status_placeholder.info("⏳ Automation is waiting for your response...")
            else:
                status_placeholder.info("⏳ Automation is running... (Click 'Refresh Status' to check for prompts)")
        elif st.session_state.results_container.get('done'):
            if st.session_state.results_container.get('error'):
                status_placeholder.error(f"❌ Error: {st.session_state.results_container['error']}")
            elif st.session_state.results_container.get('results'):
                results = st.session_state.results_container['results']
                if results.get("success"):
                    status_placeholder.success("✅ Automation completed successfully!")
                else:
                    status_placeholder.warning("⚠️ Automation completed with errors")
                st.session_state.automation_results = results
        
        # Display prompt if we have a pending question
        if st.session_state.current_question:
            with prompt_container.container():
                st.markdown("---")
                st.markdown("### 💬 AI Assistant Question")
                
                # Display question in a nice box
                st.info(f"**{st.session_state.current_question}**")
                
                # Display options if available
                if st.session_state.current_options:
                    st.markdown("**Available options:**")
                    for i, option in enumerate(st.session_state.current_options, 1):
                        st.markdown(f"{i}. {option}")
                
                # Get user input
                col1, col2 = st.columns([3, 1])
                with col1:
                    user_input = st.text_input(
                        "Your response:",
                        placeholder="Enter a number, type instructions, or 'stop' to end",
                        key="user_input_prompt"
                    )
                with col2:
                    submit_button = st.button("Submit", key="submit_prompt")
                
                if submit_button and user_input:
                    response = user_input.strip()
                    # Send response to automation thread
                    st.session_state.response_queue.put(response)
                    # Clear current question
                    st.session_state.current_question = None
                    st.session_state.current_options = None
                    st.rerun()
                elif submit_button:
                    st.warning("Please enter a response")
        
        # Display logs
        logs_text = _log_handler.get_logs()
        if logs_text:
            st.text_area(
                "Execution Logs",
                value=logs_text,
                height=400,
                disabled=True,
                key="logs_display"
            )
        else:
            st.info("No logs available")
        
        # Add a refresh button if automation is running
        if is_running:
            if st.button("🔄 Refresh Status", key="refresh_status"):
                st.rerun()
        
        # Display results when automation is complete
        results = st.session_state.automation_results
        if results and not is_running:
            # Results section
            st.divider()
            st.subheader("📋 Results")
            
            # Show extracted data if available
            extracted_data = results.get("extracted_data", [])
            if extracted_data:
                st.success(f"✅ Extracted {len(extracted_data)} items")
                
                with st.expander("View Extracted Data", expanded=True):
                    for i, item in enumerate(extracted_data, 1):
                        st.json(item)
            else:
                st.info("No extracted data available")
            
            # Show summary
            with st.expander("Execution Summary"):
                summary_data = {
                    "Success": results.get("success", False),
                    "Iterations": results.get("iterations", 0),
                    "Actions Taken": results.get("actions_taken", 0),
                    "Error": results.get("error", "None"),
                }
                st.json(summary_data)
            
            # Show output files
            config = st.session_state.automation_config or {}
            output_dir = config.get('output', './output')
            output_path = Path(output_dir)
            if output_path.exists():
                result_files = list(output_path.glob("results_*.json"))
                if result_files:
                    st.subheader("📁 Output Files")
                    latest_file = max(result_files, key=lambda p: p.stat().st_mtime)
                    st.info(f"Latest result file: `{latest_file.name}`")
                    
                    # Download button
                    with open(latest_file, "r") as f:
                        file_content = f.read()
                    st.download_button(
                        label="📥 Download Latest Results",
                        data=file_content,
                        file_name=latest_file.name,
                        mime="application/json"
                    )
    
    # Session management section
    st.divider()
    with st.expander("💾 Session Management"):
        session_dir = Path("./output/sessions")
        
        if session_dir.exists():
            sessions = list(session_dir.glob("*.json"))
            if sessions:
                st.write(f"**Found {len(sessions)} saved sessions:**")
                for session_file in sessions:
                    col_a, col_b = st.columns([3, 1])
                    with col_a:
                        st.text(session_file.stem)
                    with col_b:
                        if st.button("Delete", key=f"delete_{session_file.stem}"):
                            session_file.unlink()
                            st.success(f"Deleted {session_file.stem}")
                            st.rerun()
            else:
                st.info("No saved sessions found")
        else:
            st.info("No sessions directory found")


if __name__ == "__main__":
    main()

