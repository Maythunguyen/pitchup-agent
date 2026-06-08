# tools/pitchup_tools.py
# Pitchup-specific tools — not generic browser controls
# These 3 tools parse structured data from venue websites
# using Claude's vision to extract machine-readable JSON

import json
from core import llm_do  # PitchupAgent is the brain
from core import compress_screenshot as _compress_screenshot

# ─────────────────────────────────────────────
# TOOL DEFINITIONS — added to TOOLS list in pitchup_agent.py
# ─────────────────────────────────────────────

PITCHUP_TOOLS = [
    {
        "name": "get_availability_slots",
        "description": "Parse the current page and extract all available booking slots as structured JSON. Use this after navigating to a venue's availability or booking page.",
        "input_schema": {
            "type": "object",
            "properties": {
                "sport": {
                    "type": "string",
                    "description": "Sport type to filter for e.g. tennis, basketball"
                },
                "date": {
                    "type": "string",
                    "description": "Target date to look for e.g. Saturday 2026-05-24"
                }
            },
            "required": []
        }
    },
    {
        "name": "extract_booking_confirmation",
        "description": "After completing a booking, parse the confirmation page and extract booking details as structured JSON.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "get_page_structured_data",
        "description": "Extract specific fields from the current page as structured JSON. Better than get_page_text() when you need machine-readable data.",
        "input_schema": {
            "type": "object",
            "properties": {
                "fields": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of fields to extract e.g. ['venue name', 'address', 'price', 'phone number']"
                }
            },
            "required": ["fields"]
        }
    }
]


# ─────────────────────────────────────────────
# TOOL EXECUTION
# ─────────────────────────────────────────────

def execute_pitchup_tool(browser, tool_name: str, tool_input: dict) -> str:
    """
    Execute a Pitchup-specific tool.
    Uses Claude vision to parse screenshots into structured JSON.
    """

    if tool_name == "get_availability_slots":
        return _get_availability_slots(browser, tool_input)

    elif tool_name == "extract_booking_confirmation":
        return _extract_booking_confirmation(browser)

    elif tool_name == "get_page_structured_data":
        return _get_page_structured_data(browser, tool_input)

    return f"Unknown pitchup tool: {tool_name}"


# ─────────────────────────────────────────────
# IMPLEMENTATION
# ─────────────────────────────────────────────

def _get_availability_slots(browser, tool_input: dict) -> str:
    """
    Take a screenshot of the current page and ask Claude to extract
    all available booking slots as structured JSON.
    """
    sport = tool_input.get("sport", "")
    date = tool_input.get("date", "")

    # Take screenshot of current page
    screenshot_result = browser.take_screenshot()
    b64_data = _extract_b64(screenshot_result)
    

    filter_text = ""
    if sport:
        filter_text += f" for {sport}"
    if date:
        filter_text += f" on {date}"

    prompt = f"""Look at this venue booking page and extract all available time slots{filter_text}.

Return ONLY a JSON array with no other text, like this:
[
  {{
    "date": "Saturday 2026-05-24",
    "time": "3:00pm",
    "duration": "1 hour",
    "price": "$25",
    "available": true,
    "court": "Court 1"
  }}
]

If no slots are visible or available, return an empty array: []
If this is not a booking/availability page, return: {{"error": "not an availability page"}}"""

    result = llm_do(prompt=prompt, image_b64=b64_data)
    print(f"\n📅 Availability slots extracted:\n{result[:200]}\n")
    return result


def _extract_booking_confirmation(browser) -> str:
    """
    Take a screenshot of the confirmation page and extract
    booking details as structured JSON.
    """
    screenshot_result = browser.take_screenshot()
    b64_data = _extract_b64(screenshot_result)
    

    prompt = """Look at this booking confirmation page and extract all confirmation details.

Return ONLY a JSON object with no other text, like this:
{
  "booking_id": "ABC123",
  "venue": "Leichhardt Oval Tennis Courts",
  "address": "Allen St, Leichhardt NSW 2040",
  "sport": "Tennis",
  "date": "Saturday 2026-05-24",
  "time": "3:00pm",
  "duration": "1 hour",
  "total_price": "$25",
  "status": "confirmed",
  "confirmation_sent_to": "user@email.com"
}

If this is not a confirmation page, return: {"error": "not a confirmation page"}
Fill in null for any fields not visible on the page."""

    result = llm_do(prompt=prompt, image_b64=b64_data)
    print(f"\n✅ Booking confirmation extracted:\n{result[:200]}\n")
    return result


def _get_page_structured_data(browser, tool_input: dict) -> str:
    """
    Take a screenshot and ask Claude to extract specific fields
    as structured JSON.
    """
    fields = tool_input.get("fields", [])

    if not fields:
        return json.dumps({"error": "No fields specified"})

    screenshot_result = browser.take_screenshot()
    b64_data = _extract_b64(screenshot_result)
    b64_data = _compress_screenshot(b64_data)

    fields_list = "\n".join(f"- {f}" for f in fields)

    prompt = f"""Look at this webpage and extract the following fields:
{fields_list}

Return ONLY a JSON object with no other text. Use null for fields not found.
Example format:
{{
  "venue name": "Leichhardt Oval Tennis Courts",
  "address": "Allen St, Leichhardt NSW 2040",
  "price": "$25/hr",
  "phone number": "02 9560 1234"
}}"""

    result = llm_do(prompt=prompt, image_b64=b64_data)
    print(f"\n📋 Structured data extracted:\n{result[:200]}\n")
    return result


# ─────────────────────────────────────────────
# HELPER
# ─────────────────────────────────────────────

def _extract_b64(screenshot_result: str) -> str:
    """Extract base64 data from screenshot result string"""
    if screenshot_result.startswith("data:image/png;base64,"):
        return screenshot_result.split(",", 1)[1].split("\n")[0].strip()
    return screenshot_result