#!/bin/bash

# Function to stop the services
stop_services() {
    echo "Stopping services..."
    pkill -f "npm run server"
    pkill -f "flask --app=api run"
    exit
}

# Trap signals to stop services
trap stop_services SIGINT SIGTERM

# Start the frontend service
cd web
npm run server &

# Start the backend service
cd ../src
flask --app=api run &

# Wait for all background jobs to finish
wait
