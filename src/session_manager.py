"""
Session Manager for Browser Automation with LLM.

Handles browser state persistence, cookies, and authentication.
"""

import json
from pathlib import Path
from typing import Optional
from loguru import logger

from .browser_engine import BrowserEngine
from .config import Config


class SessionManager:
    """
    Manages browser session state for persistence across runs.
    
    Saves and loads cookies, localStorage, and other state data.
    """
    
    def __init__(self, config: Config, browser: BrowserEngine):
        """
        Initialize the session manager.
        
        Args:
            config: Configuration object
            browser: Browser engine instance
        """
        self.config = config
        self.browser = browser
        self.session_dir = config.output.output_dir / "sessions"
    
    async def save_session(self, session_name: str = "default") -> bool:
        """
        Save the current browser session state.
        
        Args:
            session_name: Name for the saved session
        
        Returns:
            True if session was saved successfully
        """
        try:
            # Create session directory if it doesn't exist
            self.session_dir.mkdir(parents=True, exist_ok=True)
            
            session_path = self.session_dir / f"{session_name}.json"
            
            # Get cookies from browser context
            cookies = await self.browser.get_cookies()
            
            # Get localStorage data
            local_storage = await self._get_local_storage()
            
            # Get current URL
            current_url = await self.browser.get_current_url()
            
            session_data = {
                "cookies": cookies,
                "local_storage": local_storage,
                "current_url": current_url,
            }
            
            with open(session_path, "w") as f:
                json.dump(session_data, f, indent=2)
            
            logger.info(f"Session saved: {session_path}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to save session: {e}")
            return False
    
    async def load_session(self, session_name: str = "default") -> bool:
        """
        Load a previously saved browser session.
        
        Args:
            session_name: Name of the session to load
        
        Returns:
            True if session was loaded successfully
        """
        try:
            session_path = self.session_dir / f"{session_name}.json"
            
            if not session_path.exists():
                logger.warning(f"Session not found: {session_path}")
                return False
            
            with open(session_path, "r") as f:
                session_data = json.load(f)
            
            # Restore cookies
            cookies = session_data.get("cookies", [])
            if cookies:
                await self.browser.set_cookies(cookies)
                logger.debug(f"Restored {len(cookies)} cookies")
            
            # Restore localStorage
            local_storage = session_data.get("local_storage", {})
            if local_storage:
                await self._set_local_storage(local_storage)
                logger.debug("Restored localStorage")
            
            # Navigate to last URL if desired
            # current_url = session_data.get("current_url")
            # if current_url:
            #     await self.browser.navigate(current_url)
            
            logger.info(f"Session loaded: {session_path}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to load session: {e}")
            return False
    
    async def clear_session(self, session_name: str = "default") -> bool:
        """
        Delete a saved session.
        
        Args:
            session_name: Name of the session to delete
        
        Returns:
            True if session was deleted
        """
        try:
            session_path = self.session_dir / f"{session_name}.json"
            
            if session_path.exists():
                session_path.unlink()
                logger.info(f"Session deleted: {session_path}")
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to delete session: {e}")
            return False
    
    async def list_sessions(self) -> list[str]:
        """
        List all saved sessions.
        
        Returns:
            List of session names
        """
        if not self.session_dir.exists():
            return []
        
        sessions = []
        for path in self.session_dir.glob("*.json"):
            sessions.append(path.stem)
        
        return sessions
    
    async def _get_local_storage(self) -> dict:
        """Get all localStorage data from the page."""
        try:
            return await self.browser.evaluate("""
                () => {
                    const data = {};
                    for (let i = 0; i < localStorage.length; i++) {
                        const key = localStorage.key(i);
                        data[key] = localStorage.getItem(key);
                    }
                    return data;
                }
            """)
        except Exception:
            return {}
    
    async def _set_local_storage(self, data: dict) -> None:
        """Set localStorage data on the page."""
        try:
            for key, value in data.items():
                await self.browser.evaluate(
                    f"localStorage.setItem('{key}', '{value}')"
                )
        except Exception as e:
            logger.debug(f"Failed to set localStorage: {e}")
    
    async def authenticate(
        self,
        login_url: str,
        username_selector: str,
        password_selector: str,
        submit_selector: str,
        username: str,
        password: str,
        success_indicator: Optional[str] = None
    ) -> bool:
        """
        Perform a login flow.
        
        Args:
            login_url: URL of the login page
            username_selector: Selector for username input
            password_selector: Selector for password input
            submit_selector: Selector for submit button
            username: Username to enter
            password: Password to enter
            success_indicator: Optional selector to verify successful login
        
        Returns:
            True if authentication succeeded
        """
        try:
            # Navigate to login page
            await self.browser.navigate(login_url)
            
            # Enter credentials
            await self.browser.type_text(username_selector, username)
            await self.browser.type_text(password_selector, password)
            
            # Submit
            await self.browser.click(submit_selector, wait_after=True)
            
            # Verify success if indicator provided
            if success_indicator:
                success = await self.browser.wait_for_selector(
                    success_indicator,
                    timeout=10000
                )
                if not success:
                    logger.warning("Login success indicator not found")
                    return False
            
            logger.info("Authentication successful")
            return True
            
        except Exception as e:
            logger.error(f"Authentication failed: {e}")
            return False

