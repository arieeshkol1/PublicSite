# FinOps Dashboard — Requirements

## Overview
Transform the existing Dashboard tab into a comprehensive BI layer for cloud cost data, providing executive-level KPIs, cost allocation, commitment intelligence, anomaly detection, and container cost visibility.

## User Stories

### US-1: Executive KPI Overview
**As a** member, **I want** to see high-level cost KPIs at a glance **so that** I can quickly assess my cloud spending health.
- **AC-1.1**: Dashboard shows total monthly spend (current + previous month) with trend arrow
- **AC-1.2**: Cost Efficiency Score displayed as a gauge chart (0-100%)
- **AC-1.3**: Month-over-month change percentage shown prominently
- **AC-1.4**: Potential savings amount displayed with breakdown

### US-2: Cost by Service Treemap
**As a** member, **I want** to see my costs visualized as a treemap **so that** I can instantly see which services dominate my spending.
- **AC-2.1**: ECharts treemap shows services proportional to cost
- **AC-2.2**: Click a service block to drill down into usage type breakdown
- **AC-2.3**: Hover shows exact dollar amount and percentage

### US-3: Daily Cost Trend with Anomaly Markers
**As a** member, **I want** to see daily cost trends with anomaly highlights **so that** I can spot unexpected spikes.
- **AC-3.1**: Line chart shows daily costs for last 30 days
- **AC-3.2**: Anomalous days (>2x average) marked with red dots
- **AC-3.3**: Click anomaly marker to see which services caused the spike

### US-4: Rightsizing Summary Widget
**As a** member, **I want** to see a summary of rightsizing opportunities **so that** I know which resources to optimize.
- **AC-4.1**: Shows count of OVER-PROVISIONED, RIGHT-SIZED, UNDER-PROVISIONED resources
- **AC-4.2**: Lists top 3 rightsizing opportunities with estimated savings
- **AC-4.3**: Includes EC2, RDS, ECS service metrics

### US-5: Commitment Coverage Widget
**As a** member, **I want** to see my Savings Plan and RI coverage **so that** I know if I'm maximizing discounts.
- **AC-5.1**: Shows percentage of spend covered by commitments
- **AC-5.2**: Shows potential savings from increasing commitment coverage
- **AC-5.3**: Recommends optimal commitment level based on usage patterns

### US-6: Multi-Account Comparison
**As a** member with multiple accounts, **I want** to compare spending across accounts **so that** I can identify the biggest cost drivers.
- **AC-6.1**: Bar chart comparing total spend per account
- **AC-6.2**: Table showing top services per account
- **AC-6.3**: Highlights which account has the most optimization potential

### US-7: Container Cost Widget (ECS/EKS)
**As a** member running containers, **I want** to see container utilization vs cost **so that** I can identify over-provisioned clusters.
- **AC-7.1**: Shows ECS service CPU/memory utilization alongside cost
- **AC-7.2**: Flags services with <20% utilization as waste candidates
- **AC-7.3**: Shows EKS cluster count and node utilization

### US-8: Waste Detection Summary
**As a** member, **I want** a quick summary of all detected waste **so that** I can take immediate action.
- **AC-8.1**: Lists all waste items: idle EBS, EIPs, Lambda, ELB, NAT GW, KMS
- **AC-8.2**: Shows total waste amount in dollars
- **AC-8.3**: Each item is clickable to ask the AI for details

## Technical Requirements
- **TR-1**: Dashboard data fetched via new `GET /members/dashboard-data` API endpoint
- **TR-2**: Backend gathers data from all connected accounts (multi-account aggregate)
- **TR-3**: All charts use Apache ECharts with dark theme
- **TR-4**: Dashboard auto-refreshes when switching to the tab
- **TR-5**: Data cached for 5 minutes to avoid excessive API calls
- **TR-6**: Responsive layout using CSS grid (2-column on desktop, 1-column on mobile)
