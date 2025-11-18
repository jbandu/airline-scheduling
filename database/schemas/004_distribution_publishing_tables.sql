-- =====================================================
-- Airline Schedule Management System
-- Distribution & Publishing Tables Schema
-- =====================================================
-- Purpose: Schedule distribution to GDS, OTA, partners
--          Publication tracking and confirmation
-- Channels: Amadeus, Sabre, Travelport, OTA platforms
-- =====================================================

-- =====================================================
-- ENUMS
-- =====================================================

-- Distribution channels
CREATE TYPE distribution_channel AS ENUM (
    'GDS_AMADEUS',       -- Amadeus GDS
    'GDS_SABRE',         -- Sabre GDS
    'GDS_TRAVELPORT',    -- Travelport (Apollo, Galileo, Worldspan)
    'OTA_EXPEDIA',       -- Expedia
    'OTA_BOOKING',       -- Booking.com
    'OTA_KAYAK',         -- Kayak
    'OTA_SKYSCANNER',    -- Skyscanner
    'AIRLINE_WEBSITE',   -- Own airline website
    'PARTNER_AIRLINE',   -- Codeshare partner
    'INTERNAL_PSS',      -- Internal Passenger Service System
    'INTERNAL_OPS',      -- Internal operations systems
    'IATA_SSIM',         -- IATA SSIM distribution
    'API_DIRECT'         -- Direct API integration
);

-- Publication status
CREATE TYPE publication_status AS ENUM (
    'pending',
    'in_progress',
    'published',
    'failed',
    'partially_published',
    'cancelled',
    'superseded'
);

-- Distribution format
CREATE TYPE distribution_format AS ENUM (
    'SSIM',              -- IATA Standard Schedules Information Manual
    'SSM',               -- IATA Standard Schedule Message
    'JSON',              -- JSON format
    'XML',               -- XML format
    'CSV',               -- CSV format
    'EDI',               -- Electronic Data Interchange
    'PROPRIETARY'        -- Channel-specific format
);

-- Subscription tier
CREATE TYPE subscription_tier AS ENUM (
    'real_time',         -- Immediate updates
    'hourly',            -- Hourly batch
    'daily',             -- Daily batch
    'weekly',            -- Weekly batch
    'on_demand'          -- Manual/API triggered
);

-- =====================================================
-- DISTRIBUTION TABLES
-- =====================================================

-- -----------------------------------------------------
-- distribution_channels: Channel configuration
-- -----------------------------------------------------
-- Description: Configuration for each distribution channel
-- Manages credentials, endpoints, and preferences
-- -----------------------------------------------------
CREATE TABLE distribution_channels (
    channel_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    -- Channel identification
    channel_code VARCHAR(50) NOT NULL UNIQUE,
    channel_name VARCHAR(200) NOT NULL,
    channel_type distribution_channel NOT NULL,

    -- Technical details
    endpoint_url VARCHAR(500),
    api_version VARCHAR(20),
    authentication_method VARCHAR(50),  -- oauth, api_key, basic_auth, certificate

    -- Credentials (encrypted in production)
    credentials_encrypted BYTEA,
    credentials_last_rotated TIMESTAMP WITH TIME ZONE,

    -- Format preferences
    preferred_format distribution_format NOT NULL DEFAULT 'JSON',
    supported_formats distribution_format[] NOT NULL,

    -- Distribution settings
    subscription_tier subscription_tier NOT NULL DEFAULT 'daily',
    auto_publish BOOLEAN DEFAULT false,
    requires_confirmation BOOLEAN DEFAULT true,

    -- Rate limiting
    max_requests_per_minute INTEGER,
    max_payload_size_mb INTEGER,

    -- Retry configuration
    max_retries INTEGER DEFAULT 3,
    retry_delay_seconds INTEGER DEFAULT 60,

    -- Contact information
    technical_contact VARCHAR(200),
    technical_email VARCHAR(200),
    support_phone VARCHAR(50),

    -- SLA
    sla_response_time_minutes INTEGER,
    sla_uptime_percentage DECIMAL(5,2),

    -- Status
    is_active BOOLEAN DEFAULT true,
    is_test_mode BOOLEAN DEFAULT false,

    -- Monitoring
    last_successful_publish TIMESTAMP WITH TIME ZONE,
    last_error TIMESTAMP WITH TIME ZONE,
    consecutive_failures INTEGER DEFAULT 0,

    -- Audit fields
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),

    -- Metadata
    metadata JSONB DEFAULT '{}'::jsonb
);

-- Add comments
COMMENT ON TABLE distribution_channels IS 'Distribution channel configurations for GDS, OTA, and partners';
COMMENT ON COLUMN distribution_channels.credentials_encrypted IS 'Encrypted credentials (use pgcrypto in production)';

-- Indexes
CREATE INDEX idx_dist_channels_type ON distribution_channels(channel_type);
CREATE INDEX idx_dist_channels_active ON distribution_channels(is_active);
CREATE INDEX idx_dist_channels_tier ON distribution_channels(subscription_tier);

-- -----------------------------------------------------
-- schedule_publications: Publication tracking
-- -----------------------------------------------------
-- Description: Tracks each schedule publication attempt
-- DistributionAgent creates and monitors these
-- -----------------------------------------------------
CREATE TABLE schedule_publications (
    publication_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    -- Schedule reference
    schedule_id UUID NOT NULL REFERENCES schedules(schedule_id) ON DELETE CASCADE,

    -- Channel reference
    channel_id UUID NOT NULL REFERENCES distribution_channels(channel_id),

    -- Workflow reference (if part of automated workflow)
    workflow_id UUID REFERENCES schedule_workflows(workflow_id),

    -- Publication details
    publication_type VARCHAR(50) NOT NULL,  -- full_schedule, incremental, cancellation
    publication_scope VARCHAR(50),          -- seasonal, weekly, daily, single_flight

    -- Content
    payload_format distribution_format NOT NULL,
    payload_size_bytes BIGINT,
    payload_hash VARCHAR(64),  -- SHA-256 hash for verification

    -- Flight coverage
    total_flights INTEGER,
    flight_ids UUID[],  -- Array of published flight IDs

    -- Timing
    scheduled_at TIMESTAMP WITH TIME ZONE,
    published_at TIMESTAMP WITH TIME ZONE,
    confirmed_at TIMESTAMP WITH TIME ZONE,

    -- Status
    status publication_status NOT NULL DEFAULT 'pending',
    status_message TEXT,

    -- Response from channel
    confirmation_received BOOLEAN DEFAULT false,
    confirmation_code VARCHAR(100),
    confirmation_data JSONB,

    -- Channel response
    channel_response_code INTEGER,
    channel_response_message TEXT,
    channel_transaction_id VARCHAR(200),

    -- Performance
    transmission_time_ms BIGINT,
    processing_time_ms BIGINT,

    -- Error handling
    error_count INTEGER DEFAULT 0,
    error_messages JSONB DEFAULT '[]'::jsonb,
    retry_count INTEGER DEFAULT 0,
    last_retry_at TIMESTAMP WITH TIME ZONE,

    -- Validation
    validation_errors JSONB DEFAULT '[]'::jsonb,
    validation_warnings JSONB DEFAULT '[]'::jsonb,

    -- Superseding
    supersedes_publication_id UUID REFERENCES schedule_publications(publication_id),
    superseded_by_publication_id UUID REFERENCES schedule_publications(publication_id),

    -- Initiated by
    initiated_by VARCHAR(255),
    initiated_by_agent VARCHAR(100),

    -- Audit fields
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),

    -- Metadata
    metadata JSONB DEFAULT '{}'::jsonb
);

-- Add comments
COMMENT ON TABLE schedule_publications IS 'Publication tracking for schedule distribution';
COMMENT ON COLUMN schedule_publications.payload_hash IS 'SHA-256 hash for payload verification';

-- Indexes
CREATE INDEX idx_pubs_schedule ON schedule_publications(schedule_id);
CREATE INDEX idx_pubs_channel ON schedule_publications(channel_id);
CREATE INDEX idx_pubs_workflow ON schedule_publications(workflow_id);
CREATE INDEX idx_pubs_status ON schedule_publications(status, scheduled_at DESC);
CREATE INDEX idx_pubs_published ON schedule_publications(published_at DESC);
CREATE INDEX idx_pubs_confirmation ON schedule_publications(confirmation_received);
CREATE INDEX idx_pubs_flights ON schedule_publications USING GIN(flight_ids);

-- -----------------------------------------------------
-- publication_flights: Individual flight publications
-- -----------------------------------------------------
-- Description: Granular tracking of each flight publication
-- Enables precise status tracking per flight per channel
-- -----------------------------------------------------
CREATE TABLE publication_flights (
    pub_flight_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    -- Publication reference
    publication_id UUID NOT NULL REFERENCES schedule_publications(publication_id) ON DELETE CASCADE,

    -- Flight reference
    flight_id UUID NOT NULL REFERENCES flights(flight_id) ON DELETE CASCADE,

    -- Status per flight
    status publication_status NOT NULL DEFAULT 'pending',
    status_message TEXT,

    -- Channel-specific flight ID (if different)
    channel_flight_id VARCHAR(100),

    -- Validation
    validation_passed BOOLEAN DEFAULT true,
    validation_issues JSONB DEFAULT '[]'::jsonb,

    -- Confirmation
    confirmed BOOLEAN DEFAULT false,
    confirmed_at TIMESTAMP WITH TIME ZONE,

    -- Audit fields
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

-- Add comments
COMMENT ON TABLE publication_flights IS 'Granular flight-level publication tracking';

-- Indexes
CREATE INDEX idx_pub_flights_publication ON publication_flights(publication_id);
CREATE INDEX idx_pub_flights_flight ON publication_flights(flight_id);
CREATE INDEX idx_pub_flights_status ON publication_flights(status);
CREATE UNIQUE INDEX idx_unique_pub_flight ON publication_flights(publication_id, flight_id);

-- -----------------------------------------------------
-- distribution_subscriptions: Partner subscriptions
-- -----------------------------------------------------
-- Description: Manages which partners receive which schedules
-- Enables selective distribution based on routes/aircraft
-- -----------------------------------------------------
CREATE TABLE distribution_subscriptions (
    subscription_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    -- Channel
    channel_id UUID NOT NULL REFERENCES distribution_channels(channel_id),

    -- Subscriber details
    subscriber_name VARCHAR(200) NOT NULL,
    subscriber_code VARCHAR(50),
    subscriber_type VARCHAR(50),  -- partner_airline, gds, ota, agent

    -- Subscription scope
    subscription_tier subscription_tier NOT NULL DEFAULT 'daily',

    -- Filters (what to receive)
    filter_carrier_codes VARCHAR(3)[],  -- Specific carriers
    filter_routes JSONB,                -- Specific routes
    filter_airports VARCHAR(3)[],       -- Specific airports
    filter_aircraft_types VARCHAR(3)[], -- Specific aircraft types
    filter_seasonal BOOLEAN,            -- Only seasonal schedules
    filter_criteria JSONB,              -- Additional filter criteria

    -- Delivery preferences
    delivery_method VARCHAR(50) DEFAULT 'api_push',  -- api_push, api_pull, email, ftp
    delivery_schedule VARCHAR(50),      -- cron-like schedule
    delivery_endpoint VARCHAR(500),
    delivery_format distribution_format NOT NULL,

    -- Notification preferences
    notify_on_publish BOOLEAN DEFAULT true,
    notify_on_change BOOLEAN DEFAULT true,
    notify_on_cancel BOOLEAN DEFAULT true,
    notification_email VARCHAR(200),
    notification_webhook VARCHAR(500),

    -- Status
    is_active BOOLEAN DEFAULT true,
    suspended BOOLEAN DEFAULT false,
    suspension_reason TEXT,

    -- Billing (if applicable)
    billing_tier VARCHAR(50),
    cost_per_update DECIMAL(10,2),

    -- Performance tracking
    total_deliveries INTEGER DEFAULT 0,
    successful_deliveries INTEGER DEFAULT 0,
    failed_deliveries INTEGER DEFAULT 0,
    last_delivery_at TIMESTAMP WITH TIME ZONE,

    -- Audit fields
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),

    -- Metadata
    metadata JSONB DEFAULT '{}'::jsonb
);

-- Add comments
COMMENT ON TABLE distribution_subscriptions IS 'Partner subscription configurations for selective distribution';

-- Indexes
CREATE INDEX idx_subs_channel ON distribution_subscriptions(channel_id);
CREATE INDEX idx_subs_active ON distribution_subscriptions(is_active);
CREATE INDEX idx_subs_tier ON distribution_subscriptions(subscription_tier);
CREATE INDEX idx_subs_filters ON distribution_subscriptions USING GIN(filter_carrier_codes);

-- -----------------------------------------------------
-- publication_confirmations: Confirmation tracking
-- -----------------------------------------------------
-- Description: Detailed confirmation messages from channels
-- Tracks ACK/NAK responses per IATA standards
-- -----------------------------------------------------
CREATE TABLE publication_confirmations (
    confirmation_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    -- Publication reference
    publication_id UUID NOT NULL REFERENCES schedule_publications(publication_id) ON DELETE CASCADE,

    -- Confirmation details
    confirmation_type VARCHAR(50) NOT NULL,  -- ACK, NAK, partial
    confirmation_code VARCHAR(100),
    confirmation_message TEXT,

    -- Timing
    received_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    processed_at TIMESTAMP WITH TIME ZONE,

    -- Raw confirmation data
    raw_confirmation TEXT,
    parsed_confirmation JSONB,

    -- Status details
    flights_confirmed INTEGER,
    flights_rejected INTEGER,
    flights_pending INTEGER,

    -- Rejection details
    rejection_reasons JSONB DEFAULT '[]'::jsonb,
    rejected_flight_ids UUID[],

    -- Metadata
    metadata JSONB DEFAULT '{}'::jsonb,

    -- Audit fields
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

-- Add comments
COMMENT ON TABLE publication_confirmations IS 'Confirmation messages from distribution channels';

-- Indexes
CREATE INDEX idx_confirmations_publication ON publication_confirmations(publication_id);
CREATE INDEX idx_confirmations_type ON publication_confirmations(confirmation_type);
CREATE INDEX idx_confirmations_received ON publication_confirmations(received_at DESC);

-- -----------------------------------------------------
-- distribution_logs: Detailed activity logs
-- -----------------------------------------------------
-- Description: Audit trail of all distribution activities
-- Useful for debugging and compliance
-- -----------------------------------------------------
CREATE TABLE distribution_logs (
    log_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    -- References
    publication_id UUID REFERENCES schedule_publications(publication_id),
    channel_id UUID REFERENCES distribution_channels(channel_id),

    -- Log details
    log_level VARCHAR(20) NOT NULL,  -- DEBUG, INFO, WARNING, ERROR, CRITICAL
    log_message TEXT NOT NULL,
    log_category VARCHAR(50),        -- api_call, validation, transformation, transmission

    -- Context
    agent_name VARCHAR(100),
    workflow_id UUID REFERENCES schedule_workflows(workflow_id),

    -- Technical details
    http_method VARCHAR(10),
    http_status_code INTEGER,
    request_url VARCHAR(500),
    request_headers JSONB,
    response_headers JSONB,
    request_body TEXT,
    response_body TEXT,

    -- Performance
    response_time_ms BIGINT,

    -- Timestamp
    logged_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),

    -- Metadata
    metadata JSONB DEFAULT '{}'::jsonb
);

-- Add comments
COMMENT ON TABLE distribution_logs IS 'Detailed activity logs for distribution operations';

-- Indexes
CREATE INDEX idx_dist_logs_publication ON distribution_logs(publication_id);
CREATE INDEX idx_dist_logs_channel ON distribution_logs(channel_id);
CREATE INDEX idx_dist_logs_level ON distribution_logs(log_level, logged_at DESC);
CREATE INDEX idx_dist_logs_logged ON distribution_logs(logged_at DESC);
CREATE INDEX idx_dist_logs_workflow ON distribution_logs(workflow_id);

-- =====================================================
-- DISTRIBUTION FUNCTIONS
-- =====================================================

-- Function to check if a schedule should be published to a channel
CREATE OR REPLACE FUNCTION should_publish_to_subscription(
    p_subscription_id UUID,
    p_flight_id UUID
)
RETURNS BOOLEAN AS $$
DECLARE
    v_should_publish BOOLEAN := true;
    v_subscription RECORD;
    v_flight RECORD;
BEGIN
    -- Get subscription
    SELECT * INTO v_subscription
    FROM distribution_subscriptions
    WHERE subscription_id = p_subscription_id;

    -- Check if active
    IF NOT v_subscription.is_active OR v_subscription.suspended THEN
        RETURN false;
    END IF;

    -- Get flight details
    SELECT * INTO v_flight
    FROM flights
    WHERE flight_id = p_flight_id;

    -- Check carrier filter
    IF v_subscription.filter_carrier_codes IS NOT NULL AND
       array_length(v_subscription.filter_carrier_codes, 1) > 0 THEN
        IF NOT (v_flight.carrier_code = ANY(v_subscription.filter_carrier_codes)) THEN
            RETURN false;
        END IF;
    END IF;

    -- Check airport filter
    IF v_subscription.filter_airports IS NOT NULL AND
       array_length(v_subscription.filter_airports, 1) > 0 THEN
        IF NOT (v_flight.origin_airport = ANY(v_subscription.filter_airports) OR
                v_flight.destination_airport = ANY(v_subscription.filter_airports)) THEN
            RETURN false;
        END IF;
    END IF;

    -- Check aircraft type filter
    IF v_subscription.filter_aircraft_types IS NOT NULL AND
       array_length(v_subscription.filter_aircraft_types, 1) > 0 THEN
        IF NOT (v_flight.aircraft_type = ANY(v_subscription.filter_aircraft_types)) THEN
            RETURN false;
        END IF;
    END IF;

    -- Additional filters can be added based on filter_criteria JSONB

    RETURN v_should_publish;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION should_publish_to_subscription IS 'Determine if flight matches subscription filters';

-- Function to get publication statistics
CREATE OR REPLACE FUNCTION get_publication_stats(
    p_schedule_id UUID
)
RETURNS TABLE (
    total_publications BIGINT,
    successful_publications BIGINT,
    failed_publications BIGINT,
    pending_publications BIGINT,
    total_channels BIGINT,
    confirmed_channels BIGINT
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        COUNT(*)::BIGINT as total_publications,
        COUNT(*) FILTER (WHERE status = 'published')::BIGINT as successful_publications,
        COUNT(*) FILTER (WHERE status = 'failed')::BIGINT as failed_publications,
        COUNT(*) FILTER (WHERE status IN ('pending', 'in_progress'))::BIGINT as pending_publications,
        COUNT(DISTINCT channel_id)::BIGINT as total_channels,
        COUNT(DISTINCT channel_id) FILTER (WHERE confirmation_received = true)::BIGINT as confirmed_channels
    FROM schedule_publications
    WHERE schedule_id = p_schedule_id;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION get_publication_stats IS 'Get publication statistics for a schedule';

-- =====================================================
-- TRIGGERS
-- =====================================================

-- Update distribution channel stats on publication
CREATE OR REPLACE FUNCTION update_channel_stats()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.status = 'published' THEN
        UPDATE distribution_channels
        SET
            last_successful_publish = NEW.published_at,
            consecutive_failures = 0,
            updated_at = NOW()
        WHERE channel_id = NEW.channel_id;
    ELSIF NEW.status = 'failed' THEN
        UPDATE distribution_channels
        SET
            last_error = NOW(),
            consecutive_failures = consecutive_failures + 1,
            updated_at = NOW()
        WHERE channel_id = NEW.channel_id;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER publication_status_changed
    AFTER INSERT OR UPDATE ON schedule_publications
    FOR EACH ROW
    WHEN (NEW.status IN ('published', 'failed'))
    EXECUTE FUNCTION update_channel_stats();

-- Update subscription delivery stats
CREATE OR REPLACE FUNCTION update_subscription_stats()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.status = 'published' THEN
        UPDATE distribution_subscriptions ds
        SET
            total_deliveries = total_deliveries + 1,
            successful_deliveries = successful_deliveries + 1,
            last_delivery_at = NEW.published_at,
            updated_at = NOW()
        FROM distribution_channels dc
        WHERE dc.channel_id = ds.channel_id
          AND dc.channel_id = NEW.channel_id;
    ELSIF NEW.status = 'failed' THEN
        UPDATE distribution_subscriptions ds
        SET
            total_deliveries = total_deliveries + 1,
            failed_deliveries = failed_deliveries + 1,
            updated_at = NOW()
        FROM distribution_channels dc
        WHERE dc.channel_id = ds.channel_id
          AND dc.channel_id = NEW.channel_id;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER subscription_delivery_tracked
    AFTER UPDATE ON schedule_publications
    FOR EACH ROW
    WHEN (OLD.status != NEW.status AND NEW.status IN ('published', 'failed'))
    EXECUTE FUNCTION update_subscription_stats();

-- Update timestamp triggers
CREATE TRIGGER update_dist_channels_updated_at
    BEFORE UPDATE ON distribution_channels
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_pubs_updated_at
    BEFORE UPDATE ON schedule_publications
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_subs_updated_at
    BEFORE UPDATE ON distribution_subscriptions
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- =====================================================
-- VIEWS
-- =====================================================

-- Active publications view
CREATE OR REPLACE VIEW v_active_publications AS
SELECT
    p.publication_id,
    p.schedule_id,
    s.season_code,
    dc.channel_name,
    dc.channel_type,
    p.status,
    p.total_flights,
    p.scheduled_at,
    p.published_at,
    p.confirmation_received
FROM schedule_publications p
JOIN schedules s ON p.schedule_id = s.schedule_id
JOIN distribution_channels dc ON p.channel_id = dc.channel_id
WHERE p.status IN ('pending', 'in_progress', 'published')
ORDER BY p.scheduled_at DESC;

COMMENT ON VIEW v_active_publications IS 'Active and recent publications';

-- Channel health view
CREATE OR REPLACE VIEW v_channel_health AS
SELECT
    dc.channel_id,
    dc.channel_name,
    dc.channel_type,
    dc.is_active,
    dc.consecutive_failures,
    dc.last_successful_publish,
    dc.last_error,
    COUNT(sp.publication_id) FILTER (WHERE sp.created_at >= NOW() - INTERVAL '24 hours') as publications_24h,
    COUNT(sp.publication_id) FILTER (WHERE sp.status = 'published' AND sp.created_at >= NOW() - INTERVAL '24 hours') as successful_24h,
    COUNT(sp.publication_id) FILTER (WHERE sp.status = 'failed' AND sp.created_at >= NOW() - INTERVAL '24 hours') as failed_24h
FROM distribution_channels dc
LEFT JOIN schedule_publications sp ON dc.channel_id = sp.channel_id
GROUP BY dc.channel_id, dc.channel_name, dc.channel_type, dc.is_active,
         dc.consecutive_failures, dc.last_successful_publish, dc.last_error;

COMMENT ON VIEW v_channel_health IS 'Distribution channel health monitoring';

-- =====================================================
-- END OF DISTRIBUTION & PUBLISHING TABLES SCHEMA
-- =====================================================
