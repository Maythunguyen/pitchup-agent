# PitchUp Browser Agent

An AI browser agent that fetches live venue availability and completes court bookings on behalf of PitchUp users. Built with Playwright + GPT-4o.

## What It Does

- Navigates venue booking sites autonomously
- Fetches real-time availability from ThinkSmart and ClubSpark systems
- Completes bookings including date selection, slot picking, duration and user details
- Returns booking summaries before payment — user confirms in PitchUp UI

## Supported Venues

| Venue | System | Login Required |
|-------|--------|---------------|
| Fawkner Park Tennis Centre | ThinkSmart | No |
| Carlton Gardens Tennis Club | ClubSpark | Yes |

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt
playwright install chromium

# Set environment variables
cp .env.example .env
# Add your OPENAI_API_KEY to .env

# Start the API server
uvicorn main:app --reload --port 8001
```

## API Endpoints

```
GET  /health               → Check agent is running
POST /fetch-availability   → Get live slots from venue
POST /complete-booking     → Agent navigates and books
POST /preview-booking      → Agent fills form, stops before payment
```

### Example Request

```bash
curl -X POST http://localhost:8001/fetch-availability \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://www.thinksmartsoftware-au.com/OB/timetable.php?c=5D34328022065&v=1&t=tennisbiz",
    "task": "Wait 3 seconds, find available slots, return as TIME — COURT — AVAILABLE or BOOKED"
  }'
```

## CLI Testing

```bash
# Test availability fetch
python cli.py run "Wait 8 seconds, use get_page_text to read all slots, say DONE" \
  --url "https://www.thinksmartsoftware-au.com/OB/timetable.php?c=5D34328022065&v=1&t=tennisbiz"

# Test full booking flow
python cli.py run "Wait 8 seconds, use click_available_slot tool, wait 2 seconds. Use select_option with value='60 minutes'. Click Add Booking. Wait 3 seconds. Use get_page_text. Say DONE." \
  --url "https://www.thinksmartsoftware-au.com/OB/timetable.php?c=5D34328022065&v=1&t=tennisbiz"
```

## Project Structure

```
browser-agent/
├── main.py              # FastAPI server — /health, /fetch-availability, /complete-booking
├── pitchup_agent.py     # PitchupAgent class — main agent loop + all tools
├── agent.py             # Creates shared agent instance
├── models.py            # Pydantic request/response models
├── utils.py             # parse_agent_slots(), extract_screenshot_from_steps()
├── cli.py               # CLI for local testing
├── tools/
│   ├── browser_tools/
│   │   ├── browser.py        # BrowserAutomation (Playwright wrapper)
│   │   └── element_finder.py # AI-powered element finder
│   └── pitchup_tools.py      # Venue-specific tools (get_availability_slots etc.)
├── prompts/
│   └── pitchup_agent.md      # System prompt
└── requirements.txt
```

## Custom Browser Tools

The agent has these tools beyond standard browser control:

| Tool | Description |
|------|-------------|
| `click_available_slot` | Clicks first `td.Selectable` cell on ThinkSmart grid |
| `select_option` | Selects dropdown value via JavaScript |
| `set_date_by_js` | Sets date input directly via JavaScript |
| `click_by_js` | Force-clicks element by text, bypasses visibility |
| `fill_field_by_js` | Fills form fields inside modals via JavaScript |

## Environment Variables

```
OPENAI_API_KEY=your_key_here
```

## Deploy to Railway

1. Push to GitHub
2. Connect repo on railway.app
3. Add `OPENAI_API_KEY` environment variable
4. Railway auto-deploys via `railway.toml`

Live URL format: `https://pitchup-agent-xxx.railway.app`

## How It Works

1. PitchUp frontend calls `/fetch-availability` with venue URL
2. Agent opens headless browser, navigates to venue site
3. Agent reads live slot data and returns structured results
4. User selects slot in PitchUp UI and confirms booking
5. PitchUp frontend calls `/complete-booking`
6. Agent navigates booking flow, fills details, stops before payment
7. Agent returns booking summary — PitchUp confirms and charges user