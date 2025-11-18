"""
Crew Feasibility Validator
Validates crew availability, qualifications, and regulatory compliance
"""

from typing import List, Dict, Any
from datetime import datetime, timedelta, time
import logging

logger = logging.getLogger(__name__)


class CrewValidator:
    """
    Validates crew feasibility for flight operations

    Checks per FAA/EASA regulations:
    - Crew availability and assignments
    - Aircraft type ratings and qualifications
    - Flight duty period (FDP) limits
    - Rest requirements between duty periods
    - Monthly flight hour limits (100 hours)
    - Yearly flight hour limits (1000 hours)
    - Crew base proximity to flight origin
    - Minimum crew complement by aircraft type
    """

    # FAA/EASA Flight Duty Period limits (hours)
    MAX_FLIGHT_DUTY_PERIOD = {
        "1_sector": 13,
        "2_sectors": 13,
        "3_sectors": 12.5,
        "4_sectors": 12,
        "5_sectors": 11.5,
        "6_sectors": 11,
        "7+_sectors": 10
    }

    # Minimum rest periods (hours)
    MIN_REST_PERIOD = 12  # Local night rest
    MIN_REST_REDUCED = 10  # Reduced rest (limited occasions)

    # Flight hour limits
    MAX_MONTHLY_HOURS = 100
    MAX_YEARLY_HOURS = 1000
    MAX_CONSECUTIVE_DUTY_DAYS = 6

    # Minimum crew requirements by aircraft category
    MIN_CREW_REQUIREMENTS = {
        "narrow_body": {"pilots": 2, "cabin_crew": 3},
        "wide_body": {"pilots": 2, "cabin_crew": 6},
        "regional": {"pilots": 2, "cabin_crew": 2}
    }

    # Aircraft categories
    AIRCRAFT_CATEGORIES = {
        "narrow_body": ["319", "320", "321", "733", "737", "738", "739"],
        "wide_body": ["330", "333", "359", "763", "764", "772", "773", "787", "788", "789"],
        "regional": ["E90", "E95", "CR7", "CR9", "DH4"]
    }

    def __init__(self, db_connection):
        self.db = db_connection

    def validate(self, flights: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Validate crew feasibility for all flights

        Args:
            flights: List of flight dictionaries

        Returns:
            List of validation issues
        """
        issues = []

        for flight in flights:
            # Check minimum crew complement
            complement_issues = self._validate_crew_complement(flight)
            issues.extend(complement_issues)

            # Check crew qualifications
            qualification_issues = self._validate_crew_qualifications(flight)
            issues.extend(qualification_issues)

            # Check crew duty time limits
            duty_issues = self._validate_duty_limits(flight)
            issues.extend(duty_issues)

            # Check crew rest requirements
            rest_issues = self._validate_rest_requirements(flight)
            issues.extend(rest_issues)

            # Check monthly/yearly hour limits
            hour_issues = self._validate_hour_limits(flight)
            issues.extend(hour_issues)

            # Check crew base proximity
            base_issues = self._validate_crew_base(flight)
            issues.extend(base_issues)

        logger.info(f"Crew validation: {len(issues)} issues found")
        return issues

    def _validate_crew_complement(
        self, flight: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Validate minimum crew requirements are met"""
        issues = []

        cursor = self.db.cursor()

        try:
            # Get assigned crew count
            cursor.execute(
                """
                SELECT crew_role, COUNT(*)
                FROM crew_assignments
                WHERE flight_id = %s
                GROUP BY crew_role
                """,
                (flight["flight_id"],)
            )

            crew_counts = dict(cursor.fetchall())

            # Determine aircraft category
            category = self._get_aircraft_category(flight["aircraft_type"])
            min_req = self.MIN_CREW_REQUIREMENTS.get(
                category, self.MIN_CREW_REQUIREMENTS["narrow_body"]
            )

            # Check pilots
            pilot_count = crew_counts.get("pilot", 0) + crew_counts.get("captain", 0) + crew_counts.get("first_officer", 0)

            if pilot_count < min_req["pilots"]:
                issues.append({
                    "severity": "critical",
                    "category": "crew_validation",
                    "flight_id": flight["flight_id"],
                    "flight_number": flight["flight_number"],
                    "issue_type": "insufficient_pilots",
                    "assigned_count": pilot_count,
                    "required_count": min_req["pilots"],
                    "aircraft_type": flight["aircraft_type"],
                    "description": f"Only {pilot_count} pilot(s) assigned, need {min_req['pilots']} for {category} aircraft",
                    "recommended_action": "Assign additional qualified pilots",
                    "impact": "Flight cannot operate without minimum pilot complement"
                })

            # Check cabin crew
            cabin_count = crew_counts.get("cabin_crew", 0) + crew_counts.get("flight_attendant", 0)

            if cabin_count < min_req["cabin_crew"]:
                issues.append({
                    "severity": "critical",
                    "category": "crew_validation",
                    "flight_id": flight["flight_id"],
                    "flight_number": flight["flight_number"],
                    "issue_type": "insufficient_cabin_crew",
                    "assigned_count": cabin_count,
                    "required_count": min_req["cabin_crew"],
                    "aircraft_type": flight["aircraft_type"],
                    "description": f"Only {cabin_count} cabin crew assigned, need {min_req['cabin_crew']} for {category} aircraft",
                    "recommended_action": "Assign additional cabin crew",
                    "impact": "Violates safety regulations for passenger evacuation"
                })

        finally:
            cursor.close()

        return issues

    def _validate_crew_qualifications(
        self, flight: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Validate crew has required aircraft type ratings"""
        issues = []

        cursor = self.db.cursor()

        try:
            # Get assigned crew
            cursor.execute(
                """
                SELECT ca.crew_member_id, ca.crew_role, c.name,
                       c.aircraft_type_ratings, c.certifications
                FROM crew_assignments ca
                JOIN crew_availability c ON ca.crew_member_id = c.crew_member_id
                WHERE ca.flight_id = %s
                """,
                (flight["flight_id"],)
            )

            crew_members = cursor.fetchall()

            for crew_id, role, name, ratings, certs in crew_members:
                # Check if crew has rating for this aircraft type
                if role in ("pilot", "captain", "first_officer"):
                    if flight["aircraft_type"] not in (ratings or []):
                        issues.append({
                            "severity": "critical",
                            "category": "crew_validation",
                            "flight_id": flight["flight_id"],
                            "flight_number": flight["flight_number"],
                            "issue_type": "missing_type_rating",
                            "crew_member_id": crew_id,
                            "crew_name": name,
                            "crew_role": role,
                            "required_rating": flight["aircraft_type"],
                            "current_ratings": ratings or [],
                            "description": f"{role.capitalize()} {name} lacks type rating for {flight['aircraft_type']}",
                            "recommended_action": "Assign crew with proper type rating or provide type rating training",
                            "impact": "Crew cannot legally operate aircraft without type rating"
                        })

                # Check certificate validity (pilots must have current medical)
                if role in ("pilot", "captain", "first_officer"):
                    if not certs or "medical_current" not in certs:
                        issues.append({
                            "severity": "critical",
                            "category": "crew_validation",
                            "flight_id": flight["flight_id"],
                            "flight_number": flight["flight_number"],
                            "issue_type": "invalid_medical_certificate",
                            "crew_member_id": crew_id,
                            "crew_name": name,
                            "crew_role": role,
                            "description": f"{role.capitalize()} {name} does not have current medical certificate",
                            "recommended_action": "Assign crew with valid medical or renew medical certificate",
                            "impact": "Pilot cannot operate without valid medical certificate"
                        })

        finally:
            cursor.close()

        return issues

    def _validate_duty_limits(
        self, flight: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Validate flight duty period limits"""
        issues = []

        cursor = self.db.cursor()

        try:
            # Get assigned crew
            cursor.execute(
                """
                SELECT crew_member_id, crew_role
                FROM crew_assignments
                WHERE flight_id = %s
                  AND crew_role IN ('pilot', 'captain', 'first_officer')
                """,
                (flight["flight_id"],)
            )

            crew_members = cursor.fetchall()

            for crew_id, role in crew_members:
                # Calculate duty period including this flight
                cursor.execute(
                    """
                    SELECT f.departure_time, f.arrival_time, f.flight_id
                    FROM crew_assignments ca
                    JOIN flights f ON ca.flight_id = f.flight_id
                    WHERE ca.crew_member_id = %s
                      AND f.effective_from = %s
                    ORDER BY f.departure_time
                    """,
                    (crew_id, flight["effective_from"])
                )

                duty_flights = cursor.fetchall()

                if duty_flights:
                    # Calculate duty period duration
                    first_dep = self._parse_time(duty_flights[0][0])
                    last_arr = self._parse_time(duty_flights[-1][1])

                    # Add 30 min pre-flight and 15 min post-flight
                    duty_start = self._add_minutes_to_time(first_dep, -30)
                    duty_end = self._add_minutes_to_time(last_arr, 15)

                    duty_hours = self._calculate_time_diff_hours(duty_start, duty_end)

                    # Determine max FDP based on sectors
                    sectors = len(duty_flights)
                    if sectors == 1:
                        max_fdp = self.MAX_FLIGHT_DUTY_PERIOD["1_sector"]
                    elif sectors == 2:
                        max_fdp = self.MAX_FLIGHT_DUTY_PERIOD["2_sectors"]
                    elif sectors == 3:
                        max_fdp = self.MAX_FLIGHT_DUTY_PERIOD["3_sectors"]
                    elif sectors == 4:
                        max_fdp = self.MAX_FLIGHT_DUTY_PERIOD["4_sectors"]
                    elif sectors == 5:
                        max_fdp = self.MAX_FLIGHT_DUTY_PERIOD["5_sectors"]
                    elif sectors == 6:
                        max_fdp = self.MAX_FLIGHT_DUTY_PERIOD["6_sectors"]
                    else:
                        max_fdp = self.MAX_FLIGHT_DUTY_PERIOD["7+_sectors"]

                    if duty_hours > max_fdp:
                        issues.append({
                            "severity": "critical",
                            "category": "crew_validation",
                            "flight_id": flight["flight_id"],
                            "flight_number": flight["flight_number"],
                            "issue_type": "fdp_exceeded",
                            "crew_member_id": crew_id,
                            "crew_role": role,
                            "duty_hours": round(duty_hours, 1),
                            "max_fdp_hours": max_fdp,
                            "sectors": sectors,
                            "description": f"Flight duty period {round(duty_hours, 1)}hrs exceeds {max_fdp}hrs limit for {sectors} sectors",
                            "recommended_action": "Reduce duty period or assign fresh crew",
                            "impact": "Violates FAA/EASA flight duty regulations"
                        })

        finally:
            cursor.close()

        return issues

    def _validate_rest_requirements(
        self, flight: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Validate crew has adequate rest between duty periods"""
        issues = []

        cursor = self.db.cursor()

        try:
            # Get assigned crew
            cursor.execute(
                """
                SELECT crew_member_id, crew_role
                FROM crew_assignments
                WHERE flight_id = %s
                  AND crew_role IN ('pilot', 'captain', 'first_officer', 'cabin_crew')
                """,
                (flight["flight_id"],)
            )

            crew_members = cursor.fetchall()

            for crew_id, role in crew_members:
                # Find previous duty period
                cursor.execute(
                    """
                    SELECT MAX(f.arrival_time)
                    FROM crew_assignments ca
                    JOIN flights f ON ca.flight_id = f.flight_id
                    WHERE ca.crew_member_id = %s
                      AND f.effective_from < %s
                    """,
                    (crew_id, flight["effective_from"])
                )

                prev_arrival = cursor.fetchone()[0]

                if prev_arrival:
                    # Calculate rest period
                    prev_end = self._add_minutes_to_time(
                        self._parse_time(prev_arrival), 15
                    )
                    current_start = self._add_minutes_to_time(
                        self._parse_time(flight["departure_time"]), -30
                    )

                    rest_hours = self._calculate_time_diff_hours(prev_end, current_start)

                    if rest_hours < self.MIN_REST_PERIOD:
                        severity = "critical" if rest_hours < self.MIN_REST_REDUCED else "high"

                        issues.append({
                            "severity": severity,
                            "category": "crew_validation",
                            "flight_id": flight["flight_id"],
                            "flight_number": flight["flight_number"],
                            "issue_type": "insufficient_rest",
                            "crew_member_id": crew_id,
                            "crew_role": role,
                            "rest_hours": round(rest_hours, 1),
                            "minimum_required": self.MIN_REST_PERIOD,
                            "description": f"Crew has only {round(rest_hours, 1)}hrs rest, minimum {self.MIN_REST_PERIOD}hrs required",
                            "recommended_action": "Assign fresh crew or adjust schedule",
                            "impact": "Violates rest requirements, creates fatigue risk"
                        })

        finally:
            cursor.close()

        return issues

    def _validate_hour_limits(
        self, flight: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Validate monthly and yearly flight hour limits"""
        issues = []

        cursor = self.db.cursor()

        try:
            # Get assigned pilots
            cursor.execute(
                """
                SELECT crew_member_id, crew_role
                FROM crew_assignments
                WHERE flight_id = %s
                  AND crew_role IN ('pilot', 'captain', 'first_officer')
                """,
                (flight["flight_id"],)
            )

            crew_members = cursor.fetchall()

            for crew_id, role in crew_members:
                # Calculate monthly hours
                cursor.execute(
                    """
                    SELECT SUM(c.monthly_hours_flown) as monthly_total
                    FROM crew_availability c
                    WHERE c.crew_member_id = %s
                    """,
                    (crew_id,)
                )

                monthly_hours = cursor.fetchone()[0] or 0

                if monthly_hours >= self.MAX_MONTHLY_HOURS:
                    issues.append({
                        "severity": "critical",
                        "category": "crew_validation",
                        "flight_id": flight["flight_id"],
                        "flight_number": flight["flight_number"],
                        "issue_type": "monthly_hours_exceeded",
                        "crew_member_id": crew_id,
                        "crew_role": role,
                        "monthly_hours": round(monthly_hours, 1),
                        "maximum_allowed": self.MAX_MONTHLY_HOURS,
                        "description": f"Crew has {round(monthly_hours, 1)} hours this month, exceeds {self.MAX_MONTHLY_HOURS}hr limit",
                        "recommended_action": "Assign different crew member",
                        "impact": "Violates FAA/EASA monthly flight hour limits"
                    })

                # Calculate yearly hours
                cursor.execute(
                    """
                    SELECT SUM(c.yearly_hours_flown) as yearly_total
                    FROM crew_availability c
                    WHERE c.crew_member_id = %s
                    """,
                    (crew_id,)
                )

                yearly_hours = cursor.fetchone()[0] or 0

                if yearly_hours >= self.MAX_YEARLY_HOURS:
                    issues.append({
                        "severity": "high",
                        "category": "crew_validation",
                        "flight_id": flight["flight_id"],
                        "flight_number": flight["flight_number"],
                        "issue_type": "yearly_hours_exceeded",
                        "crew_member_id": crew_id,
                        "crew_role": role,
                        "yearly_hours": round(yearly_hours, 1),
                        "maximum_allowed": self.MAX_YEARLY_HOURS,
                        "description": f"Crew has {round(yearly_hours, 1)} hours this year, exceeds {self.MAX_YEARLY_HOURS}hr limit",
                        "recommended_action": "Assign different crew member",
                        "impact": "Violates FAA/EASA yearly flight hour limits"
                    })

        finally:
            cursor.close()

        return issues

    def _validate_crew_base(
        self, flight: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Validate crew base is near flight origin"""
        issues = []

        cursor = self.db.cursor()

        try:
            # Get assigned crew
            cursor.execute(
                """
                SELECT ca.crew_member_id, ca.crew_role, c.name, c.base_airport
                FROM crew_assignments ca
                JOIN crew_availability c ON ca.crew_member_id = c.crew_member_id
                WHERE ca.flight_id = %s
                """,
                (flight["flight_id"],)
            )

            crew_members = cursor.fetchall()

            for crew_id, role, name, base_airport in crew_members:
                if base_airport != flight["origin_airport"]:
                    # Check if deadhead/positioning flight exists
                    cursor.execute(
                        """
                        SELECT flight_id
                        FROM flights
                        WHERE origin_airport = %s
                          AND destination_airport = %s
                          AND arrival_time < %s
                          AND effective_from = %s
                        """,
                        (base_airport, flight["origin_airport"],
                         flight["departure_time"], flight["effective_from"])
                    )

                    positioning = cursor.fetchone()

                    if not positioning:
                        issues.append({
                            "severity": "medium",
                            "category": "crew_validation",
                            "flight_id": flight["flight_id"],
                            "flight_number": flight["flight_number"],
                            "issue_type": "crew_base_mismatch",
                            "crew_member_id": crew_id,
                            "crew_name": name,
                            "crew_role": role,
                            "crew_base": base_airport,
                            "flight_origin": flight["origin_airport"],
                            "description": f"Crew based at {base_airport} but flight departs from {flight['origin_airport']}",
                            "recommended_action": "Add positioning flight or assign crew based at origin",
                            "impact": "Additional cost for deadhead transportation"
                        })

        finally:
            cursor.close()

        return issues

    def _get_aircraft_category(self, aircraft_type: str) -> str:
        """Determine aircraft category from type code"""
        for category, types in self.AIRCRAFT_CATEGORIES.items():
            if aircraft_type in types:
                return category
        return "narrow_body"

    def _parse_time(self, time_value: Any) -> time:
        """Parse time string or object to time"""
        if isinstance(time_value, time):
            return time_value

        if isinstance(time_value, str):
            parts = time_value.split(':')
            return time(int(parts[0]), int(parts[1]), int(parts[2]) if len(parts) > 2 else 0)

        return time_value

    def _add_minutes_to_time(self, time_obj: time, minutes: int) -> time:
        """Add minutes to time object"""
        dt = datetime.combine(datetime.today(), time_obj)
        dt += timedelta(minutes=minutes)
        return dt.time()

    def _calculate_time_diff_hours(self, time1: time, time2: time) -> float:
        """Calculate hour difference between two times"""
        dt1 = datetime.combine(datetime.today(), time1)
        dt2 = datetime.combine(datetime.today(), time2)

        # Handle overnight
        if dt2 < dt1:
            dt2 += timedelta(days=1)

        return (dt2 - dt1).total_seconds() / 3600
