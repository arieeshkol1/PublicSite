# Multi-Tenancy Quick Reference

## ❌ WRONG: 800 VPCs
- Operationally impossible
- $720K/year cost
- Hits AWS limits
- NOT scalable

## ✅ CORRECT: 1 VPC + Multi-Tenant App
- Operationally simple
- $361K/year cost
- Within AWS limits
- Scales to 10K+ customers

---

## 🏗️ Architecture

```
Single Production VPC
    ↓
Transit Gateway (800+ VPN connections)
    ↓
Route Tables (one per customer)
    ↓
Application Load Balancer
    ↓
EC2 Auto Scaling (Multi-Tenant App)
    ↓
Database Tier:
    ├── 10 dedicated RDS (enterprise)
    └── 1 shared RDS with 790 schemas (standard)
```

---

## 🔐 Isolation (3 Layers)

1. **Network:** Transit Gateway route tables
2. **Application:** Tenant ID in JWT tokens
3. **Database:** Schema-per-tenant + RLS

---

## 💰 Cost Savings

| | 800 VPCs | 1 VPC |
|---|---|---|
| **Cost** | $720K/year | $361K/year |
| **Savings** | - | **$359K/year** |

---

## 🎤 One-Liner

"We use a single VPC with Transit Gateway route table isolation for network segmentation, application-level multi-tenancy with JWT-based tenant context, and schema-per-tenant database architecture for 790 standard customers, plus dedicated RDS instances for 10 enterprise customers—saving $360K/year while maintaining strong isolation."

---

## 📊 Customer Tiers

**Tier 1 (10 customers):** Dedicated RDS, $50K+/year
**Tier 2 (790 customers):** Shared RDS, $5K-$50K/year

---

**This is the industry-standard SaaS approach!** ✅

