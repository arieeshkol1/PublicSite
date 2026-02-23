# AWS Outposts - Quick Reference Card

## 🎯 One-Minute Summary

AWS Outposts extends AWS infrastructure to warehouse locations for:
- **Low latency** (<10ms response time)
- **Data residency** (compliance requirements)
- **Local processing** (IoT sensor data)

**Key Point:** Same operational model as cloud—one dashboard, one set of tools.

## 📊 Critical Metrics to Monitor

| Metric | What It Means | Alert If |
|--------|---------------|----------|
| **ConnectedStatus** | Service link to AWS Region | Disconnected |
| **EC2 Capacity** | Available instance types | >80% utilized |
| **EBS Capacity** | Available storage | >80% utilized |
| **IfTrafficIn/Out** | Network bandwidth usage | Approaching limits |

## 🚨 Critical Health Events

### 1. AWS_EC2_INSTANCE_RETIREMENT_SCHEDULED
- **What:** Hardware failure detected
- **Impact:** Instance needs migration
- **Action:** Ensure spare capacity (N+M model)

### 2. AWS_OUTPOSTS_SERVICE_LINK_DOWN
- **What:** Lost connectivity to AWS Region
- **Impact:** New resources can't be created
- **Action:** Network team troubleshooting

## 🛠️ Operational Commands

### Check Outposts Status
```bash
aws outposts list-outposts
aws outposts get-outpost --outpost-id op-xxxxx
```

### Monitor Service Link
```bash
aws cloudwatch get-metric-statistics \
  --namespace AWS/Outposts \
  --metric-name ConnectedStatus \
  --dimensions Name=OutpostId,Value=op-xxxxx
```

### Remote Access (Same as Cloud)
```bash
aws ssm start-session --target i-outpost-instance-id
```

## 💡 Interview Answer (30 seconds)

**Q:** "How do you handle warehouses that need on-premises compute?"

**A:** "I deploy AWS Outposts—it's AWS infrastructure on-premises with the same operational model. I monitor the service link status with CloudWatch alarms and maintain N+M capacity for hardware failures. Systems Manager works the same way, so my team manages cloud and on-premises resources from one dashboard. This gives warehouses <10ms latency while maintaining centralized operations."

## 📈 Business Value

- ✅ **Unified Operations:** Same tools for cloud and on-premises
- ✅ **Compliance:** Data stays on-premises when required
- ✅ **Performance:** <10ms latency for real-time operations
- ✅ **Resilience:** Workloads continue during connectivity issues

## 🔗 Key AWS Services

- **AWS Outposts:** On-premises infrastructure
- **CloudWatch:** Capacity and service link monitoring
- **AWS Health:** Hardware failure alerts
- **AWS Health Aware:** Multi-account notifications
- **Systems Manager:** Remote access and patching
- **Transit Gateway:** Connectivity hub

## 📚 Reference

- Full details: `OUTPOSTS-INTEGRATION-SUMMARY.md`
- Architecture: `Made4Net-AWS-Architecture.drawio`
- HLD Section 6: `Made4Net-Operational-Excellence-HLD.docx`
- AWS Blog: [Monitoring Best Practices for AWS Outposts](https://aws.amazon.com/blogs/mt/monitoring-best-practices-for-aws-outposts/)

---

**Print this card for quick reference during interview!**
