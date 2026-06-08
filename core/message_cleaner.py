
# Removes old screenshots from message history to save tokens
def clean_messages(messages: list) -> list:
    """
    Remove old screenshot tool results from message history.
    Only keeps the latest screenshot — old ones waste tokens.
    """
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