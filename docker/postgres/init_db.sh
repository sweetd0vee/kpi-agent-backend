#!/bin/bash
# Exit immediately if a command exits with a non-zero status.
set -e

# This script creates additional databases. The main database and user
# are created by the entrypoint script from the environment variables.
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" <<-EOSQL
    CREATE DATABASE server_metrics;
    CREATE DATABASE keycloak;
EOSQL