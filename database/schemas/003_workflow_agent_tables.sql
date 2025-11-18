-- =====================================================
-- Airline Schedule Management System
-- Multi-Agent Workflow Tables Schema
-- =====================================================
-- Purpose: LangGraph multi-agent orchestration tracking
--          Workflow state management, agent execution logs
-- Architecture: SupervisorAgent coordinates 7 specialist agents
-- =====================================================

-- =====================================================
-- ENUMS
-- =====================================================

-- Workflow types
CREATE TYPE workflow_type AS ENUM (
    'weekly_update',         -- Regular weekly schedule maintenance
    'ad_hoc_change',        -- Unscheduled modification
    'seasonal_planning',    -- New season schedule creation
    'disruption_recovery',  -- IROPS and recovery
    'fleet_rebalancing',    -- Aircraft reassignment
    'crew_optimization',    -- Crew assignment optimization
    'slot_negotiation'      -- Airport slot coordination
);

-- Workflow status
CREATE TYPE workflow_status AS ENUM (
    'pending',       -- Queued for processing
    'in_progress',   -- Currently being processed
    'completed',     -- Successfully completed
    'failed',        -- Failed with errors
    'cancelled',     -- Manually cancelled
    'paused',        -- Temporarily paused
    'awaiting_approval' -- Requires human approval
);

-- Agent execution status
CREATE TYPE agent_execution_status AS ENUM (
    'queued',
    'running',
    'completed',
    'failed',
    'skipped',
    'timeout',
    'retrying'
);

-- Conflict types
CREATE TYPE conflict_type AS ENUM (
    'aircraft_overlap',      -- Same aircraft assigned to multiple flights
    'crew_unavailable',      -- Crew not available or legal
    'slot_conflict',         -- Airport slot not available
    'mct_violation',         -- Minimum connect time violation
    'curfew_violation',      -- Airport curfew violation
    'maintenance_conflict',  -- Aircraft in maintenance
    'range_limitation',      -- Aircraft range insufficient
    'capacity_exceeded',     -- Airport capacity exceeded
    'regulatory_violation',  -- Regulatory requirement not met
    'gate_conflict',         -- Gate assignment conflict
    'fuel_restriction'       -- Fuel availability issue
);

-- Conflict severity
CREATE TYPE conflict_severity AS ENUM (
    'critical',  -- Blocks operation
    'high',      -- Major issue, requires immediate attention
    'medium',    -- Should be resolved
    'low',       -- Minor optimization opportunity
    'info'       -- Informational only
);

-- Resolution status
CREATE TYPE resolution_status AS ENUM (
    'pending',
    'in_progress',
    'resolved',
    'accepted_as_exception',
    'cannot_resolve',
    'escalated'
);

-- =====================================================
-- WORKFLOW TABLES
-- =====================================================

-- -----------------------------------------------------
-- schedule_workflows: Master workflow orchestration
-- -----------------------------------------------------
-- Description: Tracks end-to-end schedule processing workflows
-- SupervisorAgent creates and monitors these
-- -----------------------------------------------------
CREATE TABLE schedule_workflows (
    workflow_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    -- Workflow classification
    workflow_type workflow_type NOT NULL,
    workflow_name VARCHAR(200) NOT NULL,
    description TEXT,

    -- Related entities
    schedule_id UUID REFERENCES schedules(schedule_id),
    ssm_message_ids UUID[],  -- Array of related SSM messages
    parent_workflow_id UUID REFERENCES schedule_workflows(workflow_id),

    -- Initiator
    initiated_by VARCHAR(255) NOT NULL,  -- User ID or system
    initiated_by_type VARCHAR(50) DEFAULT 'system',  -- user, system, agent, api

    -- Timing
    initiated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    started_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,
    deadline TIMESTAMP WITH TIME ZONE,

    -- Status
    status workflow_status NOT NULL DEFAULT 'pending',
    status_message TEXT,

    -- Current processing state
    current_agent VARCHAR(100),  -- Which agent is currently active
    current_step VARCHAR(200),   -- Current workflow step
    total_steps INTEGER,
    completed_steps INTEGER DEFAULT 0,

    -- Progress tracking
    progress_percentage DECIMAL(5,2) DEFAULT 0.00,

    -- Results
    result_summary JSONB DEFAULT '{}'::jsonb,
    flights_created INTEGER DEFAULT 0,
    flights_modified INTEGER DEFAULT 0,
    flights_cancelled INTEGER DEFAULT 0,
    conflicts_detected INTEGER DEFAULT 0,
    conflicts_resolved INTEGER DEFAULT 0,

    -- Performance metrics
    total_execution_time_ms BIGINT,
    total_tokens_used INTEGER,
    total_api_calls INTEGER,

    -- Workflow configuration
    workflow_config JSONB DEFAULT '{}'::jsonb,
    workflow_metadata JSONB DEFAULT '{}'::jsonb,

    -- Error handling
    error_count INTEGER DEFAULT 0,
    last_error TEXT,
    retry_count INTEGER DEFAULT 0,
    max_retries INTEGER DEFAULT 3,

    -- Audit fields
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

-- Add comments
COMMENT ON TABLE schedule_workflows IS 'Master workflow orchestration for schedule processing';
COMMENT ON COLUMN schedule_workflows.current_agent IS 'Name of currently executing agent';
COMMENT ON COLUMN schedule_workflows.workflow_config IS 'Workflow-specific configuration parameters';

-- Indexes
CREATE INDEX idx_workflows_type ON schedule_workflows(workflow_type);
CREATE INDEX idx_workflows_status ON schedule_workflows(status, initiated_at DESC);
CREATE INDEX idx_workflows_schedule ON schedule_workflows(schedule_id);
CREATE INDEX idx_workflows_initiated ON schedule_workflows(initiated_at DESC);
CREATE INDEX idx_workflows_parent ON schedule_workflows(parent_workflow_id);
CREATE INDEX idx_workflows_current_agent ON schedule_workflows(current_agent);
CREATE INDEX idx_workflows_ssm_messages ON schedule_workflows USING GIN(ssm_message_ids);

-- -----------------------------------------------------
-- agent_executions: Individual agent execution logs
-- -----------------------------------------------------
-- Description: Detailed logs of each agent's execution
-- Tracks 7 specialist agents + SupervisorAgent
-- -----------------------------------------------------
CREATE TABLE agent_executions (
    execution_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    -- Workflow reference
    workflow_id UUID NOT NULL REFERENCES schedule_workflows(workflow_id) ON DELETE CASCADE,

    -- Agent identification
    agent_name VARCHAR(100) NOT NULL,  -- SSMParserAgent, ValidationAgent, etc.
    agent_type VARCHAR(50),            -- parser, validator, optimizer, etc.
    agent_version VARCHAR(20),

    -- Execution order
    execution_sequence INTEGER,  -- Order in workflow

    -- Timing
    started_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMP WITH TIME ZONE,
    execution_time_ms BIGINT,

    -- Status
    status agent_execution_status NOT NULL DEFAULT 'queued',
    status_message TEXT,

    -- Input/Output
    input_data JSONB DEFAULT '{}'::jsonb,
    output_data JSONB DEFAULT '{}'::jsonb,

    -- Decisions made
    decisions_made JSONB DEFAULT '[]'::jsonb,
    recommendations JSONB DEFAULT '[]'::jsonb,

    -- Performance metrics
    tokens_used INTEGER DEFAULT 0,
    api_calls_made INTEGER DEFAULT 0,
    records_processed INTEGER DEFAULT 0,
    records_created INTEGER DEFAULT 0,
    records_updated INTEGER DEFAULT 0,

    -- LLM-specific metrics (for AI agents)
    llm_model VARCHAR(100),
    llm_temperature DECIMAL(3,2),
    llm_prompt_tokens INTEGER,
    llm_completion_tokens INTEGER,
    llm_total_tokens INTEGER,

    -- Error handling
    error_message TEXT,
    error_stack TEXT,
    error_code VARCHAR(50),
    retry_count INTEGER DEFAULT 0,

    -- Validation results
    validation_passed BOOLEAN,
    validation_warnings JSONB DEFAULT '[]'::jsonb,
    validation_errors JSONB DEFAULT '[]'::jsonb,

    -- Metadata
    execution_context JSONB DEFAULT '{}'::jsonb,
    agent_config JSONB DEFAULT '{}'::jsonb,

    -- Audit fields
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

-- Add comments
COMMENT ON TABLE agent_executions IS 'Detailed execution logs for all AI agents';
COMMENT ON COLUMN agent_executions.agent_name IS '7 agents: SSMParserAgent, ScheduleValidationAgent, ConflictResolutionAgent, FleetAssignmentAgent, CrewFeasibilityAgent, SlotComplianceAgent, DistributionAgent';
COMMENT ON COLUMN agent_executions.decisions_made IS 'Array of decisions made by agent during execution';

-- Indexes
CREATE INDEX idx_executions_workflow ON agent_executions(workflow_id, execution_sequence);
CREATE INDEX idx_executions_agent ON agent_executions(agent_name, status);
CREATE INDEX idx_executions_status ON agent_executions(status, started_at DESC);
CREATE INDEX idx_executions_started ON agent_executions(started_at DESC);
CREATE INDEX idx_executions_performance ON agent_executions(execution_time_ms DESC);

-- -----------------------------------------------------
-- schedule_conflicts: Detected scheduling conflicts
-- -----------------------------------------------------
-- Description: All detected conflicts during workflow
-- ConflictResolutionAgent processes these
-- -----------------------------------------------------
CREATE TABLE schedule_conflicts (
    conflict_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    -- Workflow reference
    workflow_id UUID NOT NULL REFERENCES schedule_workflows(workflow_id) ON DELETE CASCADE,

    -- Conflict classification
    conflict_type conflict_type NOT NULL,
    severity conflict_severity NOT NULL DEFAULT 'medium',

    -- Affected entities
    affected_flight_ids UUID[] NOT NULL,
    affected_aircraft_ids VARCHAR(10)[],
    affected_crew_ids UUID[],
    affected_airports VARCHAR(3)[],
    affected_slots UUID[],

    -- Detection
    detected_by_agent VARCHAR(100) NOT NULL,
    detected_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    detection_method VARCHAR(100),  -- rule_based, ml_model, heuristic

    -- Conflict details
    conflict_description TEXT NOT NULL,
    conflict_data JSONB DEFAULT '{}'::jsonb,  -- Detailed conflict information

    -- Impact assessment
    impact_score DECIMAL(5,2),  -- 0-100 impact score
    passenger_impact INTEGER,    -- Number of passengers affected
    cost_impact_usd DECIMAL(12,2),
    delay_minutes INTEGER,

    -- Resolution
    resolution_status resolution_status NOT NULL DEFAULT 'pending',
    resolution_priority INTEGER DEFAULT 50,  -- 0-100, higher = more urgent

    -- Resolution details
    proposed_solutions JSONB DEFAULT '[]'::jsonb,  -- Array of possible solutions
    selected_solution JSONB,
    resolution_details JSONB DEFAULT '{}'::jsonb,

    -- Resolution tracking
    assigned_to VARCHAR(255),  -- Agent or user assigned to resolve
    resolved_by VARCHAR(255),
    resolved_at TIMESTAMP WITH TIME ZONE,
    resolution_time_ms BIGINT,

    -- Approval workflow
    requires_approval BOOLEAN DEFAULT false,
    approved_by VARCHAR(255),
    approved_at TIMESTAMP WITH TIME ZONE,
    approval_notes TEXT,

    -- Related conflicts
    related_conflict_ids UUID[],  -- Other conflicts related to this one
    root_cause_conflict_id UUID REFERENCES schedule_conflicts(conflict_id),

    -- Metadata
    metadata JSONB DEFAULT '{}'::jsonb,

    -- Audit fields
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

-- Add comments
COMMENT ON TABLE schedule_conflicts IS 'Detected scheduling conflicts for resolution';
COMMENT ON COLUMN schedule_conflicts.impact_score IS 'Calculated impact score 0-100';
COMMENT ON COLUMN schedule_conflicts.proposed_solutions IS 'Array of potential resolution approaches';

-- Indexes
CREATE INDEX idx_conflicts_workflow ON schedule_conflicts(workflow_id);
CREATE INDEX idx_conflicts_type_severity ON schedule_conflicts(conflict_type, severity);
CREATE INDEX idx_conflicts_status ON schedule_conflicts(resolution_status, detected_at DESC);
CREATE INDEX idx_conflicts_flights ON schedule_conflicts USING GIN(affected_flight_ids);
CREATE INDEX idx_conflicts_detected_by ON schedule_conflicts(detected_by_agent);
CREATE INDEX idx_conflicts_priority ON schedule_conflicts(resolution_priority DESC, detected_at);
CREATE INDEX idx_conflicts_root_cause ON schedule_conflicts(root_cause_conflict_id);

-- -----------------------------------------------------
-- agent_communications: Inter-agent communication log
-- -----------------------------------------------------
-- Description: Tracks messages between agents
-- Useful for debugging multi-agent workflows
-- -----------------------------------------------------
CREATE TABLE agent_communications (
    communication_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    -- Workflow and execution context
    workflow_id UUID NOT NULL REFERENCES schedule_workflows(workflow_id) ON DELETE CASCADE,
    execution_id UUID REFERENCES agent_executions(execution_id),

    -- Communication parties
    from_agent VARCHAR(100) NOT NULL,
    to_agent VARCHAR(100) NOT NULL,

    -- Message details
    message_type VARCHAR(50) NOT NULL,  -- request, response, notification, error
    message_content JSONB NOT NULL,
    message_priority VARCHAR(20) DEFAULT 'normal',  -- low, normal, high, urgent

    -- Timing
    sent_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    received_at TIMESTAMP WITH TIME ZONE,
    processed_at TIMESTAMP WITH TIME ZONE,

    -- Status
    status VARCHAR(50) DEFAULT 'sent',  -- sent, received, processed, failed

    -- Correlation
    in_reply_to UUID REFERENCES agent_communications(communication_id),
    correlation_id UUID,  -- For tracking request-response pairs

    -- Metadata
    metadata JSONB DEFAULT '{}'::jsonb
);

-- Add comments
COMMENT ON TABLE agent_communications IS 'Inter-agent communication logs for debugging';

-- Indexes
CREATE INDEX idx_comm_workflow ON agent_communications(workflow_id, sent_at DESC);
CREATE INDEX idx_comm_agents ON agent_communications(from_agent, to_agent);
CREATE INDEX idx_comm_correlation ON agent_communications(correlation_id);
CREATE INDEX idx_comm_execution ON agent_communications(execution_id);

-- -----------------------------------------------------
-- workflow_approvals: Human-in-the-loop approvals
-- -----------------------------------------------------
-- Description: Tracks approval requests for workflows
-- Some changes may require human approval
-- -----------------------------------------------------
CREATE TABLE workflow_approvals (
    approval_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    -- Workflow reference
    workflow_id UUID NOT NULL REFERENCES schedule_workflows(workflow_id) ON DELETE CASCADE,

    -- Approval request
    approval_type VARCHAR(100) NOT NULL,  -- schedule_change, conflict_resolution, etc.
    approval_description TEXT NOT NULL,
    approval_data JSONB NOT NULL,

    -- Requestor
    requested_by VARCHAR(255) NOT NULL,
    requested_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),

    -- Urgency
    priority VARCHAR(20) DEFAULT 'normal',
    deadline TIMESTAMP WITH TIME ZONE,

    -- Status
    status VARCHAR(50) DEFAULT 'pending',  -- pending, approved, rejected, expired

    -- Approval decision
    approved_by VARCHAR(255),
    approved_at TIMESTAMP WITH TIME ZONE,
    rejection_reason TEXT,
    approval_notes TEXT,

    -- Impact summary
    impact_summary JSONB,

    -- Metadata
    metadata JSONB DEFAULT '{}'::jsonb
);

-- Add comments
COMMENT ON TABLE workflow_approvals IS 'Human-in-the-loop approval tracking';

-- Indexes
CREATE INDEX idx_approvals_workflow ON workflow_approvals(workflow_id);
CREATE INDEX idx_approvals_status ON workflow_approvals(status, requested_at DESC);
CREATE INDEX idx_approvals_deadline ON workflow_approvals(deadline) WHERE status = 'pending';

-- =====================================================
-- WORKFLOW MANAGEMENT FUNCTIONS
-- =====================================================

-- Function to calculate workflow progress
CREATE OR REPLACE FUNCTION update_workflow_progress(p_workflow_id UUID)
RETURNS VOID AS $$
DECLARE
    v_total_steps INTEGER;
    v_completed_steps INTEGER;
    v_progress DECIMAL(5,2);
BEGIN
    -- Count total and completed agent executions
    SELECT
        COUNT(*),
        COUNT(*) FILTER (WHERE status = 'completed')
    INTO v_total_steps, v_completed_steps
    FROM agent_executions
    WHERE workflow_id = p_workflow_id;

    -- Calculate progress percentage
    IF v_total_steps > 0 THEN
        v_progress := (v_completed_steps::DECIMAL / v_total_steps) * 100;
    ELSE
        v_progress := 0;
    END IF;

    -- Update workflow
    UPDATE schedule_workflows
    SET
        total_steps = v_total_steps,
        completed_steps = v_completed_steps,
        progress_percentage = v_progress,
        updated_at = NOW()
    WHERE workflow_id = p_workflow_id;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION update_workflow_progress IS 'Calculate and update workflow progress based on agent executions';

-- Function to get workflow summary
CREATE OR REPLACE FUNCTION get_workflow_summary(p_workflow_id UUID)
RETURNS TABLE (
    workflow_id UUID,
    workflow_type workflow_type,
    status workflow_status,
    progress_percentage DECIMAL,
    total_agents INTEGER,
    completed_agents INTEGER,
    failed_agents INTEGER,
    total_conflicts INTEGER,
    resolved_conflicts INTEGER,
    execution_time_seconds INTEGER
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        w.workflow_id,
        w.workflow_type,
        w.status,
        w.progress_percentage,
        COUNT(ae.execution_id)::INTEGER as total_agents,
        COUNT(ae.execution_id) FILTER (WHERE ae.status = 'completed')::INTEGER as completed_agents,
        COUNT(ae.execution_id) FILTER (WHERE ae.status = 'failed')::INTEGER as failed_agents,
        COUNT(DISTINCT c.conflict_id)::INTEGER as total_conflicts,
        COUNT(DISTINCT c.conflict_id) FILTER (WHERE c.resolution_status = 'resolved')::INTEGER as resolved_conflicts,
        EXTRACT(EPOCH FROM (COALESCE(w.completed_at, NOW()) - w.started_at))::INTEGER as execution_time_seconds
    FROM schedule_workflows w
    LEFT JOIN agent_executions ae ON w.workflow_id = ae.workflow_id
    LEFT JOIN schedule_conflicts c ON w.workflow_id = c.workflow_id
    WHERE w.workflow_id = p_workflow_id
    GROUP BY w.workflow_id, w.workflow_type, w.status, w.progress_percentage, w.started_at, w.completed_at;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION get_workflow_summary IS 'Get comprehensive workflow summary with agent and conflict stats';

-- =====================================================
-- TRIGGERS
-- =====================================================

-- Auto-update workflow progress when agent execution completes
CREATE OR REPLACE FUNCTION trigger_update_workflow_progress()
RETURNS TRIGGER AS $$
BEGIN
    PERFORM update_workflow_progress(NEW.workflow_id);
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER agent_execution_completed
    AFTER INSERT OR UPDATE ON agent_executions
    FOR EACH ROW
    WHEN (NEW.status IN ('completed', 'failed', 'skipped'))
    EXECUTE FUNCTION trigger_update_workflow_progress();

-- Auto-update conflict count in workflow
CREATE OR REPLACE FUNCTION trigger_update_conflict_count()
RETURNS TRIGGER AS $$
BEGIN
    UPDATE schedule_workflows
    SET
        conflicts_detected = (
            SELECT COUNT(*)
            FROM schedule_conflicts
            WHERE workflow_id = NEW.workflow_id
        ),
        conflicts_resolved = (
            SELECT COUNT(*)
            FROM schedule_conflicts
            WHERE workflow_id = NEW.workflow_id
              AND resolution_status = 'resolved'
        ),
        updated_at = NOW()
    WHERE workflow_id = NEW.workflow_id;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER conflict_status_changed
    AFTER INSERT OR UPDATE ON schedule_conflicts
    FOR EACH ROW
    EXECUTE FUNCTION trigger_update_conflict_count();

-- Update timestamp trigger for workflows
CREATE TRIGGER update_workflows_updated_at
    BEFORE UPDATE ON schedule_workflows
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Update timestamp trigger for conflicts
CREATE TRIGGER update_conflicts_updated_at
    BEFORE UPDATE ON schedule_conflicts
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- =====================================================
-- VIEWS
-- =====================================================

-- Active workflows view
CREATE OR REPLACE VIEW v_active_workflows AS
SELECT
    w.workflow_id,
    w.workflow_type,
    w.workflow_name,
    w.status,
    w.progress_percentage,
    w.current_agent,
    w.initiated_at,
    w.deadline,
    COUNT(ae.execution_id) as total_agents,
    COUNT(ae.execution_id) FILTER (WHERE ae.status = 'completed') as completed_agents,
    COUNT(DISTINCT c.conflict_id) as total_conflicts,
    COUNT(DISTINCT c.conflict_id) FILTER (WHERE c.resolution_status = 'resolved') as resolved_conflicts
FROM schedule_workflows w
LEFT JOIN agent_executions ae ON w.workflow_id = ae.workflow_id
LEFT JOIN schedule_conflicts c ON w.workflow_id = c.workflow_id
WHERE w.status IN ('in_progress', 'pending', 'paused')
GROUP BY w.workflow_id, w.workflow_type, w.workflow_name, w.status,
         w.progress_percentage, w.current_agent, w.initiated_at, w.deadline;

COMMENT ON VIEW v_active_workflows IS 'Currently active workflows with progress metrics';

-- Unresolved conflicts view
CREATE OR REPLACE VIEW v_unresolved_conflicts AS
SELECT
    c.conflict_id,
    c.workflow_id,
    w.workflow_name,
    c.conflict_type,
    c.severity,
    c.conflict_description,
    c.affected_flight_ids,
    c.detected_at,
    c.resolution_priority,
    c.assigned_to
FROM schedule_conflicts c
JOIN schedule_workflows w ON c.workflow_id = w.workflow_id
WHERE c.resolution_status IN ('pending', 'in_progress')
ORDER BY c.severity DESC, c.resolution_priority DESC, c.detected_at;

COMMENT ON VIEW v_unresolved_conflicts IS 'Pending and in-progress conflicts ordered by priority';

-- Agent performance view
CREATE OR REPLACE VIEW v_agent_performance AS
SELECT
    agent_name,
    COUNT(*) as total_executions,
    COUNT(*) FILTER (WHERE status = 'completed') as successful_executions,
    COUNT(*) FILTER (WHERE status = 'failed') as failed_executions,
    AVG(execution_time_ms) as avg_execution_time_ms,
    AVG(tokens_used) as avg_tokens_used,
    SUM(records_processed) as total_records_processed
FROM agent_executions
WHERE started_at >= NOW() - INTERVAL '7 days'
GROUP BY agent_name;

COMMENT ON VIEW v_agent_performance IS 'Agent performance metrics for last 7 days';

-- =====================================================
-- END OF WORKFLOW & AGENT TABLES SCHEMA
-- =====================================================
