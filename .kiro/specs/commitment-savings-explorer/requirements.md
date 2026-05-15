# Requirements Document

## Introduction

The existing committed-discount-analyzer feature provides backend APIs (`POST /members/committed-discounts/scan`) that return Savings Plan (SP) and Reserved Instance (RI) recommendations with all term/payment combinations. The frontend currently displays these results in a static table. This feature — **Commitment Savings Explorer** — makes the experience interactive by letting users explore different commitment options (term, payment, offering class) and see savings dynamically. It also integrates commitment data into the Observe dashboard and the AI chat system.

The feature has four pillars:
1. **SP Savings Explorer** — Interactive controls for exploring Savings Plan options with per-hour and per-month savings
2. **RI Savings Explorer** — Interactive controls for exploring Reserved Instance options with break-even and TCO
3. **Dashboard Integration** — Summary widgets on the Observe tab showing SP/RI coverage, utilization, and potential savings
4. **Chat Integration** — Graphs and navigation links when the AI discusses commitments

## Glossary

- **Act_Tab**: The member portal tab containing actionable optimization features (Waste Cleanup, Service Optimization, Scheduler, Committed Discounts)
- **Observe_Tab**: The member portal tab displaying the FinOps dashboard with KPI cards, charts, and widgets
- **Committed_Discounts_Section**: The existing section within the Act_Tab that displays SP and RI scan results
- **SP_Explorer**: The interactive Savings Plan exploration UI that allows selecting term and payment option to view dynamic savings
- **RI_Explorer**: The interactive Reserved Instance exploration UI that allows selecting instance type, offering class, term, and payment option
- **Member_Handler**: The existing Lambda `aws-bill-analyzer-member-api` that handles all member API routes
- **Scan_Response**: The cached response from `POST /members/committed-discounts/scan` containing SP and RI recommendations for all term/payment combinations
- **Dashboard_Widget**: A card component rendered in the Observe_Tab's grid layout showing a specific metric or visualization
- **KPI_Bar**: The top section of the Observe_Tab displaying key performance indicator cards (total spend, savings, waste, etc.)
- **AI_Chat**: The Chat tab where members ask natural language questions about their AWS costs and receive answers with optional chart data
- **Chart_Data**: The `chartData` array returned by the AI query system, used to render graphs in chat responses
- **Coverage_Percentage**: The proportion of eligible usage hours covered by active RIs or SPs [0–100]
- **Utilization_Percentage**: The proportion of purchased RI/SP hours actually consumed [0–100]
- **Break_Even_Point**: The number of months after purchase at which cumulative savings exceed the upfront cost
- **Total_Cost_of_Ownership (TCO)**: The total amount paid over the full commitment term (upfront + monthly recurring × months)
- **Savings_Per_Hour**: The estimated dollar savings per hour for a given SP commitment option
- **Savings_Per_Month**: The estimated dollar savings per month for a given SP commitment option (Savings_Per_Hour × 730)
- **Navigation_Link**: A clickable element in chat responses that navigates the user to a specific tab and section

## Requirements

### Requirement 1: SP Savings Explorer — Dynamic Option Selection

**User Story:** As a member, I want to select different commitment periods and payment options for each Savings Plan recommendation, so that I can compare savings across combinations without rescanning.

#### Acceptance Criteria

1. WHEN the Committed_Discounts_Section displays SP recommendations, THE SP_Explorer SHALL render interactive controls for each recommendation allowing selection of commitment period (1 year or 3 years) and payment option (All Upfront, Partial Upfront, No Upfront).
2. WHEN a member changes the commitment period or payment option selection, THE SP_Explorer SHALL dynamically update the displayed savings without making a new API call, using data already present in the Scan_Response.
3. THE SP_Explorer SHALL display savings in two formats for each recommendation: Savings_Per_Hour and Savings_Per_Month.
4. THE SP_Explorer SHALL default the selection to 1-year term with No Upfront payment option when first displaying recommendations.
5. WHEN the Scan_Response contains multiple SP types (Compute, EC2 Instance), THE SP_Explorer SHALL group recommendations by type and allow independent option selection within each group.

### Requirement 2: SP Savings Explorer — Savings Display

**User Story:** As a member, I want to clearly see how much I save per hour and per month for each Savings Plan option, so that I can make an informed commitment decision.

#### Acceptance Criteria

1. THE SP_Explorer SHALL display for each selected combination: the hourly commitment amount, the Savings_Per_Hour, the Savings_Per_Month, the savings percentage versus on-demand, and the estimated monthly on-demand cost equivalent.
2. WHEN a payment option with an upfront cost is selected (All Upfront or Partial Upfront), THE SP_Explorer SHALL additionally display the upfront cost amount and the Break_Even_Point in months.
3. WHEN the No Upfront payment option is selected, THE SP_Explorer SHALL display the Break_Even_Point as "Immediate" (zero upfront cost means savings begin from month one).
4. THE SP_Explorer SHALL calculate Savings_Per_Month as `Savings_Per_Hour × 730` (average hours per month).
5. THE SP_Explorer SHALL visually highlight the option with the highest total savings over the term using a "Best Value" badge.

### Requirement 3: RI Savings Explorer — Dynamic Option Selection

**User Story:** As a member, I want to select different instance types, offering classes, terms, and payment options for Reserved Instance recommendations, so that I can explore the full range of RI options interactively.

#### Acceptance Criteria

1. WHEN the Committed_Discounts_Section displays RI recommendations, THE RI_Explorer SHALL render interactive controls allowing selection of: instance type (from the recommended list), offering class (Standard or Convertible), term (1 year or 3 years), and payment option (All Upfront, Partial Upfront, No Upfront).
2. WHEN a member changes any RI selection control, THE RI_Explorer SHALL dynamically update the displayed savings, Break_Even_Point, and Total_Cost_of_Ownership without making a new API call.
3. THE RI_Explorer SHALL populate the instance type dropdown with all instance types present in the Scan_Response for the selected service (EC2 or RDS).
4. THE RI_Explorer SHALL default the selection to the first recommended instance type, Standard offering class, 1-year term, and No Upfront payment option.
5. WHEN a selected combination does not exist in the Scan_Response (e.g., a specific instance type has no Convertible RI data), THE RI_Explorer SHALL disable that option and display "Not available for this instance type."

### Requirement 4: RI Savings Explorer — Savings and TCO Display

**User Story:** As a member, I want to see estimated savings, break-even point, and total cost of ownership for each RI option, so that I can evaluate the financial impact of different RI configurations.

#### Acceptance Criteria

1. THE RI_Explorer SHALL display for each selected combination: the estimated monthly savings, the savings percentage versus on-demand, the recommended instance count, and the region.
2. WHEN a payment option with an upfront cost is selected, THE RI_Explorer SHALL display the Break_Even_Point in months calculated as `upfrontCost / monthlySavings`.
3. THE RI_Explorer SHALL display the Total_Cost_of_Ownership calculated as `upfrontCost + (monthlyRecurringCost × termInYears × 12)`.
4. THE RI_Explorer SHALL display a comparison note showing the discount difference between Standard and Convertible offering classes for the selected instance type.
5. WHEN the Standard offering class provides more than 5% additional savings over Convertible, THE RI_Explorer SHALL display a note: "Standard saves X% more but cannot be exchanged."
6. THE RI_Explorer SHALL visually highlight the option with the lowest Total_Cost_of_Ownership using a "Lowest TCO" badge.

### Requirement 5: Dashboard Integration — SP Coverage Widget

**User Story:** As a member, I want to see my Savings Plan coverage and utilization on the Observe dashboard, so that I can monitor my commitment posture at a glance without navigating to the Act tab.

#### Acceptance Criteria

1. WHEN the Observe_Tab loads and the member has previously scanned committed discounts for at least one account, THE Observe_Tab SHALL display an "SP Coverage" Dashboard_Widget in the dashboard grid.
2. THE SP Coverage widget SHALL display: the overall SP coverage percentage, the overall SP utilization percentage, and a visual indicator (progress bar or gauge) for each metric.
3. WHEN SP coverage is below 50%, THE SP Coverage widget SHALL display the coverage value in an amber/warning color.
4. WHEN SP utilization is below 80%, THE SP Coverage widget SHALL display the utilization value in a red/alert color with a tooltip: "Underutilized — you are paying for unused commitment."
5. THE SP Coverage widget SHALL include a "View Details" link that navigates the member to the Committed_Discounts_Section in the Act_Tab.
6. WHEN no committed discount scan data is available, THE SP Coverage widget SHALL display "No scan data — run a Committed Discounts scan in the Act tab" with a link to the Act_Tab.

### Requirement 6: Dashboard Integration — RI Coverage Widget

**User Story:** As a member, I want to see my Reserved Instance coverage and utilization on the Observe dashboard, so that I can quickly identify underutilized RIs.

#### Acceptance Criteria

1. WHEN the Observe_Tab loads and the member has previously scanned committed discounts, THE Observe_Tab SHALL display an "RI Coverage" Dashboard_Widget in the dashboard grid.
2. THE RI Coverage widget SHALL display: the overall RI coverage percentage, the overall RI utilization percentage, and the count of underutilized RIs (utilization below 80%).
3. WHEN underutilized RIs exist, THE RI Coverage widget SHALL display a badge showing the count (e.g., "2 underutilized") in red.
4. WHEN RI coverage is below 50%, THE RI Coverage widget SHALL display the coverage value in an amber/warning color.
5. THE RI Coverage widget SHALL include a "View Details" link that navigates the member to the Committed_Discounts_Section in the Act_Tab.
6. WHEN no committed discount scan data is available, THE RI Coverage widget SHALL display "No scan data — run a Committed Discounts scan in the Act tab" with a link to the Act_Tab.

### Requirement 7: Dashboard Integration — Potential Savings KPI

**User Story:** As a member, I want the overall savings KPI on the Observe dashboard to include potential commitment savings, so that I understand the full savings opportunity.

#### Acceptance Criteria

1. WHEN committed discount scan data is available, THE KPI_Bar SHALL include potential commitment savings in the "Total Potential Savings" KPI card.
2. THE KPI_Bar SHALL display potential commitment savings as a separate line item within the savings KPI card, labeled "Commitment Savings (estimated)".
3. THE potential commitment savings value SHALL be the sum of estimated monthly savings from all SP and RI recommendations in the most recent scan.
4. WHEN no committed discount scan data is available, THE KPI_Bar SHALL display the savings KPI without the commitment savings line item (no placeholder or zero value shown).
5. THE KPI_Bar SHALL display a tooltip on the commitment savings line explaining: "Estimated savings if all recommended Savings Plans and Reserved Instances are purchased."

### Requirement 8: Chat Integration — Savings Comparison Graphs

**User Story:** As a member, I want the AI chat to show graphs comparing savings across commitment options when I ask about commitments, so that I can visually compare options without switching tabs.

#### Acceptance Criteria

1. WHEN the AI_Chat response discusses Savings Plans or Reserved Instances and committed discount scan data is available, THE AI_Chat SHALL include Chart_Data showing a bar chart comparing savings across term and payment options.
2. THE savings comparison chart SHALL display monthly savings on the Y-axis and option labels (e.g., "1yr No Upfront", "3yr All Upfront") on the X-axis.
3. WHEN the AI_Chat response discusses a specific SP type, THE Chart_Data SHALL include savings data for all available term/payment combinations for that SP type.
4. WHEN the AI_Chat response discusses RIs for a specific instance type, THE Chart_Data SHALL include savings data for all available offering class/term/payment combinations.
5. THE Chart_Data SHALL use distinct colors to differentiate between 1-year and 3-year term options.

### Requirement 9: Chat Integration — Navigation Links

**User Story:** As a member, I want the AI chat to include clickable links that take me directly to the Committed Discounts section, so that I can act on recommendations immediately after reading about them.

#### Acceptance Criteria

1. WHEN the AI_Chat response discusses Savings Plans or Reserved Instances, THE AI_Chat SHALL include a Navigation_Link labeled "Go to Act → Committed Discounts" that navigates to the Committed_Discounts_Section.
2. THE Navigation_Link SHALL use the existing `_goToTab('act-tab','committed')` navigation pattern already implemented in the chat link system.
3. WHEN the AI_Chat response includes specific SP or RI recommendations, THE AI_Chat SHALL include the Navigation_Link at the end of the response.
4. THE Navigation_Link SHALL be rendered as a styled button consistent with existing chat navigation links (e.g., "Go to Act → Optimize").

### Requirement 10: Data Source — Frontend Cache Utilization

**User Story:** As a developer, I want the explorer and dashboard widgets to use cached scan data from sessionStorage, so that no additional API calls are needed for the interactive features.

#### Acceptance Criteria

1. THE SP_Explorer and RI_Explorer SHALL read recommendation data exclusively from the `committedDiscounts_{accountId}` sessionStorage cache populated by the existing scan flow.
2. WHEN the sessionStorage cache is empty (no prior scan), THE SP_Explorer and RI_Explorer SHALL display an empty state prompting the member to run a scan first.
3. THE Dashboard_Widgets (SP Coverage and RI Coverage) SHALL read data from sessionStorage cache for the currently selected dashboard accounts.
4. WHEN the member triggers a rescan, THE SP_Explorer and RI_Explorer SHALL automatically refresh their displayed data from the updated cache.
5. THE AI_Chat SHALL access committed discount data from sessionStorage when constructing Chart_Data for commitment-related responses.

### Requirement 11: SP Explorer — Option Comparison View

**User Story:** As a member, I want to see all SP term/payment combinations side by side in a comparison table, so that I can quickly identify the best option without toggling controls repeatedly.

#### Acceptance Criteria

1. THE SP_Explorer SHALL include a "Compare All Options" toggle that expands a comparison table showing all 6 combinations (2 terms × 3 payment options) for the selected SP type.
2. WHEN the comparison table is displayed, THE SP_Explorer SHALL show columns: Term, Payment Option, Hourly Commitment, Monthly Savings, Savings %, Upfront Cost, Break-Even Months, and Total Cost over Term.
3. THE comparison table SHALL highlight the row with the highest savings percentage in green and the row with the lowest total cost in blue.
4. WHEN the comparison table is collapsed, THE SP_Explorer SHALL return to the single-option interactive view.

### Requirement 12: RI Explorer — Option Comparison View

**User Story:** As a member, I want to see all RI options for a selected instance type in a comparison table, so that I can evaluate all combinations at once.

#### Acceptance Criteria

1. THE RI_Explorer SHALL include a "Compare All Options" toggle that expands a comparison table showing all available combinations for the selected instance type.
2. WHEN the comparison table is displayed, THE RI_Explorer SHALL show columns: Offering Class, Term, Payment Option, Monthly Savings, Savings %, Upfront Cost, Break-Even Months, and TCO.
3. THE comparison table SHALL highlight the row with the lowest TCO in blue and the row with the highest savings percentage in green.
4. WHEN the comparison table is collapsed, THE RI_Explorer SHALL return to the single-option interactive view.
5. IF fewer than 2 combinations are available for an instance type, THEN THE RI_Explorer SHALL hide the "Compare All Options" toggle and display the single available option directly.



### Requirement 13: Laddering Strategy — User-Friendly Redesign

**User Story:** As a member, I want the laddering strategy to be explained in plain language with monthly amounts, so that I understand what I'm committing to without needing to think in hourly rates.

#### Acceptance Criteria

1. THE Laddering_Strategy section SHALL display commitment amounts in monthly terms ($/month) as the primary unit, with hourly ($/hr) shown as a secondary detail in smaller text.
2. THE Laddering_Strategy section SHALL include a plain-language explanation at the top: "Instead of buying your full commitment at once, stagger multiple 1-year (or 3-year) purchases across different dates. This way they expire at different times — giving you flexibility to adjust as your usage evolves."
3. THE Customize modal SHALL accept input in monthly commitment ($/month) instead of hourly, and convert internally using `hourly = monthly / 730`.
4. THE Customize modal SHALL offer three preset buttons — "Conservative (P10 floor)", "Moderate (60% of average)", "Aggressive (70% of average)" — pre-filled with the calculated values from the baseline data, so users don't need to calculate amounts manually.
5. EACH tranche in the timeline SHALL display: the purchase number (Purchase 1, 2, 3, 4), the recommended purchase date, the monthly commitment amount for that purchase, the commitment term (1-year or 3-year), the cumulative monthly commitment after this purchase, the estimated monthly savings at that point, and the recommended plan type with a one-line rationale.
6. THE Laddering_Strategy section SHALL display a summary sentence at the top: "Recommended: Buy 4 separate commitments of ~$X/month each, purchased 3 months apart → total savings ~$Y/month once all are active" where X is per-tranche monthly commitment and Y is the cumulative savings.
7. WHEN the aggressive warning is triggered, THE Laddering_Strategy section SHALL display the warning in plain language: "This total commitment is high relative to your usage. If your workloads decrease, you'll still pay for unused commitment for 1–3 years. Consider the Moderate option."
8. THE Laddering_Strategy section SHALL clarify that each purchase is a full 1-year or 3-year commitment — not a quarterly commitment. The staggering is about WHEN you buy, not HOW LONG each commitment lasts.

### Requirement 14: Laddering Strategy — Visual Timeline Improvement

**User Story:** As a member, I want the laddering timeline to be visually clear with a progress-style layout, so that I can quickly understand the purchase schedule.

#### Acceptance Criteria

1. THE Laddering_Strategy timeline SHALL render as a horizontal progress bar with 4 milestone markers (Purchase 1–4), showing the cumulative commitment growing at each step.
2. EACH milestone marker SHALL show the purchase date and the incremental monthly commitment being added at that step, along with the commitment term (e.g., "1-year Compute SP").
3. THE timeline SHALL use color coding: past purchase dates in green, the next upcoming purchase in blue/highlighted, and future purchases in gray.
4. BELOW the timeline, THE Laddering_Strategy SHALL show a summary table with columns: Purchase #, Date, Commitment $/month, Term, Cumulative $/month, Est. Savings $/month, Plan Type.
5. THE timeline SHALL be responsive — on narrow screens, it SHALL stack vertically instead of horizontally.
