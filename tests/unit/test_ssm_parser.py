"""
Unit Tests for SSM Parser
Tests SSM message parsing logic
"""

import pytest
from datetime import datetime
from backend.app.agents.ssm_parser.parsers.ssm_parser import SSMParser


class TestSSMParser:
    """Test SSM message parser"""

    def setup_method(self):
        """Setup test fixtures"""
        self.parser = SSMParser()

    def test_parse_new_message(self):
        """Test parsing NEW message"""
        message = "NEW CM 0100 J PTY MIA 1234567 1DEC24 31MAR25 738 0715 0945"
        result = self.parser.parse(message, "NEW")

        assert result["airline"] == "CM"
        assert result["flight_number"] == "0100"
        assert result["service_type"] == "J"
        assert result["origin"] == "PTY"
        assert result["destination"] == "MIA"
        assert result["operating_days"] == "1234567"
        assert result["aircraft_type"] == "738"
        assert result["departure_time"] == "0715"
        assert result["arrival_time"] == "0945"
        assert result["effective_from"] == "1DEC24"
        assert result["effective_to"] == "31MAR25"

    def test_parse_new_message_with_day_change(self):
        """Test parsing NEW message with day change"""
        message = "NEW AA 1234 J JFK LAX 1234567 1DEC24 31MAR25 738 2200 0130 E+1"
        result = self.parser.parse(message, "NEW")

        assert result["departure_time"] == "2200"
        assert result["arrival_time"] == "0130"
        assert result["arrival_day_offset"] == 1

    def test_parse_tim_message(self):
        """Test parsing TIM (time change) message"""
        message = "TIM CM 0100 J PTY MIA 1234567 1DEC24 31MAR25 0725 0955"
        result = self.parser.parse(message, "TIM")

        assert result["airline"] == "CM"
        assert result["flight_number"] == "0100"
        assert result["departure_time"] == "0725"
        assert result["arrival_time"] == "0955"

    def test_parse_eqt_message(self):
        """Test parsing EQT (equipment change) message"""
        message = "EQT CM 0100 PTY MIA 1234567 1DEC24 31MAR25 73J"
        result = self.parser.parse(message, "EQT")

        assert result["airline"] == "CM"
        assert result["flight_number"] == "0100"
        assert result["aircraft_type"] == "73J"

    def test_parse_cnl_message(self):
        """Test parsing CNL (cancellation) message"""
        message = "CNL CM 0100 PTY MIA 1234567 15JAN25 20JAN25"
        result = self.parser.parse(message, "CNL")

        assert result["airline"] == "CM"
        assert result["flight_number"] == "0100"
        assert result["effective_from"] == "15JAN25"
        assert result["effective_to"] == "20JAN25"

    def test_parse_con_message(self):
        """Test parsing CON (continuation) message"""
        message = "CON CM 0100 PTY MIA 1234567 22JAN25 25JAN25"
        result = self.parser.parse(message, "CON")

        assert result["airline"] == "CM"
        assert result["flight_number"] == "0100"

    def test_parse_skd_message(self):
        """Test parsing SKD (schedule dump) message"""
        message = "SKD CM PTY 1DEC24 31MAR25"
        result = self.parser.parse(message, "SKD")

        assert result["airline"] == "CM"
        assert result["airport"] == "PTY"

    def test_parse_operating_days_daily(self):
        """Test parsing daily operating days"""
        days = self.parser._parse_operating_days("1234567")
        assert days == [1, 2, 3, 4, 5, 6, 7]

    def test_parse_operating_days_weekdays(self):
        """Test parsing weekday operating days"""
        days = self.parser._parse_operating_days("123456X")
        assert days == [1, 2, 3, 4, 5, 6]

    def test_parse_operating_days_custom(self):
        """Test parsing custom operating days"""
        days = self.parser._parse_operating_days("X2X4X6X")
        assert days == [2, 4, 6]

    def test_parse_ssm_date(self):
        """Test SSM date parsing"""
        date = self.parser._parse_ssm_date("1DEC24")
        assert date == datetime(2024, 12, 1)

        date = self.parser._parse_ssm_date("31MAR25")
        assert date == datetime(2025, 3, 31)

    def test_calculate_day_offset_same_day(self):
        """Test day offset calculation for same day"""
        offset = self.parser._calculate_day_offset("0800", "1200")
        assert offset == 0

    def test_calculate_day_offset_next_day(self):
        """Test day offset calculation for next day"""
        offset = self.parser._calculate_day_offset("2200", "0130")
        assert offset == 1

    def test_calculate_day_offset_explicit(self):
        """Test explicit day offset"""
        offset = self.parser._calculate_day_offset("0800", "1200", "E+1")
        assert offset == 1

    def test_invalid_message_format(self):
        """Test handling of invalid message format"""
        with pytest.raises(ValueError):
            self.parser.parse("INVALID MESSAGE", "NEW")

    def test_invalid_operating_days(self):
        """Test handling of invalid operating days"""
        with pytest.raises(ValueError):
            self.parser._parse_operating_days("12345")  # Too short

        with pytest.raises(ValueError):
            self.parser._parse_operating_days("ABCDEFG")  # Invalid characters

    def test_multi_line_parsing(self):
        """Test multi-line message parsing"""
        message = """
        NEW CM 0100 J PTY MIA 1234567 1DEC24 31MAR25 738 0715 0945
        NEW CM 0102 J PTY JFK 1234567 1DEC24 31MAR25 738 0830 1445
        """
        results = self.parser.parse_multi_line(message)

        assert len(results) == 2
        assert results[0]["flight_number"] == "0100"
        assert results[1]["flight_number"] == "0102"

    def test_confidence_score(self):
        """Test confidence score for regex parsing"""
        message = "NEW CM 0100 J PTY MIA 1234567 1DEC24 31MAR25 738 0715 0945"
        result = self.parser.parse(message, "NEW")

        assert result["confidence"] == 1.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
