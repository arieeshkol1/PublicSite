#!/usr/bin/env python3
"""
TAG Video Systems - Edge Simulator
Simulates video probe telemetry with chaos engineering capabilities
"""
import requests
import json
import time
import random
from datetime import datetime
import argparse


class VideoProbeSimulator:
    def __init__(self, api_endpoint, probe_id, base_fps=30, resolution="1920x1080"):
        self.api_endpoint = api_endpoint
        self.probe_id = probe_id
        self.base_fps = base_fps
        self.resolution = resolution
        self.chaos_mode = False
        self.jitter_enabled = False
        self.packet_loss_enabled = False
        self.variance_enabled = True  # Always enable variance for realistic simulation
        
        # Resolution options for variance
        self.resolutions = [
            "1920x1080", "1280x720", "3840x2160", "2560x1440", "1024x576"
        ]

    def generate_telemetry(self):
        """Generate telemetry payload with optional chaos and variance"""
        fps = self.base_fps
        resolution = self.resolution

        # Add natural variance (±2 FPS) for realistic simulation
        if self.variance_enabled:
            fps += random.uniform(-2, 2)
            
            # Occasionally change resolution (10% chance)
            if random.random() < 0.1:
                resolution = random.choice(self.resolutions)

        if self.chaos_mode:
            if self.jitter_enabled:
                # Add random jitter (±10 FPS)
                fps += random.uniform(-10, 10)
            
            if self.packet_loss_enabled:
                # Simulate packet loss (FPS drops significantly)
                if random.random() < 0.3:  # 30% chance of packet loss
                    fps = random.uniform(10, 20)

        # Ensure FPS doesn't go negative
        fps = max(0, fps)

        payload = {
            "ProbeID": self.probe_id,
            "Timestamp": datetime.utcnow().isoformat() + "Z",
            "FPS": round(fps, 2),
            "Resolution": resolution
        }

        return payload

    def send_telemetry(self, payload):
        """Send telemetry to API Gateway"""
        try:
            response = requests.post(
                f"{self.api_endpoint}/telemetry",
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=5
            )
            
            if response.status_code == 200:
                status = "🟢 HEALTHY" if payload["FPS"] >= 25 else "🔴 CRITICAL"
                print(f"[{payload['Timestamp']}] {self.probe_id}: FPS={payload['FPS']:.2f} {status}")
                return True
            else:
                print(f"❌ Error: HTTP {response.status_code} - {response.text}")
                return False
                
        except requests.exceptions.RequestException as e:
            print(f"❌ Network error: {e}")
            return False

    def run(self, interval=1):
        """Run the simulator continuously"""
        print(f"\n{'='*60}")
        print(f"🎥 TAG Video Probe Simulator")
        print(f"{'='*60}")
        print(f"Probe ID: {self.probe_id}")
        print(f"API Endpoint: {self.api_endpoint}")
        print(f"Base FPS: {self.base_fps}")
        print(f"Resolution: {self.resolution}")
        print(f"Interval: {interval}s")
        print(f"Variance: ENABLED (±2 FPS, occasional resolution changes)")
        print(f"Chaos Mode: {'ENABLED' if self.chaos_mode else 'DISABLED'}")
        if self.chaos_mode:
            print(f"  - Jitter: {'ON' if self.jitter_enabled else 'OFF'}")
            print(f"  - Packet Loss: {'ON' if self.packet_loss_enabled else 'OFF'}")
        print(f"{'='*60}\n")

        try:
            while True:
                payload = self.generate_telemetry()
                self.send_telemetry(payload)
                time.sleep(interval)
        except KeyboardInterrupt:
            print("\n\n⏹️  Simulator stopped by user")


def main():
    parser = argparse.ArgumentParser(
        description="TAG Video Systems - Video Probe Simulator"
    )
    parser.add_argument(
        "--api",
        required=True,
        help="API Gateway endpoint (e.g., https://xxx.execute-api.us-east-1.amazonaws.com/prod)"
    )
    parser.add_argument(
        "--probe-id",
        default="Probe-A-Encoder",
        help="Probe identifier (default: Probe-A-Encoder)"
    )
    parser.add_argument(
        "--fps",
        type=float,
        default=30.0,
        help="Base FPS (default: 30)"
    )
    parser.add_argument(
        "--resolution",
        default="1920x1080",
        help="Video resolution (default: 1920x1080)"
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=1.0,
        help="Telemetry send interval in seconds (default: 1)"
    )
    parser.add_argument(
        "--chaos",
        action="store_true",
        help="Enable chaos engineering mode"
    )
    parser.add_argument(
        "--jitter",
        action="store_true",
        help="Enable FPS jitter (requires --chaos)"
    )
    parser.add_argument(
        "--packet-loss",
        action="store_true",
        help="Enable packet loss simulation (requires --chaos)"
    )

    args = parser.parse_args()

    # Create simulator
    simulator = VideoProbeSimulator(
        api_endpoint=args.api,
        probe_id=args.probe_id,
        base_fps=args.fps,
        resolution=args.resolution
    )

    # Configure chaos mode
    if args.chaos:
        simulator.chaos_mode = True
        simulator.jitter_enabled = args.jitter
        simulator.packet_loss_enabled = args.packet_loss

    # Run simulator
    simulator.run(interval=args.interval)


if __name__ == "__main__":
    main()
