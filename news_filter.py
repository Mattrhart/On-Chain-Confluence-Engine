import datetime
from typing import List
import httpx
from pydantic import BaseModel

# 1. Define the data structure for incoming calendar events
class EconomicEvent(BaseModel):
    event: str
    currency: str
    date: str      # Format from API: "2026-05-28 14:30:00"
    impact: str    # "High", "Medium", "Low"

class ForexNewsFilter:
    def __init__(self, api_key: str):
        # Using Financial Modeling Prep or similar free economic calendar endpoint
        self.api_url = "https://financialmodelingprep.com/api/v3/economic_calendar"
        self.api_key = api_key

    async def get_high_impact_events(self) -> List[EconomicEvent]:
        """Fetches today's economic calendar events asynchronously."""
        today = datetime.date.today().isoformat()
        params = {
            "from": today,
            "to": today,
            "apikey": self.api_key
        }
        
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(self.api_url, params=params, timeout=5.0)
                if response.status_code == 200:
                    data = response.json()
                    # Filter down immediately to only High-impact spikes
                    return [
                        EconomicEvent(**item) for item in data 
                        if item.get("impact") == "High"
                    ]
            except Exception as e:
                # Operational Governance: If news API fails, default to safety or log telemetry
                print(f"Telemetry Alert: News API handshake failed: {e}")
                return []
        return []

    def is_market_unsafe(self, pair: str, events: List[EconomicEvent]) -> bool:
        """
        Evaluates if the current timestamp falls inside a high-impact news window.
        Returns True if market is UNSAFE (signal should be blocked).
        """
        # Deconstruct pair (e.g., "EUR_USD" -> ["EUR", "USD"])
        currencies_to_check = pair.upper().split("_")
        
        now = datetime.datetime.utcnow()
        
        for event in events:
            if event.currency in currencies_to_check:
                # Parse event string to datetime object
                # Adjust format based on your exact API provider's schema
                event_time = datetime.datetime.strptime(event.date, "%Y-%m-%d %H:%M:%S")
                
                # Define defensive boundaries: 30 mins before, 15 mins after
                buffer_before = event_time - datetime.timedelta(minutes=30)
                buffer_after = event_time + datetime.timedelta(minutes=15)
                
                if buffer_before <= now <= buffer_after:
                    print(f"Skeptic Filter Triggered: Blocked {pair} due to High-Impact Event: {event.event}")
                    return True
                    
        return False