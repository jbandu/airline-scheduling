"""
Database Connection Management
Provides connection pools for PostgreSQL and Neo4j
"""

import os
from typing import Optional
import psycopg2
from psycopg2 import pool
from neo4j import GraphDatabase


# PostgreSQL connection pool
_pg_pool: Optional[pool.SimpleConnectionPool] = None

# Neo4j driver
_neo4j_driver: Optional[GraphDatabase.driver] = None


def init_db_pool(
    min_conn: int = 1,
    max_conn: int = 10,
    database_url: str = None
):
    """
    Initialize PostgreSQL connection pool

    Args:
        min_conn: Minimum number of connections
        max_conn: Maximum number of connections
        database_url: PostgreSQL connection URL
    """
    global _pg_pool

    if _pg_pool is not None:
        return

    if database_url is None:
        database_url = os.getenv(
            "DATABASE_URL",
            "postgresql://postgres:postgres@localhost:5432/airline_scheduling"
        )

    _pg_pool = psycopg2.pool.SimpleConnectionPool(
        min_conn,
        max_conn,
        database_url
    )


def get_db_connection():
    """
    Get PostgreSQL database connection from pool

    Returns:
        psycopg2 connection
    """
    global _pg_pool

    if _pg_pool is None:
        init_db_pool()

    return _pg_pool.getconn()


def release_db_connection(conn):
    """
    Release PostgreSQL connection back to pool

    Args:
        conn: Connection to release
    """
    global _pg_pool

    if _pg_pool is not None:
        _pg_pool.putconn(conn)


def close_db_pool():
    """Close PostgreSQL connection pool"""
    global _pg_pool

    if _pg_pool is not None:
        _pg_pool.closeall()
        _pg_pool = None


def init_neo4j(uri: str = None, user: str = None, password: str = None):
    """
    Initialize Neo4j driver

    Args:
        uri: Neo4j URI
        user: Neo4j username
        password: Neo4j password
    """
    global _neo4j_driver

    if _neo4j_driver is not None:
        return

    if uri is None:
        uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    if user is None:
        user = os.getenv("NEO4J_USER", "neo4j")
    if password is None:
        password = os.getenv("NEO4J_PASSWORD", "password")

    _neo4j_driver = GraphDatabase.driver(uri, auth=(user, password))


def get_neo4j_driver():
    """
    Get Neo4j driver

    Returns:
        Neo4j driver instance
    """
    global _neo4j_driver

    if _neo4j_driver is None:
        init_neo4j()

    return _neo4j_driver


def close_neo4j():
    """Close Neo4j driver"""
    global _neo4j_driver

    if _neo4j_driver is not None:
        _neo4j_driver.close()
        _neo4j_driver = None


# Context managers
class DatabaseConnection:
    """Context manager for PostgreSQL connections"""

    def __enter__(self):
        self.conn = get_db_connection()
        return self.conn

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.conn:
            release_db_connection(self.conn)


class Neo4jSession:
    """Context manager for Neo4j sessions"""

    def __enter__(self):
        driver = get_neo4j_driver()
        self.session = driver.session()
        return self.session

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            self.session.close()
