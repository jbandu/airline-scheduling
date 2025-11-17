"""
Database Writer
Writes SSM parsed data to PostgreSQL database
"""

import json
import uuid
from typing import Dict, Any, List
from datetime import datetime


class DatabaseWriter:
    """Write SSM records to PostgreSQL"""

    def __init__(self, db_connection):
        """
        Initialize database writer

        Args:
            db_connection: PostgreSQL database connection
        """
        self.db = db_connection

    def save(
        self,
        records: List[Dict[str, Any]],
        raw_message: str,
        message_type: str,
        message_format: str,
        parsed_data: Dict[str, Any],
        validation_errors: List[str]
    ) -> Dict[str, Any]:
        """
        Save SSM message and related records to database

        Args:
            records: Transformed database records
            raw_message: Raw SSM message text
            message_type: Message type (NEW, TIM, etc.)
            message_format: Message format (SSM, SSIM)
            parsed_data: Parsed message data
            validation_errors: Validation errors

        Returns:
            Result with SSM record ID and affected flight IDs
        """
        cursor = self.db.cursor()
        ssm_record_id = str(uuid.uuid4())
        affected_flight_ids = []

        try:
            # Begin transaction
            cursor.execute("BEGIN")

            # 1. Insert SSM message record
            cursor.execute(
                """
                INSERT INTO ssm_messages (
                    message_id, message_type, message_format,
                    raw_message, parsed_data, sender_airline,
                    received_at, processing_status, validation_errors
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    ssm_record_id,
                    message_type,
                    message_format,
                    raw_message,
                    json.dumps(parsed_data),
                    parsed_data.get("airline"),
                    datetime.now(),
                    "completed" if not validation_errors else "failed",
                    json.dumps(validation_errors)
                )
            )

            # 2. Process records
            for record in records:
                if record["record_type"] == "flight":
                    flight_id = self._insert_flight(cursor, record)
                    affected_flight_ids.append(flight_id)

                elif record["record_type"] == "flight_leg":
                    self._insert_flight_leg(cursor, record)

                elif record["record_type"] == "flight_update":
                    flight_id = self._apply_flight_update(cursor, record)
                    if flight_id:
                        affected_flight_ids.append(flight_id)

            # 3. Update SSM message with affected flights
            cursor.execute(
                """
                UPDATE ssm_messages
                SET affected_flight_ids = %s
                WHERE message_id = %s
                """,
                (affected_flight_ids, ssm_record_id)
            )

            # Commit transaction
            cursor.execute("COMMIT")

            return {
                "ssm_record_id": ssm_record_id,
                "affected_flight_ids": affected_flight_ids
            }

        except Exception as e:
            # Rollback on error
            cursor.execute("ROLLBACK")
            raise

        finally:
            cursor.close()

    def _insert_flight(self, cursor, record: Dict[str, Any]) -> str:
        """Insert new flight record"""
        cursor.execute(
            """
            INSERT INTO flights (
                flight_id, schedule_id, flight_number, carrier_code,
                origin_airport, destination_airport,
                departure_time, arrival_time,
                departure_day_offset, arrival_day_offset,
                operating_days, effective_from, effective_to,
                aircraft_type, service_type, frequency_per_week,
                meal_service, secure_flight_required, metadata
            )
            VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s
            )
            RETURNING flight_id
            """,
            (
                record["flight_id"],
                None,  # schedule_id - to be assigned later
                record["flight_number"],
                record["carrier_code"],
                record["origin_airport"],
                record["destination_airport"],
                record["departure_time"],
                record["arrival_time"],
                record["departure_day_offset"],
                record["arrival_day_offset"],
                record["operating_days"],
                record["effective_from"],
                record["effective_to"],
                record["aircraft_type"],
                record["service_type"],
                record["frequency_per_week"],
                record.get("meal_service"),
                record.get("secure_flight_required", True),
                json.dumps(record.get("metadata", {}))
            )
        )

        return record["flight_id"]

    def _insert_flight_leg(self, cursor, record: Dict[str, Any]):
        """Insert flight leg record"""
        cursor.execute(
            """
            INSERT INTO flight_legs (
                leg_id, flight_id, leg_sequence,
                departure_airport, arrival_airport,
                departure_time, arrival_time,
                departure_day_offset, arrival_day_offset,
                aircraft_type
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                record["leg_id"],
                record["flight_id"],
                record["leg_sequence"],
                record["departure_airport"],
                record["arrival_airport"],
                record["departure_time"],
                record["arrival_time"],
                record["departure_day_offset"],
                record["arrival_day_offset"],
                record.get("aircraft_type")
            )
        )

    def _apply_flight_update(self, cursor, record: Dict[str, Any]) -> str:
        """Apply flight update (TIM, EQT, CNL)"""
        # Find matching flight
        cursor.execute(
            """
            SELECT flight_id FROM flights
            WHERE carrier_code = %s
              AND flight_number = %s
              AND origin_airport = %s
              AND destination_airport = %s
              AND operating_days = %s
              AND effective_from <= %s
              AND effective_to >= %s
            LIMIT 1
            """,
            (
                record["carrier_code"],
                record["flight_number"],
                record["origin_airport"],
                record["destination_airport"],
                record["operating_days"],
                record["effective_to"],
                record["effective_from"]
            )
        )

        result = cursor.fetchone()
        if not result:
            return None

        flight_id = result[0]

        # Apply update based on type
        if record["update_type"] == "time_change":
            cursor.execute(
                """
                UPDATE flights
                SET departure_time = %s,
                    arrival_time = %s,
                    updated_at = NOW()
                WHERE flight_id = %s
                """,
                (
                    record["new_departure_time"],
                    record["new_arrival_time"],
                    flight_id
                )
            )

        elif record["update_type"] == "equipment_change":
            cursor.execute(
                """
                UPDATE flights
                SET aircraft_type = %s,
                    updated_at = NOW()
                WHERE flight_id = %s
                """,
                (record["new_aircraft_type"], flight_id)
            )

        elif record["update_type"] == "cancellation":
            # Mark flight as cancelled (implementation varies)
            cursor.execute(
                """
                UPDATE flights
                SET metadata = jsonb_set(
                    COALESCE(metadata, '{}'::jsonb),
                    '{cancelled}',
                    'true'::jsonb
                ),
                updated_at = NOW()
                WHERE flight_id = %s
                """,
                (flight_id,)
            )

        return flight_id

    def check_duplicate(
        self,
        parsed_data: Dict[str, Any],
        message_type: str
    ) -> str:
        """
        Check for duplicate SSM messages

        Returns:
            'new', 'duplicate', or 'update'
        """
        # Simplified duplicate check
        # In production: check message hash, flight details, etc.
        return "new"
