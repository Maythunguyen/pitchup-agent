
import json
from pathlib import Path
from typing import Type, TypeVar
from pydantic import BaseModel
from dotenv import load_dotenv
import base64
import io
from PIL import Image

load_dotenv()

from openai import OpenAI

_openai = OpenAI()

T = TypeVar("T", bound=BaseModel)


# ─────────────────────────────────────────────
# SCREENSHOT COMPRESSOR
# Must be defined before PitchupAgent class
# ─────────────────────────────────────────────

def _compress_screenshot(b64_data: str, max_width: int = 1280) -> str:
    """Resize and compress screenshot to reduce token usage"""
    img_bytes = base64.b64decode(b64_data)
    img = Image.open(io.BytesIO(img_bytes))

    if img.width > max_width:
        ratio = max_width / img.width
        new_height = int(img.height * ratio)
        img = img.resize((max_width, new_height), Image.LANCZOS)

    buffer = io.BytesIO()
    img.convert("RGB").save(buffer, format="JPEG", quality=70)
    return base64.b64encode(buffer.getvalue()).decode("utf-8")


# ─────────────────────────────────────────────
# llm_do — call OpenAI like a simple function
# drop-in replacement for connectonion.llm_do
# ─────────────────────────────────────────────

def llm_do(prompt, output=None, model="gpt-4o", temperature=0.1, system=None, image_b64=None):
    messages = []
    if system:
        messages.append({"role": "system", "content": system})

    content = []
    if image_b64:
        if image_b64.startswith("data:image"):
            image_b64 = image_b64.split(",", 1)[1].split("\n")[0].strip()
        # Compress image before sending
        image_b64 = _compress_screenshot(image_b64)
        content.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}
        })

    if output:
        content.append({
            "type": "text",
            "text": f"{prompt}\n\nReturn ONLY valid JSON. No markdown."
        })
    else:
        content.append({"type": "text", "text": prompt})

    messages.append({"role": "user", "content": content})

    response = _openai.chat.completions.create(
        model=model,
        temperature=temperature,
        messages=messages
    )

    raw = response.choices[0].message.content.strip()

    if output is None:
        return raw

    try:
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        return output(**json.loads(raw.strip()))
    except Exception as e:
        raise ValueError(f"Failed to parse response: {e}")


# ─────────────────────────────────────────────
# LOAD SYSTEM PROMPT
# ─────────────────────────────────────────────

_PROMPT_PATH = Path(__file__).parent / "prompts" / "pitchup_agent.md"
SYSTEM_PROMPT = _PROMPT_PATH.read_text() if _PROMPT_PATH.exists() else """
You are PitchupAgent — an AI browser agent built for PitchUp.com.au.
You help fetch venue availability and complete bookings.
The browser is already open and on the starting URL.
ALWAYS start by taking a screenshot. Never use full_page=true.
Say DONE when finished, FAILED if unsuccessful.
"""


# ─────────────────────────────────────────────
# TOOL SCHEMA CONVERTER
# ─────────────────────────────────────────────

def _to_openai_tools(tools: list) -> list:
    """Convert Anthropic-style tool definitions to OpenAI format"""
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


# ─────────────────────────────────────────────
# MESSAGE HISTORY CLEANER
# Remove old screenshots to save tokens
# ─────────────────────────────────────────────

def _clean_messages(messages: list) -> list:
    """
    Remove old screenshot tool results from message history.
    Only keep the latest screenshot — old ones waste tokens.
    """
    cleaned = []
    screenshot_count = 0

    # Count total screenshots
    total_screenshots = sum(
        1 for m in messages
        if m.get("role") == "tool" and "image_url" in str(m.get("content", ""))
    )

    for m in messages:
        is_screenshot = (
            m.get("role") == "tool" and
            "image_url" in str(m.get("content", ""))
        )
        if is_screenshot:
            screenshot_count += 1
            # Only keep the latest screenshot
            if screenshot_count < total_screenshots:
                # Replace old screenshot with placeholder to maintain message chain
                cleaned.append({
                    "role": "tool",
                    "tool_call_id": m["tool_call_id"],
                    "content": "[screenshot removed to save context]"
                })
                continue
        cleaned.append(m)

    return cleaned


# ─────────────────────────────────────────────
# PITCHUP AGENT CLASS
# ─────────────────────────────────────────────

class PitchupAgent:
    """
    The central brain of the Pitchup browser agent system.
    OpenAI powers the LLM. Playwright handles the browser.
    Everything imports from here.
    """

    def __init__(self, max_iterations: int = 20, headless: bool = True):
        self.max_iterations = max_iterations
        self.headless = headless
        self._openai = _openai

    def run(self, task: str, url: str) -> dict:
        """
        Main agent loop — Think → Act → Observe → Repeat
        """
        from tools.browser_tools.browser import BrowserAutomation
        from tools.pitchup_tools import PITCHUP_TOOLS, execute_pitchup_tool

        BROWSER_TOOLS = _get_browser_tool_definitions()
        ALL_TOOLS = _to_openai_tools(BROWSER_TOOLS + PITCHUP_TOOLS)

        browser = BrowserAutomation(headless=self.headless)
        browser.open_browser()
        browser.go_to(url)

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": task}
        ]

        result = {"status": "failed", "data": None, "steps": []}

        print(f"\n🤖 PitchupAgent starting: {task[:80]}...")
        print(f"🌐 URL: {url}\n")

        try:
            for i in range(self.max_iterations):
                print(f"── Step {i + 1}/{self.max_iterations} ──")

                # Clean old screenshots before each API call
                clean_msgs = _clean_messages(messages)

                # Ask OpenAI what to do next
                response = self._openai.chat.completions.create(
                    model="gpt-4o",
                    max_tokens=1024,
                    tools=ALL_TOOLS,
                    messages=clean_msgs
                )

                choice = response.choices[0]
                finish_reason = choice.finish_reason
                print(f"Finish reason: {finish_reason}")

                # Done — no more tool calls
                if finish_reason == "stop":
                    final_text = choice.message.content or ""
                    print(f"✅ Finished: {final_text[:100]}")
                    result["status"] = "success"
                    result["data"] = final_text
                    break

                # Tool calls
                if finish_reason == "tool_calls" and choice.message.tool_calls:

                    # Add assistant message
                    messages.append({
                        "role": "assistant",
                        "content": choice.message.content,
                        "tool_calls": [
                            {
                                "id": tc.id,
                                "type": "function",
                                "function": {
                                    "name": tc.function.name,
                                    "arguments": tc.function.arguments
                                }
                            }
                            for tc in choice.message.tool_calls
                        ]
                    })

                    # Execute each tool
                    for tool_call in choice.message.tool_calls:
                        tool_name = tool_call.function.name
                        tool_input = json.loads(tool_call.function.arguments)

                        print(f"🔧 {tool_name}: {json.dumps(tool_input)[:60]}")

                        # Route to correct executor
                        if tool_name in ["get_availability_slots",
                                         "extract_booking_confirmation",
                                         "get_page_structured_data"]:
                            tool_output = execute_pitchup_tool(
                                browser, tool_name, tool_input
                            )
                        else:
                            tool_output = _execute_browser_tool(
                                browser, tool_name, tool_input
                            )

                        print(f"   → {str(tool_output)[:80]}")

                        # Screenshots — compress and add as image
                        if tool_name == "take_screenshot":
                            try:
                                parsed = json.loads(tool_output)
                                compressed = _compress_screenshot(parsed["data"])
                                messages.append({
                                    "role": "tool",
                                    "tool_call_id": tool_call.id,
                                    "content": json.dumps({
                                        "type": "image_url",
                                        "image_url": {
                                            "url": f"data:image/jpeg;base64,{compressed}"
                                        }
                                    })
                                })
                            except Exception:
                                messages.append({
                                    "role": "tool",
                                    "tool_call_id": tool_call.id,
                                    "content": "Screenshot taken successfully"
                                })
                        else:
                            messages.append({
                                "role": "tool",
                                "tool_call_id": tool_call.id,
                                "content": str(tool_output)
                            })

                        result["steps"].append({
                            "step": i + 1,
                            "tool": tool_name,
                            "input": tool_input,
                            "output": str(tool_output)[:200]
                        })

        finally:
            browser.close()

        return result

    # ─────────────────────────────────────────
    # PITCHUP-SPECIFIC TASKS
    # ─────────────────────────────────────────

    def fetch_availability(self, venue_url: str, sport: str, date: str) -> dict:
        """Visit a venue website and return available booking slots."""
        task = f"""
        Find available booking slots on this venue website.
        Sport: {sport} | Date: {date}
        1. Wait 3 seconds for page to load
        2. Take a screenshot
        3. Navigate to booking/availability section
        4. Use get_availability_slots tool to extract as JSON
        5. Say DONE with results — FAILED if nothing found
        """
        return self.run(task, venue_url)

    def complete_booking(self, venue_url: str, slot: dict, user: dict) -> dict:
        """Complete a booking on a venue website for a Pitchup user."""
        task = f"""
        Complete a booking: {slot.get('sport')} on {slot.get('date')} at {slot.get('time')}
        User: {user.get('name')}, {user.get('email')}, {user.get('phone')}
        1. Wait 3 seconds for page to load
        2. Take a screenshot
        3. Find booking form
        4. Fill in all details field by field
        5. Submit
        6. Use extract_booking_confirmation tool
        7. Say DONE with confirmation — FAILED if unsuccessful
        """
        return self.run(task, venue_url)

    def discover_venues(self, sport: str, suburb: str) -> dict:
        """Search Google for new venues not yet on Pitchup."""
        url = f"https://www.google.com/search?q={sport}+venue+hire+{suburb}+Australia"
        task = f"""
        Find {sport} venues in {suburb} not yet on Pitchup.
        1. Take a screenshot
        2. Find council/school/community venue websites
        3. Use get_page_structured_data to extract details
        4. Return as JSON list
        5. Say DONE when finished
        """
        return self.run(task, url)


# ─────────────────────────────────────────────
# BROWSER TOOL DEFINITIONS
# ─────────────────────────────────────────────

def _get_browser_tool_definitions():
    return [
        {
            "name": "take_screenshot",
            "description": "Take a screenshot of the current browser page. Always use full_page=false.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "full_page": {
                        "type": "boolean",
                        "description": "Always set to false",
                        "default": False
                    }
                },
                "required": []
            }
        },
        {
            "name": "go_to",
            "description": "Navigate to a URL",
            "input_schema": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "Full URL to navigate to"}
                },
                "required": ["url"]
            }
        },
        {
            "name": "click",
            "description": "Click an element using plain English description. Uses AI vision to find it.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "description": {"type": "string", "description": "e.g. 'the Sports category tab'"}
                },
                "required": ["description"]
            }
        },
        {
            "name": "type_text",
            "description": "Type text into the currently focused element",
            "input_schema": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"}
                },
                "required": ["text"]
            }
        },
        {
            "name": "keyboard_press",
            "description": "Press a key e.g. Enter, Tab, Escape",
            "input_schema": {
                "type": "object",
                "properties": {
                    "key": {"type": "string"}
                },
                "required": ["key"]
            }
        },
        {
            "name": "scroll",
            "description": "Scroll the page up or down",
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
            "description": "Get all visible text from the current page",
            "input_schema": {
                "type": "object",
                "properties": {},
                "required": []
            }
        },
        {
            "name": "get_current_url",
            "description": "Get the current page URL",
            "input_schema": {
                "type": "object",
                "properties": {},
                "required": []
            }
        },
        {
            "name": "wait",
            "description": "Wait for seconds for the page to load",
            "input_schema": {
                "type": "object",
                "properties": {
                    "seconds": {"type": "number", "default": 2}
                },
                "required": []
            }
        }
    ]


# ─────────────────────────────────────────────
# BROWSER TOOL EXECUTOR
# ─────────────────────────────────────────────

def _execute_browser_tool(browser, tool_name: str, tool_input: dict) -> str:
    """Execute a browser tool via BrowserAutomation"""

    if tool_name == "take_screenshot":
        # Always force full_page=False to avoid token limit errors
        result = browser.take_screenshot(full_page=False)
        if result.startswith("data:image/png;base64,"):
            b64 = result.split(",", 1)[1].split("\n")[0].strip()
            return json.dumps({"type": "screenshot", "data": b64})
        return json.dumps({"type": "screenshot", "data": result})

    elif tool_name == "go_to":
        return browser.go_to(tool_input["url"])

    elif tool_name == "click":
        try:
            return browser.click(tool_input["description"])
        except Exception as e:
            return f"Could not find element: {str(e)[:200]}"

    elif tool_name == "type_text":
        return browser.keyboard_type(tool_input["text"])

    elif tool_name == "keyboard_press":
        return browser.keyboard_press(tool_input["key"])

    elif tool_name == "scroll":
        return browser.scroll(
            times=tool_input.get("times", 3),
            description=f"scroll {tool_input['direction']}"
        )

    elif tool_name == "get_page_text":
        return browser.get_text()[:3000]

    elif tool_name == "get_current_url":
        return browser.get_current_url()

    elif tool_name == "wait":
        return browser.wait(tool_input.get("seconds", 2))

    return f"Unknown tool: {tool_name}"


# ─────────────────────────────────────────────
# SHARED INSTANCE
# from pitchup_agent import pitchup_agent
# ─────────────────────────────────────────────

pitchup_agent = PitchupAgent()


# ─────────────────────────────────────────────
# RUN DIRECTLY
# ─────────────────────────────────────────────

if __name__ == "__main__":
    agent = PitchupAgent(headless=False, max_iterations=15)
    result = agent.fetch_availability(
        venue_url="https://parramatta.bookable.net.au/",
        sport="tennis",
        date="Saturday 2026-05-24"
    )
    print(json.dumps(result, indent=2))