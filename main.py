
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from models import (
    AvailabilityRequest, AvailabilityResponse,
    BookingRequest, BookingResponse,
    HealthResponse, StepLog,
    PreviewRequest, ConfirmRequest
)
import uvicorn

load_dotenv()

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

#Health check endpoint
@app.get("/health", response_model=HealthResponse)
def health():
    return {"status": "ok"}


#fetch availability endpoint
@app.post("/fetch-availability", response_model=AvailabilityResponse)
def fetch_availability(req: AvailabilityRequest):
    """
    Agent navigates a venue URL and extracts available time slots + pricing.
    Returns raw text + structured slot list + optional screenshot.
    """
    from agent import create_agent
    from utils import parse_agent_slots, extract_screenshot_from_steps

    agent = create_agent(headless=True)
    result = agent.run(task=req.task, url=req.url)

    # Parse raw text into structured slots
    slots = parse_agent_slots(result.get("data", ""))

    # Extract screenshot from steps if available
    screenshot = extract_screenshot_from_steps(result.get("steps", []))

    return AvailabilityResponse(
        status=result["status"],
        data=result.get("data"),
        slots=slots,
        screenshot=screenshot,
        steps=result.get("steps")
    )

@app.post("/preview-booking")
def preview_booking(req: PreviewRequest):
    """
    Phase 1 — Agent fills the form but stops before payment.
    Returns booking details for user to review.
    """
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
        "summary": result["data"],   # booking details for user to review
        "steps": result["steps"]
    }


@app.post("/confirm-booking")
def confirm_booking(req: ConfirmRequest):
    """
    Phase 2 — User confirmed, agent clicks pay and completes.
    """
    from pitchup_agent import PitchupAgent
    agent = PitchupAgent(headless=True)

    task = f"""
    Log in with email 'nguyentranminhthu.65@gmail.com' and password 'PitchUpDemo123'.
    Navigate to the pending booking.
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

#complete booking endpoint
@app.post("/complete-booking", response_model=BookingResponse)
def complete_booking(req: BookingRequest):
    """
    Agent logs in (if credentials provided), navigates to the booking form,
    fills in user details and submits. Returns confirmation number.
    """
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


if __name__ == "__main__":
    
    uvicorn.run(app, host="0.0.0.0", port=8001)