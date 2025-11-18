"""
Aircraft Availability Validator
Validates that aircraft are available and properly routed for scheduled flights
"""

from typing import List, Dict, Any
from datetime import datetime, timedelta, time
import logging

logger = logging.getLogger(__name__)


class AircraftValidator:
    """
    Validates aircraft availability and routing

    Checks:
    - Aircraft exists and is active
    - Aircraft type matches flight requirements
    - Aircraft is not in maintenance during flight time
    - Sufficient turnaround time from previous flight
    - Aircraft routing continuity (arrival airport matches next departure)
    - Daily/weekly utilization limits
    """

    # Minimum turnaround times by aircraft category (minutes)
    MIN_TURNAROUND_TIMES = {
        "narrow_body": 45,   # A320, B737
        "wide_body": 90,     # A330, B777, B787
        "regional": 30,      # E190, CRJ
        "default": 45
    }

    # Aircraft type categories
    AIRCRAFT_CATEGORIES = {
        "narrow_body": ["319", "320", "321", "733", "737", "738", "739"],
        "wide_body": ["330", "333", "359", "763", "764", "772", "773", "787", "788", "789"],
        "regional": ["E90", "E95", "CR7", "CR9", "DH4"]
    }

    # Maximum daily flight hours per aircraft
    MAX_DAILY_FLIGHT_HOURS = 16

    def __init__(self, db_connection):
        self.db = db_connection

    def validate(self, flights: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Validate aircraft availability for all flights

        Args:
            flights: List of flight dictionaries

        Returns:
            List of validation issues
        """
        issues = []

        # Group flights by aircraft registration
        flights_by_aircraft = self._group_by_aircraft(flights)

        for aircraft_reg, aircraft_flights in flights_by_aircraft.items():
            # Check aircraft exists and is active
            aircraft_info = self._get_aircraft_info(aircraft_reg)

            if not aircraft_info:
                for flight in aircraft_flights:
                    issues.append({
                        "severity": "critical",
                        "category": "aircraft_validation",
                        "flight_id": flight["flight_id"],
                        "flight_number": flight["flight_number"],
                        "issue_type": "aircraft_not_found",
                        "aircraft_registration": aircraft_reg,
                        "description": f"Aircraft {aircraft_reg} not found in fleet database",
                        "recommended_action": "Assign valid aircraft or add aircraft to fleet",
                        "impact": "Flight cannot operate with unregistered aircraft"
                    })
                continue

            # Check aircraft is active
            if aircraft_info["status"] != "active":
                for flight in aircraft_flights:
                    issues.append({
                        "severity": "critical",
                        "category": "aircraft_validation",
                        "flight_id": flight["flight_id"],
                        "flight_number": flight["flight_number"],
                        "issue_type": "aircraft_inactive",
                        "aircraft_registration": aircraft_reg,
                        "aircraft_status": aircraft_info["status"],
                        "description": f"Aircraft {aircraft_reg} is {aircraft_info['status']}, not active",
                        "recommended_action": "Assign different aircraft",
                        "impact": "Flight cannot operate with inactive aircraft"
                    })
                continue

            # Sort flights by departure time
            sorted_flights = sorted(aircraft_flights, key=lambda f: f["departure_time"])

            # Validate each flight
            for i, flight in enumerate(sorted_flights):
                # Check aircraft type compatibility
                type_issues = self._validate_aircraft_type(flight, aircraft_info)
                issues.extend(type_issues)

                # Check maintenance conflicts
                maint_issues = self._validate_maintenance(flight, aircraft_reg)
                issues.extend(maint_issues)

                # Check turnaround time from previous flight
                if i > 0:
                    prev_flight = sorted_flights[i - 1]
                    turnaround_issues = self._validate_turnaround(
                        prev_flight, flight, aircraft_info
                    )
                    issues.extend(turnaround_issues)

                # Check routing continuity
                if i > 0:
                    prev_flight = sorted_flights[i - 1]
                    routing_issues = self._validate_routing_continuity(
                        prev_flight, flight
                    )
                    issues.extend(routing_issues)

            # Check daily utilization
            utilization_issues = self._validate_daily_utilization(
                sorted_flights, aircraft_reg
            )
            issues.extend(utilization_issues)

        logger.info(f"Aircraft validation: {len(issues)} issues found")
        return issues

    def _group_by_aircraft(
        self, flights: List[Dict[str, Any]]
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Group flights by aircraft registration"""
        grouped = {}
        for flight in flights:
            reg = flight.get("aircraft_registration")
            if reg:
                if reg not in grouped:
                    grouped[reg] = []
                grouped[reg].append(flight)
        return grouped

    def _get_aircraft_info(self, registration: str) -> Dict[str, Any]:
        """Get aircraft information from database"""
        cursor = self.db.cursor()

        try:
            cursor.execute(
                """
                SELECT registration, aircraft_type, status,
                       owner_airline, seating_capacity,
                       last_maintenance_date, next_maintenance_date
                FROM aircraft_availability
                WHERE registration = %s
                """,
                (registration,)
            )

            row = cursor.fetchone()

            if row:
                return {
                    "registration": row[0],
                    "aircraft_type": row[1],
                    "status": row[2],
                    "owner_airline": row[3],
                    "seating_capacity": row[4],
                    "last_maintenance_date": row[5],
                    "next_maintenance_date": row[6]
                }

            return None

        finally:
            cursor.close()

    def _validate_aircraft_type(
        self, flight: Dict[str, Any], aircraft_info: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Validate aircraft type matches flight requirements"""
        issues = []

        flight_aircraft_type = flight["aircraft_type"]
        actual_aircraft_type = aircraft_info["aircraft_type"]

        if flight_aircraft_type != actual_aircraft_type:
            issues.append({
                "severity": "high",
                "category": "aircraft_validation",
                "flight_id": flight["flight_id"],
                "flight_number": flight["flight_number"],
                "issue_type": "aircraft_type_mismatch",
                "aircraft_registration": aircraft_info["registration"],
                "expected_type": flight_aircraft_type,
                "actual_type": actual_aircraft_type,
                "description": f"Flight requires {flight_aircraft_type} but {aircraft_info['registration']} is {actual_aircraft_type}",
                "recommended_action": "Assign correct aircraft type or update flight aircraft type",
                "impact": "Wrong aircraft type may affect capacity, range, and operations"
            })

        return issues

    def _validate_maintenance(
        self, flight: Dict[str, Any], aircraft_reg: str
    ) -> List[Dict[str, Any]]:
        """Check for maintenance conflicts"""
        issues = []

        cursor = self.db.cursor()

        try:
            # Check if aircraft has scheduled maintenance during flight time
            cursor.execute(
                """
                SELECT maintenance_id, maintenance_type,
                       scheduled_start, scheduled_end, location
                FROM aircraft_availability
                WHERE registration = %s
                  AND scheduled_start IS NOT NULL
                  AND scheduled_end IS NOT NULL
                  AND %s BETWEEN scheduled_start AND scheduled_end
                """,
                (aircraft_reg, flight["departure_time"])
            )

            maintenance = cursor.fetchone()

            if maintenance:
                maint_id, maint_type, start, end, location = maintenance

                issues.append({
                    "severity": "critical",
                    "category": "aircraft_validation",
                    "flight_id": flight["flight_id"],
                    "flight_number": flight["flight_number"],
                    "issue_type": "maintenance_conflict",
                    "aircraft_registration": aircraft_reg,
                    "maintenance_type": maint_type,
                    "maintenance_start": str(start),
                    "maintenance_end": str(end),
                    "maintenance_location": location,
                    "description": f"Aircraft {aircraft_reg} scheduled for {maint_type} maintenance during flight time",
                    "recommended_action": f"Reschedule maintenance or assign different aircraft",
                    "impact": "Flight cannot operate during scheduled maintenance"
                })

        finally:
            cursor.close()

        return issues

    def _validate_turnaround(
        self,
        prev_flight: Dict[str, Any],
        current_flight: Dict[str, Any],
        aircraft_info: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Validate sufficient turnaround time between flights"""
        issues = []

        # Calculate turnaround time
        prev_arrival = self._parse_time(prev_flight["arrival_time"])
        current_departure = self._parse_time(current_flight["departure_time"])

        # Handle overnight turnaround
        if current_departure < prev_arrival:
            current_departure = datetime.combine(
                datetime.now().date() + timedelta(days=1),
                current_departure
            ).time()

        prev_arrival_dt = datetime.combine(datetime.now().date(), prev_arrival)
        current_departure_dt = datetime.combine(datetime.now().date(), current_departure)

        turnaround_minutes = (current_departure_dt - prev_arrival_dt).total_seconds() / 60

        # Get minimum turnaround for aircraft category
        category = self._get_aircraft_category(aircraft_info["aircraft_type"])
        min_turnaround = self.MIN_TURNAROUND_TIMES.get(
            category, self.MIN_TURNAROUND_TIMES["default"]
        )

        if turnaround_minutes < min_turnaround:
            issues.append({
                "severity": "high",
                "category": "aircraft_validation",
                "flight_id": current_flight["flight_id"],
                "flight_number": current_flight["flight_number"],
                "issue_type": "insufficient_turnaround",
                "aircraft_registration": aircraft_info["registration"],
                "previous_flight": prev_flight["flight_number"],
                "previous_arrival": prev_flight["arrival_time"],
                "current_departure": current_flight["departure_time"],
                "turnaround_minutes": round(turnaround_minutes),
                "minimum_required": min_turnaround,
                "description": f"Turnaround time {round(turnaround_minutes)}min is less than minimum {min_turnaround}min for {category} aircraft",
                "recommended_action": f"Adjust departure time or assign different aircraft",
                "impact": "Insufficient time for cleaning, refueling, and passenger boarding"
            })

        return issues

    def _validate_routing_continuity(
        self,
        prev_flight: Dict[str, Any],
        current_flight: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Validate aircraft routing continuity"""
        issues = []

        if prev_flight["destination_airport"] != current_flight["origin_airport"]:
            issues.append({
                "severity": "critical",
                "category": "aircraft_validation",
                "flight_id": current_flight["flight_id"],
                "flight_number": current_flight["flight_number"],
                "issue_type": "routing_discontinuity",
                "aircraft_registration": current_flight.get("aircraft_registration"),
                "previous_flight": prev_flight["flight_number"],
                "previous_destination": prev_flight["destination_airport"],
                "current_origin": current_flight["origin_airport"],
                "description": f"Aircraft arrives at {prev_flight['destination_airport']} but next flight departs from {current_flight['origin_airport']}",
                "recommended_action": "Add positioning flight or assign different aircraft",
                "impact": "Aircraft cannot teleport between airports"
            })

        return issues

    def _validate_daily_utilization(
        self,
        flights: List[Dict[str, Any]],
        aircraft_reg: str
    ) -> List[Dict[str, Any]]:
        """Check daily flight hour limits"""
        issues = []

        # Group flights by effective date
        flights_by_date = {}
        for flight in flights:
            date = flight.get("effective_from")
            if date not in flights_by_date:
                flights_by_date[date] = []
            flights_by_date[date].append(flight)

        for date, day_flights in flights_by_date.items():
            # Calculate total flight hours
            total_hours = 0

            for flight in day_flights:
                # Estimate flight duration
                dep = self._parse_time(flight["departure_time"])
                arr = self._parse_time(flight["arrival_time"])

                dep_dt = datetime.combine(datetime.now().date(), dep)
                arr_dt = datetime.combine(datetime.now().date(), arr)

                # Handle overnight flights
                if arr < dep:
                    arr_dt = datetime.combine(
                        datetime.now().date() + timedelta(days=1),
                        arr
                    )

                duration_hours = (arr_dt - dep_dt).total_seconds() / 3600
                total_hours += duration_hours

            if total_hours > self.MAX_DAILY_FLIGHT_HOURS:
                issues.append({
                    "severity": "medium",
                    "category": "aircraft_validation",
                    "flight_id": day_flights[0]["flight_id"],
                    "flight_number": "Multiple",
                    "issue_type": "excessive_utilization",
                    "aircraft_registration": aircraft_reg,
                    "date": str(date),
                    "total_flight_hours": round(total_hours, 1),
                    "maximum_allowed": self.MAX_DAILY_FLIGHT_HOURS,
                    "description": f"Aircraft scheduled for {round(total_hours, 1)} flight hours on {date}, exceeds {self.MAX_DAILY_FLIGHT_HOURS}hr limit",
                    "recommended_action": "Reduce daily flights or assign additional aircraft",
                    "impact": "May violate maintenance requirements and crew duty limits"
                })

        return issues

    def _get_aircraft_category(self, aircraft_type: str) -> str:
        """Determine aircraft category from type code"""
        for category, types in self.AIRCRAFT_CATEGORIES.items():
            if aircraft_type in types:
                return category
        return "default"

    def _parse_time(self, time_str: str) -> time:
        """Parse time string to time object"""
        if isinstance(time_str, time):
            return time_str

        # Handle HH:MM:SS or HH:MM format
        parts = time_str.split(':')
        hour = int(parts[0])
        minute = int(parts[1])
        second = int(parts[2]) if len(parts) > 2 else 0

        return time(hour, minute, second)
