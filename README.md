# Browser Automation with LLM

An intelligent browser automation system that uses Google Gemini LLM to navigate websites, fill forms, and extract data dynamically through an interactive conversational interface.

## Features

- **LLM-Driven Navigation**: Uses Gemini 2.5 to intelligently decide what actions to take
- **Interactive Chat Interface**: AI asks for your input only when choices are needed
- **Auto-Execution**: Actions run automatically - no confirmations required
- **Dynamic SPA Support**: Handles Single Page Applications with smart waiting strategies
- **Multimodal Understanding**: Sends screenshots to the LLM for better page comprehension
- **Structured Data Extraction**: Extracts data in structured JSON format
- **Session Persistence**: Save and load browser sessions for authenticated scraping
- **Robust Error Handling**: Shows available elements and asks for guidance on failures
- **Stealth Mode**: Anti-bot detection features for protected websites

## Installation

1. Clone this repository:

```bash
cd Scraping_Automation
```

2. Create a virtual environment:

```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:

```bash
pip install -r requirements.txt
playwright install chromium
```

4. Set up your Gemini API key:

```bash
export GEMINI_API_KEY=your_api_key_here
```

## Quick Start

### Using the CLI

```bash
# Basic usage
python cli.py run "https://example.com" "Extract the main heading and any links"

# With options
python cli.py run "https://shop.example.com" "Extract all product names and prices" \
  --no-headless \
  --max-iterations 50 \
  --output ./results
```

### Using Python

```python
import asyncio
from main import InteractiveBrowserAutomation

async def main():
    automation = InteractiveBrowserAutomation()

    results = await automation.run(
        start_url="https://example.com",
        goal="Find and extract all contact information",
        max_iterations=30
    )

    print(results["extracted_data"])

asyncio.run(main())
```

## How It Works

### High-Level Architecture

The application uses an **LLM (Google Gemini)** to control a **browser (Playwright)** through an intelligent loop:

```
1. Extract Page State → 2. Send to LLM → 3. Get Instruction → 4. Execute → 5. Repeat
```

### Core Components

#### 1. **Main Loop** (`main.py` - `InteractiveBrowserAutomation`)

The orchestrator that coordinates all components:

- **Extracts** current page state (elements, text, screenshot)
- **Sends** page state + goal + history to LLM
- **Receives** structured instruction (click, type, ask_user, etc.)
- **Executes** instruction automatically (no confirmations)
- **Handles** errors by showing available elements and asking user
- **Pauses** only when LLM uses `ask_user` action or action fails

**Key Behavior:**

- Actions execute automatically - you only interact when the AI needs your input
- Tracks execution history and statistics
- Never ends automatically - only you can stop the session

#### 2. **Browser Engine** (`src/browser_engine.py`)

Playwright wrapper that handles all browser operations:

**Features:**

- Launches Chromium with stealth settings (anti-bot detection)
- Handles navigation, clicks, typing, scrolling, etc.
- Waits for SPA stability (network idle, DOM stability)
- Applies stealth scripts to avoid detection

**Stealth Features:**

- Hides `navigator.webdriver` property
- Mocks browser plugins
- Sets realistic user agent and locale
- Disables automation flags

**SPA Support:**

- Waits for `networkidle` after navigation
- Monitors DOM stability (checks if element count stops changing)
- Custom wait strategies for dynamic content

#### 3. **Page Extractor** (`src/page_extractor.py`)

Extracts a simplified representation of the page for the LLM:

**What it extracts:**

- **Actionable elements**: buttons, links, inputs with their selectors
- **Text content**: main page text (cleaned and structured)
- **Screenshots**: optional PNG images (base64 encoded)
- **Forms**: detected forms with their inputs
- **Metadata**: page title, URL, Open Graph data

**Selector Generation Priority:**

1. `#id` - If element has unique ID
2. `[data-testid="..."]` - Data test IDs
3. `input[name="..."]` - Form inputs with name attribute (if unique)
4. `button:has-text("...")` - Playwright text-based selector
5. `xpath=/html/body/...` - XPath fallback (always unique)

**Why this matters:** The LLM can ONLY use selectors that appear in this list - it cannot invent its own selectors, ensuring reliability.

#### 4. **LLM Client** (`src/llm_client.py`)

Interfaces with Google Gemini Chat API:

**Features:**

- Uses **multi-turn chat** (maintains conversation history)
- Sends **multimodal content** (text + screenshot)
- Parses JSON instructions from LLM responses
- Rate limits API calls (30 requests/minute)

**System Prompt:**
The LLM is instructed to:

- **ONLY** use selectors from the provided actionable elements list
- **NEVER** invent, modify, or construct CSS selectors
- Use `ask_user` when uncertain or when choices exist
- **NEVER** use `done` action (user controls when to stop)

**Chat History:**

- Maintains conversation context across turns
- Remembers previous actions and outcomes
- Can reference earlier decisions

#### 5. **Instruction Executor** (`src/instruction_executor.py`)

Executes LLM instructions on the browser:

**Supported Actions:**

- `click` - Click on an element
- `type` - Type text into an input
- `navigate` - Go to a URL
- `scroll` - Scroll the page
- `select` - Select from dropdown
- `press` - Press keyboard key
- `wait` - Wait for element/page stability
- `back` - Navigate back
- `extract` - Extract data (handled by main loop)
- `ask_user` - Ask user for input (handled by main loop)

**Error Handling:**

- Validates selectors before execution
- Reports success/failure with details
- Takes error screenshots if configured

#### 6. **Session Manager** (`src/session_manager.py`)

Manages browser state persistence:

- Saves/loads cookies
- Persists localStorage
- Supports authenticated sessions across runs

### Execution Flow Example

Here's a real-world example of how the system works:

```
User: "Find property tax for 200 Hudson St"

Step 1:
  → Extract: Finds input field #Location, button "Search"
  → LLM: "Type '200 Hudson St' into #Location"
  → Execute: Types text ✓ (auto-executed)

Step 2:
  → Extract: Page shows search button
  → LLM: "Click the search button"
  → Execute: Clicks button ✓ (auto-executed)

Step 3:
  → Extract: Page shows 2 results
  → LLM: "ask_user - Which result? Option 1 or 2?"
  → Pause: User chooses "1"

Step 4:
  → Extract: Page shows "View / Pay" button
  → LLM: "Click 'View / Pay' button"
  → Execute: Clicks ✓ (auto-executed)

Step 5:
  → Extract: Property details page loaded
  → LLM: "ask_user - What would you like to extract?"
  → Pause: User says "Extract all tax information"

Step 6:
  → Extract: All property details visible
  → LLM: "extract - {account_number: '521955', tax_amount: '$5,000', ...}"
  → Display: Shows extracted data

Step 7:
  → LLM: "ask_user - What would you like to do next?"
  → Pause: User says "stop"
  → End: Session complete
```

### Data Flow

```
Page (Playwright Browser)
    ↓
PageExtractor.extract()
    ↓
PageState {
    actionable_elements: [
        {selector: "#Location", type: "input", label: "Location"},
        {selector: "button:has-text('Search')", type: "button", label: "Search"}
    ],
    text_content: "Welcome to Property Tax Search...",
    screenshot: <bytes>
}
    ↓
LLMClient.get_instruction(page_state, goal, history)
    ↓
Instruction {
    action: "type",
    selector: "#Location",  // Must match exactly from page_state
    value: "200 Hudson St",
    reasoning: "Typing address into search field"
}
    ↓
InstructionExecutor.execute(instruction)
    ↓
BrowserEngine.type_text("#Location", "200 Hudson St")
    ↓
ActionResult {
    success: true,
    duration_ms: 150
}
    ↓
Context updated with result
    ↓
Loop continues...
```

### Key Design Decisions

1. **Auto-Execution**: Actions run automatically without confirmations - you only interact when the AI needs your input
2. **Selector Safety**: LLM must use exact selectors from page extractor - prevents selector failures
3. **User Control**: Only YOU can end the session - AI never uses `done` action
4. **Error Recovery**: On failure, shows available elements and asks for guidance
5. **SPA Support**: Waits for network idle and DOM stability after actions
6. **Multimodal**: Sends screenshots to LLM for better page understanding

## Configuration

Create a `.env` file based on `.env.example`:

```env
# Required
GEMINI_API_KEY=your_api_key_here

# Browser settings
HEADLESS=true
VIEWPORT_WIDTH=1280
VIEWPORT_HEIGHT=720
USER_AGENT=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36

# Rate limiting
REQUESTS_PER_MINUTE=30
ACTION_DELAY_MS=500

# Output settings
OUTPUT_DIR=./output
SCREENSHOT_ON_ERROR=true

# LLM settings
GEMINI_MODEL=gemini-2.5-flash
INCLUDE_SCREENSHOT=true
MAX_HISTORY=10

# Logging
LOG_LEVEL=INFO
```

## CLI Commands

### Run Automation

```bash
python cli.py run <url> <goal> [options]

Options:
  --headless/--no-headless    Run browser in headless mode (default: headless)
  --screenshot/--no-screenshot Include screenshots (default: yes)
  --max-iterations, -n        Maximum actions to take (default: 100)
  --output, -o                Output directory (default: ./output)
  --session, -s               Session name to save/load
  --delay, -d                 Delay between actions in ms (default: 500)
  --log-level, -l             Logging level (DEBUG/INFO/WARNING/ERROR)
  --model, -m                 Gemini model (default: gemini-2.5-flash)
```

### Interactive Mode

```bash
python cli.py interactive <url> --no-headless
```

Opens a browser and lets you manually test page extraction.

### Session Management

```bash
python cli.py sessions        # List saved sessions
python cli.py delete-session <name>  # Delete a session
```

## Supported Actions

The LLM can instruct the browser to perform:

| Action     | Description                           |
| ---------- | ------------------------------------- |
| `click`    | Click on an element                   |
| `type`     | Type text into an input               |
| `navigate` | Go to a URL                           |
| `scroll`   | Scroll the page                       |
| `select`   | Select from a dropdown                |
| `press`    | Press a keyboard key                  |
| `wait`     | Wait for an element or page stability |
| `back`     | Navigate back                         |
| `extract`  | Extract data from the page            |
| `ask_user` | Ask user for input/choice             |

**Note:** The `done` action is disabled - only you can end the session by typing `stop`.

## Project Structure

```
Scraping_Automation/
├── src/
│   ├── browser_engine.py      # Playwright wrapper with SPA support
│   ├── page_extractor.py      # Extract elements and text from pages
│   ├── llm_client.py          # Gemini Chat API client
│   ├── instruction_executor.py # Execute browser actions
│   ├── session_manager.py     # Session persistence
│   ├── config.py              # Configuration management
│   ├── models.py              # Data models (Pydantic)
│   └── utils.py               # Utilities (rate limiting, retries)
├── tests/                     # Test suite
│   ├── conftest.py            # Test fixtures
│   ├── test_browser_engine.py
│   └── test_llm_client.py
├── examples/                  # Example scripts
│   ├── extract_product_data.py
│   ├── form_automation.py
│   ├── search_and_extract.py
│   └── multi_page_navigation.py
├── main.py                    # Main entry point and automation loop
├── cli.py                     # Command-line interface
├── requirements.txt
├── .env.example               # Environment variable template
├── .gitignore
└── README.md
```

## Error Handling

### When Actions Fail

If an action fails (e.g., selector not found), the system will:

1. **Show available elements** on the page with their selectors
2. **Ask you what to do** - you can:
   - Type a number to click that element
   - Type `scroll` to see more elements
   - Type `elements` to see all elements in a table
   - Give instructions like "Click the search button"

### Common Issues

**Selector not found:**

- The LLM should use `ask_user` to get your guidance
- You can manually select an element by number
- Or provide a new instruction

**Page not loading:**

- System waits for network idle and DOM stability
- If still failing, try `--no-headless` mode to debug

**Cloudflare/Bot Detection:**

- Use `--no-headless` mode (most reliable)
- Stealth scripts are applied automatically
- May need to manually pass challenge once, then save session

## Testing

```bash
pytest tests/ -v
```

## Troubleshooting

### "GEMINI_API_KEY not set"

Make sure you've exported your API key:

```bash
export GEMINI_API_KEY=your_key_here
```

### Page not loading correctly

Try increasing timeouts or using non-headless mode to debug:

```bash
python cli.py run <url> <goal> --no-headless --log-level DEBUG
```

### Rate limiting errors

Reduce the request rate:

```bash
python cli.py run <url> <goal> --delay 1000
```

### LLM keeps retrying failed actions

The LLM should use `ask_user` when actions fail. If it doesn't:

- Type `stop` to end the session
- Check the available elements shown
- Provide clearer instructions in your goal

### Selector issues

The LLM can only use selectors from the page extractor. If selectors aren't working:

- Check if elements are visible (may need to scroll)
- Elements may be in iframes (not currently supported)
- Try `--no-headless` to see what's happening

## Advanced Usage

### Custom Configuration

```python
from src.config import Config, BrowserConfig, LLMConfig
from main import InteractiveBrowserAutomation

config = Config(
    browser=BrowserConfig(
        headless=False,
        viewport_width=1920,
        viewport_height=1080
    ),
    llm=LLMConfig(
        api_key="your_key",
        model="gemini-2.5-flash",
        include_screenshot=True
    )
)

automation = InteractiveBrowserAutomation(config)
```

### Session Persistence

```python
# Save session after authentication
results = await automation.run(
    start_url="https://example.com/login",
    goal="Login and navigate to dashboard",
    session_name="my_session"
)

# Later, load the session
results = await automation.run(
    start_url="https://example.com/dashboard",
    goal="Extract data",
    session_name="my_session"  # Loads cookies/auth state
)
```

## License

MIT License
