
import json


def parse_agent_slots(agent_text: str) -> list:
    """
    Parse raw agent text into structured slot list.
    Handles both "1 pm" and "13" hour formats.

    Returns list of:
      { hour: int, time: str, available: bool }
    """
    if not agent_text:
        return []

    slots = []
    lines = agent_text.split("\n")

    for line in lines:
        upper = line.upper()
        is_available = "AVAILABLE" in upper
        is_booked = "BOOKED" in upper
        if not is_available and not is_booked:
            continue

        parts = line.replace("- ", "").split("—")
        if not parts:
            continue

        time_str = parts[0].strip()
        hour = _parse_hour(time_str)
        if hour is None:
            continue

        # Avoid duplicates
        if not any(s["hour"] == hour for s in slots):
            slots.append({
                "hour": hour,
                "time": time_str,
                "available": is_available
            })

    return slots


def _parse_hour(time_str: str):
    """Convert time string to 24h integer. Returns None if unparseable."""
    if not time_str:
        return None
    s = time_str.lower().strip()
    is_pm = "pm" in s
    is_am = "am" in s
    try:
        num = int(s.split(":")[0].replace("am", "").replace("pm", "").strip())
    except ValueError:
        return None
    if is_pm and num != 12:
        return num + 12
    if is_am and num == 12:
        return 0
    return num


def extract_screenshot_from_steps(steps: list) -> str | None:
    """
    Find the most recent screenshot from agent step logs.
    Returns base64 string or None.
    """
    for step in reversed(steps):
        if step.get("tool") == "take_screenshot":
            output = step.get("output", "")
            try:
                parsed = json.loads(output)
                return parsed.get("data")
            except Exception:
                pass
    return None