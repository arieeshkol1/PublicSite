# TAG Video Systems - Serverless Video Probe Monitoring

🎥 Real-time video probe monitoring system with serverless architecture

## Overview

This POC demonstrates a decoupled, serverless architecture for the TAG SaaS Control Plane. It ingests high-velocity telemetry from video probes, handles "Thundering Herd" scenarios using message queuing, and visualizes real-time health status with minimal operational overhead.

## Architecture

```
Python Simulator → API Gateway → SQS → Lambda → DynamoDB → Dashboard (S3)
```

**Key Components:**
- **API Gateway**: Public REST API for telemetry ingestion
- **SQS**: Message queue acting as shock absorber
- **Lambda (Node.js)**: Processes telemetry and evaluates health
- **DynamoDB**: Hot store for latest probe status
- **S3**: Static dashboard hosting

## Features

✅ Real-time probe monitoring  
✅ Health status evaluation (FPS-based)  
✅ Chaos engineering support (jitter, packet loss)  
✅ Serverless architecture (zero idle cost)  
✅ Sub-5-second end-to-end latency  
✅ Decoupled design (handles traffic spikes)

## Quick Start

### 1. Deploy Infrastructure

```bash
# Install dependencies
pip install -r infrastructure/requirements.txt
cd infrastructure/lambda && npm install && cd ../..

# Deploy to AWS
cdk bootstrap  # First time only
cdk deploy
```

### 2. Configure Dashboard

After deployment, you'll get:
- **API Endpoint**: `https://xxx.execute-api.us-east-1.amazonaws.com/prod`
- **Dashboard URL**: `http://xxx.s3-website-us-east-1.amazonaws.com`

Open the dashboard and paste the API endpoint.

### 3. Run Edge Simulator

```bash
cd edge-simulator
pip install -r requirements.txt

# Run demo with 2 probes
chmod +x run-demo.sh
./run-demo.sh https://YOUR-API-ENDPOINT/prod
```

Or run individual probes:

```bash
# Normal probe
python3 probe_simulator.py \
  --api https://YOUR-API-ENDPOINT/prod \
  --probe-id "Probe-A-Encoder" \
  --fps 30

# Chaos mode probe
python3 probe_simulator.py \
  --api https://YOUR-API-ENDPOINT/prod \
  --probe-id "Probe-B-CDN" \
  --fps 28 \
  --chaos --jitter --packet-loss
```

## Demo Walkthrough

1. **Baseline**: Start simulator → Dashboard shows 2 green probes
2. **The Glitch**: Chaos mode drops FPS below 25
3. **The Reaction**: Dashboard turns red within 5 seconds
4. **The Recovery**: FPS restored → Dashboard returns to green
5. **The Evidence**: Check CloudWatch logs for SQS flow

## Health Status Logic

- **FPS ≥ 25**: 🟢 HEALTHY (Green)
- **FPS < 25**: 🔴 CRITICAL (Red)

## Repository Structure

```
├── infrastructure/          # CDK infrastructure code
│   ├── app.py              # CDK app entry point
│   ├── stack.py            # Main stack definition
│   └── lambda/             # Lambda functions
│       ├── index.js        # Telemetry processor
│       ├── reader.js       # Probe status reader
│       └── package.json    # Node.js dependencies
├── dashboard/              # Static web dashboard
│   └── index.html          # Real-time monitoring UI
├── edge-simulator/         # Python probe simulator
│   ├── probe_simulator.py  # Main simulator script
│   ├── run-demo.sh         # Demo launcher
│   └── requirements.txt    # Python dependencies
└── .github/workflows/      # CI/CD pipeline
    └── deploy.yml          # Automated deployment
```

## Cost Optimization (FinOps)

- **Zero idle cost**: Pay only for actual usage
- **S3 hosting**: Pennies per month
- **Lambda**: Pay per request (free tier: 1M requests/month)
- **DynamoDB**: On-demand pricing (free tier: 25GB)
- **SQS**: First 1M requests free per month

## Development

### Local Testing

```bash
# Test Lambda locally
cd infrastructure/lambda
node index.js

# Test dashboard locally
cd dashboard
python3 -m http.server 8000
```

### Cleanup

```bash
cdk destroy
```

## Technical Stack

| Component | Technology | Rationale |
|-----------|-----------|-----------|
| IaC | AWS CDK (Python) | Repeatable infrastructure |
| Ingestion | API Gateway + SQS | Decoupled architecture |
| Compute | Lambda (Node.js) | Auto-scaling, efficient |
| Database | DynamoDB | Millisecond latency |
| Frontend | S3 Static Hosting | Zero server cost |

## Success Criteria

✅ End-to-end latency < 5 seconds  
✅ Handles traffic spikes via SQS  
✅ Real-time dashboard updates  
✅ Chaos engineering validation  
✅ CloudWatch evidence of decoupling

## AWS Account

- **Account ID**: 991105135552
- **Region**: us-east-1

## CI/CD

Automated deployment via GitHub Actions:
- Push to `main` → Auto-deploy
- Manual trigger available in Actions tab

## License

Proprietary - TAG Video Systems POC
