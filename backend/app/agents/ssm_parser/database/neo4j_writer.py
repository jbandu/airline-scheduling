"""
Neo4j Knowledge Graph Writer
Updates Neo4j graph with flight schedule relationships
"""

from typing import Dict, Any, List


class Neo4jWriter:
    """Write flight data to Neo4j knowledge graph"""

    def __init__(self, neo4j_driver):
        """
        Initialize Neo4j writer

        Args:
            neo4j_driver: Neo4j driver instance
        """
        self.driver = neo4j_driver

    def update_from_ssm(
        self,
        parsed_data: Dict[str, Any],
        flight_ids: List[str]
    ):
        """
        Update Neo4j knowledge graph from parsed SSM data

        Creates/updates:
        - Flight nodes
        - Airport nodes
        - Aircraft nodes
        - Airline nodes
        - Relationships between entities
        """
        with self.driver.session() as session:
            # Create/update airline node
            session.run(
                """
                MERGE (airline:Airline {code: $code})
                ON CREATE SET airline.name = $name
                """,
                code=parsed_data.get("airline"),
                name=parsed_data.get("airline")
            )

            # Create/update airport nodes
            for airport_field in ["origin", "destination"]:
                if airport_field in parsed_data:
                    session.run(
                        """
                        MERGE (airport:Airport {code: $code})
                        """,
                        code=parsed_data[airport_field]
                    )

            # Create/update aircraft node
            if "aircraft_type" in parsed_data:
                session.run(
                    """
                    MERGE (aircraft:AircraftType {code: $code})
                    """,
                    code=parsed_data["aircraft_type"]
                )

            # Create flight node and relationships
            for flight_id in flight_ids:
                session.run(
                    """
                    MERGE (flight:Flight {id: $flight_id})
                    SET flight.number = $flight_number,
                        flight.departure_time = $departure,
                        flight.arrival_time = $arrival

                    WITH flight
                    MATCH (airline:Airline {code: $airline_code})
                    MERGE (airline)-[:OPERATES]->(flight)

                    WITH flight
                    MATCH (origin:Airport {code: $origin})
                    MERGE (flight)-[:DEPARTS_FROM]->(origin)

                    WITH flight
                    MATCH (dest:Airport {code: $destination})
                    MERGE (flight)-[:ARRIVES_AT]->(dest)

                    WITH flight
                    MATCH (aircraft:AircraftType {code: $aircraft_type})
                    MERGE (flight)-[:USES_AIRCRAFT]->(aircraft)
                    """,
                    flight_id=flight_id,
                    flight_number=f"{parsed_data['airline']}{parsed_data['flight_number']}",
                    departure=parsed_data.get("departure_time", ""),
                    arrival=parsed_data.get("arrival_time", ""),
                    airline_code=parsed_data["airline"],
                    origin=parsed_data.get("origin"),
                    destination=parsed_data.get("destination"),
                    aircraft_type=parsed_data.get("aircraft_type")
                )
