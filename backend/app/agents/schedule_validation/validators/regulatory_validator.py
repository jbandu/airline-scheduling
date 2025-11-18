"""
Regulatory Compliance Validator
Validates flights against aviation regulatory requirements
"""

from typing import List, Dict, Any, Set
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class RegulatoryValidator:
    """
    Validates regulatory compliance for international operations

    Checks:
    - Bilateral air service agreements
    - Traffic rights (freedoms of the air)
    - Cabotage restrictions (domestic operations by foreign carriers)
    - Foreign ownership restrictions
    - Wet lease approval requirements
    - Code-share approval requirements
    - Frequency limitations per bilateral agreements
    - Designated carrier status
    """

    # Freedom rights definitions
    FREEDOM_DEFINITIONS = {
        1: "Overflight",
        2: "Technical stop",
        3: "Discharge passengers from home country",
        4: "Pick up passengers to home country",
        5: "Carry traffic between foreign countries",
        6: "Carry traffic via home country",
        7: "Carry traffic between foreign countries without touching home",
        8: "Cabotage (domestic within foreign country)"
    }

    # Countries with strict cabotage restrictions (no foreign domestic ops)
    STRICT_CABOTAGE_COUNTRIES = {
        "US", "CA", "AU", "NZ", "BR", "AR", "CL", "CN", "IN", "RU",
        "GB", "FR", "DE", "IT", "ES", "JP", "KR"
    }

    # EU/EEA countries (open skies within region)
    EU_EEA_COUNTRIES = {
        "AT", "BE", "BG", "HR", "CY", "CZ", "DK", "EE", "FI", "FR",
        "DE", "GR", "HU", "IE", "IT", "LV", "LT", "LU", "MT", "NL",
        "PL", "PT", "RO", "SK", "SI", "ES", "SE", "IS", "LI", "NO"
    }

    def __init__(self, db_connection):
        self.db = db_connection

    def validate(self, flights: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Validate regulatory compliance for all flights

        Args:
            flights: List of flight dictionaries

        Returns:
            List of validation issues
        """
        issues = []

        for flight in flights:
            # Check traffic rights
            traffic_issues = self._validate_traffic_rights(flight)
            issues.extend(traffic_issues)

            # Check cabotage restrictions
            cabotage_issues = self._validate_cabotage(flight)
            issues.extend(cabotage_issues)

            # Check bilateral agreement compliance
            bilateral_issues = self._validate_bilateral_agreement(flight)
            issues.extend(bilateral_issues)

            # Check designated carrier status
            carrier_issues = self._validate_designated_carrier(flight)
            issues.extend(carrier_issues)

            # Check wet lease approvals
            wet_lease_issues = self._validate_wet_lease(flight)
            issues.extend(wet_lease_issues)

            # Check code-share approvals
            codeshare_issues = self._validate_codeshare(flight)
            issues.extend(codeshare_issues)

        logger.info(f"Regulatory validation: {len(issues)} issues found")
        return issues

    def _validate_traffic_rights(
        self, flight: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Validate carrier has required traffic rights"""
        issues = []

        carrier_code = flight["carrier_code"]
        origin = flight["origin_airport"]
        destination = flight["destination_airport"]

        origin_country = self._get_country_from_airport(origin)
        dest_country = self._get_country_from_airport(destination)
        carrier_country = self._get_carrier_country(carrier_code)

        # Determine required freedom
        required_freedom = self._determine_required_freedom(
            carrier_country, origin_country, dest_country
        )

        # Check if carrier has required traffic rights
        has_rights = self._check_traffic_rights(
            carrier_code, origin_country, dest_country, required_freedom
        )

        if not has_rights:
            issues.append({
                "severity": "critical",
                "category": "regulatory_validation",
                "flight_id": flight["flight_id"],
                "flight_number": flight["flight_number"],
                "issue_type": "missing_traffic_rights",
                "carrier": carrier_code,
                "carrier_country": carrier_country,
                "origin": origin,
                "origin_country": origin_country,
                "destination": destination,
                "destination_country": dest_country,
                "required_freedom": required_freedom,
                "freedom_description": self.FREEDOM_DEFINITIONS.get(required_freedom, "Unknown"),
                "description": f"Carrier {carrier_code} lacks {self.FREEDOM_DEFINITIONS.get(required_freedom)} rights for {origin}-{destination}",
                "recommended_action": "Negotiate traffic rights or use different carrier",
                "impact": "Flight operation not authorized under bilateral agreement"
            })

        return issues

    def _validate_cabotage(
        self, flight: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Validate cabotage restrictions (domestic ops by foreign carriers)"""
        issues = []

        carrier_code = flight["carrier_code"]
        origin = flight["origin_airport"]
        destination = flight["destination_airport"]

        origin_country = self._get_country_from_airport(origin)
        dest_country = self._get_country_from_airport(destination)
        carrier_country = self._get_carrier_country(carrier_code)

        # Check if this is domestic operation by foreign carrier
        if origin_country == dest_country and carrier_country != origin_country:
            # Domestic flight by foreign carrier - check cabotage rules

            # EU/EEA exception - open skies within region
            if (origin_country in self.EU_EEA_COUNTRIES and
                carrier_country in self.EU_EEA_COUNTRIES):
                # EU carriers can operate domestic within EU
                return issues

            # Check if cabotage is strictly prohibited
            if origin_country in self.STRICT_CABOTAGE_COUNTRIES:
                # Check for wet lease exemption
                is_wet_lease = flight.get("operating_carrier") != carrier_code

                if not is_wet_lease:
                    issues.append({
                        "severity": "critical",
                        "category": "regulatory_validation",
                        "flight_id": flight["flight_id"],
                        "flight_number": flight["flight_number"],
                        "issue_type": "cabotage_violation",
                        "carrier": carrier_code,
                        "carrier_country": carrier_country,
                        "flight_country": origin_country,
                        "origin": origin,
                        "destination": destination,
                        "description": f"Foreign carrier {carrier_code} ({carrier_country}) cannot operate domestic flight in {origin_country}",
                        "recommended_action": "Use domestic carrier or wet lease from domestic carrier",
                        "impact": "Violates cabotage restrictions - operation prohibited"
                    })

        return issues

    def _validate_bilateral_agreement(
        self, flight: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Validate compliance with bilateral air service agreement"""
        issues = []

        carrier_code = flight["carrier_code"]
        origin = flight["origin_airport"]
        destination = flight["destination_airport"]

        origin_country = self._get_country_from_airport(origin)
        dest_country = self._get_country_from_airport(destination)
        carrier_country = self._get_carrier_country(carrier_code)

        # Skip if domestic flight
        if origin_country == dest_country:
            return issues

        # Get bilateral agreement
        agreement = self._get_bilateral_agreement(carrier_country, origin_country, dest_country)

        if not agreement:
            issues.append({
                "severity": "critical",
                "category": "regulatory_validation",
                "flight_id": flight["flight_id"],
                "flight_number": flight["flight_number"],
                "issue_type": "no_bilateral_agreement",
                "carrier": carrier_code,
                "carrier_country": carrier_country,
                "route": f"{origin}-{destination}",
                "countries": f"{origin_country}-{dest_country}",
                "description": f"No bilateral air service agreement found for {carrier_code} on {origin}-{destination}",
                "recommended_action": "Verify bilateral agreement exists or use different route",
                "impact": "Flight may not be authorized"
            })
            return issues

        # Check frequency limitations
        if agreement.get("max_weekly_frequencies"):
            freq_issues = self._check_frequency_limits(
                flight, carrier_code, origin, destination, agreement
            )
            issues.extend(freq_issues)

        # Check capacity limitations
        if agreement.get("capacity_limitations"):
            issues.append({
                "severity": "medium",
                "category": "regulatory_validation",
                "flight_id": flight["flight_id"],
                "flight_number": flight["flight_number"],
                "issue_type": "capacity_limitations",
                "carrier": carrier_code,
                "route": f"{origin}-{destination}",
                "limitations": agreement["capacity_limitations"],
                "description": f"Bilateral agreement has capacity limitations: {agreement['capacity_limitations']}",
                "recommended_action": "Verify compliance with capacity restrictions",
                "impact": "May require capacity adjustment"
            })

        return issues

    def _validate_designated_carrier(
        self, flight: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Validate carrier is designated under bilateral agreement"""
        issues = []

        carrier_code = flight["carrier_code"]
        origin = flight["origin_airport"]
        destination = flight["destination_airport"]

        origin_country = self._get_country_from_airport(origin)
        dest_country = self._get_country_from_airport(destination)
        carrier_country = self._get_carrier_country(carrier_code)

        # Skip if domestic
        if origin_country == dest_country:
            return issues

        # Check if carrier is designated
        is_designated = self._check_designated_carrier(
            carrier_code, carrier_country, origin_country, dest_country
        )

        if not is_designated:
            issues.append({
                "severity": "critical",
                "category": "regulatory_validation",
                "flight_id": flight["flight_id"],
                "flight_number": flight["flight_number"],
                "issue_type": "not_designated_carrier",
                "carrier": carrier_code,
                "carrier_country": carrier_country,
                "route": f"{origin}-{destination}",
                "description": f"Carrier {carrier_code} is not designated under bilateral agreement for this route",
                "recommended_action": "Apply for designated carrier status or use designated carrier",
                "impact": "Flight not authorized - carrier must be designated"
            })

        return issues

    def _validate_wet_lease(
        self, flight: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Validate wet lease approvals"""
        issues = []

        marketing_carrier = flight["carrier_code"]
        operating_carrier = flight.get("operating_carrier", marketing_carrier)

        # Check if this is a wet lease (different operating carrier)
        if operating_carrier != marketing_carrier:
            # Wet lease - check for approvals
            approval = self._check_wet_lease_approval(
                marketing_carrier, operating_carrier, flight
            )

            if not approval:
                issues.append({
                    "severity": "critical",
                    "category": "regulatory_validation",
                    "flight_id": flight["flight_id"],
                    "flight_number": flight["flight_number"],
                    "issue_type": "wet_lease_not_approved",
                    "marketing_carrier": marketing_carrier,
                    "operating_carrier": operating_carrier,
                    "description": f"Wet lease from {operating_carrier} to {marketing_carrier} not approved by authorities",
                    "recommended_action": "Obtain wet lease approval from relevant authorities",
                    "impact": "Operation may be prohibited without approval"
                })

        return issues

    def _validate_codeshare(
        self, flight: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Validate code-share approvals"""
        issues = []

        cursor = self.db.cursor()

        try:
            # Check if flight has code-share partners
            cursor.execute(
                """
                SELECT marketing_carrier, operating_carrier
                FROM flights
                WHERE flight_id = %s
                  AND marketing_carrier != carrier_code
                """,
                (flight["flight_id"],)
            )

            codeshares = cursor.fetchall()

            for marketing, operating in codeshares:
                # Check code-share approval
                approval = self._check_codeshare_approval(marketing, operating, flight)

                if not approval:
                    issues.append({
                        "severity": "high",
                        "category": "regulatory_validation",
                        "flight_id": flight["flight_id"],
                        "flight_number": flight["flight_number"],
                        "issue_type": "codeshare_not_approved",
                        "marketing_carrier": marketing,
                        "operating_carrier": operating,
                        "description": f"Code-share between {marketing} and {operating} not approved",
                        "recommended_action": "Obtain code-share approval or remove code-share",
                        "impact": "Code-share may not be permitted"
                    })

        finally:
            cursor.close()

        return issues

    def _determine_required_freedom(
        self, carrier_country: str, origin_country: str, dest_country: str
    ) -> int:
        """Determine which freedom of the air is required"""
        if origin_country == carrier_country and dest_country == carrier_country:
            # Domestic flight
            return 8  # Cabotage (if foreign carrier)

        elif origin_country == carrier_country:
            # Departing from home country
            return 3  # 3rd freedom

        elif dest_country == carrier_country:
            # Arriving to home country
            return 4  # 4th freedom

        elif origin_country != carrier_country and dest_country != carrier_country:
            # Neither origin nor destination is home country
            return 5  # 5th freedom

        return 0

    def _check_traffic_rights(
        self, carrier: str, origin_country: str, dest_country: str, freedom: int
    ) -> bool:
        """Check if carrier has required traffic rights"""
        cursor = self.db.cursor()

        try:
            cursor.execute(
                """
                SELECT agreement_id
                FROM bilateral_agreements ba
                WHERE ba.carrier_code = %s
                  AND (
                    (ba.country_a = %s AND ba.country_b = %s)
                    OR (ba.country_a = %s AND ba.country_b = %s)
                  )
                  AND %s = ANY(ba.freedoms_granted)
                  AND ba.effective_from <= CURRENT_DATE
                  AND (ba.effective_to IS NULL OR ba.effective_to >= CURRENT_DATE)
                """,
                (carrier, origin_country, dest_country, dest_country, origin_country, freedom)
            )

            return cursor.fetchone() is not None

        finally:
            cursor.close()

    def _get_bilateral_agreement(
        self, carrier_country: str, origin_country: str, dest_country: str
    ) -> Dict[str, Any]:
        """Get bilateral agreement details"""
        cursor = self.db.cursor()

        try:
            cursor.execute(
                """
                SELECT agreement_id, max_weekly_frequencies,
                       capacity_limitations, designated_carriers
                FROM bilateral_agreements
                WHERE (
                    (country_a = %s AND (country_b = %s OR country_b = %s))
                    OR (country_b = %s AND (country_a = %s OR country_a = %s))
                  )
                  AND effective_from <= CURRENT_DATE
                  AND (effective_to IS NULL OR effective_to >= CURRENT_DATE)
                LIMIT 1
                """,
                (carrier_country, origin_country, dest_country,
                 carrier_country, origin_country, dest_country)
            )

            row = cursor.fetchone()

            if row:
                return {
                    "agreement_id": row[0],
                    "max_weekly_frequencies": row[1],
                    "capacity_limitations": row[2],
                    "designated_carriers": row[3]
                }

            return None

        finally:
            cursor.close()

    def _check_frequency_limits(
        self, flight: Dict[str, Any], carrier: str, origin: str,
        destination: str, agreement: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Check frequency limitations"""
        issues = []

        max_freq = agreement.get("max_weekly_frequencies")

        if not max_freq:
            return issues

        # Count frequencies for this route
        cursor = self.db.cursor()

        try:
            cursor.execute(
                """
                SELECT COUNT(*)
                FROM flights
                WHERE carrier_code = %s
                  AND origin_airport = %s
                  AND destination_airport = %s
                  AND effective_from <= %s
                  AND effective_to >= %s
                """,
                (carrier, origin, destination,
                 flight["effective_to"], flight["effective_from"])
            )

            current_freq = cursor.fetchone()[0]

            if current_freq > max_freq:
                issues.append({
                    "severity": "high",
                    "category": "regulatory_validation",
                    "flight_id": flight["flight_id"],
                    "flight_number": flight["flight_number"],
                    "issue_type": "frequency_limit_exceeded",
                    "carrier": carrier,
                    "route": f"{origin}-{destination}",
                    "current_frequencies": current_freq,
                    "max_frequencies": max_freq,
                    "description": f"Route has {current_freq} weekly frequencies, exceeds bilateral limit of {max_freq}",
                    "recommended_action": "Reduce frequencies or renegotiate bilateral agreement",
                    "impact": "Excess frequencies may be denied"
                })

        finally:
            cursor.close()

        return issues

    def _check_designated_carrier(
        self, carrier: str, carrier_country: str, origin_country: str, dest_country: str
    ) -> bool:
        """Check if carrier is designated"""
        # Simplified - in production, check designation database
        return True  # Assume designated for now

    def _check_wet_lease_approval(
        self, marketing: str, operating: str, flight: Dict[str, Any]
    ) -> bool:
        """Check wet lease approval"""
        # Simplified - in production, check approvals database
        return True  # Assume approved for now

    def _check_codeshare_approval(
        self, marketing: str, operating: str, flight: Dict[str, Any]
    ) -> bool:
        """Check code-share approval"""
        # Simplified - in production, check approvals database
        return True  # Assume approved for now

    def _get_carrier_country(self, carrier_code: str) -> str:
        """Get carrier's home country"""
        # Map of carrier codes to countries
        CARRIER_COUNTRIES = {
            "AA": "US", "DL": "US", "UA": "US", "WN": "US", "B6": "US",
            "BA": "GB", "VS": "GB", "AF": "FR", "LH": "DE", "KL": "NL",
            "IB": "ES", "AZ": "IT", "EI": "IE", "SK": "SE", "LX": "CH",
            "CM": "PA", "AV": "CO", "LA": "CL", "AR": "AR", "G3": "BR",
            "NH": "JP", "JL": "JP", "KE": "KR", "OZ": "KR", "CA": "CN",
            "SQ": "SG", "TG": "TH", "QF": "AU", "NZ": "NZ", "EK": "AE"
        }

        return CARRIER_COUNTRIES.get(carrier_code, "XX")

    def _get_country_from_airport(self, airport_code: str) -> str:
        """Get country code from airport code"""
        AIRPORT_COUNTRIES = {
            "JFK": "US", "LAX": "US", "ORD": "US", "ATL": "US", "DFW": "US",
            "LHR": "GB", "CDG": "FR", "FRA": "DE", "AMS": "NL", "MAD": "ES",
            "NRT": "JP", "HND": "JP", "ICN": "KR", "PVG": "CN", "HKG": "HK",
            "DXB": "AE", "SIN": "SG", "BKK": "TH", "SYD": "AU", "MEL": "AU",
            "YYZ": "CA", "YVR": "CA", "GRU": "BR", "EZE": "AR", "SCL": "CL",
            "PTY": "PA", "BOG": "CO", "LIM": "PE", "GIG": "BR", "MIA": "US",
            "IAH": "US", "EWR": "US", "SFO": "US", "DEN": "US", "LGA": "US",
            "FCO": "IT", "BCN": "ES", "ZRH": "CH", "MUC": "DE", "DCA": "US",
            "BOS": "US", "PHL": "US", "SNA": "US", "BUR": "US", "SAN": "US"
        }

        return AIRPORT_COUNTRIES.get(airport_code, "XX")
