"""
SSM Message Parser
Regex-based parser for IATA Standard Schedule Messages (SSM)
"""

import re
from datetime import datetime
from typing import Dict, Any, List, Optional


class SSMParser:
    """
    Parser for IATA SSM (Standard Schedule Message) format

    Supported message types:
    - NEW: New flight schedule
    - TIM: Time change
    - EQT: Equipment change
    - CNL: Cancellation
    - CON: Continuation/restore
    - SKD: Schedule dump request
    - RPL: Replace
    """

    # SSM Format regex patterns
    PATTERNS = {
        # NEW CM 0100 J PTY MIA 1234567 1DEC24 31MAR25 738 0715 0945 0230 E0 M JP
        "NEW": re.compile(
            r"^NEW\s+"
            r"(?P<airline>[A-Z0-9]{2,3})\s+"
            r"(?P<flight_number>\d{1,4}[A-Z]?)\s+"
            r"(?P<service_type>[JFCH])\s+"
            r"(?P<origin>[A-Z]{3})\s+"
            r"(?P<destination>[A-Z]{3})\s+"
            r"(?P<operating_days>[1-7X]{7})\s+"
            r"(?P<effective_from>\d{1,2}[A-Z]{3}\d{2})\s+"
            r"(?P<effective_to>\d{1,2}[A-Z]{3}\d{2})\s+"
            r"(?P<aircraft_type>[A-Z0-9]{3})\s+"
            r"(?P<departure_time>\d{4})\s+"
            r"(?P<arrival_time>\d{4})"
            r"(?:\s+(?P<block_time>\d{4}))?"
            r"(?:\s+(?P<day_change>[E+-]\d))?"
            r"(?:\s+(?P<meal_service>[BMSLRNVKODFC]))?"
            r"(?:\s+(?P<secure_flight>[A-Z]{2}))?"
            r".*$",
            re.IGNORECASE
        ),

        # TIM CM 0100 J PTY MIA 1234567 1DEC24 31MAR25 0725 0955
        "TIM": re.compile(
            r"^TIM\s+"
            r"(?P<airline>[A-Z0-9]{2,3})\s+"
            r"(?P<flight_number>\d{1,4}[A-Z]?)\s+"
            r"(?P<service_type>[JFCH])?\s*"
            r"(?P<origin>[A-Z]{3})\s+"
            r"(?P<destination>[A-Z]{3})\s+"
            r"(?P<operating_days>[1-7X]{7})\s+"
            r"(?P<effective_from>\d{1,2}[A-Z]{3}\d{2})\s+"
            r"(?P<effective_to>\d{1,2}[A-Z]{3}\d{2})\s+"
            r"(?P<departure_time>\d{4})\s+"
            r"(?P<arrival_time>\d{4})"
            r".*$",
            re.IGNORECASE
        ),

        # EQT CM 0100 PTY MIA 1234567 1DEC24 31MAR25 73J
        "EQT": re.compile(
            r"^EQT\s+"
            r"(?P<airline>[A-Z0-9]{2,3})\s+"
            r"(?P<flight_number>\d{1,4}[A-Z]?)\s+"
            r"(?P<origin>[A-Z]{3})\s+"
            r"(?P<destination>[A-Z]{3})\s+"
            r"(?P<operating_days>[1-7X]{7})\s+"
            r"(?P<effective_from>\d{1,2}[A-Z]{3}\d{2})\s+"
            r"(?P<effective_to>\d{1,2}[A-Z]{3}\d{2})\s+"
            r"(?P<aircraft_type>[A-Z0-9]{3})"
            r".*$",
            re.IGNORECASE
        ),

        # CNL CM 0100 PTY MIA 1234567 15JAN25 20JAN25
        "CNL": re.compile(
            r"^CNL\s+"
            r"(?P<airline>[A-Z0-9]{2,3})\s+"
            r"(?P<flight_number>\d{1,4}[A-Z]?)\s+"
            r"(?P<origin>[A-Z]{3})\s+"
            r"(?P<destination>[A-Z]{3})\s+"
            r"(?P<operating_days>[1-7X]{7})\s+"
            r"(?P<effective_from>\d{1,2}[A-Z]{3}\d{2})\s+"
            r"(?P<effective_to>\d{1,2}[A-Z]{3}\d{2})"
            r".*$",
            re.IGNORECASE
        ),

        # CON CM 0100 PTY MIA 1234567 22JAN25 25JAN25
        "CON": re.compile(
            r"^CON\s+"
            r"(?P<airline>[A-Z0-9]{2,3})\s+"
            r"(?P<flight_number>\d{1,4}[A-Z]?)\s+"
            r"(?P<origin>[A-Z]{3})\s+"
            r"(?P<destination>[A-Z]{3})\s+"
            r"(?P<operating_days>[1-7X]{7})\s+"
            r"(?P<effective_from>\d{1,2}[A-Z]{3}\d{2})\s+"
            r"(?P<effective_to>\d{1,2}[A-Z]{3}\d{2})"
            r".*$",
            re.IGNORECASE
        ),

        # SKD CM PTY 1DEC24 31MAR25
        "SKD": re.compile(
            r"^SKD\s+"
            r"(?P<airline>[A-Z0-9]{2,3})\s+"
            r"(?P<airport>[A-Z]{3})\s+"
            r"(?P<effective_from>\d{1,2}[A-Z]{3}\d{2})\s+"
            r"(?P<effective_to>\d{1,2}[A-Z]{3}\d{2})"
            r".*$",
            re.IGNORECASE
        ),

        # RPL CM 0100 J PTY MIA 1234567 1DEC24 31MAR25 738 0715 0945
        "RPL": re.compile(
            r"^RPL\s+"
            r"(?P<airline>[A-Z0-9]{2,3})\s+"
            r"(?P<flight_number>\d{1,4}[A-Z]?)\s+"
            r"(?P<service_type>[JFCH])\s+"
            r"(?P<origin>[A-Z]{3})\s+"
            r"(?P<destination>[A-Z]{3})\s+"
            r"(?P<operating_days>[1-7X]{7})\s+"
            r"(?P<effective_from>\d{1,2}[A-Z]{3}\d{2})\s+"
            r"(?P<effective_to>\d{1,2}[A-Z]{3}\d{2})\s+"
            r"(?P<aircraft_type>[A-Z0-9]{3})\s+"
            r"(?P<departure_time>\d{4})\s+"
            r"(?P<arrival_time>\d{4})"
            r".*$",
            re.IGNORECASE
        )
    }

    def parse(self, message: str, message_type: str) -> Dict[str, Any]:
        """
        Parse SSM message

        Args:
            message: Raw SSM message text
            message_type: Message type (NEW, TIM, EQT, etc.)

        Returns:
            Parsed data dictionary

        Raises:
            ValueError: If message format is invalid
        """
        if message_type not in self.PATTERNS:
            raise ValueError(f"Unsupported message type: {message_type}")

        # Get pattern for message type
        pattern = self.PATTERNS[message_type]

        # Match pattern
        match = pattern.match(message.strip())

        if not match:
            raise ValueError(
                f"Message does not match {message_type} format: {message[:100]}"
            )

        # Extract matched groups
        data = match.groupdict()

        # Post-process fields
        data = self._post_process(data, message_type)

        return data

    def _post_process(self, data: Dict[str, Any], message_type: str) -> Dict[str, Any]:
        """
        Post-process parsed data

        - Convert dates to datetime objects
        - Parse operating days pattern
        - Parse times
        - Calculate day offsets
        """
        # Parse dates
        if "effective_from" in data and data["effective_from"]:
            data["effective_from_date"] = self._parse_ssm_date(data["effective_from"])

        if "effective_to" in data and data["effective_to"]:
            data["effective_to_date"] = self._parse_ssm_date(data["effective_to"])

        # Parse operating days
        if "operating_days" in data and data["operating_days"]:
            data["operating_days_array"] = self._parse_operating_days(
                data["operating_days"]
            )

        # Parse times
        if "departure_time" in data and data["departure_time"]:
            data["departure_hour"] = int(data["departure_time"][:2])
            data["departure_minute"] = int(data["departure_time"][2:])

        if "arrival_time" in data and data["arrival_time"]:
            data["arrival_hour"] = int(data["arrival_time"][:2])
            data["arrival_minute"] = int(data["arrival_time"][2:])

        # Calculate day offset
        if "departure_time" in data and "arrival_time" in data:
            data["arrival_day_offset"] = self._calculate_day_offset(
                data.get("departure_time"),
                data.get("arrival_time"),
                data.get("day_change")
            )

        # Add confidence score (regex-based parsing is highly confident)
        data["confidence"] = 1.0

        return data

    def _parse_ssm_date(self, date_str: str) -> datetime:
        """
        Parse SSM date format (DDMMMYY)

        Examples:
        - 1DEC24 → December 1, 2024
        - 31MAR25 → March 31, 2025
        """
        # Format: DDMMMYY (e.g., 1DEC24, 31MAR25)
        try:
            return datetime.strptime(date_str.upper(), "%d%b%y")
        except ValueError:
            raise ValueError(f"Invalid SSM date format: {date_str}")

    def _parse_operating_days(self, pattern: str) -> List[int]:
        """
        Parse operating days pattern

        Input: '1234567' (daily), '123456X' (weekdays), 'X2X4X6X' (Tue/Thu/Sat)
        Output: [1,2,3,4,5,6,7] or [1,2,3,4,5,6] or [2,4,6]

        Where: 1=Monday, 2=Tuesday, ..., 7=Sunday, X=Not operating
        """
        if len(pattern) != 7:
            raise ValueError(f"Invalid operating days pattern: {pattern}")

        operating_days = []
        for i, char in enumerate(pattern, start=1):
            if char == str(i):
                operating_days.append(i)
            elif char.upper() != 'X':
                raise ValueError(f"Invalid character in operating days: {char}")

        return operating_days

    def _calculate_day_offset(
        self,
        departure: str,
        arrival: str,
        day_change: Optional[str] = None
    ) -> int:
        """
        Calculate arrival day offset

        If arrival time < departure time, flight arrives next day (+1)
        Can be explicitly specified in day_change field (E0, E+1, E+2)
        """
        if day_change:
            # Parse explicit day change (E0, E+1, E+2, E-1)
            if day_change.startswith('E'):
                offset_str = day_change[1:]
                if offset_str in ['0', '+0']:
                    return 0
                elif offset_str.startswith('+'):
                    return int(offset_str[1:])
                elif offset_str.startswith('-'):
                    return -int(offset_str[1:])
            return 0

        # Auto-calculate based on times
        dep_minutes = int(departure[:2]) * 60 + int(departure[2:])
        arr_minutes = int(arrival[:2]) * 60 + int(arrival[2:])

        if arr_minutes < dep_minutes:
            return 1  # Arrives next day
        else:
            return 0  # Same day

    def parse_multi_line(self, message: str) -> List[Dict[str, Any]]:
        """
        Parse multi-line SSM message

        Some SSM messages span multiple lines for multi-leg flights
        or additional information
        """
        lines = message.strip().split('\n')
        results = []

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # Detect message type from line
            first_word = line.split()[0].upper()
            if first_word in self.PATTERNS:
                try:
                    parsed = self.parse(line, first_word)
                    results.append(parsed)
                except ValueError as e:
                    # Skip invalid lines
                    results.append({"error": str(e), "raw_line": line})

        return results

    def extract_additional_fields(self, message: str) -> Dict[str, Any]:
        """
        Extract additional optional fields from SSM message

        Fields may include:
        - Meal service codes
        - Secure flight indicator
        - Codeshare information
        - Terminal information
        - Special service indicators
        """
        additional = {}

        # Meal service codes (B, M, S, L, etc.)
        meal_match = re.search(r'\s+([BMSLRNVKODFC])\s+', message)
        if meal_match:
            additional["meal_service"] = meal_match.group(1)

        # Secure flight (JP, etc.)
        secure_match = re.search(r'\s+([A-Z]{2})\s*$', message)
        if secure_match:
            additional["secure_flight"] = secure_match.group(1)

        return additional


# Service type codes
SERVICE_TYPES = {
    "J": "Passenger Jet",
    "F": "Cargo",
    "C": "Combi (Passenger/Cargo)",
    "H": "Charter"
}

# Meal service codes
MEAL_SERVICE_CODES = {
    "B": "Breakfast",
    "M": "Meal",
    "S": "Snack",
    "L": "Lunch",
    "D": "Dinner",
    "R": "Refreshment",
    "N": "No meal",
    "V": "Vegetarian meal available",
    "K": "Kosher meal available",
    "O": "Cold meal",
    "F": "Food for purchase"
}

# Day change indicators
DAY_CHANGE_CODES = {
    "E0": "Same day arrival",
    "E+1": "Arrival next day (+1)",
    "E+2": "Arrival two days later (+2)",
    "E-1": "Arrival previous day (-1)"
}
