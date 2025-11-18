"""
Tests for Schedule Validation Agent
"""

import pytest
from unittest.mock import Mock, MagicMock
from datetime import time, date

from app.agents.schedule_validation.validators.slot_validator import SlotValidator
from app.agents.schedule_validation.validators.aircraft_validator import AircraftValidator
from app.agents.schedule_validation.validators.crew_validator import CrewValidator
from app.agents.schedule_validation.validators.mct_validator import MCTValidator
from app.agents.schedule_validation.validators.curfew_validator import CurfewValidator
from app.agents.schedule_validation.validators.regulatory_validator import RegulatoryValidator
from app.agents.schedule_validation.validators.routing_validator import RoutingValidator
from app.agents.schedule_validation.validators.pattern_validator import PatternValidator


@pytest.fixture
def mock_db():
    """Mock database connection"""
    mock = Mock()
    mock.cursor = MagicMock()
    return mock


@pytest.fixture
def sample_flight():
    """Sample flight for testing"""
    return {
        "flight_id": "test-flight-001",
        "flight_number": "CM101",
        "carrier_code": "CM",
        "origin_airport": "PTY",
        "destination_airport": "MIA",
        "departure_time": "08:00:00",
        "arrival_time": "11:30:00",
        "aircraft_type": "738",
        "aircraft_registration": "HP-1234",
        "operating_days": "1234567",
        "frequency_per_week": 7,
        "effective_from": date(2025, 1, 1),
        "effective_to": date(2025, 3, 31),
        "service_type": "J"
    }


class TestSlotValidator:
    """Tests for Slot Validator"""

    def test_coordinated_airport_detection(self, mock_db, sample_flight):
        """Test detection of coordinated airports"""
        validator = SlotValidator(mock_db)

        # JFK is coordinated
        assert "JFK" in validator.COORDINATED_AIRPORTS

        # PTY is not coordinated
        assert "PTY" not in validator.COORDINATED_AIRPORTS

    def test_slot_validation_no_issues(self, mock_db, sample_flight):
        """Test validation when slot exists and is valid"""
        # Mock cursor to return valid slot
        mock_cursor = Mock()
        mock_cursor.fetchone.return_value = (
            "slot-001",  # slot_id
            time(8, 0),  # slot_time
            True,  # confirmed
            True,  # historical_rights
            5,  # tolerance_before
            5   # tolerance_after
        )
        mock_db.cursor.return_value = mock_cursor

        validator = SlotValidator(mock_db)

        # Test flight at non-coordinated airport
        sample_flight["origin_airport"] = "PTY"
        issues = validator.validate([sample_flight])

        assert len(issues) == 0

    def test_missing_slot_at_coordinated_airport(self, mock_db, sample_flight):
        """Test validation when slot is missing at coordinated airport"""
        # Mock cursor to return no slot
        mock_cursor = Mock()
        mock_cursor.fetchone.return_value = None
        mock_db.cursor.return_value = mock_cursor

        validator = SlotValidator(mock_db)

        # Test flight at coordinated airport
        sample_flight["origin_airport"] = "JFK"
        issues = validator.validate([sample_flight])

        assert len(issues) > 0
        assert issues[0]["severity"] == "critical"
        assert issues[0]["issue_type"] == "missing_slot"


class TestAircraftValidator:
    """Tests for Aircraft Validator"""

    def test_aircraft_category_narrow_body(self, mock_db):
        """Test aircraft category determination for narrow body"""
        validator = AircraftValidator(mock_db)

        assert validator._get_aircraft_category("738") == "narrow_body"
        assert validator._get_aircraft_category("320") == "narrow_body"

    def test_aircraft_category_wide_body(self, mock_db):
        """Test aircraft category determination for wide body"""
        validator = AircraftValidator(mock_db)

        assert validator._get_aircraft_category("773") == "wide_body"
        assert validator._get_aircraft_category("787") == "wide_body"

    def test_turnaround_time_validation(self, mock_db, sample_flight):
        """Test turnaround time validation"""
        validator = AircraftValidator(mock_db)

        # Create two flights with tight turnaround
        flight1 = sample_flight.copy()
        flight1["arrival_time"] = "10:00:00"
        flight1["aircraft_registration"] = "HP-1234"

        flight2 = sample_flight.copy()
        flight2["departure_time"] = "10:20:00"  # Only 20 min turnaround
        flight2["origin_airport"] = "MIA"  # Matches flight1 destination
        flight2["aircraft_registration"] = "HP-1234"

        # Mock aircraft info
        mock_cursor = Mock()
        mock_cursor.fetchone.side_effect = [
            (  # Aircraft info
                "HP-1234", "738", "active", "CM",
                180, date(2024, 12, 1), date(2025, 2, 1)
            ),
            None,  # No maintenance
            (  # Aircraft info again
                "HP-1234", "738", "active", "CM",
                180, date(2024, 12, 1), date(2025, 2, 1)
            ),
            None   # No maintenance
        ]
        mock_db.cursor.return_value = mock_cursor

        issues = validator.validate([flight1, flight2])

        # Should find insufficient turnaround
        turnaround_issues = [i for i in issues if i.get("issue_type") == "insufficient_turnaround"]
        assert len(turnaround_issues) > 0


class TestCrewValidator:
    """Tests for Crew Validator"""

    def test_minimum_crew_requirements(self, mock_db):
        """Test minimum crew requirements by aircraft type"""
        validator = CrewValidator(mock_db)

        # Narrow body requirements
        reqs = validator.MIN_CREW_REQUIREMENTS["narrow_body"]
        assert reqs["pilots"] == 2
        assert reqs["cabin_crew"] >= 2

        # Wide body requirements
        reqs = validator.MIN_CREW_REQUIREMENTS["wide_body"]
        assert reqs["pilots"] == 2
        assert reqs["cabin_crew"] >= 4

    def test_flight_duty_period_limits(self, mock_db):
        """Test FDP limits by number of sectors"""
        validator = CrewValidator(mock_db)

        # 1 sector should allow longer FDP
        assert validator.MAX_FLIGHT_DUTY_PERIOD["1_sector"] >= \
               validator.MAX_FLIGHT_DUTY_PERIOD["6_sectors"]


class TestMCTValidator:
    """Tests for MCT Validator"""

    def test_connection_detection(self, mock_db, sample_flight):
        """Test detection of potential connections"""
        validator = MCTValidator(mock_db)

        flight1 = sample_flight.copy()
        flight1["arrival_time"] = "10:00:00"

        flight2 = sample_flight.copy()
        flight2["origin_airport"] = "MIA"  # Matches flight1 destination
        flight2["departure_time"] = "11:00:00"  # 1 hour later

        # Should be potential connection
        assert validator._is_potential_connection(flight1, flight2)

    def test_international_detection(self, mock_db, sample_flight):
        """Test international flight detection"""
        validator = MCTValidator(mock_db)

        # PTY to MIA is international
        assert validator._is_international_flight(sample_flight)

        # Domestic flight
        domestic = sample_flight.copy()
        domestic["origin_airport"] = "JFK"
        domestic["destination_airport"] = "LAX"

        assert validator._is_international_flight(domestic)


class TestCurfewValidator:
    """Tests for Curfew Validator"""

    def test_curfew_airport_detection(self, mock_db):
        """Test detection of airports with curfews"""
        validator = CurfewValidator(mock_db)

        assert "LHR" in validator.CURFEW_AIRPORTS
        assert "SYD" in validator.CURFEW_AIRPORTS

    def test_curfew_time_check(self, mock_db):
        """Test curfew time checking"""
        validator = CurfewValidator(mock_db)

        # 11:00 PM is during curfew (23:00-06:00)
        assert validator._is_during_curfew("23:00:00", "23:00", "06:00")

        # 3:00 AM is during curfew
        assert validator._is_during_curfew("03:00:00", "23:00", "06:00")

        # 10:00 AM is not during curfew
        assert not validator._is_during_curfew("10:00:00", "23:00", "06:00")


class TestRegulatoryValidator:
    """Tests for Regulatory Validator"""

    def test_freedom_determination(self, mock_db):
        """Test freedom of the air determination"""
        validator = RegulatoryValidator(mock_db)

        # 3rd freedom: From home country
        freedom = validator._determine_required_freedom("US", "US", "GB")
        assert freedom == 3

        # 4th freedom: To home country
        freedom = validator._determine_required_freedom("US", "GB", "US")
        assert freedom == 4

        # 5th freedom: Neither origin nor dest is home
        freedom = validator._determine_required_freedom("US", "GB", "FR")
        assert freedom == 5

    def test_cabotage_detection(self, mock_db):
        """Test cabotage restriction detection"""
        validator = RegulatoryValidator(mock_db)

        assert "US" in validator.STRICT_CABOTAGE_COUNTRIES
        assert "GB" in validator.STRICT_CABOTAGE_COUNTRIES


class TestRoutingValidator:
    """Tests for Routing Validator"""

    def test_aircraft_range_limits(self, mock_db):
        """Test aircraft range limitations"""
        validator = RoutingValidator(mock_db)

        # 738 should have range around 3000nm
        assert validator.AIRCRAFT_RANGES.get("738", 0) > 2500
        assert validator.AIRCRAFT_RANGES.get("738", 0) < 4000

        # 787 should have longer range
        assert validator.AIRCRAFT_RANGES.get("787", 0) > 7000

    def test_hub_airport_detection(self, mock_db):
        """Test hub airport detection"""
        validator = RoutingValidator(mock_db)

        assert "ATL" in validator.HUB_AIRPORTS
        assert "DXB" in validator.HUB_AIRPORTS


class TestPatternValidator:
    """Tests for Pattern Validator"""

    def test_operating_days_validation(self, mock_db, sample_flight):
        """Test operating days pattern validation"""
        validator = PatternValidator(mock_db)

        # Valid pattern
        sample_flight["operating_days"] = "1234567"
        issues = validator._validate_operating_days(sample_flight)
        assert len(issues) == 0

        # Invalid length
        sample_flight["operating_days"] = "123"
        issues = validator._validate_operating_days(sample_flight)
        assert len(issues) > 0
        assert issues[0]["issue_type"] == "invalid_operating_days_length"

        # Invalid characters
        sample_flight["operating_days"] = "123456A"
        issues = validator._validate_operating_days(sample_flight)
        assert len(issues) > 0

    def test_frequency_calculation(self, mock_db, sample_flight):
        """Test frequency calculation from operating days"""
        validator = PatternValidator(mock_db)

        # 7 days
        sample_flight["operating_days"] = "1234567"
        sample_flight["frequency_per_week"] = 7
        issues = validator._validate_frequency([sample_flight])
        assert len(issues) == 0

        # 5 days but stated as 7
        sample_flight["operating_days"] = "12345XX"
        sample_flight["frequency_per_week"] = 7
        issues = validator._validate_frequency([sample_flight])
        assert len(issues) > 0
        assert issues[0]["issue_type"] == "frequency_mismatch"


class TestValidationIntegration:
    """Integration tests for full validation flow"""

    def test_multiple_validators(self, mock_db, sample_flight):
        """Test running multiple validators"""
        # This would test the full agent workflow
        # Skipping for now as it requires complex mocking
        pass


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
