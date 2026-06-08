from pydantic import BaseModel
from typing import Optional

# Request models
class AvailabilityRequest(BaseModel):
    """Request to fetch live availability from a venue site."""
    url: str
    task: str

    class Config:
        json_schema_extra = {
            "example": {
                "url": "https://www.tennisvenues.com.au/booking/sydney-boys-high-school",
                "task": "Find available slots for Saturday 2026-06-07, extract time and price."
            }
        }


class SlotInfo(BaseModel):
    """Selected time slot details."""
    sport: str
    date: str       # e.g. "2026-06-07"
    time: str       # e.g. "10:00am"
    duration: Optional[int] = 60  # minutes


class UserInfo(BaseModel):
    """User details for booking form."""
    name: str
    email: str
    phone: str


class BookingRequest(BaseModel):
    """Request to complete a booking on a venue site."""
    url: str
    slot: SlotInfo
    user: UserInfo
    login_email: Optional[str] = None
    login_password: Optional[str] = None

    class Config:
        json_schema_extra = {
            "example": {
                "url": "https://clubspark.lta.org.uk/CarltonGardensTennisClub",
                "slot": {
                    "sport": "Tennis",
                    "date": "2026-06-07",
                    "time": "10:00am",
                    "duration": 60
                },
                "user": {
                    "name": "May Nguyen",
                    "email": "may@pitchup.com.au",
                    "phone": "0400000000"
                },
                "login_email": "demo@pitchup.com.au",
                "login_password": "PitchUpDemo123"
            }
        }


#Response models
class StepLog(BaseModel):
    """Single agent step log entry."""
    step: int
    tool: str
    input: dict
    output: str


class AvailabilityResponse(BaseModel):
    """Response from /fetch-availability."""
    status: str                         # "success" | "failed"
    data: Optional[str] = None          # raw agent text output
    slots: Optional[list] = None        # structured slot list
    screenshot: Optional[str] = None    # base64 image
    steps: Optional[list] = None        # agent step logs


class PreviewRequest(BaseModel):
    url: str
    slot: dict
    user: dict
    login_email: str = "demo@pitchup.com.au"
    login_password: str = "PitchUpDemo123"

class ConfirmRequest(BaseModel):
    url: str
    session_id: str  # to resume where agent left off


class BookingResponse(BaseModel):
    """Response from /complete-booking."""
    status: str                         # "success" | "failed"
    confirmation: Optional[str] = None  # confirmation number / text
    steps: Optional[list] = None        # agent step logs


class HealthResponse(BaseModel):
    """Response from /health."""
    status: str