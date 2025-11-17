"""
Record Transformer
Transforms parsed SSM/SSIM data into database schema format
"""

import uuid
from datetime import datetime, time
from typing import Dict, Any, List


class RecordTransformer:
    """Transform parsed messages to database records"""

    def transform(
        self,
        parsed_data: Dict[str, Any],
        message_type: str,
        message_id: str
    ) -> List[Dict[str, Any]]:
        """
        Transform parsed data to database records

        Args:
            parsed_data: Parsed message data
            message_type: Message type (NEW, TIM, etc.)
            message_id: SSM message ID

        Returns:
            List of database records
        """
        if message_type in ["NEW", "RPL"]:
            return self._transform_new_flight(parsed_data, message_id)
        elif message_type == "TIM":
            return self._transform_time_change(parsed_data, message_id)
        elif message_type == "EQT":
            return self._transform_equipment_change(parsed_data, message_id)
        elif message_type in ["CNL", "CON"]:
            return self._transform_cancellation(parsed_data, message_id, message_type)
        else:
            return []

    def _transform_new_flight(
        self,
        data: Dict[str, Any],
        message_id: str
    ) -> List[Dict[str, Any]]:
        """Transform NEW message to flight record"""
        flight_id = str(uuid.uuid4())

        # Main flight record
        flight_record = {
            "record_type": "flight",
            "flight_id": flight_id,
            "flight_number": f"{data['airline']}{data['flight_number']}",
            "carrier_code": data["airline"],
            "service_type": data.get("service_type", "J"),
            "origin_airport": data["origin"],
            "destination_airport": data["destination"],
            "departure_time": time(
                hour=data["departure_hour"],
                minute=data["departure_minute"]
            ).strftime("%H:%M:%S"),
            "arrival_time": time(
                hour=data["arrival_hour"],
                minute=data["arrival_minute"]
            ).strftime("%H:%M:%S"),
            "departure_day_offset": 0,
            "arrival_day_offset": data.get("arrival_day_offset", 0),
            "operating_days": data["operating_days"],
            "effective_from": data["effective_from_date"].date(),
            "effective_to": data["effective_to_date"].date(),
            "aircraft_type": data.get("aircraft_type"),
            "frequency_per_week": len(data.get("operating_days_array", [])),
            "meal_service": data.get("meal_service"),
            "secure_flight_required": data.get("secure_flight") is not None,
            "metadata": {
                "ssm_message_id": message_id,
                "parsed_confidence": data.get("confidence", 1.0)
            }
        }

        records = [flight_record]

        # Multi-leg flights (SSIM Type 4 continuation legs)
        if data.get("is_multi_leg") and data.get("continuation_legs"):
            for idx, leg in enumerate(data["continuation_legs"], start=2):
                leg_record = {
                    "record_type": "flight_leg",
                    "leg_id": str(uuid.uuid4()),
                    "flight_id": flight_id,
                    "leg_sequence": idx,
                    "departure_airport": leg["origin"],
                    "arrival_airport": leg["destination"],
                    "departure_time": time(
                        hour=leg["departure_hour"],
                        minute=leg["departure_minute"]
                    ).strftime("%H:%M:%S"),
                    "arrival_time": time(
                        hour=leg["arrival_hour"],
                        minute=leg["arrival_minute"]
                    ).strftime("%H:%M:%S"),
                    "departure_day_offset": 0,
                    "arrival_day_offset": leg.get("arrival_day_offset", 0),
                    "aircraft_type": leg.get("aircraft_type")
                }
                records.append(leg_record)

        return records

    def _transform_time_change(
        self,
        data: Dict[str, Any],
        message_id: str
    ) -> List[Dict[str, Any]]:
        """Transform TIM message to update record"""
        return [{
            "record_type": "flight_update",
            "update_type": "time_change",
            "carrier_code": data["airline"],
            "flight_number": f"{data['airline']}{data['flight_number']}",
            "origin_airport": data["origin"],
            "destination_airport": data["destination"],
            "effective_from": data["effective_from_date"].date(),
            "effective_to": data["effective_to_date"].date(),
            "operating_days": data["operating_days"],
            "new_departure_time": time(
                hour=data["departure_hour"],
                minute=data["departure_minute"]
            ).strftime("%H:%M:%S"),
            "new_arrival_time": time(
                hour=data["arrival_hour"],
                minute=data["arrival_minute"]
            ).strftime("%H:%M:%S"),
            "metadata": {"ssm_message_id": message_id}
        }]

    def _transform_equipment_change(
        self,
        data: Dict[str, Any],
        message_id: str
    ) -> List[Dict[str, Any]]:
        """Transform EQT message to update record"""
        return [{
            "record_type": "flight_update",
            "update_type": "equipment_change",
            "carrier_code": data["airline"],
            "flight_number": f"{data['airline']}{data['flight_number']}",
            "origin_airport": data["origin"],
            "destination_airport": data["destination"],
            "effective_from": data["effective_from_date"].date(),
            "effective_to": data["effective_to_date"].date(),
            "operating_days": data["operating_days"],
            "new_aircraft_type": data["aircraft_type"],
            "metadata": {"ssm_message_id": message_id}
        }]

    def _transform_cancellation(
        self,
        data: Dict[str, Any],
        message_id: str,
        message_type: str
    ) -> List[Dict[str, Any]]:
        """Transform CNL/CON message"""
        return [{
            "record_type": "flight_update",
            "update_type": "cancellation" if message_type == "CNL" else "reinstate",
            "carrier_code": data["airline"],
            "flight_number": f"{data['airline']}{data['flight_number']}",
            "origin_airport": data["origin"],
            "destination_airport": data["destination"],
            "effective_from": data["effective_from_date"].date(),
            "effective_to": data["effective_to_date"].date(),
            "operating_days": data["operating_days"],
            "metadata": {"ssm_message_id": message_id}
        }]
