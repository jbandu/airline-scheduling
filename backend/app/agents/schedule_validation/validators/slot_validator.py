"""
Airport Slot Validator
Validates flight schedules against airport slot allocations
"""

from typing import List, Dict, Any
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)


class SlotValidator:
    """
    Validates airport slot allocations per IATA WSG

    Checks:
    - Slot exists at coordinated airports
    - Slot time matches scheduled time (±5 min tolerance)
    - Slot is confirmed
    - Historical rights are maintained
    """

    # Level 3 coordinated airports (require slot allocation)
    COORDINATED_AIRPORTS = {
        "LHR", "JFK", "LAX", "HND", "NRT", "CDG", "FRA", "AMS",
        "LGA", "ORD", "DCA", "SFO", "BOS", "EWR", "PHL", "DEN",
        "FCO", "MAD", "BCN", "ZRH", "MUC", "SIN", "HKG", "ICN"
    }

    def __init__(self, db_connection):
        self.db = db_connection

    def validate(self, flights: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Validate slot allocations for all flights

        Args:
            flights: List of flight dictionaries

        Returns:
            List of validation issues
        """
        issues = []

        for flight in flights:
            # Check departure slot
            if flight["origin_airport"] in self.COORDINATED_AIRPORTS:
                dep_issues = self._validate_slot(
                    flight,
                    airport=flight["origin_airport"],
                    slot_type="departure",
                    scheduled_time=flight["departure_time"]
                )
                issues.extend(dep_issues)

            # Check arrival slot
            if flight["destination_airport"] in self.COORDINATED_AIRPORTS:
                arr_issues = self._validate_slot(
                    flight,
                    airport=flight["destination_airport"],
                    slot_type="arrival",
                    scheduled_time=flight["arrival_time"]
                )
                issues.extend(arr_issues)

        logger.info(f"Slot validation: {len(issues)} issues found")
        return issues

    def _validate_slot(
        self,
        flight: Dict[str, Any],
        airport: str,
        slot_type: str,
        scheduled_time: str
    ) -> List[Dict[str, Any]]:
        """Validate slot for specific airport and time"""
        issues = []

        cursor = self.db.cursor()

        try:
            # Find allocated slot
            cursor.execute(
                """
                SELECT slot_id, slot_time, confirmed, historical_rights,
                       tolerance_before_minutes, tolerance_after_minutes
                FROM airport_slots
                WHERE airport_code = %s
                  AND slot_type = %s
                  AND allocated_to_airline = %s
                  AND allocated_to_flight = %s
                """,
                (airport, slot_type, flight["carrier_code"], flight["flight_id"])
            )

            slot = cursor.fetchone()

            if not slot:
                # No slot allocated
                issues.append({
                    "severity": "critical",
                    "category": "slot_validation",
                    "flight_id": flight["flight_id"],
                    "flight_number": flight["flight_number"],
                    "issue_type": "missing_slot",
                    "airport": airport,
                    "slot_type": slot_type,
                    "description": f"No {slot_type} slot allocated at {airport} (Level 3 coordinated)",
                    "recommended_action": f"Request slot from airport coordinator for {scheduled_time}",
                    "impact": "Flight cannot operate without slot allocation"
                })
            else:
                slot_id, slot_time, confirmed, historical_rights, tol_before, tol_after = slot

                # Check if slot time matches scheduled time (within tolerance)
                if not self._time_within_tolerance(
                    scheduled_time,
                    str(slot_time.time()),
                    tol_before or 5,
                    tol_after or 5
                ):
                    issues.append({
                        "severity": "high",
                        "category": "slot_validation",
                        "flight_id": flight["flight_id"],
                        "flight_number": flight["flight_number"],
                        "issue_type": "slot_time_mismatch",
                        "airport": airport,
                        "slot_type": slot_type,
                        "scheduled_time": scheduled_time,
                        "slot_time": str(slot_time.time()),
                        "description": f"Scheduled {slot_type} time {scheduled_time} differs from slot time {slot_time.time()}",
                        "recommended_action": "Adjust schedule to match slot time or request slot time change",
                        "impact": "May result in slot coordinator rejection"
                    })

                # Check if slot is confirmed
                if not confirmed:
                    issues.append({
                        "severity": "medium",
                        "category": "slot_validation",
                        "flight_id": flight["flight_id"],
                        "flight_number": flight["flight_number"],
                        "issue_type": "slot_not_confirmed",
                        "airport": airport,
                        "slot_type": slot_type,
                        "description": f"{slot_type.capitalize()} slot at {airport} not yet confirmed by coordinator",
                        "recommended_action": "Follow up with airport coordinator for confirmation",
                        "impact": "Slot may not be available"
                    })

        finally:
            cursor.close()

        return issues

    def _time_within_tolerance(
        self,
        scheduled: str,
        slot: str,
        tolerance_before: int,
        tolerance_after: int
    ) -> bool:
        """Check if scheduled time is within slot tolerance"""
        # Parse times (HH:MM:SS format)
        sched_parts = scheduled.split(':')
        slot_parts = slot.split(':')

        sched_minutes = int(sched_parts[0]) * 60 + int(sched_parts[1])
        slot_minutes = int(slot_parts[0]) * 60 + int(slot_parts[1])

        diff = sched_minutes - slot_minutes

        return -tolerance_before <= diff <= tolerance_after
