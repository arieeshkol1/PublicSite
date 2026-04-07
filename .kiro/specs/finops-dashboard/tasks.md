# FinOps Dashboard — Tasks

## Task 1: Backend — `GET /members/dashboard-data` endpoint
- [ ] Add route to member-handler lambda_function.py
- [ ] Add `handle_dashboard_data()` function that:
  - Iterates all connected accounts for the member
  - Assumes role and gathers cost data (CE monthly, daily, usage breakdown)
  - Gathers CloudWatch rightsizing metrics (EC2, RDS, ECS)
  - Computes efficiency score, waste detection, anomaly detection
  - Merges into aggregate + per-account structure
  - Returns structured JSON payload
- [ ] Add API Gateway route in viewmybill-stack.yaml
- [ ] Refs: #[[file:member-handler/lambda_function.py]], #[[file:infrastructure/viewmybill-stack.yaml]]

## Task 2: Frontend — Dashboard tab HTML structure
- [ ] Replace existing dashboard tab content with CSS grid layout
- [ ] Add 8 widget containers with IDs for ECharts
- [ ] Add KPI bar at top with summary cards
- [ ] Responsive: 2-column desktop, 1-column mobile
- [ ] Refs: #[[file:members/index.html]], #[[file:members/members.css]]

## Task 3: Frontend — KPI Summary Bar
- [ ] Render: Total Spend, MoM Change (with arrow), Efficiency Score gauge, Potential Savings, Account count
- [ ] Color coding: green for improvement, red for increase
- [ ] Refs: #[[file:members/members.js]]

## Task 4: Frontend — Cost by Service Treemap
- [ ] ECharts treemap showing services proportional to cost
- [ ] Click to drill down into usage type breakdown
- [ ] Hover tooltip with dollar amount and percentage
- [ ] Refs: #[[file:members/members.js]]

## Task 5: Frontend — Daily Trend with Anomaly Markers
- [ ] ECharts line chart for 30-day daily costs
- [ ] Red markPoint for anomalous days (>2x average)
- [ ] Click anomaly to show root cause
- [ ] Refs: #[[file:members/members.js]]

## Task 6: Frontend — Rightsizing Summary Widget
- [ ] Gauge chart showing over/right/under-provisioned counts
- [ ] List top 3 opportunities with estimated savings
- [ ] Click to ask AI for details
- [ ] Refs: #[[file:members/members.js]]

## Task 7: Frontend — Waste Detection Widget
- [ ] List all waste items with type, resource, monthly cost
- [ ] Total waste amount prominently displayed
- [ ] Each item clickable to ask AI for details
- [ ] Refs: #[[file:members/members.js]]

## Task 8: Frontend — Monthly Trend + Account Comparison
- [ ] Grouped bar chart for monthly service costs
- [ ] Horizontal bar chart comparing account totals
- [ ] Refs: #[[file:members/members.js]]

## Task 9: Frontend — Container Cost Widget
- [ ] ECS service CPU/memory utilization bars alongside cost
- [ ] Flag services with <20% utilization
- [ ] EKS cluster summary
- [ ] Refs: #[[file:members/members.js]]

## Task 10: Integration & Testing
- [ ] Wire dashboard tab switch to fetch data
- [ ] Implement 5-minute cache in localStorage
- [ ] Test with single account and multi-account
- [ ] Test responsive layout
- [ ] Refs: #[[file:members/members.js]]
