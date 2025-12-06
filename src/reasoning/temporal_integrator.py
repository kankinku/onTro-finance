from datetime import date, datetime
from typing import Optional

class TemporalIntegrator:
    """
    [Reasoning - Temporal Layer]
    Resolves fuzzy time descriptions (e.g., "Year-end") to concrete timeframes.
    Calculates if a condition is currently active.
    """
    
    def __init__(self, current_date: Optional[date] = None):
        self.current_date = current_date if current_date else date.today()

    def is_condition_met(self, time_desc: str) -> float:
        """
        Returns a probability (0.0 - 1.0) that the time condition is met.
        """
        if not time_desc:
            return 1.0 # No condition = always active
            
        desc_lower = time_desc.lower()
        month = self.current_date.month
        day = self.current_date.day
        
        # Rule: "Year-end" or "연말" -> Dec 1 to Dec 31
        if "year-end" in desc_lower or "연말" in desc_lower:
            if month == 12:
                # Higher weight closer to 31st
                return 0.8 + (day / 31.0) * 0.2
            return 0.1
            
        # Rule: "Quarter-end" -> Mar, Jun, Sep, Dec
        if "quarter-end" in desc_lower or "분기말" in desc_lower:
            if month in [3, 6, 9, 12]:
                return 0.9
            return 0.1

        return 0.5 # Unknown time condition
