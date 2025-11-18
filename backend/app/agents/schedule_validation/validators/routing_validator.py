"""
Aircraft Routing Validator
Validates aircraft routing efficiency and feasibility
"""

from typing import List, Dict, Any, Tuple
from datetime import datetime, timedelta, time
import logging

logger = logging.getLogger(__name__)


class RoutingValidator:
    """
    Validates aircraft routing patterns

    Checks:
    - Routing continuity (arrival airport = next departure airport)
    - Circular routing patterns (aircraft returns to base)
    - Deadhead/positioning flight efficiency
    - Aircraft range limitations
    - Fuel stops if required
    - Hub connectivity optimization
    - Daily aircraft utilization
    """

    # Aircraft range (nautical miles)
    AIRCRAFT_RANGES = {
        "319": 3750,
        "320": 3300,
        "321": 3200,
        "733": 3000,
        "737": 3000,
        "738": 3100,
        "739": 3300,
        "330": 6350,
        "333": 6350,
        "359": 8100,
        "763": 6385,
        "764": 6385,
        "772": 7730,
        "773": 7370,
        "787": 7355,
        "788": 7355,
        "789": 7635,
        "E90": 2300,
        "E95": 2300,
        "CR7": 2000,
        "CR9": 2400,
        "DH4": 1200
    }

    # Approximate distances between major airports (nautical miles)
    # In production, use Great Circle distance calculation
    AIRPORT_DISTANCES = {
        ("JFK", "LHR"): 2999,
        ("LAX", "NRT"): 4766,
        ("LAX", "SYD"): 6511,
        ("DFW", "LHR"): 4115,
        ("ORD", "LHR"): 3428,
        # Add more as needed
    }

    # Hub airports for routing optimization
    HUB_AIRPORTS = {
        "ATL", "DFW", "ORD", "LAX", "DEN", "JFK", "SFO", "IAH", "LHR",
        "CDG", "FRA", "AMS", "DXB", "SIN", "HKG", "ICN", "NRT", "SYD"
    }

    def __init__(self, db_connection):
        self.db = db_connection

    def validate(self, flights: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Validate aircraft routing for all flights

        Args:
            flights: List of flight dictionaries

        Returns:
            List of validation issues
        """
        issues = []

        # Group flights by aircraft and date
        flights_by_aircraft = self._group_by_aircraft_and_date(flights)

        for (aircraft_reg, date), daily_flights in flights_by_aircraft.items():
            # Sort by departure time
            sorted_flights = sorted(daily_flights, key=lambda f: f["departure_time"])

            # Validate routing chain
            routing_issues = self._validate_routing_chain(sorted_flights, aircraft_reg, date)
            issues.extend(routing_issues)

            # Validate range limitations
            range_issues = self._validate_range_limitations(sorted_flights)
            issues.extend(range_issues)

            # Validate hub connectivity
            hub_issues = self._validate_hub_connectivity(sorted_flights)
            issues.extend(hub_issues)

            # Check for inefficient positioning
            positioning_issues = self._check_positioning_efficiency(sorted_flights)
            issues.extend(positioning_issues)

        logger.info(f"Routing validation: {len(issues)} issues found")
        return issues

    def _group_by_aircraft_and_date(
        self, flights: List[Dict[str, Any]]
    ) -> Dict[Tuple[str, str], List[Dict[str, Any]]]:
        """Group flights by aircraft registration and date"""
        grouped = {}

        for flight in flights:
            reg = flight.get("aircraft_registration")
            date = flight.get("effective_from")

            if reg and date:
                key = (reg, date)
                if key not in grouped:
                    grouped[key] = []
                grouped[key].append(flight)

        return grouped

    def _validate_routing_chain(
        self, flights: List[Dict[str, Any]], aircraft_reg: str, date: str
    ) -> List[Dict[str, Any]]:
        """Validate routing chain continuity"""
        issues = []

        for i in range(len(flights) - 1):
            current = flights[i]
            next_flight = flights[i + 1]

            # Check if arrival airport matches next departure
            if current["destination_airport"] != next_flight["origin_airport"]:
                # Routing discontinuity - check if positioning flight exists
                positioning = self._find_positioning_flight(
                    current, next_flight, flights
                )

                if not positioning:
                    issues.append({
                        "severity": "critical",
                        "category": "routing_validation",
                        "flight_id": next_flight["flight_id"],
                        "flight_number": next_flight["flight_number"],
                        "issue_type": "routing_discontinuity",
                        "aircraft_registration": aircraft_reg,
                        "date": date,
                        "previous_flight": current["flight_number"],
                        "previous_destination": current["destination_airport"],
                        "next_origin": next_flight["origin_airport"],
                        "description": f"Aircraft at {current['destination_airport']} but next flight departs from {next_flight['origin_airport']}",
                        "recommended_action": "Add positioning flight or adjust routing",
                        "impact": "Aircraft cannot teleport - routing is impossible"
                    })

        # Check if routing forms a circular pattern (returns to starting point)
        if len(flights) > 0:
            first_origin = flights[0]["origin_airport"]
            last_dest = flights[-1]["destination_airport"]

            if first_origin != last_dest:
                # Aircraft doesn't return to origin
                issues.append({
                    "severity": "medium",
                    "category": "routing_validation",
                    "flight_id": flights[-1]["flight_id"],
                    "flight_number": "Daily pattern",
                    "issue_type": "non_circular_routing",
                    "aircraft_registration": aircraft_reg,
                    "date": date,
                    "first_origin": first_origin,
                    "last_destination": last_dest,
                    "description": f"Aircraft starts at {first_origin} but ends at {last_dest} - non-circular routing",
                    "recommended_action": "Add return flight or plan overnight at different base",
                    "impact": "May require repositioning or overnight away from base"
                })

        return issues

    def _validate_range_limitations(
        self, flights: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Validate flights are within aircraft range"""
        issues = []

        for flight in flights:
            aircraft_type = flight["aircraft_type"]
            origin = flight["origin_airport"]
            destination = flight["destination_airport"]

            # Get aircraft range
            max_range = self.AIRCRAFT_RANGES.get(aircraft_type, 3000)  # Default 3000nm

            # Get flight distance
            distance = self._get_distance(origin, destination)

            # Add 10% reserve for reserves and weather
            required_range = distance * 1.1

            if required_range > max_range:
                # Flight exceeds range
                # Check if fuel stop is planned
                has_fuel_stop = self._check_fuel_stop(flight, origin, destination)

                if not has_fuel_stop:
                    issues.append({
                        "severity": "critical",
                        "category": "routing_validation",
                        "flight_id": flight["flight_id"],
                        "flight_number": flight["flight_number"],
                        "issue_type": "range_exceeded",
                        "aircraft_type": aircraft_type,
                        "origin": origin,
                        "destination": destination,
                        "distance_nm": round(distance),
                        "required_range_nm": round(required_range),
                        "aircraft_range_nm": max_range,
                        "shortfall_nm": round(required_range - max_range),
                        "description": f"Flight distance {round(distance)}nm exceeds {aircraft_type} range {max_range}nm",
                        "recommended_action": "Add fuel stop, use different aircraft type, or cancel flight",
                        "impact": "Aircraft cannot complete flight without refueling"
                    })

        return issues

    def _validate_hub_connectivity(
        self, flights: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Validate hub connectivity for network efficiency"""
        issues = []

        # Count hub vs spoke flights
        hub_flights = 0
        spoke_flights = 0

        for flight in flights:
            origin = flight["origin_airport"]
            dest = flight["destination_airport"]

            if origin in self.HUB_AIRPORTS or dest in self.HUB_AIRPORTS:
                hub_flights += 1
            else:
                spoke_flights += 1

        # If more than 50% are spoke-to-spoke, might be inefficient
        if len(flights) > 3 and spoke_flights > hub_flights:
            issues.append({
                "severity": "low",
                "category": "routing_validation",
                "flight_id": flights[0]["flight_id"],
                "flight_number": "Daily pattern",
                "issue_type": "low_hub_connectivity",
                "hub_flights": hub_flights,
                "spoke_flights": spoke_flights,
                "description": f"Routing has {spoke_flights} spoke-to-spoke flights vs {hub_flights} hub flights",
                "recommended_action": "Consider routing via hubs for better network connectivity",
                "impact": "Reduced passenger connection opportunities"
            })

        return issues

    def _check_positioning_efficiency(
        self, flights: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Check for inefficient empty positioning flights"""
        issues = []

        for flight in flights:
            # Check if this is a positioning flight (no passengers)
            if flight.get("service_type") == "positioning" or flight.get("is_ferry"):
                # Check if there's a more efficient routing
                issues.append({
                    "severity": "low",
                    "category": "routing_validation",
                    "flight_id": flight["flight_id"],
                    "flight_number": flight["flight_number"],
                    "issue_type": "positioning_flight",
                    "origin": flight["origin_airport"],
                    "destination": flight["destination_airport"],
                    "description": f"Empty positioning flight from {flight['origin_airport']} to {flight['destination_airport']}",
                    "recommended_action": "Review routing to minimize positioning flights",
                    "impact": "Inefficient use of aircraft - generates cost without revenue"
                })

        return issues

    def _find_positioning_flight(
        self,
        current: Dict[str, Any],
        next_flight: Dict[str, Any],
        all_flights: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Find positioning flight between current and next"""
        # Look for flight from current destination to next origin
        for flight in all_flights:
            if (flight["origin_airport"] == current["destination_airport"] and
                flight["destination_airport"] == next_flight["origin_airport"]):

                # Check timing
                current_arr = self._parse_time(current["arrival_time"])
                positioning_dep = self._parse_time(flight["departure_time"])
                next_dep = self._parse_time(next_flight["departure_time"])

                if current_arr < positioning_dep < next_dep:
                    return flight

        return None

    def _get_distance(self, origin: str, dest: str) -> float:
        """Get distance between airports in nautical miles"""
        # Check both orderings
        key1 = (origin, dest)
        key2 = (dest, origin)

        if key1 in self.AIRPORT_DISTANCES:
            return self.AIRPORT_DISTANCES[key1]
        elif key2 in self.AIRPORT_DISTANCES:
            return self.AIRPORT_DISTANCES[key2]

        # Try database
        distance = self._get_distance_from_db(origin, dest)
        if distance:
            return distance

        # Estimate based on rough calculation (simplified)
        # In production, use Great Circle formula with lat/long
        return 2000  # Default estimate

    def _get_distance_from_db(self, origin: str, dest: str) -> float:
        """Get distance from database"""
        cursor = self.db.cursor()

        try:
            cursor.execute(
                """
                SELECT distance_nm
                FROM airport_pairs
                WHERE (origin_airport = %s AND destination_airport = %s)
                   OR (origin_airport = %s AND destination_airport = %s)
                LIMIT 1
                """,
                (origin, dest, dest, origin)
            )

            result = cursor.fetchone()
            if result:
                return float(result[0])

            return None

        finally:
            cursor.close()

    def _check_fuel_stop(
        self, flight: Dict[str, Any], origin: str, dest: str
    ) -> bool:
        """Check if fuel stop is planned"""
        cursor = self.db.cursor()

        try:
            # Check if flight has multiple legs (indicating fuel stop)
            cursor.execute(
                """
                SELECT COUNT(*)
                FROM flight_legs
                WHERE flight_id = %s
                """,
                (flight["flight_id"],)
            )

            leg_count = cursor.fetchone()[0]

            return leg_count > 2  # Origin + Fuel Stop + Destination

        finally:
            cursor.close()

    def _parse_time(self, time_value: Any) -> time:
        """Parse time string or object to time"""
        if isinstance(time_value, time):
            return time_value

        if isinstance(time_value, str):
            parts = time_value.split(':')
            return time(int(parts[0]), int(parts[1]), int(parts[2]) if len(parts) > 2 else 0)

        return time_value
