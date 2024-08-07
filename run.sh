#!/bin/bash

# Function to stop the services
stop_services() {
    echo "Stopping services..."
    pkill -f "npm run server"
    pkill -f "python -m src.api"
    exit
}

# Trap signals to stop services
trap stop_services SIGINT SIGTERM

# Start the server
python -m src.api &

# Start the frontend service
cd web
npm run server &

# Wait for all background jobs to finish
wait
