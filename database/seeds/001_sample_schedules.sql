-- =====================================================
-- Sample Data Seed Script
-- Airline Schedule Management System
-- =====================================================
-- Purpose: Insert sample data for testing and development
-- Airlines: CM (Copa), AA (American), DL (Delta)
-- Season: W25 (Winter 2025)
-- =====================================================

-- =====================================================
-- 1. SCHEDULES
-- =====================================================

-- Winter 2025 Schedule
INSERT INTO schedules (schedule_id, season_code, effective_from, effective_to, version_number, status, created_by)
VALUES
    ('550e8400-e29b-41d4-a716-446655440001', 'W25', '2025-01-01', '2025-03-31', 1, 'active', 'system'),
    ('550e8400-e29b-41d4-a716-446655440002', 'S25', '2025-04-01', '2025-10-31', 1, 'draft', 'system');

-- =====================================================
-- 2. FLIGHTS - Copa Airlines (CM)
-- =====================================================

-- CM101: Panama City (PTY) to Miami (MIA) - Daily
INSERT INTO flights (
    flight_id, schedule_id, flight_number, carrier_code,
    origin_airport, destination_airport,
    departure_time, arrival_time, departure_day_offset, arrival_day_offset,
    operating_days, effective_from, effective_to,
    aircraft_type, service_type, frequency_per_week,
    seats_total, seats_business, seats_economy
) VALUES (
    '650e8400-e29b-41d4-a716-446655440001',
    '550e8400-e29b-41d4-a716-446655440001',
    'CM101', 'CM',
    'PTY', 'MIA',
    '06:00', '09:15', 0, 0,
    '1234567', '2025-01-01', '2025-03-31',
    '738', 'J', 7,
    160, 16, 144
);

-- CM102: Miami (MIA) to Panama City (PTY) - Daily
INSERT INTO flights (
    flight_id, schedule_id, flight_number, carrier_code,
    origin_airport, destination_airport,
    departure_time, arrival_time, departure_day_offset, arrival_day_offset,
    operating_days, effective_from, effective_to,
    aircraft_type, service_type, frequency_per_week,
    seats_total, seats_business, seats_economy
) VALUES (
    '650e8400-e29b-41d4-a716-446655440002',
    '550e8400-e29b-41d4-a716-446655440001',
    'CM102', 'CM',
    'MIA', 'PTY',
    '11:00', '14:00', 0, 0,
    '1234567', '2025-01-01', '2025-03-31',
    '738', 'J', 7,
    160, 16, 144
);

-- CM201: Panama City (PTY) to New York JFK (JFK) - Daily
INSERT INTO flights (
    flight_id, schedule_id, flight_number, carrier_code,
    origin_airport, destination_airport,
    departure_time, arrival_time, departure_day_offset, arrival_day_offset,
    operating_days, effective_from, effective_to,
    aircraft_type, service_type, frequency_per_week,
    seats_total, seats_business, seats_economy
) VALUES (
    '650e8400-e29b-41d4-a716-446655440003',
    '550e8400-e29b-41d4-a716-446655440001',
    'CM201', 'CM',
    'PTY', 'JFK',
    '08:30', '14:45', 0, 0,
    '1234567', '2025-01-01', '2025-03-31',
    '738', 'J', 7,
    160, 16, 144
);

-- CM202: New York JFK (JFK) to Panama City (PTY) - Daily
INSERT INTO flights (
    flight_id, schedule_id, flight_number, carrier_code,
    origin_airport, destination_airport,
    departure_time, arrival_time, departure_day_offset, arrival_day_offset,
    operating_days, effective_from, effective_to,
    aircraft_type, service_type, frequency_per_week,
    seats_total, seats_business, seats_economy
) VALUES (
    '650e8400-e29b-41d4-a716-446655440004',
    '550e8400-e29b-41d4-a716-446655440001',
    'CM202', 'CM',
    'JFK', 'PTY',
    '16:30', '21:30', 0, 0,
    '1234567', '2025-01-01', '2025-03-31',
    '738', 'J', 7,
    160, 16, 144
);

-- CM301: Panama City (PTY) to Los Angeles (LAX) - Daily except Sunday
INSERT INTO flights (
    flight_id, schedule_id, flight_number, carrier_code,
    origin_airport, destination_airport,
    departure_time, arrival_time, departure_day_offset, arrival_day_offset,
    operating_days, effective_from, effective_to,
    aircraft_type, service_type, frequency_per_week,
    seats_total, seats_business, seats_economy
) VALUES (
    '650e8400-e29b-41d4-a716-446655440005',
    '550e8400-e29b-41d4-a716-446655440001',
    'CM301', 'CM',
    'PTY', 'LAX',
    '10:00', '15:30', 0, 0,
    '123456X', '2025-01-01', '2025-03-31',
    '73J', 'J', 6,
    172, 16, 156
);

-- =====================================================
-- 3. FLIGHTS - American Airlines (AA)
-- =====================================================

-- AA1: Miami (MIA) to New York JFK (JFK) - Daily
INSERT INTO flights (
    flight_id, schedule_id, flight_number, carrier_code,
    origin_airport, destination_airport,
    departure_time, arrival_time, departure_day_offset, arrival_day_offset,
    operating_days, effective_from, effective_to,
    aircraft_type, service_type, frequency_per_week,
    seats_total, seats_business, seats_economy
) VALUES (
    '650e8400-e29b-41d4-a716-446655440010',
    '550e8400-e29b-41d4-a716-446655440001',
    'AA1', 'AA',
    'MIA', 'JFK',
    '07:00', '10:15', 0, 0,
    '1234567', '2025-01-01', '2025-03-31',
    '321', 'J', 7,
    187, 20, 167
);

-- AA100: New York JFK (JFK) to Los Angeles (LAX) - Daily
INSERT INTO flights (
    flight_id, schedule_id, flight_number, carrier_code,
    origin_airport, destination_airport,
    departure_time, arrival_time, departure_day_offset, arrival_day_offset,
    operating_days, effective_from, effective_to,
    aircraft_type, service_type, frequency_per_week,
    seats_total, seats_business, seats_economy
) VALUES (
    '650e8400-e29b-41d4-a716-446655440011',
    '550e8400-e29b-41d4-a716-446655440001',
    'AA100', 'AA',
    'JFK', 'LAX',
    '08:00', '11:30', 0, 0,
    '1234567', '2025-01-01', '2025-03-31',
    '32B', 'J', 7,
    200, 30, 170
);

-- =====================================================
-- 4. FLIGHTS - Delta Air Lines (DL)
-- =====================================================

-- DL1: Miami (MIA) to Atlanta (ATL) - Daily
INSERT INTO flights (
    flight_id, schedule_id, flight_number, carrier_code,
    origin_airport, destination_airport,
    departure_time, arrival_time, departure_day_offset, arrival_day_offset,
    operating_days, effective_from, effective_to,
    aircraft_type, service_type, frequency_per_week,
    seats_total, seats_business, seats_economy
) VALUES (
    '650e8400-e29b-41d4-a716-446655440020',
    '550e8400-e29b-41d4-a716-446655440001',
    'DL1', 'DL',
    'MIA', 'ATL',
    '06:30', '08:30', 0, 0,
    '1234567', '2025-01-01', '2025-03-31',
    '738', 'J', 7,
    160, 16, 144
);

-- DL100: Atlanta (ATL) to Los Angeles (LAX) - Daily
INSERT INTO flights (
    flight_id, schedule_id, flight_number, carrier_code,
    origin_airport, destination_airport,
    departure_time, arrival_time, departure_day_offset, arrival_day_offset,
    operating_days, effective_from, effective_to,
    aircraft_type, service_type, frequency_per_week,
    seats_total, seats_business, seats_economy
) VALUES (
    '650e8400-e29b-41d4-a716-446655440021',
    '550e8400-e29b-41d4-a716-446655440001',
    'DL100', 'DL',
    'ATL', 'LAX',
    '09:30', '11:45', 0, 0,
    '1234567', '2025-01-01', '2025-03-31',
    '73H', 'J', 7,
    175, 20, 155
);

-- =====================================================
-- 5. SSM MESSAGES
-- =====================================================

-- Sample NEW message
INSERT INTO ssm_messages (
    message_id, message_type, message_format,
    raw_message, sender_airline, receiver_airline,
    action_code, received_at, processing_status,
    created_by_agent
) VALUES (
    '750e8400-e29b-41d4-a716-446655440001',
    'NEW', 'SSM',
    E'NEW\nCM 101 PTY MIA 1234567 01JAN25 31MAR25 738 0600 0915',
    'CM', 'AA',
    'ADD',
    '2025-01-01 00:00:00+00',
    'completed',
    'SSMParserAgent'
);

-- Sample TIM (time change) message
INSERT INTO ssm_messages (
    message_id, message_type, message_format,
    raw_message, sender_airline,
    action_code, received_at, processing_status,
    created_by_agent
) VALUES (
    '750e8400-e29b-41d4-a716-446655440002',
    'TIM', 'SSM',
    E'TIM\nCM 201 PTY JFK 15JAN25 15JAN25\nDEP 0845 ARR 1500',
    'CM',
    'MOD',
    '2025-01-10 12:00:00+00',
    'pending',
    'SSMParserAgent'
);

-- =====================================================
-- 6. AIRPORT CONSTRAINTS
-- =====================================================

-- PTY (Panama City Tocumen) - Level 2 coordinated
INSERT INTO airport_constraints (
    constraint_id, airport_code, constraint_type,
    constraint_name, constraint_data,
    effective_from, coordination_level
) VALUES (
    '850e8400-e29b-41d4-a716-446655440001',
    'PTY', 'slot_coordination',
    'PTY Slot Coordination Level 2',
    '{"max_movements_per_hour": 40, "coordination_required": true}'::jsonb,
    '2025-01-01',
    'level_2'
);

-- MIA (Miami) - Curfew restrictions
INSERT INTO airport_constraints (
    constraint_id, airport_code, constraint_type,
    constraint_name, constraint_data,
    effective_from
) VALUES (
    '850e8400-e29b-41d4-a716-446655440002',
    'MIA', 'curfew',
    'MIA Night Curfew',
    '{"start_time": "23:00", "end_time": "06:00", "exceptions": ["cargo", "medical"]}'::jsonb,
    '2025-01-01'
);

-- JFK (New York JFK) - Capacity limits
INSERT INTO airport_constraints (
    constraint_id, airport_code, constraint_type,
    constraint_name, constraint_data,
    effective_from
) VALUES (
    '850e8400-e29b-41d4-a716-446655440003',
    'JFK', 'capacity',
    'JFK Hourly Capacity',
    '{"max_arrivals_per_hour": 45, "max_departures_per_hour": 45}'::jsonb,
    '2025-01-01'
);

-- =====================================================
-- 7. MINIMUM CONNECT TIMES (MCT)
-- =====================================================

-- PTY - Domestic to International
INSERT INTO minimum_connect_times (
    mct_id, airport_code, connection_type,
    mct_minutes, effective_from
) VALUES (
    '950e8400-e29b-41d4-a716-446655440001',
    'PTY', 'domestic_international',
    60, '2025-01-01'
);

-- PTY - International to International
INSERT INTO minimum_connect_times (
    mct_id, airport_code, connection_type,
    mct_minutes, effective_from
) VALUES (
    '950e8400-e29b-41d4-a716-446655440002',
    'PTY', 'international_international',
    90, '2025-01-01'
);

-- MIA - International to International
INSERT INTO minimum_connect_times (
    mct_id, airport_code, connection_type,
    mct_minutes, effective_from,
    requires_customs
) VALUES (
    '950e8400-e29b-41d4-a716-446655440003',
    'MIA', 'international_international',
    120, '2025-01-01',
    true
);

-- JFK - International to Domestic
INSERT INTO minimum_connect_times (
    mct_id, airport_code, connection_type,
    mct_minutes, effective_from,
    requires_customs, requires_immigration
) VALUES (
    '950e8400-e29b-41d4-a716-446655440004',
    'JFK', 'international_domestic',
    150, '2025-01-01',
    true, true
);

-- ATL - Domestic to Domestic
INSERT INTO minimum_connect_times (
    mct_id, airport_code, connection_type,
    mct_minutes, effective_from
) VALUES (
    '950e8400-e29b-41d4-a716-446655440005',
    'ATL', 'domestic_domestic',
    45, '2025-01-01'
);

-- =====================================================
-- 8. AIRCRAFT AVAILABILITY
-- =====================================================

-- Copa Airlines Fleet
INSERT INTO aircraft_availability (
    availability_id, aircraft_registration, aircraft_type,
    owner_airline, operating_airline, home_base,
    available_from, status, etops_certified
) VALUES
    ('a50e8400-e29b-41d4-a716-446655440001', 'HP-1825CMP', '738', 'CM', 'CM', 'PTY', '2025-01-01 00:00:00+00', 'available', true),
    ('a50e8400-e29b-41d4-a716-446655440002', 'HP-1849CMP', '738', 'CM', 'CM', 'PTY', '2025-01-01 00:00:00+00', 'available', true),
    ('a50e8400-e29b-41d4-a716-446655440003', 'HP-9901CMP', '73J', 'CM', 'CM', 'PTY', '2025-01-01 00:00:00+00', 'available', true);

-- American Airlines Fleet
INSERT INTO aircraft_availability (
    availability_id, aircraft_registration, aircraft_type,
    owner_airline, operating_airline, home_base,
    available_from, status, etops_certified
) VALUES
    ('a50e8400-e29b-41d4-a716-446655440010', 'N123AA', '321', 'AA', 'AA', 'MIA', '2025-01-01 00:00:00+00', 'available', false),
    ('a50e8400-e29b-41d4-a716-446655440011', 'N456AA', '32B', 'AA', 'AA', 'JFK', '2025-01-01 00:00:00+00', 'available', true);

-- Delta Airlines Fleet
INSERT INTO aircraft_availability (
    availability_id, aircraft_registration, aircraft_type,
    owner_airline, operating_airline, home_base,
    available_from, status, etops_certified
) VALUES
    ('a50e8400-e29b-41d4-a716-446655440020', 'N123DL', '738', 'DL', 'DL', 'ATL', '2025-01-01 00:00:00+00', 'available', true),
    ('a50e8400-e29b-41d4-a716-446655440021', 'N456DL', '73H', 'DL', 'DL', 'ATL', '2025-01-01 00:00:00+00', 'available', true);

-- =====================================================
-- 9. CREW BASES
-- =====================================================

INSERT INTO crew_bases (
    base_id, base_code, base_name, airport_code,
    airline_code, has_pilots, has_cabin_crew,
    pilot_capacity, cabin_crew_capacity
) VALUES
    ('b50e8400-e29b-41d4-a716-446655440001', 'PTY-CM', 'Copa Airlines Panama City Base', 'PTY', 'CM', true, true, 500, 1200),
    ('b50e8400-e29b-41d4-a716-446655440002', 'MIA-AA', 'American Airlines Miami Base', 'MIA', 'AA', true, true, 800, 2000),
    ('b50e8400-e29b-41d4-a716-446655440003', 'ATL-DL', 'Delta Air Lines Atlanta Base', 'ATL', 'DL', true, true, 1000, 2500);

-- =====================================================
-- 10. DISTRIBUTION CHANNELS
-- =====================================================

INSERT INTO distribution_channels (
    channel_id, channel_code, channel_name, channel_type,
    endpoint_url, preferred_format, subscription_tier,
    is_active
) VALUES
    ('c50e8400-e29b-41d4-a716-446655440001', 'AMADEUS-PROD', 'Amadeus GDS Production', 'GDS_AMADEUS',
     'https://api.amadeus.com/schedules', 'SSIM', 'real_time', true),
    ('c50e8400-e29b-41d4-a716-446655440002', 'SABRE-PROD', 'Sabre GDS Production', 'GDS_SABRE',
     'https://api.sabre.com/schedules', 'SSM', 'hourly', true),
    ('c50e8400-e29b-41d4-a716-446655440003', 'EXPEDIA-API', 'Expedia OTA API', 'OTA_EXPEDIA',
     'https://api.expedia.com/flights', 'JSON', 'daily', true);

-- =====================================================
-- 11. SAMPLE WORKFLOW
-- =====================================================

INSERT INTO schedule_workflows (
    workflow_id, workflow_type, workflow_name,
    schedule_id, initiated_by, status,
    current_agent, total_steps, completed_steps
) VALUES (
    'd50e8400-e29b-41d4-a716-446655440001',
    'weekly_update', 'W25 Weekly Schedule Update - Week 1',
    '550e8400-e29b-41d4-a716-446655440001',
    'scheduler_system', 'completed',
    'DistributionAgent', 7, 7
);

-- =====================================================
-- Data Verification Queries
-- =====================================================

-- Verify schedules
-- SELECT * FROM schedules;

-- Verify flights count
-- SELECT carrier_code, COUNT(*) as flight_count FROM flights GROUP BY carrier_code;

-- Verify operating days pattern
-- SELECT flight_number, operating_days, parse_ssm_operating_days(operating_days) FROM flights WHERE carrier_code = 'CM';

-- Verify MCT settings
-- SELECT * FROM minimum_connect_times;

-- Verify aircraft availability
-- SELECT operating_airline, COUNT(*) FROM aircraft_availability GROUP BY operating_airline;

-- =====================================================
-- END OF SAMPLE DATA SEED
-- =====================================================
