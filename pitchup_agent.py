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


def _compress_screenshot(b64_data: str, max_width: int = 1280) -> str:
    img_bytes = base64.b64decode(b64_data)
    img = Image.open(io.BytesIO(img_bytes))
    if img.width > max_width:
        ratio = max_width / img.width
        new_height = int(img.height * ratio)
        img = img.resize((max_width, new_height), Image.LANCZOS)
    buffer = io.BytesIO()
    img.convert("RGB").save(buffer, format="JPEG", quality=70)
    return base64.b64encode(buffer.getvalue()).decode("utf-8")


def llm_do(prompt, output=None, model="gpt-4o", temperature=0.1, system=None, image_b64=None):
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    content = []
    if image_b64:
        if image_b64.startswith("data:image"):
            image_b64 = image_b64.split(",", 1)[1].split("\n")[0].strip()
        image_b64 = _compress_screenshot(image_b64)
        content.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}})
    if output:
        content.append({"type": "text", "text": f"{prompt}\n\nReturn ONLY valid JSON. No markdown."})
    else:
        content.append({"type": "text", "text": prompt})
    messages.append({"role": "user", "content": content})
    response = _openai.chat.completions.create(model=model, temperature=temperature, messages=messages)
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


_PROMPT_PATH = Path(__file__).parent / "prompts" / "pitchup_agent.md"
SYSTEM_PROMPT = _PROMPT_PATH.read_text() if _PROMPT_PATH.exists() else """
You are PitchupAgent — an AI browser agent built for PitchUp.com.au.
You help fetch venue availability and complete bookings.
The browser is already open and on the starting URL.
ALWAYS start by taking a screenshot. Never use full_page=true.
Say DONE when finished, FAILED if unsuccessful.
"""


def _to_openai_tools(tools: list) -> list:
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


def _clean_messages(messages: list) -> list:
    cleaned = []
    screenshot_count = 0
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
            if screenshot_count < total_screenshots:
                cleaned.append({
                    "role": "tool",
                    "tool_call_id": m["tool_call_id"],
                    "content": "[screenshot removed to save context]"
                })
                continue
        cleaned.append(m)
    return cleaned


class PitchupAgent:
    def __init__(self, max_iterations: int = 20, headless: bool = True):
        self.max_iterations = max_iterations
        self.headless = headless
        self._openai = _openai

    def run(self, task: str, url: str) -> dict:
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
                clean_msgs = _clean_messages(messages)
                response = self._openai.chat.completions.create(
                    model="gpt-4o",
                    max_tokens=2048,
                    tools=ALL_TOOLS,
                    messages=clean_msgs
                )
                choice = response.choices[0]
                finish_reason = choice.finish_reason
                print(f"Finish reason: {finish_reason}")

                if finish_reason == "stop":
                    final_text = choice.message.content or ""
                    print(f"✅ Finished: {final_text[:100]}")
                    result["status"] = "success"
                    result["data"] = final_text
                    break

                if finish_reason == "tool_calls" and choice.message.tool_calls:
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

                    for tool_call in choice.message.tool_calls:
                        tool_name = tool_call.function.name
                        tool_input = json.loads(tool_call.function.arguments)
                        print(f"🔧 {tool_name}: {json.dumps(tool_input)[:60]}")

                        if tool_name in ["get_availability_slots", "extract_booking_confirmation", "get_page_structured_data"]:
                            tool_output = execute_pitchup_tool(browser, tool_name, tool_input)
                        else:
                            tool_output = _execute_browser_tool(browser, tool_name, tool_input)

                        print(f"   → {str(tool_output)[:80]}")

                        if tool_name == "take_screenshot":
                            try:
                                parsed = json.loads(tool_output)
                                compressed = _compress_screenshot(parsed["data"])
                                messages.append({
                                    "role": "tool",
                                    "tool_call_id": tool_call.id,
                                    "content": json.dumps({
                                        "type": "image_url",
                                        "image_url": {"url": f"data:image/jpeg;base64,{compressed}"}
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

    def fetch_availability(self, venue_url: str, sport: str, date: str) -> dict:
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

    def complete_booking(self, venue_url: str, slot: dict, user: dict,
                         login_email: str = None, login_password: str = None) -> dict:

        duration_mins = slot.get('duration', 60)

        # ── ThinkSmart (Fawkner Park) — no login, use CSS selector ──
        if "thinksmartsoftware" in venue_url:
            raw_date = slot.get('date', '')
            try:
                parts = raw_date.split("-")
                display_date = f"{parts[2]}/{parts[1]}/{parts[0]}"
            except:
                display_date = raw_date

            task = f"""
            STEP 1 — Set date:
            - Wait 8 seconds for page to load
            - Use set_date_by_js tool with date='{display_date}'
            - Wait 2 seconds, take a screenshot
            - DO NOT click the date field or open any calendar

            STEP 2 — Click available slot:
            - Use click_available_slot tool
            - Wait 2 seconds

            STEP 3 — Select duration:
            - Use select_option tool with selector='select' and value='{duration_mins} minutes'
            - Wait 1 second

            STEP 4 — Add Booking:
            - Click the 'Add Booking' button
            - Wait 3 seconds, take a screenshot

            STEP 5 — Read booking summary:
            - A "View Bookings" modal appears showing Date, Court, Time, Duration
            - Use get_page_text to read all details
            - DO NOT click Checkout yet
            - Say DONE with: Court, Date, Time, Duration

            IMPORTANT: Do not say DONE until you see the View Bookings modal.
            """
            self.max_iterations = 30
            return self.run(task, venue_url)

        # ── ClubSpark (Carlton Gardens) — login required ──
        login_step = f"""
        STEP 1 — Log in:
        - Navigate to: https://auth-play.tennis.com.au/account/signin
        - Wait 3 seconds
        - Click Email address field, type '{login_email}'
        - Click Password field, type '{login_password}'
        - Click Sign in button
        - Wait 5 seconds
        - Navigate to: {venue_url}
        - Wait 5 seconds, take a screenshot
        """ if login_email else ""

        task = f"""
        {login_step}

        STEP 2 — Navigate to correct date:
        - Take a screenshot to confirm booking page loaded
        - Click the '>' Next Day button until date shows {slot.get('date')}
        - Wait 2 seconds after each click, take screenshot, check date
        - Do NOT proceed until correct date confirmed on screen

        STEP 3 — Find and click available slot:
        - Use get_page_text to read all text on the page
        - Available slots show a price like "$12.50" or "$15.00"
        - Click the element showing a price closest to {slot.get('time')}
        - Wait 3 seconds, take a screenshot

        STEP 4 — On "Confirm your booking and pay" page:
        - Verify page title says "Confirm your booking and pay"
        - Use get_page_text to read ALL details
        - DO NOT click "Confirm and pay"
        - Say DONE with: Venue, Court, Date, Time, Total Cost

        CRITICAL: Summary must match what is ACTUALLY on screen.
        Do not say DONE until you reach the Confirm page.
        """
        self.max_iterations = 30
        return self.run(task, venue_url)

    def discover_venues(self, sport: str, suburb: str) -> dict:
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


def _get_browser_tool_definitions():
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
                "properties": {"description": {"type": "string", "description": "e.g. 'the Sports category tab'"}},
                "required": ["description"]
            }
        },
        {
            "name": "click_available_slot",
            "description": "Click the first available booking slot on ThinkSmart venue grid using CSS selector td.Selectable. Use this for Fawkner Park and Powlett Reserve bookings.",
            "input_schema": {
                "type": "object",
                "properties": {},
                "required": []
            }
        },
        {
            "name": "select_option",
            "description": "Select an option from a dropdown by its label text. Use this instead of click for <select> dropdowns.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "selector": {
                        "type": "string",
                        "description": "CSS selector for the select element e.g. 'select'"
                    },
                    "value": {
                        "type": "string", 
                        "description": "The option label to select e.g. '60 minutes'"
                    }
                },
                "required": ["selector", "value"]
            }
        },
        {
            "name": "fill_field_by_js",
            "description": "Fill an input field using JavaScript by finding it via its label text. Use when normal click+type fails inside modals.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "label": {"type": "string", "description": "Label text above the field e.g. 'First name', 'Email address'"},
                    "value": {"type": "string", "description": "Value to fill in"}
                },
                "required": ["label", "value"]
            }
        },
        {
            "name": "click_by_js",
            "description": "Force click a button by its text using JavaScript. Use when normal click fails with 'element not visible'. Works even if element is behind overlays.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "Button text to click e.g. 'I am not a Member'"}
                },
                "required": ["text"]
            }
        },
        {
            "name": "set_date_by_js",
            "description": "Set the date on ThinkSmart booking calendar directly using JavaScript. Use this instead of clicking the calendar. Date must be in DD/MM/YYYY format e.g. '19/06/2026'.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "date": {
                        "type": "string",
                        "description": "Date in DD/MM/YYYY format e.g. '19/06/2026'"
                    }
                },
                "required": ["date"]
            }
        },
        {
            "name": "type_text",
            "description": "Type text into the currently focused element",
            "input_schema": {
                "type": "object",
                "properties": {"text": {"type": "string"}},
                "required": ["text"]
            }
        },
        {
            "name": "keyboard_press",
            "description": "Press a key e.g. Enter, Tab, Escape, ArrowRight, ArrowLeft",
            "input_schema": {
                "type": "object",
                "properties": {"key": {"type": "string"}},
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
            "input_schema": {"type": "object", "properties": {}, "required": []}
        },
        {
            "name": "get_current_url",
            "description": "Get the current page URL",
            "input_schema": {"type": "object", "properties": {}, "required": []}
        },
        {
            "name": "wait",
            "description": "Wait for seconds for the page to load",
            "input_schema": {
                "type": "object",
                "properties": {"seconds": {"type": "number", "default": 2}},
                "required": []
            }
        }
    ]


def _execute_browser_tool(browser, tool_name: str, tool_input: dict) -> str:
    if tool_name == "take_screenshot":
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

    elif tool_name == "click_available_slot":
        # ── ThinkSmart: click first td.Selectable cell directly ──
        try:
            browser.page.wait_for_selector("td.Selectable", timeout=8000)
            first_slot = browser.page.locator("td.Selectable").first
            first_slot.click()
            browser.page.wait_for_timeout(1000)
            print("\n[browser] CLICKED first td.Selectable slot\n")
            return "Clicked first available slot (td.Selectable)"
        except Exception as e:
            return f"Could not click available slot: {str(e)[:200]}"
        
    elif tool_name == "select_option":
        try:
            value = tool_input.get("value", "")
            # Pure JS — no locator, works inside any modal
            browser.page.evaluate(f"""
                (() => {{
                    const selects = document.querySelectorAll('select');
                    for (const sel of selects) {{
                        const options = Array.from(sel.options);
                        const opt = options.find(o => o.text.trim() === '{value}');
                        if (opt) {{
                            sel.value = opt.value;
                            sel.dispatchEvent(new Event('change', {{ bubbles: true }}));
                            sel.dispatchEvent(new Event('input', {{ bubbles: true }}));
                            break;
                        }}
                    }}
                }})();
            """)
            browser.page.wait_for_timeout(800)
            print(f"\n[browser] SELECTED option '{value}' via JavaScript\n")
            return f"Selected option: {value}"
        except Exception as e:
            return f"Could not select option: {str(e)[:200]}"
        
    elif tool_name == "click_by_js":
        # Force click using JavaScript — bypasses visibility checks
        try:
            text = tool_input.get("text", "")
            browser.page.evaluate(f"""
                (() => {{
                    const buttons = Array.from(document.querySelectorAll('button, a, input[type="button"]'));
                    const btn = buttons.find(b => b.textContent.trim().includes('{text}'));
                    if (btn) btn.click();
                }})();
            """)
            browser.page.wait_for_timeout(1000)
            print(f"\n[browser] JS CLICKED button with text '{text}'\n")
            return f"JS clicked: {text}"
        except Exception as e:
            return f"Could not JS click: {str(e)[:200]}"
        
    elif tool_name == "fill_field_by_js":
        try:
            label = tool_input.get("label", "")
            value = tool_input.get("value", "")
            index = tool_input.get("index", -1)

            # Find the input element via JS to get its selector
            selector = browser.page.evaluate(f"""
                (() => {{
                    let input = null;

                    if ({index} >= 0) {{
                        const inputs = document.querySelectorAll('input');
                        input = inputs[{index}];
                    }}

                    if (!input) {{
                        const labels = Array.from(document.querySelectorAll('label'));
                        const lbl = labels.find(l => l.textContent.trim().toLowerCase().includes('{label.lower()}'));
                        if (lbl) {{
                            input = document.getElementById(lbl.htmlFor) || lbl.nextElementSibling;
                        }}
                    }}

                    if (!input) {{
                        input = Array.from(document.querySelectorAll('input')).find(i =>
                            (i.placeholder && i.placeholder.toLowerCase().includes('{label.lower()}')) ||
                            (i.name && i.name.toLowerCase().includes('{label.lower()}'))
                        );
                    }}

                    if (input) {{
                        // Use native setter to trigger React/Vue onChange
                        const nativeInputValueSetter = Object.getOwnPropertyDescriptor(
                            window.HTMLInputElement.prototype, 'value').set;
                        nativeInputValueSetter.call(input, '{value}');
                        input.dispatchEvent(new Event('input', {{ bubbles: true }}));
                        input.dispatchEvent(new Event('change', {{ bubbles: true }}));
                        input.dispatchEvent(new Event('blur', {{ bubbles: true }}));
                        return true;
                    }}
                    return false;
                }})();
            """)
            browser.page.wait_for_timeout(300)
            print(f"\n[browser] FILLED field '{label}' with '{value}'\n")
            return f"Filled {label}: {value}"
        except Exception as e:
            return f"Could not fill field: {str(e)[:200]}"
        
    elif tool_name == "set_date_by_js":
        try:
            date_val = tool_input.get("date", "")
            browser.page.evaluate(f"""
                (() => {{
                    const input = document.querySelector('input[type="text"]');
                    if (input) {{
                        input.value = '{date_val}';
                        input.dispatchEvent(new Event('change', {{ bubbles: true }}));
                        input.dispatchEvent(new Event('blur', {{ bubbles: true }}));
                    }}
                }})();
            """)
            browser.page.wait_for_timeout(1000)
            return f"Date set to: {date_val}"
        except Exception as e:
            return f"Could not set date: {str(e)}"
    elif tool_name == "type_text":
        return browser.keyboard_type(tool_input["text"])

    elif tool_name == "keyboard_press":
        # Fix common key name mistakes
        key_map = {
            "RightArrow": "ArrowRight",
            "LeftArrow": "ArrowLeft",
            "UpArrow": "ArrowUp",
            "DownArrow": "ArrowDown",
        }
        key = key_map.get(tool_input["key"], tool_input["key"])
        return browser.keyboard_press(key)

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


pitchup_agent = PitchupAgent()


if __name__ == "__main__":
    agent = PitchupAgent(headless=False, max_iterations=15)
    result = agent.fetch_availability(
        venue_url="https://parramatta.bookable.net.au/",
        sport="tennis",
        date="Saturday 2026-05-24"
    )
    print(json.dumps(result, indent=2))