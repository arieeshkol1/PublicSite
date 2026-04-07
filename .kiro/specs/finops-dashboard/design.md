# FinOps Dashboard — Design

## Architecture

### Backend: `GET /members/dashboard-data`
New API endpoint that gathers data from ALL connected accounts and returns a structured dashboard payload.

```
Response: {
  summary: {
    totalSpend: 856.42,
    previousMonthSpend: 1023.15,
    monthOverMonthChange: -16.3,
    efficiencyScore: 75.9,
    efficiencyRating: "Good",
    potentialSavings: 147.20,
    savingsBreakdown: { "RDS SP/RI": 98.40, "Idle EIPs": 3.65, ... },
    totalAccounts: 2,
    accountsAnalyzed: 2,
  },
  costByService: [ { service, cost, pct } ],
  dailyTrend: [ { date, cost, isAnomaly, spikePct } ],
  monthlyTrend: { "2026-01": { svc: cost }, "2026-02": { ... } },
  rightsizing: {
    overProvisioned: 3, rightSized: 12, underProvisioned: 1,
    topOpportunities: [ { resource, currentType, recommendedType, monthlySavings } ],
  },
  waste: {
    totalWaste: 42.50,
    items: [ { type, resource, monthlyCost, action } ],
  },
  perAccount: [
    { accountId, accountName, totalSpend, topServices, efficiencyScore },
  ],
  containers: {
    ecsClusters: [ { name, avgCpu, avgMemory, runningTasks, waste } ],
    eksClusters: [ { name, status, version } ],
  },
}
```

### Frontend: Dashboard Tab Layout (CSS Grid)

```
┌─────────────────────────────────────────────────┐
│  KPI Bar: Total Spend | MoM Change | Efficiency │
│           | Potential Savings | Accounts         │
├────────────────────────┬────────────────────────┤
│  Cost by Service       │  Daily Trend +         │
│  (Treemap)             │  Anomaly Markers       │
├────────────────────────┼────────────────────────┤
│  Rightsizing Summary   │  Waste Detection       │
│  (Gauge + List)        │  (List + Total)        │
├────────────────────────┼────────────────────────┤
│  Monthly Trend         │  Account Comparison    │
│  (Grouped Bar)         │  (Horizontal Bar)      │
├────────────────────────┴────────────────────────┤
│  Container Costs (ECS/EKS) — full width         │
└─────────────────────────────────────────────────┘
```

### Data Flow
1. User switches to Dashboard tab
2. Frontend calls `GET /members/dashboard-data`
3. Backend iterates all connected accounts, assumes role, gathers data
4. Merges into aggregate + per-account structure
5. Returns JSON payload
6. Frontend renders 8 ECharts widgets in CSS grid

### Caching
- Frontend caches dashboard data for 5 minutes (localStorage with timestamp)
- Backend uses Lambda execution context caching (warm start reuse)
