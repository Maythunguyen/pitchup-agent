
# All browser tool definitions for the OpenAI function calling API
# Add new tools here — executor lives in tool_executor.py


def get_browser_tool_definitions() -> list:
    """Returns all browser tool schemas for OpenAI function calling."""
    return [
        {
            "name": "take_screenshot",
            "description": "Take a screenshot of the current browser page. Always use full_page=false.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "full_page": {"type": "boolean", "description": "Always set to false", "default": False}
                },
                "required": []
            }
        },
        {
            "name": "go_to",
            "description": "Navigate to a URL",
            "input_schema": {
                "type": "object",
                "properties": {"url": {"type": "string", "description": "Full URL to navigate to"}},
                "required": ["url"]
            }
        },
        {
            "name": "click",
            "description": "Click an element using plain English description. Uses AI vision to find it.",
            "input_schema": {
                "type": "object",
                "properties": {"description": {"type": "string", "description": "e.g. 'the Sign in button'"}},
                "required": ["description"]
            }
        },
        {
            "name": "click_available_slot",
            "description": "Click the first available booking slot on ThinkSmart grid using CSS selector td.Selectable.",
            "input_schema": {
                "type": "object",
                "properties": {},
                "required": []
            }
        },
        {
            "name": "click_by_js",
            "description": "Force click a button by its text using JavaScript. Use when normal click fails with 'element not visible'.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "Button text e.g. 'I am not a Member'"}
                },
                "required": ["text"]
            }
        },
        {
            "name": "select_option",
            "description": "Select a dropdown option by label text using JavaScript. Use for <select> elements.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "selector": {"type": "string", "description": "CSS selector e.g. 'select'"},
                    "value": {"type": "string", "description": "Option label e.g. '60 minutes'"}
                },
                "required": ["selector", "value"]
            }
        },
        {
            "name": "set_date_by_js",
            "description": "Set the date on ThinkSmart booking calendar via JavaScript. Date must be DD/MM/YYYY.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "date": {"type": "string", "description": "Date in DD/MM/YYYY e.g. '19/06/2026'"}
                },
                "required": ["date"]
            }
        },
        {
            "name": "fill_field_by_js",
            "description": "Fill an input field via JavaScript by label text. Use when normal click+type fails inside modals.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "label": {"type": "string", "description": "Label text e.g. 'First name', 'Email address'"},
                    "value": {"type": "string", "description": "Value to fill in"}
                },
                "required": ["label", "value"]
            }
        },
        {
            "name": "type_text",
            "description": "Type text into the currently focused element.",
            "input_schema": {
                "type": "object",
                "properties": {"text": {"type": "string"}},
                "required": ["text"]
            }
        },
        {
            "name": "keyboard_press",
            "description": "Press a key e.g. Enter, Tab, Escape, ArrowRight, ArrowLeft.",
            "input_schema": {
                "type": "object",
                "properties": {"key": {"type": "string"}},
                "required": ["key"]
            }
        },
        {
            "name": "scroll",
            "description": "Scroll the page up or down.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "direction": {"type": "string", "enum": ["up", "down"]},
                    "times": {"type": "integer", "default": 3}
                },
                "required": ["direction"]
            }
        },
        {
            "name": "get_page_text",
            "description": "Get all visible text from the current page.",
            "input_schema": {"type": "object", "properties": {}, "required": []}
        },
        {
            "name": "get_current_url",
            "description": "Get the current page URL.",
            "input_schema": {"type": "object", "properties": {}, "required": []}
        },
        {
            "name": "wait",
            "description": "Wait for N seconds for the page to load.",
            "input_schema": {
                "type": "object",
                "properties": {"seconds": {"type": "number", "default": 2}},
                "required": []
            }
        }
    ]


def to_openai_tools(tools: list) -> list:
    """Convert Anthropic-style tool definitions to OpenAI function calling format."""
    return [
        {
            "type": "function",
            "function": {
                "name": tool["name"],
                "description": tool["description"],
                "parameters": tool["input_schema"]
            }
        }
        for tool in tools
    ]