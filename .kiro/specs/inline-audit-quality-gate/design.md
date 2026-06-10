# Design: Inline Audit Quality Gate

## Architecture

```
User Question
    │
    ▼
┌─────────────────────────────┐
│  member-handler Lambda       │
│  (handle_ai_query)           │
│                              │
│  1. Enrich prompt            │
│  2. Invoke Bedrock Agent     │
│  3. ◄── NEW: Inline Audit ──►│
│     │                        │
│     ├─ score ≥ 70 → return   │
│     │                        │
│     ├─ score < 70 +          │
│     │  can_improve=true →    │
│     │  Re-invoke Agent with  │
│     │  enhanced prompt       │
│     │  → return rewrite      │
│     │                        │
│     └─ score < 70 +          │
│        can_improve=false →   │
│        Return guiding Qs     │
│        (needsClarification)  │
│                              │
│  4. Build response JSON      │
│  5. Log transaction (async)  │
└─────────────────────────────┘
```

## Component: `_inline_audit_score(question, answer)`

Located in `member-handler/lambda_function.py`. A new function that:

1. Calls Bedrock `invoke_model` with Amazon Nova Lite (`us.amazon.nova-lite-v1:0`)
2. Uses a compact scoring prompt (under 2000 chars) — much shorter than the full async audit prompt
3. Returns a dict: `{"score": int, "can_improve": bool, "improvement": str, "guiding_questions": list}`

### Scoring Prompt (compact)
```
Score this AI response 0-100. Question: "{question}" Response: "{answer}"
Rules: 80+ = directly answers with specific data. 50-79 = partially answers. <50 = doesn't answer.
Return JSON: {"score": N, "can_improve": true/false, "improvement": "...", "guiding_questions": ["...", "..."]}
- can_improve=true if the response has data but presented it poorly (reformat/restructure would fix it)
- can_improve=false if the question is ambiguous or the system lacks data to answer
- guiding_questions: 2-3 questions to help clarify (only needed when can_improve=false)
```

## Integration Point

After the Bedrock Agent `invoke_agent` call returns the streamed answer (around line ~8145 in current code), insert:

```python
# --- Inline Audit Quality Gate ---
audit_threshold = int(os.environ.get('AUDIT_QUALITY_THRESHOLD', '70'))
inline_audit = _inline_audit_score(question, answer)
inline_score = inline_audit.get('score', 100)

if inline_score < audit_threshold:
    if inline_audit.get('can_improve'):
        # Option 1: Re-invoke with improvement instructions
        enhanced = enriched_prompt + f"\n\n[QUALITY GATE: Previous answer scored {inline_score}/100. Issues: {inline_audit['improvement']}. Rewrite the answer addressing these issues.]"
        answer = _reinvoke_agent(enhanced, ...)  # simplified re-invocation
    else:
        # Option 2: Return guiding questions
        return create_response(200, {
            'answer': 'I need a bit more detail to give you an accurate answer.',
            'needsClarification': True,
            'guidingQuestions': inline_audit.get('guiding_questions', []),
            'interactionId': interaction_id,
            ...
        })
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `AUDIT_QUALITY_THRESHOLD` | `70` | Minimum score to pass quality gate |
| `AUDIT_QUALITY_GATE_ENABLED` | `true` | Feature flag to enable/disable |

## Response JSON Changes

New fields added to the ai-query response:

```json
{
  "answer": "...",
  "needsClarification": false,       // NEW: true when Option 2 triggers
  "guidingQuestions": [],             // NEW: 2-3 questions when needsClarification=true
  "inlineAuditScore": 85,            // NEW: score from inline gate (for debugging)
  "inlineAuditAction": "pass",       // NEW: "pass" | "rewrite" | "clarify"
  ...existing fields...
}
```

## Performance Budget

| Step | Expected Time | Notes |
|------|--------------|-------|
| Bedrock Agent | 2-20s | Existing |
| Inline audit scoring | 1-3s | Nova Lite, short prompt |
| Rewrite (if triggered) | 3-8s | Only on low-quality, ~20% of queries |
| **Total worst case** | **~30s** | Only when rewrite triggers |
| **Total happy path** | **+2s** | Most queries pass on first try |

## Affected Files

1. `member-handler/lambda_function.py` — Add `_inline_audit_score()`, integrate quality gate after agent response
2. `members/members.js` — Handle `needsClarification` response, display guiding questions as clickable buttons
3. `audit-evaluator/lambda_function.py` — No changes (async audit remains independent)
