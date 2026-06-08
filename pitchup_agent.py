
# PitchupAgent — the central brain of the PitchUp browser agent system
# Thin orchestration layer: imports tools, core utils, and runs the agent loop

import json
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

from openai import OpenAI
from core import llm_do, compress_screenshot, clean_messages
from tools import get_browser_tool_definitions, to_openai_tools, execute_browser_tool

_openai = OpenAI()


_PROMPT_PATH = Path(__file__).parent / "prompts" / "pitchup_agent.md"
SYSTEM_PROMPT = _PROMPT_PATH.read_text() if _PROMPT_PATH.exists() else """
You are PitchupAgent — an AI browser agent built for PitchUp.com.au.
You help fetch venue availability and complete bookings.
The browser is already open and on the starting URL.
ALWAYS start by taking a screenshot. Never use full_page=true.
Say DONE when finished, FAILED if unsuccessful.
"""

class PitchupAgent:
    """
    Orchestrates the browser agent loop.
    OpenAI drives decisions. Playwright executes actions.
    """

    def __init__(self, max_iterations: int = 20, headless: bool = True):
        self.max_iterations = max_iterations
        self.headless = headless
        self._openai = _openai

    def run(self, task: str, url: str) -> dict:
        """Main agent loop — Think → Act → Observe → Repeat."""
        from tools.pitchup_tools import PITCHUP_TOOLS, execute_pitchup_tool
        from tools.browser_tools.browser import BrowserAutomation

        BROWSER_TOOLS = get_browser_tool_definitions()
        ALL_TOOLS = to_openai_tools(BROWSER_TOOLS + PITCHUP_TOOLS)

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

                clean_msgs = clean_messages(messages)
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

                        # Route to correct executor
                        if tool_name in ["get_availability_slots", "extract_booking_confirmation", "get_page_structured_data"]:
                            tool_output = execute_pitchup_tool(browser, tool_name, tool_input)
                        else:
                            tool_output = execute_browser_tool(browser, tool_name, tool_input)

                        print(f"   → {str(tool_output)[:80]}")

                        # Screenshots get added as images; everything else as text
                        if tool_name == "take_screenshot":
                            try:
                                parsed = json.loads(tool_output)
                                compressed = compress_screenshot(parsed["data"])
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

    def complete_booking(self, venue_url: str, slot: dict, user: dict,
                         login_email: str = None, login_password: str = None) -> dict:
        """Navigate venue site and complete a booking up to the payment page."""

        duration_mins = slot.get("duration", 60)

        # ── ThinkSmart (Fawkner Park) ──
        if "thinksmartsoftware" in venue_url:
            return self._complete_thinksmart(venue_url, slot, user, duration_mins)

        # ── ClubSpark (Carlton Gardens) ──
        return self._complete_clubspark(venue_url, slot, user, login_email, login_password)

    def _complete_thinksmart(self, venue_url: str, slot: dict, user: dict, duration_mins: int) -> dict:
        """ThinkSmart booking flow — no login required."""
        raw_date = slot.get("date", "")
        try:
            parts = raw_date.split("-")
            display_date = f"{parts[2]}/{parts[1]}/{parts[0]}"
        except Exception:
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

        STEP 5 — Read View Bookings modal:
        - Use get_page_text to read all details
        - DO NOT click Checkout yet
        - Say DONE with: Court, Date, Time, Duration

        IMPORTANT: Do not say DONE until you see the View Bookings modal.
        """
        self.max_iterations = 30
        return self.run(task, venue_url)

    def _complete_clubspark(self, venue_url: str, slot: dict, user: dict,
                             login_email: str, login_password: str) -> dict:
        """ClubSpark booking flow — login required."""
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
        - Click '>' Next Day button until date shows {slot.get('date')}
        - Wait 2 seconds after each click, check date
        - Do NOT proceed until correct date confirmed

        STEP 3 — Find and click available slot:
        - Use get_page_text to read all text
        - Available slots show "$12.50" or "$15.00"
        - Click the price element closest to {slot.get('time')}
        - Wait 3 seconds, take a screenshot

        STEP 4 — On "Confirm your booking and pay" page:
        - Use get_page_text to read ALL details
        - DO NOT click "Confirm and pay"
        - Say DONE with: Venue, Court, Date, Time, Total Cost

        CRITICAL: Summary must match what is ACTUALLY on screen.
        """
        self.max_iterations = 30
        return self.run(task, venue_url)


pitchup_agent = PitchupAgent()