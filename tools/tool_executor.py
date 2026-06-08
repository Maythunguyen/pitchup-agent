
# Executes browser tool calls dispatched by the agent loop
# Each tool maps to a BrowserAutomation method or JS helper


import json


def execute_browser_tool(browser, tool_name: str, tool_input: dict) -> str:
    """Route a tool call to the correct browser action."""

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
        return _click_available_slot(browser)

    elif tool_name == "click_by_js":
        return _click_by_js(browser, tool_input.get("text", ""))

    elif tool_name == "select_option":
        return _select_option(browser, tool_input.get("value", ""))

    elif tool_name == "set_date_by_js":
        return _set_date_by_js(browser, tool_input.get("date", ""))

    elif tool_name == "fill_field_by_js":
        return _fill_field_by_js(
            browser,
            tool_input.get("label", ""),
            tool_input.get("value", ""),
            tool_input.get("index", -1)
        )

    elif tool_name == "type_text":
        return browser.keyboard_type(tool_input["text"])

    elif tool_name == "keyboard_press":
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


# ─────────────────────────────────────────────
# PRIVATE HELPERS
# ─────────────────────────────────────────────

def _click_available_slot(browser) -> str:
    """Click first td.Selectable cell — ThinkSmart booking grid."""
    try:
        browser.page.wait_for_selector("td.Selectable", timeout=8000)
        browser.page.locator("td.Selectable").first.click()
        browser.page.wait_for_timeout(1000)
        print("\n[browser] CLICKED first td.Selectable slot\n")
        return "Clicked first available slot (td.Selectable)"
    except Exception as e:
        return f"Could not click available slot: {str(e)[:200]}"


def _click_by_js(browser, text: str) -> str:
    """Force click by button text — bypasses visibility checks."""
    try:
        browser.page.evaluate(f"""
            (() => {{
                const buttons = Array.from(document.querySelectorAll('button, a, input[type="button"]'));
                const btn = buttons.find(b => b.textContent.trim().includes('{text}'));
                if (btn) btn.click();
            }})();
        """)
        browser.page.wait_for_timeout(1000)
        print(f"\n[browser] JS CLICKED '{text}'\n")
        return f"JS clicked: {text}"
    except Exception as e:
        return f"Could not JS click: {str(e)[:200]}"


def _select_option(browser, value: str) -> str:
    """Select dropdown option via JavaScript — works inside modals."""
    try:
        browser.page.evaluate(f"""
            (() => {{
                const selects = document.querySelectorAll('select');
                for (const sel of selects) {{
                    const opt = Array.from(sel.options).find(o => o.text.trim() === '{value}');
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
        print(f"\n[browser] SELECTED '{value}' via JavaScript\n")
        return f"Selected option: {value}"
    except Exception as e:
        return f"Could not select option: {str(e)[:200]}"


def _set_date_by_js(browser, date_val: str) -> str:
    """Set ThinkSmart date input directly via JavaScript."""
    try:
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
        browser.page.wait_for_timeout(2000)
        print(f"\n[browser] SET DATE to '{date_val}'\n")
        return f"Date set to: {date_val}"
    except Exception as e:
        return f"Could not set date: {str(e)[:200]}"


def _fill_field_by_js(browser, label: str, value: str, index: int = -1) -> str:
    """Fill form field via JavaScript — works inside modals."""
    try:
        browser.page.evaluate(f"""
            (() => {{
                let input = null;

                if ({index} >= 0) {{
                    input = document.querySelectorAll('input')[{index}];
                }}

                if (!input) {{
                    const lbl = Array.from(document.querySelectorAll('label'))
                        .find(l => l.textContent.trim().toLowerCase().includes('{label.lower()}'));
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
                    const setter = Object.getOwnPropertyDescriptor(
                        window.HTMLInputElement.prototype, 'value').set;
                    setter.call(input, '{value}');
                    input.dispatchEvent(new Event('input', {{ bubbles: true }}));
                    input.dispatchEvent(new Event('change', {{ bubbles: true }}));
                    input.dispatchEvent(new Event('blur', {{ bubbles: true }}));
                }}
            }})();
        """)
        browser.page.wait_for_timeout(300)
        print(f"\n[browser] FILLED '{label}' with '{value}'\n")
        return f"Filled {label}: {value}"
    except Exception as e:
        return f"Could not fill field: {str(e)[:200]}"