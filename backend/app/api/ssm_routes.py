"""
FastAPI Routes for SSM/SSIM Message Processing
Endpoints for ingesting and processing airline schedule messages
"""

from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime

from ..agents.ssm_parser.agent import SSMParserAgent
from ..database import get_db_connection, get_neo4j_driver


router = APIRouter(prefix="/api/schedules/ssm", tags=["SSM Processing"])


# ============================================================================
# REQUEST/RESPONSE MODELS
# ============================================================================

class SSMMessageInput(BaseModel):
    """SSM message input"""
    message: str = Field(..., description="Raw SSM/SSIM message text")
    sender_airline: Optional[str] = Field(None, description="Sender airline code")
    receiver_airline: Optional[str] = Field(None, description="Receiver airline code")

    class Config:
        json_schema_extra = {
            "example": {
                "message": "NEW CM 0100 J PTY MIA 1234567 1DEC24 31MAR25 738 0715 0945",
                "sender_airline": "CM"
            }
        }


class SSMBatchInput(BaseModel):
    """Batch SSM messages input"""
    messages: List[str] = Field(..., description="List of raw SSM messages")
    batch_size: int = Field(100, description="Batch processing size", ge=1, le=1000)


class SSMProcessingResponse(BaseModel):
    """SSM processing response"""
    message_id: str
    status: str
    message_type: Optional[str]
    message_format: Optional[str]
    parsing_method: Optional[str]
    confidence_score: Optional[float]
    affected_flight_ids: List[str]
    ssm_record_id: Optional[str]
    validation_errors: List[str]
    validation_warnings: List[str]
    processing_time_ms: Optional[int]


class SSMBatchResponse(BaseModel):
    """Batch processing response"""
    total: int
    successful: int
    failed: int
    rejected: int
    results: List[SSMProcessingResponse]


# ============================================================================
# DEPENDENCY INJECTION
# ============================================================================

def get_ssm_agent():
    """Get SSM Parser Agent instance"""
    db = get_db_connection()
    neo4j = get_neo4j_driver()

    return SSMParserAgent(
        db_connection=db,
        neo4j_driver=neo4j,
        use_llm_fallback=True
    )


# ============================================================================
# ENDPOINTS
# ============================================================================

@router.post("/ingest", response_model=SSMProcessingResponse)
async def ingest_ssm_message(
    input_data: SSMMessageInput,
    agent: SSMParserAgent = Depends(get_ssm_agent)
):
    """
    Ingest and process a single SSM/SSIM message

    **Supported Message Types:**
    - NEW: New flight schedule
    - TIM: Time change
    - EQT: Equipment change
    - CNL: Cancellation
    - CON: Continuation/restore
    - RPL: Replace
    - SKD: Schedule dump request

    **Example SSM Messages:**
    ```
    NEW CM 0100 J PTY MIA 1234567 1DEC24 31MAR25 738 0715 0945
    TIM CM 0100 J PTY MIA 1234567 1DEC24 31MAR25 0725 0955
    EQT CM 0100 PTY MIA 1234567 1DEC24 31MAR25 73J
    CNL CM 0100 PTY MIA 1234567 15JAN25 20JAN25
    ```

    **Returns:**
    - Processing result with status and flight IDs
    """
    try:
        result = agent.process(
            input_data.message,
            sender_airline=input_data.sender_airline,
            receiver_airline=input_data.receiver_airline
        )

        return SSMProcessingResponse(**result)

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Processing failed: {str(e)}")


@router.post("/batch", response_model=SSMBatchResponse)
async def ingest_ssm_batch(
    input_data: SSMBatchInput,
    background_tasks: BackgroundTasks,
    agent: SSMParserAgent = Depends(get_ssm_agent)
):
    """
    Ingest and process multiple SSM messages in batch

    **Features:**
    - Process up to 1000 messages per request
    - Configurable batch size
    - Automatic error handling per message
    - Progress tracking

    **Example:**
    ```json
    {
        "messages": [
            "NEW CM 0100 J PTY MIA 1234567 1DEC24 31MAR25 738 0715 0945",
            "NEW CM 0102 J PTY JFK 1234567 1DEC24 31MAR25 738 0830 1445"
        ],
        "batch_size": 100
    }
    ```

    **Returns:**
    - Batch processing results with success/failure counts
    """
    try:
        result = agent.process_batch(
            input_data.messages,
            batch_size=input_data.batch_size
        )

        # Convert to response model
        return SSMBatchResponse(
            total=result["total"],
            successful=result["successful"],
            failed=result["failed"],
            rejected=result["rejected"],
            results=[SSMProcessingResponse(**r) for r in result["results"]]
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Batch processing failed: {str(e)}")


@router.get("/messages/{message_id}")
async def get_ssm_message_status(message_id: str):
    """
    Get processing status of an SSM message

    **Returns:**
    - Message details, processing status, and affected flights
    """
    db = get_db_connection()
    cursor = db.cursor()

    try:
        cursor.execute(
            """
            SELECT
                message_id,
                message_type,
                message_format,
                processing_status,
                validation_errors,
                affected_flight_ids,
                received_at,
                processed_at
            FROM ssm_messages
            WHERE message_id = %s
            """,
            (message_id,)
        )

        result = cursor.fetchone()

        if not result:
            raise HTTPException(status_code=404, detail="Message not found")

        return {
            "message_id": result[0],
            "message_type": result[1],
            "message_format": result[2],
            "processing_status": result[3],
            "validation_errors": result[4],
            "affected_flight_ids": result[5],
            "received_at": result[6].isoformat() if result[6] else None,
            "processed_at": result[7].isoformat() if result[7] else None
        }

    finally:
        cursor.close()


@router.post("/messages/{message_id}/reprocess")
async def reprocess_failed_message(
    message_id: str,
    agent: SSMParserAgent = Depends(get_ssm_agent)
):
    """
    Reprocess a failed SSM message

    **Use Cases:**
    - Retry after fixing validation issues
    - Reprocess with updated reference data
    - Manual intervention for complex messages

    **Returns:**
    - New processing result
    """
    db = get_db_connection()
    cursor = db.cursor()

    try:
        # Get original message
        cursor.execute(
            "SELECT raw_message, sender_airline FROM ssm_messages WHERE message_id = %s",
            (message_id,)
        )

        result = cursor.fetchone()

        if not result:
            raise HTTPException(status_code=404, detail="Message not found")

        raw_message, sender_airline = result

        # Reprocess
        result = agent.process(raw_message, sender_airline=sender_airline)

        return SSMProcessingResponse(**result)

    finally:
        cursor.close()


@router.get("/statistics")
async def get_ssm_statistics():
    """
    Get SSM processing statistics

    **Returns:**
    - Total messages processed
    - Success/failure rates
    - Processing times
    - Message type distribution
    """
    db = get_db_connection()
    cursor = db.cursor()

    try:
        # Overall statistics
        cursor.execute(
            """
            SELECT
                COUNT(*) as total_messages,
                COUNT(*) FILTER (WHERE processing_status = 'completed') as successful,
                COUNT(*) FILTER (WHERE processing_status = 'failed') as failed,
                COUNT(*) FILTER (WHERE processing_status = 'rejected') as rejected,
                AVG(EXTRACT(EPOCH FROM (processed_at - received_at)) * 1000)::INT as avg_processing_ms
            FROM ssm_messages
            WHERE received_at >= NOW() - INTERVAL '24 hours'
            """
        )

        stats = cursor.fetchone()

        # Message type distribution
        cursor.execute(
            """
            SELECT
                message_type,
                COUNT(*) as count
            FROM ssm_messages
            WHERE received_at >= NOW() - INTERVAL '24 hours'
            GROUP BY message_type
            ORDER BY count DESC
            """
        )

        type_distribution = {row[0]: row[1] for row in cursor.fetchall()}

        return {
            "last_24_hours": {
                "total_messages": stats[0],
                "successful": stats[1],
                "failed": stats[2],
                "rejected": stats[3],
                "avg_processing_time_ms": stats[4]
            },
            "message_type_distribution": type_distribution
        }

    finally:
        cursor.close()


@router.delete("/messages/{message_id}")
async def delete_ssm_message(message_id: str):
    """
    Delete an SSM message record

    **Warning:** This is a destructive operation
    """
    db = get_db_connection()
    cursor = db.cursor()

    try:
        cursor.execute(
            "DELETE FROM ssm_messages WHERE message_id = %s RETURNING message_id",
            (message_id,)
        )

        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Message not found")

        db.commit()

        return {"message": "Message deleted successfully", "message_id": message_id}

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Delete failed: {str(e)}")

    finally:
        cursor.close()
