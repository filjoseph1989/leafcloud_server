#!/bin/bash

# Load environment variables from .env if present
if [ -f .env ]; then
    source .env
fi

# Default DB URL if not set
# Updated to leafcloud3 as per the recent database setup
DB_URL=${DATABASE_URL:-"postgresql://tin:@localhost/leafcloud3"}

APPEND=false
ARGS=()
for arg in "$@"; do
    if [ "$arg" = "--append" ]; then
        APPEND=true
    else
        ARGS+=("$arg")
    fi
done

QUERY="${ARGS[*]}"

if [ -z "$QUERY" ]; then
    echo "Usage: ./scripts/run-query.sh [--append] \"<sql_query>\""
    echo "Example: ./scripts/run-query.sh \"SELECT * FROM users;\""
    exit 1
fi

if [ "$APPEND" = true ]; then
    psql "$DB_URL" -c "$QUERY" >> database-query.result
else
    psql "$DB_URL" -c "$QUERY" > database-query.result
fi

echo "Query results saved to database-query.result"
