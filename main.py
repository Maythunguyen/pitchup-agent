
import asyncio
from concurrent.futures import ThreadPoolExecutor
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from models import (
    AvailabilityRequest, AvailabilityResponse,
    BookingRequest, BookingResponse,
    HealthResponse,
    PreviewRequest, ConfirmRequest
)
import uvicorn

load_dotenv()

# ── Thread pool — Playwright sync must run in a thread inside asyncio ──
executor = ThreadPoolExecutor(max_workers=2)

app = FastAPI(
    title="PitchUp Browser Agent API",
    description="AI agent that navigates venue booking sites autonomously.",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def root():
    return {
        "name": "PitchUp Browser Agent API",
        "version": "1.0.0",
        "status": "running",
        "docs": "/docs",
        "endpoints": {
            "health": "GET /health",
            "fetch_availability": "POST /fetch-availability",
            "complete_booking": "POST /complete-booking",
            "preview_booking": "POST /preview-booking",
        }
    }

@app.get("/health", response_model=HealthResponse)
def health():
    return {"status": "ok"}


@app.post("/fetch-availability", response_model=AvailabilityResponse)
async def fetch_availability(req: AvailabilityRequest):
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(executor, lambda: _run_fetch(req))
    return result


def _run_fetch(req: AvailabilityRequest):
    from agent import create_agent
    from utils import parse_agent_slots

    agent = create_agent(headless=True)
    result = agent.run(task=req.task, url=req.url)
    slots = parse_agent_slots(result.get("data", ""))

    return AvailabilityResponse(
        status=result["status"],
        data=result.get("data"),
        slots=slots,
        steps=result.get("steps")
    )

@app.post("/complete-booking", response_model=BookingResponse)
async def complete_booking(req: BookingRequest):
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(executor, lambda: _run_complete(req))
    return result


def _run_complete(req: BookingRequest):
    from pitchup_agent import PitchupAgent

    agent = PitchupAgent(headless=True)
    result = agent.complete_booking(
        venue_url=req.url,
        slot=req.slot.model_dump(),
        user=req.user.model_dump(),
        login_email=req.login_email,
        login_password=req.login_password
    )

    return BookingResponse(
        status=result["status"],
        confirmation=result.get("data"),
        steps=result.get("steps")
    )

@app.post("/preview-booking")
async def preview_booking(req: PreviewRequest):
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(executor, lambda: _run_preview(req))
    return result


def _run_preview(req: PreviewRequest):
    from pitchup_agent import PitchupAgent

    agent = PitchupAgent(headless=True)

    task = f"""
    Log in with email '{req.login_email}' and password '{req.login_password}'.
    Wait 3 seconds.
    Navigate to book a court on {req.slot.get('date')} at {req.slot.get('time')}.
    Fill in the booking form:
      Name: {req.user.get('name')}
      Email: {req.user.get('email')}
      Phone: {req.user.get('phone')}
    Take a screenshot of the completed form.
    DO NOT click pay or submit.
    Use get_page_text to read all booking details on screen.
    Return: venue, date, time, price, court number, any reference shown.
    Say DONE.
    """

    result = agent.run(task=task, url=req.url)
    return {
        "status": result["status"],
        "summary": result["data"],
        "steps": result["steps"]
    }


# ─────────────────────────────────────────────
# CONFIRM BOOKING
# Phase 2 — user confirmed, agent clicks pay
# ─────────────────────────────────────────────

@app.post("/confirm-booking")
async def confirm_booking(req: ConfirmRequest):
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(executor, lambda: _run_confirm(req))
    return result


def _run_confirm(req: ConfirmRequest):
    from pitchup_agent import PitchupAgent

    agent = PitchupAgent(headless=True)

    task = f"""
    Navigate to the pending booking page.
    Click the pay or confirm button to complete the booking.
    Wait for confirmation page.
    Use extract_booking_confirmation to get the confirmation number.
    Say DONE with the confirmation reference.
    """

    result = agent.run(task=task, url=req.url)
    return {
        "status": result["status"],
        "confirmation": result["data"],
        "steps": result["steps"]
    }

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8001)