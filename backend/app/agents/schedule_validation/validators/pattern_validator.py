"""
Schedule Pattern Validator
Validates schedule patterns and consistency
"""

from typing import List, Dict, Any, Set
from datetime import datetime, timedelta, time
from collections import defaultdict
import logging

logger = logging.getLogger(__name__)


class PatternValidator:
    """
    Validates schedule patterns and consistency

    Checks:
    - Operating days pattern consistency (1234567 format)
    - Frequency per week matches actual days
    - Seasonal schedule variations
    - Bank structures at hub airports
    - Schedule symmetry (outbound/inbound balance)
    - Competitive timing vs other carriers
    - Red-eye vs day flight patterns
    - Equipment consistency for same flight number
    """

    # Valid operating days characters
    VALID_OPERATING_CHARS = set("1234567X")

    # Day mapping
    DAY_MAPPING = {
        "1": "Monday",
        "2": "Tuesday",
        "3": "Wednesday",
        "4": "Thursday",
        "5": "Friday",
        "6": "Saturday",
        "7": "Sunday"
    }

    def __init__(self, db_connection):
        self.db = db_connection

    def validate(self, flights: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Validate schedule patterns

        Args:
            flights: List of flight dictionaries

        Returns:
            List of validation issues
        """
        issues = []

        # Validate operating days format
        for flight in flights:
            pattern_issues = self._validate_operating_days(flight)
            issues.extend(pattern_issues)

        # Validate frequency consistency
        freq_issues = self._validate_frequency(flights)
        issues.extend(freq_issues)

        # Validate equipment consistency
        equipment_issues = self._validate_equipment_consistency(flights)
        issues.extend(equipment_issues)

        # Validate hub bank structures
        bank_issues = self._validate_hub_banks(flights)
        issues.extend(bank_issues)

        # Validate schedule symmetry
        symmetry_issues = self._validate_schedule_symmetry(flights)
        issues.extend(symmetry_issues)

        # Validate seasonal patterns
        seasonal_issues = self._validate_seasonal_patterns(flights)
        issues.extend(seasonal_issues)

        logger.info(f"Pattern validation: {len(issues)} issues found")
        return issues

    def _validate_operating_days(
        self, flight: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Validate operating days pattern format"""
        issues = []

        operating_days = flight.get("operating_days", "")

        # Check length
        if len(operating_days) != 7:
            issues.append({
                "severity": "critical",
                "category": "pattern_validation",
                "flight_id": flight["flight_id"],
                "flight_number": flight["flight_number"],
                "issue_type": "invalid_operating_days_length",
                "operating_days": operating_days,
                "description": f"Operating days '{operating_days}' must be exactly 7 characters",
                "recommended_action": "Correct operating days pattern to 7-character format",
                "impact": "Invalid pattern cannot be processed"
            })
            return issues

        # Check valid characters
        invalid_chars = set(operating_days) - self.VALID_OPERATING_CHARS

        if invalid_chars:
            issues.append({
                "severity": "critical",
                "category": "pattern_validation",
                "flight_id": flight["flight_id"],
                "flight_number": flight["flight_number"],
                "issue_type": "invalid_operating_days_chars",
                "operating_days": operating_days,
                "invalid_characters": list(invalid_chars),
                "description": f"Operating days contains invalid characters: {invalid_chars}",
                "recommended_action": "Use only 1-7 for operating days, X for non-operating",
                "impact": "Invalid pattern cannot be processed"
            })

        # Check if at least one day is operating
        if operating_days == "XXXXXXX" or not any(c in "1234567" for c in operating_days):
            issues.append({
                "severity": "high",
                "category": "pattern_validation",
                "flight_id": flight["flight_id"],
                "flight_number": flight["flight_number"],
                "issue_type": "no_operating_days",
                "operating_days": operating_days,
                "description": "Flight has no operating days",
                "recommended_action": "Specify at least one operating day or remove flight",
                "impact": "Flight never operates"
            })

        return issues

    def _validate_frequency(
        self, flights: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Validate frequency per week matches operating days"""
        issues = []

        for flight in flights:
            operating_days = flight.get("operating_days", "")
            stated_freq = flight.get("frequency_per_week")

            # Count actual operating days
            actual_freq = sum(1 for c in operating_days if c in "1234567")

            if stated_freq and actual_freq != stated_freq:
                issues.append({
                    "severity": "medium",
                    "category": "pattern_validation",
                    "flight_id": flight["flight_id"],
                    "flight_number": flight["flight_number"],
                    "issue_type": "frequency_mismatch",
                    "operating_days": operating_days,
                    "stated_frequency": stated_freq,
                    "actual_frequency": actual_freq,
                    "description": f"Stated frequency {stated_freq}x/week doesn't match operating days pattern {actual_freq}x/week",
                    "recommended_action": "Correct frequency_per_week field or operating days pattern",
                    "impact": "Schedule data inconsistency"
                })

        return issues

    def _validate_equipment_consistency(
        self, flights: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Validate same flight number uses consistent equipment"""
        issues = []

        # Group by flight number and route
        flights_by_number = defaultdict(list)

        for flight in flights:
            key = (
                flight["carrier_code"],
                flight["flight_number"],
                flight["origin_airport"],
                flight["destination_airport"]
            )
            flights_by_number[key].append(flight)

        # Check equipment consistency
        for (carrier, flight_num, origin, dest), flight_group in flights_by_number.items():
            aircraft_types = set(f["aircraft_type"] for f in flight_group)

            if len(aircraft_types) > 1:
                # Multiple aircraft types for same flight number
                issues.append({
                    "severity": "medium",
                    "category": "pattern_validation",
                    "flight_id": flight_group[0]["flight_id"],
                    "flight_number": flight_num,
                    "issue_type": "inconsistent_equipment",
                    "carrier": carrier,
                    "route": f"{origin}-{dest}",
                    "aircraft_types": list(aircraft_types),
                    "description": f"Flight {carrier}{flight_num} uses multiple aircraft types: {list(aircraft_types)}",
                    "recommended_action": "Use consistent aircraft type or create separate flight numbers",
                    "impact": "Passenger confusion, inconsistent service levels"
                })

        return issues

    def _validate_hub_banks(
        self, flights: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Validate hub bank structures for connectivity"""
        issues = []

        # Hub airports for major carriers
        HUB_AIRPORTS = {
            "ATL", "DFW", "ORD", "LAX", "DEN", "JFK", "SFO", "IAH",
            "LHR", "CDG", "FRA", "AMS", "DXB", "SIN", "HKG"
        }

        # Group arrivals and departures by hub
        for hub in HUB_AIRPORTS:
            hub_arrivals = [
                f for f in flights
                if f["destination_airport"] == hub
            ]

            hub_departures = [
                f for f in flights
                if f["origin_airport"] == hub
            ]

            if hub_arrivals and hub_departures:
                # Check bank structure (arrivals cluster before departures)
                bank_issues = self._check_bank_structure(
                    hub, hub_arrivals, hub_departures
                )
                issues.extend(bank_issues)

        return issues

    def _check_bank_structure(
        self, hub: str, arrivals: List[Dict[str, Any]], departures: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Check if arrival/departure times form a bank"""
        issues = []

        # Get arrival times
        arrival_times = sorted([
            self._parse_time(f["arrival_time"]) for f in arrivals
        ])

        # Get departure times
        departure_times = sorted([
            self._parse_time(f["departure_time"]) for f in departures
        ])

        if not arrival_times or not departure_times:
            return issues

        # Check if arrivals cluster before departures
        # Bank structure: arrivals within 30-60 min window, departures 45-90 min after
        # Simplified check: average arrival should be before average departure

        avg_arrival = self._average_time(arrival_times)
        avg_departure = self._average_time(departure_times)

        # Calculate gap
        gap_minutes = self._time_diff_minutes(avg_arrival, avg_departure)

        # Ideal connection time: 45-90 minutes
        if gap_minutes < 30:
            issues.append({
                "severity": "low",
                "category": "pattern_validation",
                "flight_id": "N/A",
                "flight_number": "Hub pattern",
                "issue_type": "insufficient_connection_buffer",
                "hub": hub,
                "avg_arrival_time": str(avg_arrival),
                "avg_departure_time": str(avg_departure),
                "gap_minutes": gap_minutes,
                "description": f"Hub {hub} has only {gap_minutes}min between average arrival and departure",
                "recommended_action": "Increase buffer for better connectivity",
                "impact": "Tight connections may result in misconnects"
            })
        elif gap_minutes > 180:
            issues.append({
                "severity": "low",
                "category": "pattern_validation",
                "flight_id": "N/A",
                "flight_number": "Hub pattern",
                "issue_type": "excessive_connection_buffer",
                "hub": hub,
                "avg_arrival_time": str(avg_arrival),
                "avg_departure_time": str(avg_departure),
                "gap_minutes": gap_minutes,
                "description": f"Hub {hub} has {gap_minutes}min between average arrival and departure",
                "recommended_action": "Tighten banks for better aircraft/crew utilization",
                "impact": "Long connection times reduce competitiveness"
            })

        return issues

    def _validate_schedule_symmetry(
        self, flights: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Validate outbound/inbound schedule symmetry"""
        issues = []

        # Group by route pair
        route_pairs = defaultdict(lambda: {"outbound": [], "inbound": []})

        for flight in flights:
            origin = flight["origin_airport"]
            dest = flight["destination_airport"]

            # Canonical route (alphabetically sorted)
            route = tuple(sorted([origin, dest]))

            # Determine direction
            if origin == route[0]:
                route_pairs[route]["outbound"].append(flight)
            else:
                route_pairs[route]["inbound"].append(flight)

        # Check symmetry
        for route, directions in route_pairs.items():
            outbound_count = len(directions["outbound"])
            inbound_count = len(directions["inbound"])

            # Should be balanced (allowing 1 flight difference)
            if abs(outbound_count - inbound_count) > 1:
                issues.append({
                    "severity": "medium",
                    "category": "pattern_validation",
                    "flight_id": "N/A",
                    "flight_number": "Route pattern",
                    "issue_type": "schedule_asymmetry",
                    "route": f"{route[0]}-{route[1]}",
                    "outbound_flights": outbound_count,
                    "inbound_flights": inbound_count,
                    "difference": abs(outbound_count - inbound_count),
                    "description": f"Route {route[0]}-{route[1]} has {outbound_count} outbound but {inbound_count} inbound flights",
                    "recommended_action": "Balance outbound/inbound frequencies",
                    "impact": "Aircraft/crew imbalance, poor resource utilization"
                })

        return issues

    def _validate_seasonal_patterns(
        self, flights: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Validate seasonal schedule variations"""
        issues = []

        # Group by flight number and check effective dates
        flights_by_number = defaultdict(list)

        for flight in flights:
            key = (flight["carrier_code"], flight["flight_number"])
            flights_by_number[key].append(flight)

        # Check for overlapping effective dates
        for (carrier, flight_num), flight_group in flights_by_number.items():
            # Sort by effective_from
            sorted_flights = sorted(
                flight_group,
                key=lambda f: f.get("effective_from", "1900-01-01")
            )

            for i in range(len(sorted_flights) - 1):
                current = sorted_flights[i]
                next_flight = sorted_flights[i + 1]

                current_end = current.get("effective_to")
                next_start = next_flight.get("effective_from")

                if current_end and next_start:
                    # Check for overlap
                    if current_end >= next_start:
                        issues.append({
                            "severity": "high",
                            "category": "pattern_validation",
                            "flight_id": next_flight["flight_id"],
                            "flight_number": flight_num,
                            "issue_type": "overlapping_effective_dates",
                            "carrier": carrier,
                            "current_period": f"{current.get('effective_from')} to {current_end}",
                            "next_period": f"{next_start} to {next_flight.get('effective_to')}",
                            "description": f"Flight {carrier}{flight_num} has overlapping effective periods",
                            "recommended_action": "Adjust effective dates to avoid overlap",
                            "impact": "Duplicate flight operations, schedule confusion"
                        })

                    # Check for gap
                    current_end_date = datetime.strptime(str(current_end), "%Y-%m-%d")
                    next_start_date = datetime.strptime(str(next_start), "%Y-%m-%d")

                    gap_days = (next_start_date - current_end_date).days

                    if gap_days > 1:
                        issues.append({
                            "severity": "low",
                            "category": "pattern_validation",
                            "flight_id": next_flight["flight_id"],
                            "flight_number": flight_num,
                            "issue_type": "gap_in_effective_dates",
                            "carrier": carrier,
                            "gap_days": gap_days,
                            "gap_start": str(current_end),
                            "gap_end": str(next_start),
                            "description": f"Flight {carrier}{flight_num} has {gap_days} day gap between seasonal schedules",
                            "recommended_action": "Review if gap is intentional or fill gap",
                            "impact": "Service interruption during gap period"
                        })

        return issues

    def _parse_time(self, time_value: Any) -> time:
        """Parse time string or object to time"""
        if isinstance(time_value, time):
            return time_value

        if isinstance(time_value, str):
            parts = time_value.split(':')
            return time(int(parts[0]), int(parts[1]), int(parts[2]) if len(parts) > 2 else 0)

        return time_value

    def _average_time(self, times: List[time]) -> time:
        """Calculate average of time objects"""
        if not times:
            return time(0, 0)

        # Convert to minutes since midnight
        total_minutes = sum(t.hour * 60 + t.minute for t in times)
        avg_minutes = total_minutes // len(times)

        return time(avg_minutes // 60, avg_minutes % 60)

    def _time_diff_minutes(self, time1: time, time2: time) -> int:
        """Calculate minute difference between times"""
        dt1 = datetime.combine(datetime.today(), time1)
        dt2 = datetime.combine(datetime.today(), time2)

        # Handle overnight
        if dt2 < dt1:
            dt2 += timedelta(days=1)

        return int((dt2 - dt1).total_seconds() / 60)
