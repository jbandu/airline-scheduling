"""
Airport Hours and Curfew Validator
Validates flights against airport operating hours and noise curfews
"""

from typing import List, Dict, Any
from datetime import datetime, time
import logging

logger = logging.getLogger(__name__)


class CurfewValidator:
    """
    Validates airport operating hours and curfew restrictions

    Checks:
    - Airport operating hours (open/close times)
    - Noise curfew restrictions
    - Night movement limitations
    - Slot-controlled curfew exemptions
    - Seasonal operating hour variations
    - Emergency/special exemptions
    """

    # Airports with known strict curfews (for reference)
    CURFEW_AIRPORTS = {
        "LHR": {"start": "23:00", "end": "06:00", "strict": True},
        "SYD": {"start": "23:00", "end": "06:00", "strict": True},
        "FRA": {"start": "23:00", "end": "05:00", "strict": True},
        "ZRH": {"start": "23:30", "end": "06:00", "strict": True},
        "DCA": {"start": "22:00", "end": "07:00", "strict": True},
        "SNA": {"start": "22:00", "end": "07:00", "strict": True},
        "BUR": {"start": "22:00", "end": "07:00", "strict": True},
        "LGA": {"start": "22:00", "end": "06:00", "strict": False},
        "SAN": {"start": "23:30", "end": "06:30", "strict": False}
    }

    # Noise categories (quieter aircraft may have exemptions)
    AIRCRAFT_NOISE_CATEGORIES = {
        "Chapter 3": ["763", "764", "773"],
        "Chapter 4": ["737", "738", "739", "320", "321", "787", "788", "789"],
        "Chapter 14": ["320neo", "321neo", "A35K"]  # Quietest
    }

    def __init__(self, db_connection):
        self.db = db_connection

    def validate(self, flights: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Validate flights against airport curfews and operating hours

        Args:
            flights: List of flight dictionaries

        Returns:
            List of validation issues
        """
        issues = []

        for flight in flights:
            # Check departure airport
            dep_issues = self._validate_airport_hours(
                flight,
                airport=flight["origin_airport"],
                operation="departure",
                scheduled_time=flight["departure_time"]
            )
            issues.extend(dep_issues)

            # Check arrival airport
            arr_issues = self._validate_airport_hours(
                flight,
                airport=flight["destination_airport"],
                operation="arrival",
                scheduled_time=flight["arrival_time"]
            )
            issues.extend(arr_issues)

        logger.info(f"Curfew validation: {len(issues)} issues found")
        return issues

    def _validate_airport_hours(
        self,
        flight: Dict[str, Any],
        airport: str,
        operation: str,
        scheduled_time: str
    ) -> List[Dict[str, Any]]:
        """Validate operation against airport hours and curfew"""
        issues = []

        # Get airport constraints from database
        constraints = self._get_airport_constraints(airport)

        if not constraints:
            # No constraints in database, check hardcoded list
            if airport in self.CURFEW_AIRPORTS:
                constraints = {
                    "airport_code": airport,
                    "curfew_start": self.CURFEW_AIRPORTS[airport]["start"],
                    "curfew_end": self.CURFEW_AIRPORTS[airport]["end"],
                    "strict_curfew": self.CURFEW_AIRPORTS[airport]["strict"],
                    "operating_hours_start": "00:00",
                    "operating_hours_end": "23:59",
                    "max_night_movements": None
                }
            else:
                # No constraints - airport operates 24/7
                return issues

        # Check operating hours
        if constraints.get("operating_hours_start") and constraints.get("operating_hours_end"):
            if not self._is_within_operating_hours(
                scheduled_time,
                constraints["operating_hours_start"],
                constraints["operating_hours_end"]
            ):
                issues.append({
                    "severity": "critical",
                    "category": "curfew_validation",
                    "flight_id": flight["flight_id"],
                    "flight_number": flight["flight_number"],
                    "issue_type": "outside_operating_hours",
                    "airport": airport,
                    "operation": operation,
                    "scheduled_time": scheduled_time,
                    "operating_hours": f"{constraints['operating_hours_start']}-{constraints['operating_hours_end']}",
                    "description": f"{operation.capitalize()} at {scheduled_time} is outside airport operating hours {constraints['operating_hours_start']}-{constraints['operating_hours_end']}",
                    "recommended_action": "Reschedule within operating hours or request special approval",
                    "impact": "Airport is closed - operation not permitted"
                })

        # Check curfew restrictions
        if constraints.get("curfew_start") and constraints.get("curfew_end"):
            if self._is_during_curfew(
                scheduled_time,
                constraints["curfew_start"],
                constraints["curfew_end"]
            ):
                # Check if exemption applies
                has_exemption = self._check_curfew_exemption(
                    flight, airport, operation, constraints
                )

                severity = "critical" if constraints.get("strict_curfew") else "high"

                if not has_exemption:
                    issues.append({
                        "severity": severity,
                        "category": "curfew_validation",
                        "flight_id": flight["flight_id"],
                        "flight_number": flight["flight_number"],
                        "issue_type": "curfew_violation",
                        "airport": airport,
                        "operation": operation,
                        "scheduled_time": scheduled_time,
                        "curfew_period": f"{constraints['curfew_start']}-{constraints['curfew_end']}",
                        "strict_curfew": constraints.get("strict_curfew", False),
                        "description": f"{operation.capitalize()} at {scheduled_time} violates noise curfew {constraints['curfew_start']}-{constraints['curfew_end']}",
                        "recommended_action": "Reschedule outside curfew or apply for exemption",
                        "impact": "May face fines, penalties, or operation denial"
                    })
                else:
                    # Has exemption but still flag for awareness
                    issues.append({
                        "severity": "low",
                        "category": "curfew_validation",
                        "flight_id": flight["flight_id"],
                        "flight_number": flight["flight_number"],
                        "issue_type": "curfew_exemption_used",
                        "airport": airport,
                        "operation": operation,
                        "scheduled_time": scheduled_time,
                        "curfew_period": f"{constraints['curfew_start']}-{constraints['curfew_end']}",
                        "exemption_reason": has_exemption,
                        "description": f"{operation.capitalize()} during curfew but exemption applies: {has_exemption}",
                        "recommended_action": "Verify exemption documentation is filed",
                        "impact": "Minimal if exemption is properly documented"
                    })

        # Check night movement limits
        if constraints.get("max_night_movements"):
            night_movement_issues = self._check_night_movement_quota(
                flight, airport, operation, scheduled_time, constraints
            )
            issues.extend(night_movement_issues)

        # Check noise restrictions
        noise_issues = self._check_noise_restrictions(
            flight, airport, operation, scheduled_time, constraints
        )
        issues.extend(noise_issues)

        return issues

    def _get_airport_constraints(self, airport_code: str) -> Dict[str, Any]:
        """Get airport constraints from database"""
        cursor = self.db.cursor()

        try:
            cursor.execute(
                """
                SELECT airport_code, operating_hours_start, operating_hours_end,
                       curfew_start, curfew_end, strict_curfew,
                       max_night_movements, noise_category_required,
                       exemption_types
                FROM airport_constraints
                WHERE airport_code = %s
                  AND effective_from <= CURRENT_DATE
                  AND (effective_to IS NULL OR effective_to >= CURRENT_DATE)
                ORDER BY effective_from DESC
                LIMIT 1
                """,
                (airport_code,)
            )

            row = cursor.fetchone()

            if row:
                return {
                    "airport_code": row[0],
                    "operating_hours_start": str(row[1]) if row[1] else None,
                    "operating_hours_end": str(row[2]) if row[2] else None,
                    "curfew_start": str(row[3]) if row[3] else None,
                    "curfew_end": str(row[4]) if row[4] else None,
                    "strict_curfew": row[5],
                    "max_night_movements": row[6],
                    "noise_category_required": row[7],
                    "exemption_types": row[8]
                }

            return None

        finally:
            cursor.close()

    def _is_within_operating_hours(
        self, scheduled: str, start: str, end: str
    ) -> bool:
        """Check if time is within operating hours"""
        sched_time = self._parse_time(scheduled)
        start_time = self._parse_time(start)
        end_time = self._parse_time(end)

        # Handle overnight operating hours
        if end_time < start_time:
            # Operating hours span midnight
            return sched_time >= start_time or sched_time <= end_time
        else:
            return start_time <= sched_time <= end_time

    def _is_during_curfew(
        self, scheduled: str, curfew_start: str, curfew_end: str
    ) -> bool:
        """Check if time is during curfew period"""
        sched_time = self._parse_time(scheduled)
        start_time = self._parse_time(curfew_start)
        end_time = self._parse_time(curfew_end)

        # Curfew typically spans midnight
        if end_time < start_time:
            return sched_time >= start_time or sched_time <= end_time
        else:
            return start_time <= sched_time <= end_time

    def _check_curfew_exemption(
        self,
        flight: Dict[str, Any],
        airport: str,
        operation: str,
        constraints: Dict[str, Any]
    ) -> str:
        """Check if flight qualifies for curfew exemption"""
        # Common exemption reasons:
        # 1. Emergency/medical
        # 2. Government/military
        # 3. Mail/cargo
        # 4. Delayed inbound (arrival only)
        # 5. Quiet aircraft exemption

        exemption_types = constraints.get("exemption_types", [])

        # Check if flight has exemption in database
        cursor = self.db.cursor()

        try:
            cursor.execute(
                """
                SELECT exemption_type, exemption_reason
                FROM airport_slots
                WHERE airport_code = %s
                  AND allocated_to_flight = %s
                  AND slot_type = %s
                  AND exemption_granted = TRUE
                """,
                (airport, flight["flight_id"], operation)
            )

            exemption = cursor.fetchone()

            if exemption:
                return f"{exemption[0]}: {exemption[1]}"

            # Check service type
            if flight.get("service_type") == "F":  # Cargo
                if "cargo" in exemption_types:
                    return "Cargo exemption"

            # Check aircraft noise category
            aircraft_type = flight["aircraft_type"]
            if self._is_quiet_aircraft(aircraft_type):
                if "quiet_aircraft" in exemption_types:
                    return "Quiet aircraft exemption"

            return None

        finally:
            cursor.close()

    def _check_night_movement_quota(
        self,
        flight: Dict[str, Any],
        airport: str,
        operation: str,
        scheduled_time: str,
        constraints: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Check night movement quota limits"""
        issues = []

        max_movements = constraints.get("max_night_movements")

        if not max_movements:
            return issues

        # Check if during night period
        if not self._is_during_curfew(
            scheduled_time,
            constraints.get("curfew_start", "23:00"),
            constraints.get("curfew_end", "06:00")
        ):
            return issues

        # Count night movements for this date
        cursor = self.db.cursor()

        try:
            cursor.execute(
                """
                SELECT COUNT(*)
                FROM flights f
                WHERE (f.origin_airport = %s OR f.destination_airport = %s)
                  AND f.effective_from = %s
                  AND (
                    (f.departure_time BETWEEN %s AND '23:59:59'
                     OR f.departure_time BETWEEN '00:00:00' AND %s)
                    OR
                    (f.arrival_time BETWEEN %s AND '23:59:59'
                     OR f.arrival_time BETWEEN '00:00:00' AND %s)
                  )
                """,
                (
                    airport, airport,
                    flight["effective_from"],
                    constraints.get("curfew_start", "23:00"),
                    constraints.get("curfew_end", "06:00"),
                    constraints.get("curfew_start", "23:00"),
                    constraints.get("curfew_end", "06:00")
                )
            )

            current_movements = cursor.fetchone()[0]

            if current_movements >= max_movements:
                issues.append({
                    "severity": "high",
                    "category": "curfew_validation",
                    "flight_id": flight["flight_id"],
                    "flight_number": flight["flight_number"],
                    "issue_type": "night_movement_quota_exceeded",
                    "airport": airport,
                    "operation": operation,
                    "scheduled_time": scheduled_time,
                    "current_movements": current_movements,
                    "max_movements": max_movements,
                    "description": f"Night movements at {airport} already at {current_movements}/{max_movements} quota",
                    "recommended_action": "Reschedule outside night period or request quota increase",
                    "impact": "May be denied or face significant penalties"
                })

        finally:
            cursor.close()

        return issues

    def _check_noise_restrictions(
        self,
        flight: Dict[str, Any],
        airport: str,
        operation: str,
        scheduled_time: str,
        constraints: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Check aircraft noise category requirements"""
        issues = []

        required_category = constraints.get("noise_category_required")

        if not required_category:
            return issues

        # Check if during noise-sensitive period
        if not self._is_during_curfew(
            scheduled_time,
            constraints.get("curfew_start", "23:00"),
            constraints.get("curfew_end", "06:00")
        ):
            return issues

        # Check aircraft noise category
        aircraft_type = flight["aircraft_type"]
        aircraft_category = self._get_noise_category(aircraft_type)

        # Chapter 14 > Chapter 4 > Chapter 3
        category_hierarchy = ["Chapter 3", "Chapter 4", "Chapter 14"]

        if category_hierarchy.index(aircraft_category) < category_hierarchy.index(required_category):
            issues.append({
                "severity": "high",
                "category": "curfew_validation",
                "flight_id": flight["flight_id"],
                "flight_number": flight["flight_number"],
                "issue_type": "noise_category_violation",
                "airport": airport,
                "operation": operation,
                "scheduled_time": scheduled_time,
                "aircraft_type": aircraft_type,
                "aircraft_noise_category": aircraft_category,
                "required_category": required_category,
                "description": f"Aircraft {aircraft_type} ({aircraft_category}) does not meet required {required_category} for night operations",
                "recommended_action": "Use quieter aircraft or reschedule outside night period",
                "impact": "May face noise penalties or operation denial"
            })

        return issues

    def _is_quiet_aircraft(self, aircraft_type: str) -> bool:
        """Check if aircraft is in quiet category"""
        return aircraft_type in self.AIRCRAFT_NOISE_CATEGORIES.get("Chapter 14", [])

    def _get_noise_category(self, aircraft_type: str) -> str:
        """Get noise category for aircraft type"""
        for category, types in self.AIRCRAFT_NOISE_CATEGORIES.items():
            if aircraft_type in types:
                return category

        return "Chapter 3"  # Default to loudest

    def _parse_time(self, time_value: Any) -> time:
        """Parse time string or object to time"""
        if isinstance(time_value, time):
            return time_value

        if isinstance(time_value, str):
            parts = time_value.split(':')
            return time(int(parts[0]), int(parts[1]), int(parts[2]) if len(parts) > 2 else 0)

        return time_value
