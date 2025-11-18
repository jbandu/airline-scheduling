"""
SSM Parser Agent - IATA Schedule Message Processing
Intelligent agent for ingesting, parsing, validating, and transforming
IATA SSM/SSIM messages into structured database records.
"""

import json
import uuid
import logging
from datetime import datetime, date
from typing import TypedDict, List, Optional, Dict, Any, Literal
from enum import Enum

from langgraph.graph import StateGraph, END
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage

from .parsers.ssm_parser import SSMParser
from .parsers.ssim_parser import SSIMParser
from .validators.message_validator import MessageValidator
from .transformers.record_transformer import RecordTransformer
from .database.db_writer import DatabaseWriter
from .database.neo4j_writer import Neo4jWriter

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class MessageType(str, Enum):
    """IATA SSM Message Types"""
    NEW = "NEW"  # New flight schedule
    TIM = "TIM"  # Time change
    EQT = "EQT"  # Equipment/aircraft change
    CNL = "CNL"  # Cancellation
    CON = "CON"  # Continuation/restore
    SKD = "SKD"  # Full schedule dump request
    ACK = "ACK"  # Acknowledgment
    REJ = "REJ"  # Rejection
    RPL = "RPL"  # Replace
    ADM = "ADM"  # Administrative


class MessageFormat(str, Enum):
    """Message format types"""
    SSM = "SSM"
    SSIM = "SSIM"
    JSON = "JSON"
    UNKNOWN = "UNKNOWN"


class ProcessingStatus(str, Enum):
    """Processing status"""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    REJECTED = "rejected"


class SSMParserState(TypedDict):
    """State for SSM parsing workflow"""
    # Input
    raw_message: str
    message_id: str
    sender_airline: Optional[str]
    receiver_airline: Optional[str]

    # Detection
    message_type: Optional[str]
    message_format: Optional[str]

    # Parsing
    parsed_data: Optional[Dict[str, Any]]
    parsing_method: Optional[str]  # 'regex', 'llm', 'hybrid'

    # Validation
    validation_errors: List[str]
    validation_warnings: List[str]
    is_valid: bool

    # Transformation
    database_records: List[Dict[str, Any]]
    affected_flight_ids: List[str]

    # Persistence
    ssm_record_id: Optional[str]
    neo4j_updated: bool

    # Status
    processing_status: str
    error_message: Optional[str]

    # Metadata
    processed_at: Optional[datetime]
    processing_time_ms: Optional[int]
    llm_tokens_used: int
    confidence_score: Optional[float]


class SSMParserAgent:
    """
    SSM Parser Agent - Intelligent IATA SSM/SSIM message processor

    Capabilities:
    - Parse all IATA SSM message types (NEW, TIM, EQT, CNL, CON, SKD)
    - Parse SSIM Type 3 and Type 4 records
    - Validate against IATA standards
    - Transform to database schema
    - Update PostgreSQL and Neo4j
    - LLM-assisted parsing for ambiguous messages
    - Duplicate detection and idempotency
    """

    def __init__(
        self,
        db_connection,
        neo4j_driver,
        llm_model: str = "claude-sonnet-4-20250514",
        use_llm_fallback: bool = True
    ):
        """
        Initialize SSM Parser Agent

        Args:
            db_connection: PostgreSQL database connection
            neo4j_driver: Neo4j driver instance
            llm_model: Claude model for LLM-assisted parsing
            use_llm_fallback: Enable LLM fallback for complex messages
        """
        self.db = db_connection
        self.neo4j_driver = neo4j_driver
        self.use_llm_fallback = use_llm_fallback

        # Initialize LLM
        self.llm = ChatAnthropic(
            model=llm_model,
            temperature=0,
            max_tokens=4096
        )

        # Initialize components
        self.ssm_parser = SSMParser()
        self.ssim_parser = SSIMParser()
        self.validator = MessageValidator(db_connection)
        self.transformer = RecordTransformer()
        self.db_writer = DatabaseWriter(db_connection)
        self.neo4j_writer = Neo4jWriter(neo4j_driver)

        # Build LangGraph workflow
        self.graph = self._build_graph()

        logger.info(f"SSMParserAgent initialized with model: {llm_model}")

    def _build_graph(self) -> StateGraph:
        """
        Build LangGraph workflow for SSM processing

        Workflow:
        1. Detect message format (SSM vs SSIM)
        2. Parse message (regex-based or LLM-assisted)
        3. Validate parsed data
        4. Transform to database records
        5. Save to PostgreSQL
        6. Update Neo4j knowledge graph
        """
        workflow = StateGraph(SSMParserState)

        # Add nodes
        workflow.add_node("detect_format", self.detect_message_format)
        workflow.add_node("parse_ssm", self.parse_ssm_message)
        workflow.add_node("parse_ssim", self.parse_ssim_message)
        workflow.add_node("parse_with_llm", self.parse_with_llm_fallback)
        workflow.add_node("validate_parsed_data", self.validate_data)
        workflow.add_node("transform_to_records", self.transform_to_database_records)
        workflow.add_node("check_duplicates", self.check_duplicate_messages)
        workflow.add_node("save_to_database", self.save_records)
        workflow.add_node("update_knowledge_graph", self.update_neo4j)
        workflow.add_node("handle_errors", self.error_handler)
        workflow.add_node("generate_acknowledgment", self.generate_ack)

        # Set entry point
        workflow.set_entry_point("detect_format")

        # Route by detected format
        workflow.add_conditional_edges(
            "detect_format",
            self.route_by_format,
            {
                "ssm": "parse_ssm",
                "ssim": "parse_ssim",
                "unknown": "parse_with_llm"
            }
        )

        # After parsing, validate
        workflow.add_edge("parse_ssm", "validate_parsed_data")
        workflow.add_edge("parse_ssim", "validate_parsed_data")
        workflow.add_edge("parse_with_llm", "validate_parsed_data")

        # Route based on validation
        workflow.add_conditional_edges(
            "validate_parsed_data",
            self.check_validation,
            {
                "valid": "transform_to_records",
                "invalid": "handle_errors"
            }
        )

        # After transformation, check duplicates
        workflow.add_edge("transform_to_records", "check_duplicates")

        # Route based on duplicate check
        workflow.add_conditional_edges(
            "check_duplicates",
            self.route_after_duplicate_check,
            {
                "new": "save_to_database",
                "duplicate": "handle_errors",
                "update": "save_to_database"
            }
        )

        # After saving, update Neo4j
        workflow.add_edge("save_to_database", "update_knowledge_graph")

        # After Neo4j, generate ACK
        workflow.add_edge("update_knowledge_graph", "generate_acknowledgment")

        # End states
        workflow.add_edge("generate_acknowledgment", END)
        workflow.add_edge("handle_errors", END)

        return workflow.compile()

    def process(self, raw_message: str, **kwargs) -> Dict[str, Any]:
        """
        Process a single SSM/SSIM message

        Args:
            raw_message: Raw SSM/SSIM message text
            **kwargs: Additional parameters (sender_airline, receiver_airline, etc.)

        Returns:
            Processing result with status and details
        """
        start_time = datetime.now()

        # Initialize state
        initial_state: SSMParserState = {
            "raw_message": raw_message.strip(),
            "message_id": str(uuid.uuid4()),
            "sender_airline": kwargs.get("sender_airline"),
            "receiver_airline": kwargs.get("receiver_airline"),
            "message_type": None,
            "message_format": None,
            "parsed_data": None,
            "parsing_method": None,
            "validation_errors": [],
            "validation_warnings": [],
            "is_valid": False,
            "database_records": [],
            "affected_flight_ids": [],
            "ssm_record_id": None,
            "neo4j_updated": False,
            "processing_status": ProcessingStatus.PROCESSING.value,
            "error_message": None,
            "processed_at": None,
            "processing_time_ms": None,
            "llm_tokens_used": 0,
            "confidence_score": None
        }

        try:
            # Execute workflow
            logger.info(f"Processing SSM message: {initial_state['message_id']}")
            final_state = self.graph.invoke(initial_state)

            # Calculate processing time
            end_time = datetime.now()
            processing_time = (end_time - start_time).total_seconds() * 1000
            final_state["processing_time_ms"] = int(processing_time)
            final_state["processed_at"] = end_time

            logger.info(
                f"Message {final_state['message_id']} processed: "
                f"status={final_state['processing_status']}, "
                f"time={processing_time:.0f}ms"
            )

            return self._format_result(final_state)

        except Exception as e:
            logger.error(f"Error processing message: {str(e)}", exc_info=True)
            return {
                "message_id": initial_state["message_id"],
                "status": ProcessingStatus.FAILED.value,
                "error": str(e),
                "processing_time_ms": int((datetime.now() - start_time).total_seconds() * 1000)
            }

    def process_batch(
        self,
        messages: List[str],
        batch_size: int = 100
    ) -> Dict[str, Any]:
        """
        Process multiple SSM messages in batches

        Args:
            messages: List of raw SSM messages
            batch_size: Number of messages to process per batch

        Returns:
            Batch processing results
        """
        logger.info(f"Processing batch of {len(messages)} messages")

        results = {
            "total": len(messages),
            "successful": 0,
            "failed": 0,
            "rejected": 0,
            "results": []
        }

        # Process in batches
        for i in range(0, len(messages), batch_size):
            batch = messages[i:i + batch_size]
            logger.info(f"Processing batch {i // batch_size + 1}")

            for message in batch:
                result = self.process(message)
                results["results"].append(result)

                if result["status"] == ProcessingStatus.COMPLETED.value:
                    results["successful"] += 1
                elif result["status"] == ProcessingStatus.REJECTED.value:
                    results["rejected"] += 1
                else:
                    results["failed"] += 1

        logger.info(
            f"Batch processing complete: "
            f"{results['successful']} successful, "
            f"{results['failed']} failed, "
            f"{results['rejected']} rejected"
        )

        return results

    # =========================================================================
    # WORKFLOW NODES
    # =========================================================================

    def detect_message_format(self, state: SSMParserState) -> SSMParserState:
        """Detect message format (SSM, SSIM, or unknown)"""
        raw_message = state["raw_message"]

        # Check for SSM format (starts with message type)
        ssm_pattern = r"^(NEW|TIM|EQT|CNL|CON|SKD|RPL|ADM)"
        if raw_message.strip().startswith(tuple(MessageType)):
            state["message_format"] = MessageFormat.SSM.value
            # Extract message type (first word)
            state["message_type"] = raw_message.split()[0].upper()

        # Check for SSIM format (starts with '3 ' or '4 ')
        elif raw_message.strip().startswith(('3 ', '4 ')):
            state["message_format"] = MessageFormat.SSIM.value
            state["message_type"] = "SSIM"

        else:
            state["message_format"] = MessageFormat.UNKNOWN.value
            logger.warning(f"Unknown message format: {raw_message[:50]}...")

        logger.info(
            f"Detected format: {state['message_format']}, "
            f"type: {state['message_type']}"
        )

        return state

    def parse_ssm_message(self, state: SSMParserState) -> SSMParserState:
        """Parse SSM format message using regex"""
        try:
            parsed_data = self.ssm_parser.parse(
                state["raw_message"],
                state["message_type"]
            )
            state["parsed_data"] = parsed_data
            state["parsing_method"] = "regex"
            state["confidence_score"] = parsed_data.get("confidence", 1.0)

            logger.info(f"SSM parsed successfully: {state['message_type']}")

        except Exception as e:
            logger.error(f"SSM parsing failed: {str(e)}")
            # Try LLM fallback if enabled
            if self.use_llm_fallback:
                state["parsing_method"] = "llm_fallback"
                return self.parse_with_llm_fallback(state)
            else:
                state["validation_errors"].append(f"Parsing failed: {str(e)}")

        return state

    def parse_ssim_message(self, state: SSMParserState) -> SSMParserState:
        """Parse SSIM format message"""
        try:
            parsed_data = self.ssim_parser.parse(state["raw_message"])
            state["parsed_data"] = parsed_data
            state["parsing_method"] = "regex"
            state["confidence_score"] = parsed_data.get("confidence", 1.0)

            logger.info("SSIM parsed successfully")

        except Exception as e:
            logger.error(f"SSIM parsing failed: {str(e)}")
            if self.use_llm_fallback:
                state["parsing_method"] = "llm_fallback"
                return self.parse_with_llm_fallback(state)
            else:
                state["validation_errors"].append(f"Parsing failed: {str(e)}")

        return state

    def parse_with_llm_fallback(self, state: SSMParserState) -> SSMParserState:
        """Use Claude to parse ambiguous or complex messages"""
        logger.info("Using LLM-assisted parsing")

        try:
            parsed_data = self._llm_assisted_parse(state["raw_message"])
            state["parsed_data"] = parsed_data
            state["parsing_method"] = "llm"
            state["confidence_score"] = parsed_data.get("confidence", 0.8)
            state["llm_tokens_used"] = parsed_data.get("tokens_used", 0)

            logger.info("LLM parsing successful")

        except Exception as e:
            logger.error(f"LLM parsing failed: {str(e)}")
            state["validation_errors"].append(f"LLM parsing failed: {str(e)}")

        return state

    def validate_data(self, state: SSMParserState) -> SSMParserState:
        """Validate parsed data against IATA standards"""
        if not state["parsed_data"]:
            state["is_valid"] = False
            state["validation_errors"].append("No parsed data available")
            return state

        try:
            validation_result = self.validator.validate(
                state["parsed_data"],
                state["message_type"]
            )

            state["validation_errors"] = validation_result["errors"]
            state["validation_warnings"] = validation_result["warnings"]
            state["is_valid"] = validation_result["is_valid"]

            if state["is_valid"]:
                logger.info("Validation passed")
            else:
                logger.warning(
                    f"Validation failed: {len(state['validation_errors'])} errors"
                )

        except Exception as e:
            logger.error(f"Validation error: {str(e)}")
            state["is_valid"] = False
            state["validation_errors"].append(f"Validation error: {str(e)}")

        return state

    def transform_to_database_records(self, state: SSMParserState) -> SSMParserState:
        """Transform parsed data to database schema"""
        try:
            records = self.transformer.transform(
                state["parsed_data"],
                state["message_type"],
                state["message_id"]
            )

            state["database_records"] = records
            state["affected_flight_ids"] = [
                r["flight_id"] for r in records if "flight_id" in r
            ]

            logger.info(f"Transformed to {len(records)} database records")

        except Exception as e:
            logger.error(f"Transformation error: {str(e)}")
            state["validation_errors"].append(f"Transformation error: {str(e)}")
            state["is_valid"] = False

        return state

    def check_duplicate_messages(self, state: SSMParserState) -> SSMParserState:
        """Check for duplicate SSM messages"""
        try:
            duplicate_status = self.db_writer.check_duplicate(
                state["parsed_data"],
                state["message_type"]
            )

            state["duplicate_status"] = duplicate_status

            logger.info(f"Duplicate check: {duplicate_status}")

        except Exception as e:
            logger.error(f"Duplicate check error: {str(e)}")
            state["duplicate_status"] = "new"  # Default to new

        return state

    def save_records(self, state: SSMParserState) -> SSMParserState:
        """Save records to PostgreSQL"""
        try:
            result = self.db_writer.save(
                state["database_records"],
                state["raw_message"],
                state["message_type"],
                state["message_format"],
                state["parsed_data"],
                state["validation_errors"]
            )

            state["ssm_record_id"] = result["ssm_record_id"]
            state["affected_flight_ids"] = result["affected_flight_ids"]

            logger.info(f"Records saved: SSM ID {state['ssm_record_id']}")

        except Exception as e:
            logger.error(f"Database save error: {str(e)}")
            state["error_message"] = f"Database save failed: {str(e)}"
            state["processing_status"] = ProcessingStatus.FAILED.value

        return state

    def update_neo4j(self, state: SSMParserState) -> SSMParserState:
        """Update Neo4j knowledge graph"""
        try:
            self.neo4j_writer.update_from_ssm(
                state["parsed_data"],
                state["affected_flight_ids"]
            )

            state["neo4j_updated"] = True
            logger.info("Neo4j updated successfully")

        except Exception as e:
            logger.error(f"Neo4j update error: {str(e)}")
            # Don't fail the whole process if Neo4j fails
            state["neo4j_updated"] = False
            state["validation_warnings"].append(f"Neo4j update failed: {str(e)}")

        return state

    def error_handler(self, state: SSMParserState) -> SSMParserState:
        """Handle errors and generate rejection message"""
        state["processing_status"] = ProcessingStatus.REJECTED.value

        if state["validation_errors"]:
            state["error_message"] = "; ".join(state["validation_errors"])

        logger.error(f"Message rejected: {state['error_message']}")

        return state

    def generate_ack(self, state: SSMParserState) -> SSMParserState:
        """Generate IATA-compliant ACK message"""
        if state["processing_status"] != ProcessingStatus.REJECTED.value:
            state["processing_status"] = ProcessingStatus.COMPLETED.value
            state["acknowledgment"] = self._generate_ack_message(state)
        else:
            state["acknowledgment"] = self._generate_rej_message(state)

        return state

    # =========================================================================
    # ROUTING FUNCTIONS
    # =========================================================================

    def route_by_format(self, state: SSMParserState) -> str:
        """Route based on detected message format"""
        format_type = state["message_format"]

        if format_type == MessageFormat.SSM.value:
            return "ssm"
        elif format_type == MessageFormat.SSIM.value:
            return "ssim"
        else:
            return "unknown"

    def check_validation(self, state: SSMParserState) -> str:
        """Route based on validation result"""
        return "valid" if state["is_valid"] else "invalid"

    def route_after_duplicate_check(self, state: SSMParserState) -> str:
        """Route based on duplicate check result"""
        return state.get("duplicate_status", "new")

    # =========================================================================
    # HELPER METHODS
    # =========================================================================

    def _llm_assisted_parse(self, raw_message: str) -> Dict[str, Any]:
        """Use Claude to parse complex or ambiguous SSM messages"""

        system_prompt = """You are an expert in IATA SSM and SSIM message formats.
Parse airline schedule messages with precision according to IATA standards.

SSM Format Examples:
- NEW CM 0100 J PTY MIA 1234567 1DEC24 31MAR25 738 0715 0945 0230 E0 M JP
- TIM CM 0100 J PTY MIA 1234567 1DEC24 31MAR25 0725 0955
- EQT CM 0100 PTY MIA 1234567 1DEC24 31MAR25 73J
- CNL CM 0100 PTY MIA 1234567 15JAN25 20JAN25

SSIM Format Example:
- 3 CM 0100JPTYMIA1234567 01DEC2431MAR25738 0715 0945 0230 E0 M JP

Return a JSON object with all extracted fields. Include a 'confidence' score (0-1)
and list any 'ambiguities' found."""

        user_prompt = f"""Parse this airline schedule message:

{raw_message}

Extract all fields according to IATA standards and return as JSON."""

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt)
        ]

        response = self.llm.invoke(messages)

        # Parse JSON from response
        try:
            parsed_data = json.loads(response.content)
            parsed_data["tokens_used"] = response.usage_metadata.get("total_tokens", 0)
            return parsed_data
        except json.JSONDecodeError:
            # Try to extract JSON from markdown code blocks
            content = response.content
            if "```json" in content:
                json_str = content.split("```json")[1].split("```")[0].strip()
                parsed_data = json.loads(json_str)
                parsed_data["tokens_used"] = response.usage_metadata.get("total_tokens", 0)
                return parsed_data
            raise

    def _generate_ack_message(self, state: SSMParserState) -> str:
        """Generate IATA ACK (acknowledgment) message"""
        return f"ACK {state['message_id']} {state['message_type']} PROCESSED"

    def _generate_rej_message(self, state: SSMParserState) -> str:
        """Generate IATA REJ (rejection) message"""
        return f"REJ {state['message_id']} {state['message_type']} {state['error_message']}"

    def _format_result(self, state: SSMParserState) -> Dict[str, Any]:
        """Format final result for API response"""
        return {
            "message_id": state["message_id"],
            "status": state["processing_status"],
            "message_type": state["message_type"],
            "message_format": state["message_format"],
            "parsing_method": state["parsing_method"],
            "confidence_score": state["confidence_score"],
            "affected_flight_ids": state["affected_flight_ids"],
            "ssm_record_id": state["ssm_record_id"],
            "neo4j_updated": state["neo4j_updated"],
            "validation_errors": state["validation_errors"],
            "validation_warnings": state["validation_warnings"],
            "acknowledgment": state.get("acknowledgment"),
            "processed_at": state["processed_at"].isoformat() if state["processed_at"] else None,
            "processing_time_ms": state["processing_time_ms"],
            "llm_tokens_used": state["llm_tokens_used"]
        }
