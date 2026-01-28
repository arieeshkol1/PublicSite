#!/bin/bash
# TAG Video Systems - Demo Script
# Runs two probes simultaneously with different configurations

if [ -z "$1" ]; then
    echo "Usage: ./run-demo.sh <API_ENDPOINT>"
    echo "Example: ./run-demo.sh https://xxx.execute-api.us-east-1.amazonaws.com/prod"
    exit 1
fi

API_ENDPOINT=$1

echo "Starting TAG Video Probe Demo..."
echo "API Endpoint: $API_ENDPOINT"
echo ""

# Start Probe A (Encoder) - Normal operation
echo "Starting Probe-A-Encoder (Normal)..."
python3 probe_simulator.py \
    --api "$API_ENDPOINT" \
    --probe-id "Probe-A-Encoder" \
    --fps 30 \
    --resolution "1920x1080" \
    --interval 2 &

PROBE_A_PID=$!

# Start Probe B (CDN) - With chaos mode
echo "Starting Probe-B-CDN (Chaos Mode)..."
python3 probe_simulator.py \
    --api "$API_ENDPOINT" \
    --probe-id "Probe-B-CDN" \
    --fps 28 \
    --resolution "1280x720" \
    --interval 2 \
    --chaos \
    --jitter \
    --packet-loss &

PROBE_B_PID=$!

echo ""
echo "✓ Both probes started!"
echo "  Probe A PID: $PROBE_A_PID"
echo "  Probe B PID: $PROBE_B_PID"
echo ""
echo "Press Ctrl+C to stop all probes..."

# Wait for user interrupt
trap "kill $PROBE_A_PID $PROBE_B_PID 2>/dev/null; echo 'Stopped all probes'; exit" INT
wait
