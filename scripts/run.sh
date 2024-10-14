#!/bin/bash

# Function to stop the services
stop_services() {
    echo "Stopping services..."
    pkill -f "npm run server"
    pkill -f "uvicorn src.main:app --host 0.0.0.0 --port 5000 --reload"
    exit
}

# Trap signals to stop services
trap stop_services SIGINT SIGTERM

# Start the server
uvicorn src.main:app --host 0.0.0.0 --port 5000 --reload &

# Start the frontend service
cd web
npm run server &

# Wait for all background jobs to finish
wait
