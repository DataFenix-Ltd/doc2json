"""Destination connectors for writing extraction results."""

from doc2json.connectors.destinations.jsonl import JSONLDestination
from doc2json.connectors import register_destination

# Register built-in destinations
register_destination("jsonl", JSONLDestination)

# Register optional connectors (only if dependencies are available)
try:
    from doc2json.connectors.destinations.postgres import PostgresDestination
    register_destination("postgres", PostgresDestination)
except ImportError:
    pass  # psycopg2 not installed

try:
    from doc2json.connectors.destinations.mongodb import MongoDBDestination
    register_destination("mongodb", MongoDBDestination)
except ImportError:
    pass  # pymongo not installed

try:
    from doc2json.connectors.destinations.snowflake import SnowflakeDestination
    register_destination("snowflake", SnowflakeDestination)
except ImportError:
    pass  # snowflake-connector-python not installed

try:
    from doc2json.connectors.destinations.bigquery import BigQueryDestination
    register_destination("bigquery", BigQueryDestination)
except ImportError:
    pass  # google-cloud-bigquery not installed

try:
    from doc2json.connectors.destinations.sql import SQLDestination
    register_destination("sql", SQLDestination)
except ImportError:
    pass  # sqlalchemy not installed
