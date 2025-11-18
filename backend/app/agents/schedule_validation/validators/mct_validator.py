"""
Minimum Connect Time (MCT) Validator
Validates passenger connection times between flights
"""

from typing import List, Dict, Any, Tuple
from datetime import datetime, timedelta, time
import logging

logger = logging.getLogger(__name__)


class MCTValidator:
    """
    Validates Minimum Connect Times per IATA standards

    Checks:
    - Connection time meets minimum for airport/terminal combination
    - Domestic vs international connections
    - Terminal changes and inter-terminal transfer time
    - Same airline vs interline connections
    - Baggage re-check requirements
    - Immigration/customs processing time
    """

    # Default MCT values (minutes) if not in database
    DEFAULT_MCT = {
        "domestic_domestic": 45,
        "domestic_international": 75,
        "international_domestic": 90,
        "international_international": 60,
        "same_terminal": 0,      # Adjustment
        "terminal_change": 20,    # Additional time
        "interline": 15,         # Additional time for interline
        "baggage_recheck": 30    # Additional time for baggage re-check
    }

    # Hub airports with complex terminal layouts
    HUB_AIRPORTS = {
        "JFK", "LHR", "CDG", "FRA", "AMS", "ORD", "LAX", "DFW",
        "ATL", "DEN", "IAH", "SFO", "MIA", "EWR", "LGA"
    }

    # Schengen countries (no immigration between them)
    SCHENGEN_COUNTRIES = {
        "AT", "BE", "CZ", "DK", "EE", "FI", "FR", "DE", "GR", "HU",
        "IS", "IT", "LV", "LI", "LT", "LU", "MT", "NL", "NO", "PL",
        "PT", "SK", "SI", "ES", "SE", "CH"
    }

    def __init__(self, db_connection):
        self.db = db_connection

    def validate(self, flights: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Validate MCT for all connecting flight pairs

        Args:
            flights: List of flight dictionaries

        Returns:
            List of validation issues
        """
        issues = []

        # Build connection map
        connections = self._find_connections(flights)

        for (inbound_flight, outbound_flight) in connections:
            # Validate connection time
            mct_issues = self._validate_connection_time(
                inbound_flight, outbound_flight
            )
            issues.extend(mct_issues)

        logger.info(f"MCT validation: {len(issues)} issues found across {len(connections)} connections")
        return issues

    def _find_connections(
        self, flights: List[Dict[str, Any]]
    ) -> List[Tuple[Dict[str, Any], Dict[str, Any]]]:
        """Find all valid connecting flight pairs"""
        connections = []

        # Group flights by airport and date
        flights_by_airport = {}

        for flight in flights:
            dest = flight["destination_airport"]
            date = flight.get("effective_from")

            key = (dest, date)

            if key not in flights_by_airport:
                flights_by_airport[key] = []

            flights_by_airport[key].append(flight)

        # Find connections
        for flight in flights:
            origin = flight["origin_airport"]
            date = flight.get("effective_from")

            # Look for outbound flights from this flight's destination
            dest_key = (flight["destination_airport"], date)

            if dest_key in flights_by_airport:
                for outbound in flights_by_airport[dest_key]:
                    # Check if timing allows connection
                    if self._is_potential_connection(flight, outbound):
                        connections.append((flight, outbound))

        return connections

    def _is_potential_connection(
        self, inbound: Dict[str, Any], outbound: Dict[str, Any]
    ) -> bool:
        """Check if flights can be a connection"""
        # Must arrive before departure
        arr_time = self._parse_time(inbound["arrival_time"])
        dep_time = self._parse_time(outbound["departure_time"])

        # Calculate connection time (handle overnight)
        arr_dt = datetime.combine(datetime.today(), arr_time)
        dep_dt = datetime.combine(datetime.today(), dep_time)

        if dep_dt < arr_dt:
            dep_dt += timedelta(days=1)

        connection_minutes = (dep_dt - arr_dt).total_seconds() / 60

        # Must be between 30 min and 6 hours to be a valid connection
        return 30 <= connection_minutes <= 360

    def _validate_connection_time(
        self,
        inbound: Dict[str, Any],
        outbound: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Validate connection meets MCT requirements"""
        issues = []

        connection_airport = inbound["destination_airport"]

        # Calculate actual connection time
        arr_time = self._parse_time(inbound["arrival_time"])
        dep_time = self._parse_time(outbound["departure_time"])

        arr_dt = datetime.combine(datetime.today(), arr_time)
        dep_dt = datetime.combine(datetime.today(), dep_time)

        if dep_dt < arr_dt:
            dep_dt += timedelta(days=1)

        actual_connection_minutes = (dep_dt - arr_dt).total_seconds() / 60

        # Get MCT from database or calculate
        required_mct = self._get_required_mct(
            connection_airport,
            inbound,
            outbound
        )

        # Check if connection time is sufficient
        if actual_connection_minutes < required_mct:
            issues.append({
                "severity": "high",
                "category": "mct_validation",
                "flight_id": outbound["flight_id"],
                "flight_number": outbound["flight_number"],
                "issue_type": "insufficient_connection_time",
                "connection_airport": connection_airport,
                "inbound_flight": inbound["flight_number"],
                "inbound_arrival": str(arr_time),
                "outbound_flight": outbound["flight_number"],
                "outbound_departure": str(dep_time),
                "actual_connection_minutes": round(actual_connection_minutes),
                "required_mct_minutes": required_mct,
                "shortfall_minutes": round(required_mct - actual_connection_minutes),
                "description": f"Connection time {round(actual_connection_minutes)}min is less than MCT {required_mct}min at {connection_airport}",
                "recommended_action": "Adjust departure time or mark as non-bookable connection",
                "impact": "Passengers may miss connection, baggage may not transfer"
            })

        # Check if connection is too tight (within 5 min of MCT)
        elif actual_connection_minutes < required_mct + 5:
            issues.append({
                "severity": "medium",
                "category": "mct_validation",
                "flight_id": outbound["flight_id"],
                "flight_number": outbound["flight_number"],
                "issue_type": "tight_connection",
                "connection_airport": connection_airport,
                "inbound_flight": inbound["flight_number"],
                "outbound_flight": outbound["flight_number"],
                "actual_connection_minutes": round(actual_connection_minutes),
                "required_mct_minutes": required_mct,
                "buffer_minutes": round(actual_connection_minutes - required_mct),
                "description": f"Connection time {round(actual_connection_minutes)}min has only {round(actual_connection_minutes - required_mct)}min buffer over MCT",
                "recommended_action": "Consider adding buffer time or restricting sales",
                "impact": "High risk of misconnection if inbound flight delayed"
            })

        return issues

    def _get_required_mct(
        self,
        airport: str,
        inbound: Dict[str, Any],
        outbound: Dict[str, Any]
    ) -> int:
        """Calculate required MCT for connection"""
        # Try to get from database first
        db_mct = self._get_mct_from_database(airport, inbound, outbound)

        if db_mct:
            return db_mct

        # Calculate based on IATA standards
        mct = 0

        # Base MCT by connection type
        inbound_intl = self._is_international_flight(inbound)
        outbound_intl = self._is_international_flight(outbound)

        if not inbound_intl and not outbound_intl:
            # Domestic to domestic
            mct = self.DEFAULT_MCT["domestic_domestic"]
        elif not inbound_intl and outbound_intl:
            # Domestic to international
            mct = self.DEFAULT_MCT["domestic_international"]
        elif inbound_intl and not outbound_intl:
            # International to domestic
            mct = self.DEFAULT_MCT["international_domestic"]
        else:
            # International to international
            mct = self.DEFAULT_MCT["international_international"]

            # Check if Schengen to Schengen (no immigration)
            if self._is_schengen_connection(inbound, outbound):
                mct = self.DEFAULT_MCT["domestic_domestic"]  # Treat as domestic

        # Add terminal change time if needed
        if self._requires_terminal_change(airport, inbound, outbound):
            mct += self.DEFAULT_MCT["terminal_change"]

        # Add interline buffer if different airlines
        if inbound["carrier_code"] != outbound["carrier_code"]:
            mct += self.DEFAULT_MCT["interline"]

        # Add baggage re-check time if required
        if self._requires_baggage_recheck(inbound, outbound):
            mct += self.DEFAULT_MCT["baggage_recheck"]

        # Add extra time for hub airports
        if airport in self.HUB_AIRPORTS:
            mct += 10

        return mct

    def _get_mct_from_database(
        self,
        airport: str,
        inbound: Dict[str, Any],
        outbound: Dict[str, Any]
    ) -> int:
        """Get MCT from database if available"""
        cursor = self.db.cursor()

        try:
            cursor.execute(
                """
                SELECT mct_minutes
                FROM minimum_connect_times
                WHERE airport_code = %s
                  AND (
                    (arrival_airline = %s AND departure_airline = %s)
                    OR (arrival_airline = %s AND departure_airline IS NULL)
                    OR (arrival_airline IS NULL AND departure_airline = %s)
                    OR (arrival_airline IS NULL AND departure_airline IS NULL)
                  )
                ORDER BY
                  CASE
                    WHEN arrival_airline = %s AND departure_airline = %s THEN 1
                    WHEN arrival_airline = %s THEN 2
                    WHEN departure_airline = %s THEN 3
                    ELSE 4
                  END
                LIMIT 1
                """,
                (
                    airport,
                    inbound["carrier_code"], outbound["carrier_code"],
                    inbound["carrier_code"],
                    outbound["carrier_code"],
                    inbound["carrier_code"], outbound["carrier_code"],
                    inbound["carrier_code"],
                    outbound["carrier_code"]
                )
            )

            result = cursor.fetchone()

            if result:
                return result[0]

            return None

        finally:
            cursor.close()

    def _is_international_flight(self, flight: Dict[str, Any]) -> bool:
        """Determine if flight is international"""
        # Get country codes from airport codes (first 2 chars typically indicate country)
        # This is simplified - in production, use airport master data

        origin_country = self._get_country_from_airport(flight["origin_airport"])
        dest_country = self._get_country_from_airport(flight["destination_airport"])

        return origin_country != dest_country

    def _is_schengen_connection(
        self, inbound: Dict[str, Any], outbound: Dict[str, Any]
    ) -> bool:
        """Check if connection is within Schengen area"""
        inbound_country = self._get_country_from_airport(inbound["destination_airport"])
        outbound_country = self._get_country_from_airport(outbound["destination_airport"])

        return (
            inbound_country in self.SCHENGEN_COUNTRIES and
            outbound_country in self.SCHENGEN_COUNTRIES
        )

    def _requires_terminal_change(
        self, airport: str, inbound: Dict[str, Any], outbound: Dict[str, Any]
    ) -> bool:
        """Check if connection requires terminal change"""
        # Query database for terminal assignments
        cursor = self.db.cursor()

        try:
            cursor.execute(
                """
                SELECT terminal
                FROM flight_legs
                WHERE flight_id = %s
                  AND airport_code = %s
                  AND leg_type = 'arrival'
                """,
                (inbound["flight_id"], airport)
            )

            inbound_terminal = cursor.fetchone()

            cursor.execute(
                """
                SELECT terminal
                FROM flight_legs
                WHERE flight_id = %s
                  AND airport_code = %s
                  AND leg_type = 'departure'
                """,
                (outbound["flight_id"], airport)
            )

            outbound_terminal = cursor.fetchone()

            if inbound_terminal and outbound_terminal:
                return inbound_terminal[0] != outbound_terminal[0]

            # Default: assume terminal change for different airlines at hub airports
            if airport in self.HUB_AIRPORTS:
                if inbound["carrier_code"] != outbound["carrier_code"]:
                    return True

            return False

        finally:
            cursor.close()

    def _requires_baggage_recheck(
        self, inbound: Dict[str, Any], outbound: Dict[str, Any]
    ) -> bool:
        """Check if baggage re-check is required"""
        # Different airlines (interline) often require baggage re-check
        if inbound["carrier_code"] != outbound["carrier_code"]:
            # Check if codeshare or alliance partner
            # Simplified: assume re-check needed
            return True

        # US domestic to international usually requires re-check
        inbound_intl = self._is_international_flight(inbound)
        outbound_intl = self._is_international_flight(outbound)

        if not inbound_intl and outbound_intl:
            # Domestic to international - check if US
            if self._get_country_from_airport(inbound["origin_airport"]) == "US":
                return True

        return False

    def _get_country_from_airport(self, airport_code: str) -> str:
        """Get country code from airport code"""
        # This is simplified - in production, use airport master data
        # Map of airport codes to country codes
        AIRPORT_COUNTRIES = {
            "JFK": "US", "LAX": "US", "ORD": "US", "ATL": "US", "DFW": "US",
            "LHR": "GB", "CDG": "FR", "FRA": "DE", "AMS": "NL", "MAD": "ES",
            "NRT": "JP", "HND": "JP", "ICN": "KR", "PVG": "CN", "HKG": "HK",
            "DXB": "AE", "SIN": "SG", "BKK": "TH", "SYD": "AU", "MEL": "AU",
            "YYZ": "CA", "YVR": "CA", "GRU": "BR", "EZE": "AR", "SCL": "CL",
            "PTY": "PA", "BOG": "CO", "LIM": "PE", "GIG": "BR", "MIA": "US",
            "IAH": "US", "EWR": "US", "SFO": "US", "DEN": "US", "LGA": "US"
        }

        return AIRPORT_COUNTRIES.get(airport_code, "XX")

    def _parse_time(self, time_value: Any) -> time:
        """Parse time string or object to time"""
        if isinstance(time_value, time):
            return time_value

        if isinstance(time_value, str):
            parts = time_value.split(':')
            return time(int(parts[0]), int(parts[1]), int(parts[2]) if len(parts) > 2 else 0)

        return time_value
