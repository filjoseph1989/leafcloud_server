    #!/bin/bash

# Load environment variables from .env if present
if [ -f .env ]; then
    source .env
fi

# Default DB URL if not set
DB_URL=${DATABASE_URL:-"postgresql://fil:@localhost/leafcloud2"}

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
    echo "Usage: ./run-query.sh [--append] \"<sql_query>\""
    echo "Example: ./run-query.sh \"SELECT * FROM daily_readings WHERE experiment_id=4 ORDER BY id ASC;\""
    exit 1
fi

if [ "$APPEND" = true ]; then
    psql "$DB_URL" -c "$QUERY" >> database-query.result
else
    psql "$DB_URL" -c "$QUERY" > database-query.result
fi

echo "Query results saved to database-query.result"
code database-query.result