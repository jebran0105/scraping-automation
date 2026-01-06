"""
Tests for the LLM Client.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.llm_client import LLMClient
from src.models import ActionType, PageState, ActionableElement, ElementType
from src.config import LLMConfig


@pytest.fixture
def llm_config():
    """Create LLM configuration for testing."""
    return LLMConfig(
        api_key="test_api_key",
        model="gemini-2.5-flash",
        include_screenshot=False,
        max_history=10
    )


@pytest.fixture
def mock_genai_response():
    """Create a mock Gemini API response."""
    response = MagicMock()
    response.text = '''
    {
        "action": "click",
        "selector": "#submit-btn",
        "reasoning": "Clicking the submit button to proceed"
    }
    '''
    return response


class TestLLMClient:
    """Tests for LLMClient class."""
    
    def test_init(self, llm_config):
        """Test LLM client initialization."""
        with patch("src.llm_client.genai"):
            client = LLMClient(llm_config)
            assert client.config == llm_config
            assert client.conversation_history == []
    
    @pytest.mark.asyncio
    async def test_get_instruction_click(self, llm_config, sample_page_state, mock_genai_response):
        """Test getting a click instruction from LLM."""
        with patch("src.llm_client.genai") as mock_genai:
            mock_client = MagicMock()
            mock_client.models.generate_content = MagicMock(return_value=mock_genai_response)
            mock_genai.Client.return_value = mock_client
            
            client = LLMClient(llm_config)
            client.client = mock_client
            
            instruction = await client.get_instruction(
                page_state=sample_page_state,
                goal="Submit the form"
            )
            
            assert instruction.action == ActionType.CLICK
            assert instruction.selector == "#submit-btn"
            assert "submit" in instruction.reasoning.lower()
    
    @pytest.mark.asyncio
    async def test_get_instruction_navigate(self, llm_config, sample_page_state):
        """Test getting a navigate instruction from LLM."""
        mock_response = MagicMock()
        mock_response.text = '''
        {
            "action": "navigate",
            "url": "https://example.com/about",
            "reasoning": "Navigating to the about page"
        }
        '''
        
        with patch("src.llm_client.genai") as mock_genai:
            mock_client = MagicMock()
            mock_client.models.generate_content = MagicMock(return_value=mock_response)
            mock_genai.Client.return_value = mock_client
            
            client = LLMClient(llm_config)
            client.client = mock_client
            
            instruction = await client.get_instruction(
                page_state=sample_page_state,
                goal="Go to the about page"
            )
            
            assert instruction.action == ActionType.NAVIGATE
            assert instruction.url == "https://example.com/about"
    
    @pytest.mark.asyncio
    async def test_get_instruction_extract(self, llm_config, sample_page_state):
        """Test getting an extract instruction from LLM."""
        mock_response = MagicMock()
        mock_response.text = '''
        {
            "action": "extract",
            "reasoning": "Extracting the data",
            "extracted_data": {"title": "Example Domain", "items": ["item1", "item2"]}
        }
        '''
        
        with patch("src.llm_client.genai") as mock_genai:
            mock_client = MagicMock()
            mock_client.models.generate_content = MagicMock(return_value=mock_response)
            mock_genai.Client.return_value = mock_client
            
            client = LLMClient(llm_config)
            client.client = mock_client
            
            instruction = await client.get_instruction(
                page_state=sample_page_state,
                goal="Extract the data"
            )
            
            assert instruction.action == ActionType.EXTRACT
            assert instruction.extracted_data is not None
            assert "title" in instruction.extracted_data
    
    @pytest.mark.asyncio
    async def test_get_instruction_handles_malformed_json(self, llm_config, sample_page_state):
        """Test handling of malformed JSON response."""
        mock_response = MagicMock()
        mock_response.text = "This is not valid JSON"
        
        with patch("src.llm_client.genai") as mock_genai:
            mock_client = MagicMock()
            mock_client.models.generate_content = MagicMock(return_value=mock_response)
            mock_genai.Client.return_value = mock_client
            
            client = LLMClient(llm_config)
            client.client = mock_client
            
            instruction = await client.get_instruction(
                page_state=sample_page_state,
                goal="Do something"
            )
            
            # Should return a wait instruction on error
            assert instruction.action == ActionType.WAIT
    
    def test_clear_history(self, llm_config):
        """Test clearing conversation history."""
        with patch("src.llm_client.genai"):
            client = LLMClient(llm_config)
            client.conversation_history = [{"role": "user", "content": "test"}]
            
            client.clear_history()
            
            assert client.conversation_history == []
    
    def test_parse_json_from_markdown(self, llm_config):
        """Test parsing JSON from markdown code blocks."""
        with patch("src.llm_client.genai"):
            client = LLMClient(llm_config)
            
            response_text = '''
            Here's my response:
            
            ```json
            {
                "action": "type",
                "selector": "input",
                "value": "hello",
                "reasoning": "Typing text"
            }
            ```
            '''
            
            instruction = client._parse_response(response_text)
            
            assert instruction.action == ActionType.TYPE
            assert instruction.value == "hello"

