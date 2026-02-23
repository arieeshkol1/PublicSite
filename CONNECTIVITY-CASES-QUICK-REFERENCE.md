# Connectivity Cases - Quick Reference Card

## 🎯 Two Connectivity Patterns

---

## 📱 CASE 1: End User (Tenant Login)

### Flow
```
User → CloudFront → ALB → EC2 → Cognito/RDS
```

### Details
| Aspect | Value |
|--------|-------|
| **Protocol** | HTTPS (443) |
| **Auth** | Cognito (SSO + MFA) |
| **Latency** | <200ms |
| **Entry** | CloudFront CDN |
| **Security** | WAF + DDoS Shield |
| **Pattern** | Request/Response |

### Use Case
Warehouse manager logs into WMS web application to view inventory, process orders, manage staff.

---

## 🤖 CASE 2: IoT Device (Robot/Sensor)

### Flow
```
Device → IoT Core → Rules Engine → Kinesis/Lambda/DynamoDB
```

### Details
| Aspect | Value |
|--------|-------|
| **Protocol** | MQTT/TLS (8883) |
| **Auth** | X.509 Certificates |
| **Latency** | <50ms |
| **Entry** | AWS IoT Core |
| **Security** | Certificate Rotation |
| **Pattern** | Persistent Connection |

### Device Types
- 🤖 Autonomous Robots (position, battery, tasks)
- 📡 RFID Sensors (tag reads, inventory)
- 📦 Smart Shelves (weight, stock levels)
- 🔍 Barcode Scanners (scan events)
- 🌡️ Temperature Sensors (cold storage)

### Data Paths
1. **Real-Time:** Kinesis → Lambda → DynamoDB
2. **Analytics:** Firehose → S3 → Athena
3. **Alerts:** IoT Events → SNS → Ops Team

---

## 🏢 Outposts Variant (IoT)

### Flow
```
Device → Local Gateway → AWS Lambda on Outpost → Service Link → Region
```

### Benefits
- ⚡ <10ms local processing
- 📉 80% bandwidth reduction
- 🔒 Data residency compliance
- 🚀 Real-time automation

---

## 🔄 Comparison

| | End User | IoT Device |
|---|---|---|
| **Who** | Warehouse Manager | Robot/Sensor |
| **What** | Web UI Access | Telemetry Data |
| **How** | HTTPS | MQTT |
| **Speed** | <200ms | <50ms |
| **Volume** | KB/request | MB/second |
| **Connection** | Short | Long |

---

## 🎤 One-Liner Explanations

### End User
"Users access the WMS via CloudFront and ALB with Cognito authentication, achieving sub-200ms response times globally."

### IoT Device
"IoT devices connect via MQTT to IoT Core with certificate auth, processing data in real-time through Kinesis and Lambda with sub-50ms latency."

### Outposts IoT
"Outposts processes IoT data locally with AWS Lambda on Outpost for sub-10ms latency, sending only aggregated data to the Region."

---

## 📊 Key Metrics

### End User
- 10,000 req/sec capacity
- 50,000 concurrent users
- 99.99% availability
- 60% latency reduction (CloudFront)

### IoT Device
- 1M concurrent connections
- 20,000 msg/sec per device
- 10 TB/day data volume
- 90-day cert rotation

---

## 🔐 Security Highlights

### End User
✅ WAF at edge
✅ DDoS protection
✅ SSL/TLS encryption
✅ MFA enforcement
✅ Tenant isolation

### IoT Device
✅ X.509 certificates
✅ Certificate rotation
✅ Device Defender
✅ Encrypted MQTT
✅ Network isolation

---

**Print this card for interview reference!** 📄

