"""
Page Extractor for Browser Automation with LLM.

Extracts actionable elements, text content, and screenshots from pages.
"""

from typing import Optional
from playwright.async_api import Page
from loguru import logger

from .models import PageState, ActionableElement, ElementType
from .utils import clean_text, generate_unique_selector


# JavaScript to extract interactive elements from the page
EXTRACT_ELEMENTS_JS = """
() => {
    const elements = [];
    const seen = new Set();
    
    // Selectors for interactive elements
    const selectors = [
        'button',
        'a[href]',
        'input:not([type="hidden"])',
        'select',
        'textarea',
        '[role="button"]',
        '[role="link"]',
        '[role="menuitem"]',
        '[role="tab"]',
        '[role="checkbox"]',
        '[role="radio"]',
        '[role="switch"]',
        '[role="combobox"]',
        '[onclick]',
        '[tabindex]:not([tabindex="-1"])'
    ];
    
    // Helper to get element text
    function getElementText(el) {
        // Check for aria-label first
        if (el.getAttribute('aria-label')) {
            return el.getAttribute('aria-label');
        }
        // Check for title
        if (el.title) {
            return el.title;
        }
        // Check for inner text (limited)
        const text = el.innerText || el.textContent || '';
        return text.trim().substring(0, 100);
    }
    
    // Helper to determine element type
    function getElementType(el) {
        const tag = el.tagName.toLowerCase();
        const type = el.type?.toLowerCase() || '';
        const role = el.getAttribute('role')?.toLowerCase() || '';
        
        if (tag === 'button' || role === 'button') return 'button';
        if (tag === 'a') return 'link';
        if (tag === 'select' || role === 'combobox') return 'select';
        if (tag === 'textarea') return 'textarea';
        if (tag === 'input') {
            if (type === 'checkbox') return 'checkbox';
            if (type === 'radio') return 'radio';
            if (type === 'file') return 'file';
            if (type === 'submit') return 'submit';
            return 'input';
        }
        return 'other';
    }
    
    // Helper to generate a UNIQUE selector that will definitely work
    function generateSelector(el, index) {
        // Try ID first - most reliable
        if (el.id) {
            return '#' + CSS.escape(el.id);
        }
        
        // Try data-testid
        if (el.dataset.testid) {
            return `[data-testid="${CSS.escape(el.dataset.testid)}"]`;
        }
        
        // Try name attribute for inputs
        if (el.name && (el.tagName === 'INPUT' || el.tagName === 'SELECT' || el.tagName === 'TEXTAREA')) {
            const selector = `${el.tagName.toLowerCase()}[name="${CSS.escape(el.name)}"]`;
            // Verify it's unique
            if (document.querySelectorAll(selector).length === 1) {
                return selector;
            }
        }
        
        // Try aria-label if unique
        if (el.getAttribute('aria-label')) {
            const label = el.getAttribute('aria-label');
            const selector = `[aria-label="${CSS.escape(label)}"]`;
            if (document.querySelectorAll(selector).length === 1) {
                return selector;
            }
        }
        
        // Try text content for buttons and links
        const text = (el.innerText || el.textContent || '').trim();
        if (text && text.length < 50 && (el.tagName === 'BUTTON' || el.tagName === 'A')) {
            // Use text selector
            const tag = el.tagName.toLowerCase();
            // Try :has-text pseudo-selector (Playwright supports this)
            return `${tag}:has-text("${text.replace(/"/g, '\\"').substring(0, 30)}")`;
        }
        
        // Generate XPath as fallback - always unique
        function getXPath(element) {
            if (element.id) {
                return `//*[@id="${element.id}"]`;
            }
            if (element === document.body) {
                return '/html/body';
            }
            
            let ix = 1;
            const siblings = element.parentNode ? element.parentNode.childNodes : [];
            for (let i = 0; i < siblings.length; i++) {
                const sibling = siblings[i];
                if (sibling === element) {
                    const parentPath = getXPath(element.parentNode);
                    const tag = element.tagName.toLowerCase();
                    return `${parentPath}/${tag}[${ix}]`;
                }
                if (sibling.nodeType === 1 && sibling.tagName === element.tagName) {
                    ix++;
                }
            }
            return '';
        }
        
        // Return xpath selector (Playwright supports xpath with xpath= prefix)
        return 'xpath=' + getXPath(el);
    }
    
    // Helper to check visibility
    function isVisible(el) {
        const rect = el.getBoundingClientRect();
        const style = window.getComputedStyle(el);
        
        return (
            rect.width > 0 &&
            rect.height > 0 &&
            style.visibility !== 'hidden' &&
            style.display !== 'none' &&
            style.opacity !== '0'
        );
    }
    
    // Process each selector
    selectors.forEach(selector => {
        try {
            document.querySelectorAll(selector).forEach((el, index) => {
                // Skip hidden elements
                if (!isVisible(el)) return;
                
                // Skip duplicates
                const key = el.outerHTML.substring(0, 200);
                if (seen.has(key)) return;
                seen.add(key);
                
                const rect = el.getBoundingClientRect();
                
                elements.push({
                    selector: generateSelector(el, index),
                    element_type: getElementType(el),
                    label: getElementText(el),
                    value: el.value || '',
                    placeholder: el.placeholder || '',
                    aria_label: el.getAttribute('aria-label') || '',
                    position: {
                        x: Math.round(rect.x),
                        y: Math.round(rect.y),
                        width: Math.round(rect.width),
                        height: Math.round(rect.height)
                    },
                    visible: true,
                    enabled: !el.disabled,
                    attributes: {
                        tag: el.tagName.toLowerCase(),
                        type: el.type || null,
                        name: el.name || null,
                        href: el.href || null,
                        role: el.getAttribute('role') || null
                    }
                });
            });
        } catch (e) {
            console.error('Error processing selector:', selector, e);
        }
    });
    
    // Sort by position (top to bottom, left to right)
    elements.sort((a, b) => {
        const yDiff = a.position.y - b.position.y;
        if (Math.abs(yDiff) > 10) return yDiff;
        return a.position.x - b.position.x;
    });
    
    // Limit to prevent overwhelming the LLM
    return elements.slice(0, 100);
}
"""

# JavaScript to extract main text content
EXTRACT_TEXT_JS = """
() => {
    // Remove script and style elements
    const clone = document.body.cloneNode(true);
    clone.querySelectorAll('script, style, noscript, iframe').forEach(el => el.remove());
    
    // Get text content
    let text = clone.innerText || clone.textContent || '';
    
    // Clean up whitespace
    text = text.replace(/\\s+/g, ' ').trim();
    
    // Limit length
    return text.substring(0, 10000);
}
"""

# JavaScript to extract form information
EXTRACT_FORMS_JS = """
() => {
    const forms = [];
    
    document.querySelectorAll('form').forEach((form, index) => {
        const inputs = [];
        
        form.querySelectorAll('input, select, textarea').forEach(el => {
            if (el.type === 'hidden') return;
            
            inputs.push({
                name: el.name || null,
                type: el.type || el.tagName.toLowerCase(),
                label: el.labels?.[0]?.textContent || el.placeholder || el.name || '',
                value: el.value || '',
                required: el.required || false
            });
        });
        
        forms.push({
            id: form.id || `form-${index}`,
            action: form.action || '',
            method: form.method || 'get',
            inputs: inputs
        });
    });
    
    return forms;
}
"""


class PageExtractor:
    """
    Extracts page state for LLM processing.
    
    Provides a simplified representation of the page including
    actionable elements, text content, and optional screenshots.
    """
    
    def __init__(self, include_screenshot: bool = True, max_elements: int = 100):
        """
        Initialize the page extractor.
        
        Args:
            include_screenshot: Whether to capture screenshots
            max_elements: Maximum number of elements to extract
        """
        self.include_screenshot = include_screenshot
        self.max_elements = max_elements
    
    async def extract(self, page: Page) -> PageState:
        """
        Extract the current state of the page.
        
        Args:
            page: Playwright page object
        
        Returns:
            PageState object with extracted information
        """
        logger.debug("Extracting page state...")
        
        # Get basic page info
        url = page.url
        title = await page.title()
        
        # Extract elements
        elements = await self._extract_elements(page)
        
        # Extract text content
        text_content = await self._extract_text(page)
        
        # Extract forms
        forms = await self._extract_forms(page)
        
        # Take screenshot if enabled
        screenshot = None
        if self.include_screenshot:
            screenshot = await self._take_screenshot(page)
        
        # Extract metadata
        metadata = await self._extract_metadata(page)
        
        page_state = PageState(
            url=url,
            title=title,
            actionable_elements=elements,
            text_content=text_content,
            screenshot=screenshot,
            forms=forms,
            metadata=metadata
        )
        
        logger.debug(
            f"Extracted: {len(elements)} elements, "
            f"{len(text_content)} chars text, "
            f"{len(forms)} forms"
        )
        
        return page_state
    
    async def _extract_elements(self, page: Page) -> list[ActionableElement]:
        """Extract actionable elements from the page."""
        try:
            raw_elements = await page.evaluate(EXTRACT_ELEMENTS_JS)
            
            elements = []
            for el in raw_elements[:self.max_elements]:
                try:
                    element = ActionableElement(
                        selector=el.get("selector", ""),
                        element_type=ElementType(el.get("element_type", "other")),
                        label=el.get("label", ""),
                        value=el.get("value", ""),
                        placeholder=el.get("placeholder", ""),
                        aria_label=el.get("aria_label", ""),
                        position=el.get("position", {}),
                        visible=el.get("visible", True),
                        enabled=el.get("enabled", True),
                        attributes=el.get("attributes", {})
                    )
                    elements.append(element)
                except Exception as e:
                    logger.debug(f"Error parsing element: {e}")
                    continue
            
            return elements
            
        except Exception as e:
            logger.error(f"Error extracting elements: {e}")
            return []
    
    async def _extract_text(self, page: Page) -> str:
        """Extract main text content from the page."""
        try:
            text = await page.evaluate(EXTRACT_TEXT_JS)
            return clean_text(text)
        except Exception as e:
            logger.error(f"Error extracting text: {e}")
            return ""
    
    async def _extract_forms(self, page: Page) -> list[dict]:
        """Extract form information from the page."""
        try:
            return await page.evaluate(EXTRACT_FORMS_JS)
        except Exception as e:
            logger.error(f"Error extracting forms: {e}")
            return []
    
    async def _take_screenshot(self, page: Page) -> Optional[bytes]:
        """Take a screenshot of the visible viewport."""
        try:
            return await page.screenshot(type="png")
        except Exception as e:
            logger.error(f"Error taking screenshot: {e}")
            return None
    
    async def _extract_metadata(self, page: Page) -> dict:
        """Extract page metadata (title, description, etc.)."""
        try:
            metadata = await page.evaluate("""
                () => {
                    const getMeta = (name) => {
                        const el = document.querySelector(`meta[name="${name}"], meta[property="${name}"]`);
                        return el ? el.content : null;
                    };
                    
                    return {
                        description: getMeta('description') || getMeta('og:description'),
                        keywords: getMeta('keywords'),
                        og_title: getMeta('og:title'),
                        og_image: getMeta('og:image'),
                        canonical: document.querySelector('link[rel="canonical"]')?.href
                    };
                }
            """)
            return metadata
        except Exception as e:
            logger.debug(f"Error extracting metadata: {e}")
            return {}
    
    def format_for_llm(self, page_state: PageState, max_elements: int = 50) -> str:
        """
        Format page state as a string for LLM input.
        
        Args:
            page_state: PageState to format
            max_elements: Max elements to include
        
        Returns:
            Formatted string representation
        """
        parts = [
            f"Current URL: {page_state.url}",
            f"Page Title: {page_state.title}",
            ""
        ]
        
        # Add elements section
        if page_state.actionable_elements:
            parts.append("=== ACTIONABLE ELEMENTS ===")
            for i, el in enumerate(page_state.actionable_elements[:max_elements], 1):
                label = el.label or el.placeholder or el.aria_label or "(no label)"
                value_part = f'value="{el.value[:30]}"' if el.value else ""
                parts.append(
                    f"{i}. [{el.element_type.value.upper()}] "
                    f'selector="{el.selector}" '
                    f'label="{label[:50]}" '
                    f"{value_part}"
                )
            parts.append("")
        
        # Add forms section
        if page_state.forms:
            parts.append("=== FORMS ===")
            for form in page_state.forms:
                parts.append(f"Form: {form.get('id', 'unnamed')} ({form.get('method', 'get').upper()})")
                for inp in form.get("inputs", []):
                    parts.append(f"  - {inp.get('label', 'input')}: [{inp.get('type')}] name=\"{inp.get('name')}\"")
            parts.append("")
        
        # Add text content (truncated)
        if page_state.text_content:
            parts.append("=== PAGE TEXT (excerpt) ===")
            parts.append(page_state.text_content[:2000])
            if len(page_state.text_content) > 2000:
                parts.append("... [text truncated]")
        
        return "\n".join(parts)

