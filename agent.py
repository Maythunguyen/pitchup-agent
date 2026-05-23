import os
from dotenv import load_dotenv
from pitchup_agent import PitchupAgent
 
load_dotenv()
 
 
def create_agent(headless: bool = True, max_iterations: int = 20) -> PitchupAgent:
    """
    Create a fresh PitchupAgent instance.
    Called per request to ensure proper isolation.
    """
    return PitchupAgent(
        max_iterations=max_iterations,
        headless=headless
    )
 
 
if __name__ == "__main__":
    agent = create_agent(headless=False)
 
    result = agent.fetch_availability(
        venue_url="https://www.pitchup.com.au",
        sport="tennis",
        date="Saturday 2026-05-24"
    )
    print(result)
 