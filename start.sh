#!/bin/bash
# Navigate to the script's directory
cd "$(dirname "$0")"

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "Error: 'venv' directory not found in '$(pwd)'."
    echo "Please create a virtual environment and install dependencies first."
    exit 1
fi

# Run the uvicorn server on port 8000
echo "Starting Personal Finz on http://127.0.0.1:8000..."
DB_PATH=personal_finz.db ./venv/bin/uvicorn api.main:app --host 127.0.0.1 --port 8000 --reload
