"""
FastAPI Main Application
Airline Schedule Management System
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from .api.ssm_routes import router as ssm_router
from .database import init_db_pool, init_neo4j, close_db_pool, close_neo4j


# Lifespan context manager
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler"""
    # Startup
    print("Initializing database connections...")
    init_db_pool()
    init_neo4j()
    print("Application started successfully")

    yield

    # Shutdown
    print("Closing database connections...")
    close_db_pool()
    close_neo4j()
    print("Application shutdown complete")


# Create FastAPI app
app = FastAPI(
    title="Airline Schedule Management System",
    description="Production-ready airline schedule management with 7 AI agents",
    version="1.0.0",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(ssm_router)


# Root endpoint
@app.get("/")
async def root():
    """API root endpoint"""
    return {
        "name": "Airline Schedule Management System",
        "version": "1.0.0",
        "description": "IATA SSM/SSIM processing with multi-agent AI",
        "agents": {
            "SSMParserAgent": "Parse and validate IATA schedule messages",
            "ScheduleValidationAgent": "Validate schedules against constraints",
            "ConflictResolutionAgent": "Detect and resolve conflicts",
            "FleetAssignmentAgent": "Optimize aircraft assignments",
            "CrewFeasibilityAgent": "Ensure crew availability",
            "SlotComplianceAgent": "Validate airport slots",
            "DistributionAgent": "Publish to GDS/OTA channels"
        },
        "endpoints": {
            "ssm": "/api/schedules/ssm",
            "docs": "/docs",
            "redoc": "/redoc"
        }
    }


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
