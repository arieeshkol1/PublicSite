# TAG Video Systems - Serverless Video Probe Monitoring System

## Project Overview
**Owner:** Ariel Eshkol  
**Timeline:** 3 Days (Rapid Prototype)  
**Objective:** Validate a decoupled, serverless architecture for TAG SaaS Control Plane

## 1. Executive Summary
This POC demonstrates how to ingest high-velocity telemetry from video probes, handle "Thundering Herd" scenarios using message queuing, and visualize real-time health status with minimal operational overhead (FinOps).

## 2. Functional Requirements

### 2.1. Telemetry Simulation (The Edge)
- **Source:** Standalone Python script acting as "Edge" simulator
- **Protocol:** HTTP/HTTPS POST requests (simulating cURL)
- **Workload:**
  - Simulate 2 distinct Video Probes (Probe-A-Encoder, Probe-B-CDN)
  - JSON Payload:
    - ProbeID (String)
    - Timestamp (ISO 8601)
    - FPS (Float - Frames Per Second)
    - Resolution (String - e.g., "1920x1080")
- **Chaos Engineering:** Toggle to inject "Jitter" and "Packet Loss"

### 2.2. Ingestion & Decoupling
- **Endpoint:** Amazon API Gateway (REST API)
- **Buffering:** Amazon SQS as shock absorber
- **Constraint:** API returns 200 OK immediately upon queuing

### 2.3. Data Processing & Logic
- **Compute:** AWS Lambda (Node.js runtime)
- **Business Logic:**
  - Parse JSON payload
  - Evaluate Health Status:
    - FPS > 25: Status = HEALTHY (Green)
    - FPS < 25: Status = CRITICAL (Red)
  - Write normalized state to database

### 2.4. Data Storage
- **Hot Store:** Amazon DynamoDB
- **Schema:**
  - Partition Key: ProbeID
  - Attributes: Status, LastMetric, Timestamp

### 2.5. Visualization (Dashboard)
- **Interface:** Static HTML/JavaScript SPA
- **Hosting:** Amazon S3 (Static Web Hosting)
- **Data Retrieval:** Poll API every 1-2 seconds

## 3. Non-Functional Requirements

### 3.1. Reliability & Decoupling
- SQS prevents database overwhelm during "Thundering Herd"
- Malformed JSON must not block pipeline

### 3.2. Performance & Latency
- End-to-End Latency: < 5 seconds (Critical payload → Dashboard Red)
- Node.js Lambda uses async/await for efficient I/O

### 3.3. Cost Optimization (FinOps)
- Zero idle cost (S3 storage only)
- API Gateway Direct Integration to DynamoDB for read-path

## 4. Technical Stack

| Layer      | Service                  | Rationale                                    |
|------------|--------------------------|----------------------------------------------|
| IaC        | AWS CDK (TypeScript)     | Zero friction deployment and repeatability   |
| Ingest     | API Gateway + SQS        | Decouples producers from consumers           |
| Compute    | AWS Lambda (Node.js)     | High-concurrency JSON processing             |
| Database   | Amazon DynamoDB          | Millisecond latency for real-time lookups    |
| Frontend   | Amazon S3                | Lowest cost hosting model                    |

## 5. Success Criteria

The POC is successful if this sequence can be demonstrated:

1. **Baseline:** Python script starts. Dashboard shows 2 Green Icons (Probe A & B)
2. **The Glitch:** Python script injects fault (Probe A drops to 15 FPS)
3. **The Reaction:** Within seconds, Dashboard icon for Probe A turns Red
4. **The Recovery:** Python script restores normal FPS. Dashboard returns to Green
5. **The Evidence:** CloudWatch logs prove message flowed through SQS

## 6. Architecture Diagram

```
┌─────────────────┐
│  Python Script  │ (Edge Simulator)
│  Probe-A, B     │
└────────┬────────┘
         │ HTTP POST
         ▼
┌─────────────────┐
│  API Gateway    │ (Public REST API)
└────────┬────────┘
         │ Enqueue
         ▼
┌─────────────────┐
│   Amazon SQS    │ (Message Queue - Shock Absorber)
└────────┬────────┘
         │ Poll
         ▼
┌─────────────────┐
│  Lambda (Node)  │ (Process & Evaluate Health)
└────────┬────────┘
         │ Write
         ▼
┌─────────────────┐
│   DynamoDB      │ (Hot Store - Latest State)
└────────┬────────┘
         │ Read
         ▼
┌─────────────────┐
│  API Gateway    │ (Read API - Direct Integration)
└────────┬────────┘
         │ Poll (1-2s)
         ▼
┌─────────────────┐
│  S3 Dashboard   │ (Static HTML/JS SPA)
└─────────────────┘
```

## 7. Implementation Plan

### Phase 1: Infrastructure (CDK)
- Create CDK stack with:
  - DynamoDB table (ProbeID as partition key)
  - SQS queue
  - API Gateway (Ingestion endpoint)
  - Lambda function (Processor)
  - S3 bucket (Dashboard hosting)
  - IAM roles and permissions

### Phase 2: Backend Logic
- Lambda function (Node.js):
  - SQS event handler
  - JSON parsing
  - Health status evaluation
  - DynamoDB write operations

### Phase 3: API Layer
- API Gateway endpoints:
  - POST /telemetry (→ SQS)
  - GET /probes (→ DynamoDB direct integration)

### Phase 4: Frontend
- Static HTML/JS dashboard:
  - Real-time status display
  - Auto-refresh (1-2s polling)
  - Visual indicators (Green/Red)

### Phase 5: Edge Simulator
- Python script:
  - Simulate 2 probes
  - HTTP POST to API Gateway
  - Chaos engineering toggles
  - Configurable FPS/jitter

### Phase 6: Testing & Demo
- End-to-end testing
- Performance validation
- Demo walkthrough preparation
