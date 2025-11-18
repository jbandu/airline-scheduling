"""
SSM Message Validator
Validates parsed SSM/SSIM messages against IATA standards
"""

import re
from datetime import datetime, date
from typing import Dict, Any, List


# IATA airport codes (sample - in production, query from database)
VALID_AIRPORTS = {
    "PTY", "MIA", "JFK", "LAX", "ATL", "ORD", "DFW", "DEN", "SFO", "SEA",
    "LAS", "PHX", "IAH", "MCO", "EWR", "MSP", "DTW", "BOS", "PHL", "LGA",
    "FLL", "BWI", "DCA", "SLC", "SAN", "TPA", "PDX", "STL", "HNL", "AUS",
    "LHR", "CDG", "FRA", "AMS", "MAD", "BCN", "FCO", "MXP", "ZRH", "VIE",
    "GRU", "EZE", "BOG", "LIM", "SCL", "MEX", "CUN", "GDL", "MTY"
}

# IATA airline codes (sample)
VALID_AIRLINES = {
    "CM", "AA", "DL", "UA", "WN", "B6", "AS", "NK", "F9", "G4",
    "BA", "AF", "LH", "KL", "IB", "AZ", "LX", "OS", "TP", "SK"
}

# IATA aircraft types (sample)
VALID_AIRCRAFT = {
    "738", "73J", "73H", "737", "73G", "73W", "7M8", "7M9",
    "320", "321", "319", "318", "32A", "32B", "32N", "32Q",
    "77W", "77L", "777", "788", "789", "781", "380", "359", "350"
}


class MessageValidator:
    """Validator for SSM/SSIM parsed messages"""

    def __init__(self, db_connection=None):
        """
        Initialize validator

        Args:
            db_connection: Optional database connection for reference data
        """
        self.db = db_connection

    def validate(
        self,
        parsed_data: Dict[str, Any],
        message_type: str
    ) -> Dict[str, Any]:
        """
        Validate parsed message data

        Args:
            parsed_data: Parsed message data
            message_type: Message type (NEW, TIM, etc.)

        Returns:
            Validation result with errors and warnings
        """
        errors = []
        warnings = []

        # Required field validation
        required_errors = self._validate_required_fields(parsed_data, message_type)
        errors.extend(required_errors)

        # Data format validation
        format_errors = self._validate_data_formats(parsed_data)
        errors.extend(format_errors)

        # Business logic validation
        logic_errors, logic_warnings = self._validate_business_logic(parsed_data)
        errors.extend(logic_errors)
        warnings.extend(logic_warnings)

        # Cross-field validation
        cross_errors = self._validate_cross_fields(parsed_data)
        errors.extend(cross_errors)

        return {
            "is_valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings
        }

    def _validate_required_fields(
        self,
        data: Dict[str, Any],
        message_type: str
    ) -> List[str]:
        """Validate required fields by message type"""
        errors = []

        # Common required fields
        common_required = ["airline", "flight_number"]

        # Type-specific required fields
        type_required = {
            "NEW": ["service_type", "origin", "destination", "operating_days",
                    "effective_from", "effective_to", "aircraft_type",
                    "departure_time", "arrival_time"],
            "TIM": ["origin", "destination", "operating_days",
                    "effective_from", "effective_to", "departure_time", "arrival_time"],
            "EQT": ["origin", "destination", "operating_days",
                    "effective_from", "effective_to", "aircraft_type"],
            "CNL": ["origin", "destination", "operating_days",
                    "effective_from", "effective_to"],
            "CON": ["origin", "destination", "operating_days",
                    "effective_from", "effective_to"],
            "SKD": ["airport", "effective_from", "effective_to"]
        }

        required_fields = common_required + type_required.get(message_type, [])

        for field in required_fields:
            if field not in data or data[field] is None or data[field] == "":
                errors.append(f"Missing required field: {field}")

        return errors

    def _validate_data_formats(self, data: Dict[str, Any]) -> List[str]:
        """Validate data formats (codes, patterns, etc.)"""
        errors = []

        # Validate airline code
        if "airline" in data and data["airline"]:
            if not re.match(r"^[A-Z0-9]{2,3}$", data["airline"]):
                errors.append(f"Invalid airline code format: {data['airline']}")
            # Check against known airlines (in production, query database)
            if data["airline"] not in VALID_AIRLINES:
                errors.append(f"Unknown airline code: {data['airline']}")

        # Validate airport codes
        for field in ["origin", "destination", "airport"]:
            if field in data and data[field]:
                if not re.match(r"^[A-Z]{3}$", data[field]):
                    errors.append(f"Invalid {field} code format: {data[field]}")
                if data[field] not in VALID_AIRPORTS:
                    errors.append(f"Unknown {field} code: {data[field]}")

        # Validate aircraft type
        if "aircraft_type" in data and data["aircraft_type"]:
            if not re.match(r"^[A-Z0-9]{3}$", data["aircraft_type"]):
                errors.append(f"Invalid aircraft type format: {data['aircraft_type']}")
            if data["aircraft_type"] not in VALID_AIRCRAFT:
                errors.append(f"Unknown aircraft type: {data['aircraft_type']}")

        # Validate flight number
        if "flight_number" in data and data["flight_number"]:
            if not re.match(r"^\d{1,4}[A-Z]?$", data["flight_number"]):
                errors.append(f"Invalid flight number format: {data['flight_number']}")

        # Validate operating days
        if "operating_days" in data and data["operating_days"]:
            if not re.match(r"^[1-7X]{7}$", data["operating_days"], re.IGNORECASE):
                errors.append(f"Invalid operating days pattern: {data['operating_days']}")

        # Validate service type
        if "service_type" in data and data["service_type"]:
            if data["service_type"] not in ["J", "F", "C", "H"]:
                errors.append(f"Invalid service type: {data['service_type']}")

        # Validate times (HHMM format)
        for time_field in ["departure_time", "arrival_time"]:
            if time_field in data and data[time_field]:
                if not re.match(r"^\d{4}$", data[time_field]):
                    errors.append(f"Invalid {time_field} format: {data[time_field]}")
                else:
                    hour = int(data[time_field][:2])
                    minute = int(data[time_field][2:])
                    if hour > 23 or minute > 59:
                        errors.append(f"Invalid {time_field}: {data[time_field]}")

        return errors

    def _validate_business_logic(
        self,
        data: Dict[str, Any]
    ) -> tuple[List[str], List[str]]:
        """Validate business logic rules"""
        errors = []
        warnings = []

        # Validate date range
        if "effective_from_date" in data and "effective_to_date" in data:
            if data["effective_from_date"] and data["effective_to_date"]:
                if data["effective_from_date"] > data["effective_to_date"]:
                    errors.append(
                        f"effective_from ({data['effective_from']}) must be before "
                        f"effective_to ({data['effective_to']})"
                    )

                # Check if dates are in the past
                today = datetime.now().date()
                if data["effective_to_date"].date() < today:
                    warnings.append("Schedule effective_to date is in the past")

                # Check if date range is reasonable (not too far in future)
                days_ahead = (data["effective_from_date"].date() - today).days
                if days_ahead > 365:
                    warnings.append("Schedule starts more than 1 year in the future")

        # Validate origin != destination
        if "origin" in data and "destination" in data:
            if data["origin"] == data["destination"]:
                errors.append("Origin and destination airports must be different")

        # Validate operating days (at least one day must be active)
        if "operating_days_array" in data:
            if not data["operating_days_array"]:
                errors.append("At least one operating day must be selected")

        return errors, warnings

    def _validate_cross_fields(self, data: Dict[str, Any]) -> List[str]:
        """Validate cross-field relationships"""
        errors = []

        # Validate departure vs arrival times
        if "departure_time" in data and "arrival_time" in data:
            if data["departure_time"] and data["arrival_time"]:
                dep_hour = data.get("departure_hour")
                dep_min = data.get("departure_minute")
                arr_hour = data.get("arrival_hour")
                arr_min = data.get("arrival_minute")

                if all(v is not None for v in [dep_hour, dep_min, arr_hour, arr_min]):
                    dep_minutes = dep_hour * 60 + dep_min
                    arr_minutes = arr_hour * 60 + arr_min

                    # If same day (day_offset = 0) and arrival < departure
                    day_offset = data.get("arrival_day_offset", 0)
                    if day_offset == 0 and arr_minutes <= dep_minutes:
                        errors.append(
                            "Arrival time must be after departure time for same-day flights"
                        )

        return errors

    def validate_batch(
        self,
        messages: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Validate multiple messages"""
        results = []

        for msg in messages:
            result = self.validate(
                msg.get("parsed_data", {}),
                msg.get("message_type", "")
            )
            results.append({
                "message_id": msg.get("message_id"),
                **result
            })

        return results
