# Virtual Tagging (Cost Categories) — Requirements

## Overview
Finout-style virtual tagging using AWS Cost Categories backend. Members define "Business Units" with visual rule builder, shared cost splitting, and AI agent integration.

## User Stories

### US-1: Create Business Unit
**As a** member, **I want** to define business units with simple rules **so that** costs are allocated to teams.
- AC: Name a business unit (e.g., "Data Science Team")
- AC: Add rules: Account ID equals X, OR Service equals Y, OR Tag contains Z
- AC: Multiple OR conditions per business unit

### US-2: Shared Cost Splitting
**As a** member, **I want** to split untaggable costs (support, networking) **so that** all costs are allocated.
- AC: Three split modes: Even, Proportional, Custom Percentage
- AC: Applies to costs not matched by any rule

### US-3: Processing Status
**As a** member, **I want** to see when my rules are being processed **so that** I know when data is ready.
- AC: Status: Processing (just saved) → Active (24h later)
- AC: Friendly message: "Rules saved! Dashboard will reflect changes within 24 hours."

### US-4: AI Agent Integration
**As a** member, **I want** to ask "Why did Data Science team's cost spike?" **so that** the AI uses my business units.
- AC: AI maps business unit names to allocation rules
- AC: Filters cost data by the matched business unit's rules
