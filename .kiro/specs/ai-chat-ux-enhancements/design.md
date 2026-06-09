# Design Document: AI Chat UX Enhancements

## Overview

This feature enhances the AI chat experience in the members portal with two improvements: (1) Data Source Buttons that display collapsible, labeled buttons after each AI response to reveal the tabular data used to generate the answer, and (2) Backend-Generated Follow-up Question Suggestions that replace the current client-side keyword matching with contextual, adaptive questions returned by the AI agent in the API response payload.

## Architecture

This feature adds two capabilities to the existing AI chat pipeline:

1. **Data Source Buttons** — Collapsible buttons rendered in the frontend `addAIMessage()` function that reveal tabular source data used by the AI to generate its answer.
2. **Backend-Generated Follow-up Suggestions** — The `member-handler` Lambda generates contextual follow-up questions after each Bedrock Agent response, replacing the client-side keyword-matching logic.

The changes span two layers:
- **Backend** (`member-handler/lambda_function.py`): Enriches the API response with `followUpQuestions` and `dataSources` fields.
- **Frontend** (`members/members.js`): Renders data source buttons with expand/collapse behavior, and conditionally uses backend follow-ups instead of client-side generated ones.

No new infrastructure or services are introduced. The feature extends the existing `POST /members/accounts/ai-query` endpoint response payload and the `addAIMessage()` rendering function.

---

## Components and Interfaces

### 1. Backend: Follow-up Question Generator (`_generate_follow_ups`)

A new pure function in `member-handler/lambda_function.py` that produces 2–3 contextual follow-up questions from the data analyzed during the query.

**Inputs:**
- `account_data` (dict): The gathered account data including `cost_by_service`, `daily_cost_trend`, comparison data, etc.
- `answer` (str): The AI agent's response text.
- `question` (str): The original user question.

**Output:**
- `list[str]`: Array of 2–3 follow-up question strings, each ≤100 characters.

**Logic:**
```python
def _generate_follow_ups(account_data, answer, question):
    """Generate 2-3 contextual follow-up questions from analyzed data.
    
    Adaptive count:
    - 3 questions when multi-service data (3+ services with cost > $1)
    - 2 questions when single-service or limited data
    - Empty array when no meaningful data context
    """
    follow_ups = []
    
    cost_by_service = account_data.get('cost_by_service', [])
    significant_services = [s for s in cost_by_service if s.get('cost_usd', 0) > 1.0]
    
    if not significant_services:
        return []
    
    is_rich_data = len(significant_services) >= 3
    target_count = 3 if is_rich_data else 2
    
    # Strategy: pick services/patterns from the data and formulate questions
    # 1. Top cost driver drill-down
    # 2. Trend/comparison question if daily data exists
    # 3. Optimization opportunity from top service
    
    # ... template-based generation referencing actual service names ...
    
    # Enforce constraints
    follow_ups = [q[:100] for q in follow_ups[:target_count]]
    return follow_ups
```

### 2. Backend: Data Sources Extractor (`_extract_data_sources`)

A new pure function that extracts the tabular data already available in the pre-computed context (comparison data, forecast data, cost breakdowns) into the `dataSources` response field.

**Inputs:**
- `account_data` (dict): The gathered account data.
- `chart_data` (list): The chart data array built by `_build_chart_data()`.

**Output:**
- `list[dict]`: Array of `{label: str, data: list[dict]}` objects.

```python
def _extract_data_sources(account_data, chart_data):
    """Extract tabular data sources from pre-computed data for frontend display.
    
    Each source has:
    - label: descriptive title matching the chart data title
    - data: array of row objects with column keys and values
    """
    sources = []
    
    for chart in chart_data:
        title = chart.get('title', '')
        labels = chart.get('labels', [])
        data_values = chart.get('data', [])
        
        if not labels or not data_values:
            continue
        
        rows = []
        for i, label in enumerate(labels):
            row = {'name': label}
            if i < len(data_values):
                row['value'] = data_values[i]
            # Include secondary dataset if present (e.g., month comparison)
            if 'data2' in chart and i < len(chart['data2']):
                row['value2'] = chart['data2'][i]
            rows.append(row)
        
        sources.append({'label': title, 'data': rows})
    
    return sources
```

### 3. Backend: Response Assembly (modified `_invoke_bedrock_agent`)

The existing `_invoke_bedrock_agent` function is modified to:
1. After receiving the agent answer, call `_generate_follow_ups()` with a try/except (returning `[]` on error).
2. Build `chart_data` from the pre-computed comparison/forecast data injected into prompts.
3. Call `_extract_data_sources()` to build the `dataSources` field.
4. Include both new fields in the response.

```python
# In _invoke_bedrock_agent, after building the answer:
try:
    follow_ups = _generate_follow_ups(account_data, answer, question)
except Exception as e:
    logger.warning(f"Follow-up generation failed (non-fatal): {e}")
    follow_ups = []

chart_data = _build_chart_data(account_data)
data_sources = _extract_data_sources(account_data, chart_data)

result = create_response(200, {
    'answer': answer,
    'interactionId': interaction_id,
    'commands': ['Bedrock Agent orchestrated the analysis'],
    'results': [],
    'tipFound': tip_found,
    'agentUsed': True,
    'chartData': chart_data,           # existing field, now also in agent path
    'followUpQuestions': follow_ups,    # NEW
    'dataSources': data_sources,        # NEW
})
```

### 4. Frontend: Data Source Buttons Renderer

A new function `_renderDataSourceButtons(tableArea, dataSources)` in `members.js` that creates collapsible buttons in the `.ai-table-area` DOM section.

```javascript
function _renderDataSourceButtons(tableArea, dataSources) {
    if (!tableArea || !dataSources || dataSources.length === 0) return;
    
    dataSources.forEach(function(source, idx) {
        var wrapper = document.createElement('div');
        wrapper.className = 'ai-datasource-wrapper';
        wrapper.style.marginBottom = '8px';
        
        // Button
        var btn = document.createElement('button');
        btn.className = 'btn btn-outline btn-sm ai-datasource-btn';
        btn.setAttribute('aria-expanded', 'false');
        btn.innerHTML = '<span class="ai-ds-indicator">\u25B6</span> \uD83D\uDCCB ' + esc(source.label);
        btn.dataset.dsIndex = idx;
        
        // Table container (hidden by default)
        var tableContainer = document.createElement('div');
        tableContainer.className = 'ai-datasource-table';
        tableContainer.style.display = 'none';
        tableContainer.innerHTML = _buildDataTable(source.data);
        
        // Toggle behavior
        btn.onclick = function() {
            var isExpanded = btn.getAttribute('aria-expanded') === 'true';
            if (isExpanded) {
                tableContainer.style.display = 'none';
                btn.setAttribute('aria-expanded', 'false');
                btn.querySelector('.ai-ds-indicator').textContent = '\u25B6';
                btn.style.borderColor = '';
            } else {
                tableContainer.style.display = 'block';
                btn.setAttribute('aria-expanded', 'true');
                btn.querySelector('.ai-ds-indicator').textContent = '\u25BC';
                btn.style.borderColor = '#6366f1';
            }
        };
        
        wrapper.appendChild(btn);
        wrapper.appendChild(tableContainer);
        tableArea.appendChild(wrapper);
    });
}
```

### 5. Frontend: Table Builder

A helper function `_buildDataTable(rows)` that converts row objects into an HTML table string with proper formatting.

```javascript
function _buildDataTable(rows) {
    if (!rows || rows.length === 0) return '<p style="color:#8b949e;">No data</p>';
    
    // Extract column keys from first row
    var keys = Object.keys(rows[0]);
    
    var html = '<table class="ai-source-table" style="width:100%;border-collapse:collapse;font-size:0.85em;margin-top:8px;">';
    // Header
    html += '<thead><tr>';
    keys.forEach(function(k) {
        html += '<th style="text-align:left;padding:6px 8px;border-bottom:1px solid #30363d;color:#8b949e;">' + esc(k) + '</th>';
    });
    html += '</tr></thead>';
    // Body
    html += '<tbody>';
    rows.forEach(function(row) {
        html += '<tr>';
        keys.forEach(function(k) {
            var val = row[k];
            var formatted = _formatCellValue(val, k);
            html += '<td style="padding:6px 8px;border-bottom:1px solid #21262d;color:#c9d1d9;">' + formatted + '</td>';
        });
        html += '</tr>';
    });
    html += '</tbody></table>';
    return html;
}

function _formatCellValue(val, key) {
    if (val == null) return '-';
    if (typeof val === 'number') {
        // Detect currency vs percentage based on key name or value range
        var keyLower = (key || '').toLowerCase();
        if (keyLower.indexOf('pct') !== -1 || keyLower.indexOf('percent') !== -1 || keyLower.indexOf('change') !== -1) {
            return val.toFixed(1) + '%';
        }
        if (keyLower.indexOf('cost') !== -1 || keyLower.indexOf('value') !== -1 || keyLower.indexOf('amount') !== -1 || keyLower.indexOf('price') !== -1) {
            return '$' + val.toFixed(2);
        }
        return val.toFixed(2);
    }
    return esc(String(val));
}
```

### 6. Frontend: Conditional Follow-up Rendering

The existing follow-up generation block in `addAIMessage()` is wrapped with a check for backend-provided follow-ups. When `followUpQuestions` is present and non-empty in the response, those are rendered directly; otherwise, the existing client-side logic runs as fallback.

```javascript
// In askAI(), after receiving data:
// Pass followUpQuestions to addAIMessage via a new parameter or data attribute
addAIMessage('answer', data.answer || 'No answer available.', data.topServices || [], data.followUpQuestions || []);

// In addAIMessage(), the follow-up section becomes:
var followUps = [];
if (backendFollowUps && backendFollowUps.length > 0) {
    // Use backend-provided follow-ups directly
    followUps = backendFollowUps;
} else {
    // Existing client-side keyword-matching logic (unchanged)
    // ... current logic ...
}
```

---

## Data Models

### API Response Contract (Enhanced)

```json
{
  "answer": "string",
  "interactionId": "string",
  "commands": ["string"],
  "results": [],
  "tipFound": true,
  "agentUsed": true,
  "chartData": [
    {
      "id": "service-costs",
      "title": "Cost by Service (Last 30 Days)",
      "type": "bar",
      "labels": ["EC2", "S3", "RDS"],
      "data": [145.20, 32.50, 89.10]
    }
  ],
  "followUpQuestions": [
    "What's driving my EC2 cost increase?",
    "Show my S3 storage class breakdown",
    "Compare this month to last month"
  ],
  "dataSources": [
    {
      "label": "Cost by Service (Last 30 Days)",
      "data": [
        {"name": "EC2", "value": 145.20},
        {"name": "S3", "value": 32.50},
        {"name": "RDS", "value": 89.10}
      ]
    }
  ]
}
```

### Constraints

| Field | Type | Min | Max | Notes |
|-------|------|-----|-----|-------|
| `followUpQuestions` | `string[]` | 0 | 3 | Empty when no data context or on error |
| `followUpQuestions[i]` | `string` | 1 | 100 | Character limit per question |
| `dataSources` | `object[]` | 0 | N | One per chart data item |
| `dataSources[i].label` | `string` | 1 | — | Matches chart title |
| `dataSources[i].data` | `object[]` | 0 | — | Row objects with column keys |

---

---

## Interfaces

### Modified Function: `addAIMessage(type, content, topServices, backendFollowUps)`

Added fourth parameter `backendFollowUps` (array of strings, default `[]`). When non-empty, these replace the client-side follow-up generation.

### New Function: `_renderDataSourceButtons(tableArea, dataSources)`

Renders collapsible data source buttons into the `.ai-table-area` element. Called from `askAI()` after rendering the answer message.

### New Function: `_buildDataTable(rows)`

Converts an array of row objects into an HTML table string with formatted values.

### New Function: `_formatCellValue(val, key)`

Formats a cell value based on its type and column key name. Currency values get `$X.XX`, percentages get `X.X%`.

### New Function: `_generate_follow_ups(account_data, answer, question)`

Backend Python function. Generates 2–3 contextual follow-up questions from the analyzed data.

### New Function: `_extract_data_sources(account_data, chart_data)`

Backend Python function. Extracts tabular data from chart data into the `dataSources` response format.

---

## Error Handling

| Scenario | Behavior |
|----------|----------|
| `_generate_follow_ups` throws an exception | Caught in `_invoke_bedrock_agent`; returns `followUpQuestions: []`; main answer unaffected |
| `_extract_data_sources` throws an exception | Caught; returns `dataSources: []`; main answer unaffected |
| `followUpQuestions` missing from API response | Frontend falls back to existing client-side follow-up logic |
| `dataSources` missing or empty | No data source buttons rendered; table area remains empty |
| Chart data item has no `labels` or `data` | Skipped by `_extract_data_sources`; no source entry created |
| Backend returns `followUpQuestions` with > 3 items | Frontend renders all provided (backend enforces the limit) |

---

## Testing Strategy

**Unit Tests (example-based):**
- Toggle behavior: click collapsed → expands, click expanded → collapses (Requirements 1.4, 1.5, 2.2, 2.4)
- Backend follow-up override: when `followUpQuestions` present, client-side logic skipped (Requirement 5.2)
- Click follow-up button submits query (Requirement 5.3)
- Fallback to client-side when field absent (Requirement 5.4)
- Error resilience: follow-up generator throws → empty array returned (Requirement 7.5)
- Empty chartData renders no buttons (Requirement 3.4)

**Property Tests (100+ iterations):**
- Properties 1–12 as defined in the Correctness Properties section above
- Generators produce random chart data arrays, service cost arrays, and question/answer strings

---

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system—essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property 1: Data source button count equals chart data items

*For any* non-empty `dataSources` array in the API response, the number of rendered Data_Source_Buttons in the `.ai-table-area` SHALL equal the length of the `dataSources` array, and each button's label text SHALL contain the corresponding source's `label` value prefixed with 📋.

**Validates: Requirements 1.1, 1.2, 2.1**

### Property 2: Default collapsed state invariant

*For any* rendered Data_Source_Button, immediately after rendering it SHALL have `aria-expanded="false"`, its associated table container SHALL have `display: none`, and the directional indicator SHALL be ▶.

**Validates: Requirements 1.3, 2.2**

### Property 3: Independent toggle isolation

*For any* pair of Data_Source_Buttons, expanding or collapsing one button SHALL NOT change the `aria-expanded` attribute or display state of any other button in the same `.ai-table-area`.

**Validates: Requirements 3.5**

### Property 4: Table structure matches source data dimensions

*For any* `dataSources` entry with `data` containing N rows and M keys per row, the rendered HTML table SHALL have exactly M column headers and N body rows.

**Validates: Requirements 3.1**

### Property 5: Currency formatting round-trip preserves value

*For any* numeric value where the column key indicates currency (contains "cost", "value", "amount", or "price"), `_formatCellValue` SHALL produce a string matching the pattern `$X.XX` where parsing the numeric portion back yields a value within 0.005 of the original.

**Validates: Requirements 3.2**

### Property 6: Percentage formatting correctness

*For any* numeric value where the column key indicates percentage (contains "pct", "percent", or "change"), `_formatCellValue` SHALL produce a string matching the pattern `X.X%` where parsing the numeric portion back yields a value within 0.05 of the original.

**Validates: Requirements 3.3**

### Property 7: Follow-up count adapts to data richness

*For any* `account_data` with 3 or more services having `cost_usd > 1.0`, `_generate_follow_ups` SHALL return exactly 3 questions. *For any* `account_data` with 1–2 services having `cost_usd > 1.0`, it SHALL return exactly 2 questions. *For any* `account_data` with zero significant services, it SHALL return an empty array.

**Validates: Requirements 4.1, 6.1, 6.2, 6.3, 6.4**

### Property 8: Follow-up character limit invariant

*For any* string returned by `_generate_follow_ups`, its length SHALL be less than or equal to 100 characters.

**Validates: Requirements 4.5**

### Property 9: Follow-up questions reference input data

*For any* non-empty output of `_generate_follow_ups`, at least one question SHALL contain a substring matching a service name, cost pattern keyword, or anomaly indicator present in the input `account_data`.

**Validates: Requirements 4.3**

### Property 10: API response contract structure

*For any* successful AI query response where `agentUsed` is `true`, the response payload SHALL contain a `followUpQuestions` field (array of 0–3 strings), a `dataSources` field (array of objects each having `label` as string and `data` as array), and a `chartData` field (array unchanged from existing format).

**Validates: Requirements 7.1, 7.2, 7.3, 7.4**

### Property 11: Follow-up generation error resilience

*For any* error thrown during `_generate_follow_ups` execution, the API response SHALL still contain the `answer` field with the AI response and `followUpQuestions` SHALL be an empty array.

**Validates: Requirements 7.5**

### Property 12: Conditional follow-up source selection

*For any* API response where `followUpQuestions` is a non-empty array, the Chat_UI SHALL render buttons with text matching those backend-provided questions (not client-side generated ones). *For any* response where `followUpQuestions` is absent or empty, the Chat_UI SHALL use the existing client-side keyword-matching logic.

**Validates: Requirements 5.1, 5.2, 5.4**
