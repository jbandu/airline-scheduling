"""
SSIM Message Parser
Parser for IATA Standard Schedules Information Manual (SSIM) format
"""

import re
from datetime import datetime
from typing import Dict, Any, List


class SSIMParser:
    """
    Parser for IATA SSIM (Standard Schedules Information Manual) format

    SSIM Type 3: Flight leg record
    SSIM Type 4: Segment data (continuation legs)

    Format: 3 CM 0100JPTYMIA1234567 01DEC2431MAR25738 0715 0945 0230 E0 M JP
    """

    # SSIM Type 3 pattern (main flight leg)
    TYPE_3_PATTERN = re.compile(
        r"^3\s+"
        r"(?P<airline>[A-Z0-9]{2,3})\s+"
        r"(?P<flight_number>\d{1,4}[A-Z]?)"
        r"(?P<service_type>[JFCH])"
        r"(?P<origin>[A-Z]{3})"
        r"(?P<destination>[A-Z]{3})"
        r"(?P<operating_days>[1-7X]{7})\s+"
        r"(?P<effective_from>\d{2}[A-Z]{3}\d{2})"
        r"(?P<effective_to>\d{2}[A-Z]{3}\d{2})"
        r"(?P<aircraft_type>[A-Z0-9]{3})\s+"
        r"(?P<departure_time>\d{4})\s+"
        r"(?P<arrival_time>\d{4})"
        r"(?:\s+(?P<block_time>\d{4}))?"
        r"(?:\s+(?P<day_change>[E+-]\d))?"
        r"(?:\s+(?P<meal_service>[BMSLRNVKODFC]))?"
        r"(?:\s+(?P<additional>[A-Z0-9 ]+))?"
        r".*$",
        re.IGNORECASE
    )

    # SSIM Type 4 pattern (continuation leg)
    TYPE_4_PATTERN = re.compile(
        r"^4\s+"
        r"(?P<airline>[A-Z0-9]{2,3})\s+"
        r"(?P<flight_number>\d{1,4}[A-Z]?)"
        r"(?P<origin>[A-Z]{3})"
        r"(?P<destination>[A-Z]{3})\s+"
        r"(?P<aircraft_type>[A-Z0-9]{3})\s+"
        r"(?P<departure_time>\d{4})\s+"
        r"(?P<arrival_time>\d{4})"
        r"(?:\s+(?P<block_time>\d{4}))?"
        r"(?:\s+(?P<day_change>[E+-]\d))?"
        r"(?:\s+(?P<meal_service>[BMSLRNVKODFC]))?"
        r".*$",
        re.IGNORECASE
    )

    def parse(self, message: str) -> Dict[str, Any]:
        """
        Parse SSIM message (Type 3 and Type 4 records)

        Args:
            message: Raw SSIM message text

        Returns:
            Parsed data dictionary with main leg and continuation legs
        """
        lines = message.strip().split('\n')

        # Parse Type 3 (main leg) - must be first
        main_leg = None
        continuation_legs = []

        for line in lines:
            line = line.strip()
            if not line:
                continue

            if line.startswith('3 '):
                if main_leg is not None:
                    raise ValueError("Multiple Type 3 records found")
                main_leg = self._parse_type_3(line)

            elif line.startswith('4 '):
                if main_leg is None:
                    raise ValueError("Type 4 record before Type 3")
                continuation_legs.append(self._parse_type_4(line))

        if main_leg is None:
            raise ValueError("No Type 3 record found")

        # Combine results
        result = {
            **main_leg,
            "is_multi_leg": len(continuation_legs) > 0,
            "continuation_legs": continuation_legs,
            "total_legs": 1 + len(continuation_legs)
        }

        return result

    def _parse_type_3(self, line: str) -> Dict[str, Any]:
        """Parse SSIM Type 3 record (main flight leg)"""
        match = self.TYPE_3_PATTERN.match(line)

        if not match:
            raise ValueError(f"Invalid SSIM Type 3 format: {line}")

        data = match.groupdict()

        # Post-process
        return self._post_process(data)

    def _parse_type_4(self, line: str) -> Dict[str, Any]:
        """Parse SSIM Type 4 record (continuation leg)"""
        match = self.TYPE_4_PATTERN.match(line)

        if not match:
            raise ValueError(f"Invalid SSIM Type 4 format: {line}")

        data = match.groupdict()

        # Post-process
        return self._post_process(data)

    def _post_process(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Post-process parsed data"""
        # Parse dates
        if "effective_from" in data and data["effective_from"]:
            data["effective_from_date"] = self._parse_ssim_date(data["effective_from"])

        if "effective_to" in data and data["effective_to"]:
            data["effective_to_date"] = self._parse_ssim_date(data["effective_to"])

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

        # Add confidence score
        data["confidence"] = 1.0

        return data

    def _parse_ssim_date(self, date_str: str) -> datetime:
        """Parse SSIM date format (DDMMMYY)"""
        try:
            return datetime.strptime(date_str.upper(), "%d%b%y")
        except ValueError:
            raise ValueError(f"Invalid SSIM date format: {date_str}")

    def _parse_operating_days(self, pattern: str) -> List[int]:
        """Parse operating days pattern"""
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
        day_change: str = None
    ) -> int:
        """Calculate arrival day offset"""
        if day_change:
            if day_change.startswith('E'):
                offset_str = day_change[1:]
                if offset_str in ['0', '+0']:
                    return 0
                elif offset_str.startswith('+'):
                    return int(offset_str[1:])
                elif offset_str.startswith('-'):
                    return -int(offset_str[1:])
            return 0

        # Auto-calculate
        dep_minutes = int(departure[:2]) * 60 + int(departure[2:])
        arr_minutes = int(arrival[:2]) * 60 + int(arrival[2:])

        return 1 if arr_minutes < dep_minutes else 0
