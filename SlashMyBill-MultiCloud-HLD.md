# SlashMyBill — Multi-Cloud Support High-Level Design

## 1. Executive Summary

Multi-Cloud Support extends SlashMyBill from an AWS-only FinOps platform to a unified multi-cloud solution supporting **AWS, Microsoft Azure, and Google Cloud Platform (GCP)**. Members connect accounts from all three providers within the same user account, view unified cost data in a single dashboard, and receive cloud-specific optimization tips — all powered by the same AI agent.

The extension uses a **Provider Connector pattern** where each cloud provider has a dedicated connector module implementing a common interface. A shared Cost Normalizer transforms provider-specific responses into a unified schema for display and AI analysis. The existing AWS flow remains completely unchanged.

**Supported Providers:** AWS | Azure | GCP
**Platform URL:** https://www.eshkolai.com/members/
**AWS Account:** 991105135552 (us-east-1)

---

## 2. Architecture Overview

### 2.1 Core Components (New/Extended)

| Component | Technology | Purpose |
|-----------|-----------|---------|
| AWS Connector | Python 3.12 (existing) | STS AssumeRole + Cost Explorer (unchanged) |
| Azure Connector | Python 3.12 (new) | OAuth2 Service Principal + Azure Cost Management API |
| GCP Connector | Python 3.12 (new) | JWT Service Account + GCP Cloud Billing API |
| Cost Normalizer | Python 3.12 (new) | Transforms provider-specific cost data → common schema |
| Member Handler | Python 3.12 Lambda (extended) | Multi-cloud account CRUD, connection testing, unified dashboard |
| Admin Handler | Python 3.12 Lambda (extended) | Multi-cloud tips management, per-provider filtering |
| Tips Sync Lambda | Python 3.12 Lambda (extended) | Daily sync of Azure + GCP tips from curated JSON files |
| KMS | AWS KMS (existing) | Encrypts Azure Client Secrets and GCP private keys |
| Accounts Table | DynamoDB (extended) | New `cloudProvider` + `credentials` attributes |
| Tips Table | DynamoDB (extended) | New `cloudProvider` attribute per tip |
| Cost Cache Table | DynamoDB (extended) | Cache key includes `cloudProvider` |
| Member Portal | HTML/CSS/JS (extended) | Provider selection, unified dashboard, provider icons |
| Admin Panel | HTML/CSS/JS (extended) | Provider tabs, sync status display |

### 2.2 Multi-Cloud Access Model

| Provider | Authentication Method | Required Permissions |
|----------|----------------------|---------------------|
| AWS | STS AssumeRole with ExternalId (SHA-256 of email) | ReadOnlyAccess + Cost Explorer inline policy (unchanged) |
| Azure | OAuth2 Client Credentials (Service Principal) | "Cost Management Reader" role on subscription |
| GCP | Self-signed JWT (Service Account key) | "Billing Account Viewer" + "BigQuery User" roles |

### 2.3 System Context Diagram

```
                    ┌─────────────────────────────────────────────────┐
                    │              Member Browser                       │
                    └──────────────────────┬──────────────────────────┘
                                           │ HTTPS
                                           ▼
                    ┌─────────────────────────────────────────────────┐
                    │         CloudFront + API Gateway                  │
                    └──────────────────────┬──────────────────────────┘
                                           │
                                           ▼
                    ┌─────────────────────────────────────────────────┐
                    │           Member Handler Lambda                   │
                    │  (account CRUD, connection test, dashboard data)  │
                    └───┬──────────────┬──────────────┬───────────────┘
                        │              │              │
              ┌─────────▼───┐  ┌───────▼──────┐  ┌───▼────────────┐
              │ AWS Connector│  │Azure Connector│  │ GCP Connector  │
              │ STS + CE     │  │ OAuth2 + CM   │  │ JWT + Billing  │
              └─────────┬───┘  └───────┬──────┘  └───┬────────────┘
                        │              │              │
              ┌─────────▼───┐  ┌───────▼──────┐  ┌───▼────────────┐
              │ Customer AWS │  │ Azure Cost   │  │ GCP Cloud      │
              │ Account      │  │ Management   │  │ Billing API    │
              └─────────────┘  └──────────────┘  └────────────────┘
                        │              │              │
                        └──────────────┼──────────────┘
                                       ▼
                    ┌─────────────────────────────────────────────────┐
                    │              Cost Normalizer                      │
                    │  (common schema: date, service, cost, provider)   │
                    └──────────────────────┬──────────────────────────┘
                                           │
                        ┌──────────────────┼──────────────────┐
                        ▼                  ▼                  ▼
              ┌─────────────────┐ ┌────────────────┐ ┌───────────────┐
              │ DynamoDB        │ │ Cost Cache     │ │ Unified       │
              │ Accounts Table  │ │ Table          │ │ Dashboard     │
              └─────────────────┘ └────────────────┘ └───────────────┘
```

---

## 3. Connection Flows

### 3.1 Azure Connection Flow

```
Member selects "Azure" → Enters Subscription ID, Tenant ID, Client ID
                                    ↓
                    API stores account (status: "pending")
                                    ↓
        Member creates Service Principal in Azure AD
        (assigns "Cost Management Reader" role)
                                    ↓
            Member provides Client Secret → KMS encrypts → stored in DynamoDB
                                    ↓
                    Member clicks "Test Connection"
                                    ↓
        ┌───────────────────────────────────────────────────────┐
        │ 1. Decrypt Client Secret (KMS)                         │
        │ 2. POST /oauth2/token (Tenant ID, Client ID, Secret)  │
        │ 3. POST /costManagement/query (Subscription ID)        │
        │ 4. Update status → "connected"                         │
        └───────────────────────────────────────────────────────┘
```

### 3.2 GCP Connection Flow

```
Member selects "GCP" → Enters Project ID + uploads Service Account JSON key
                                    ↓
        API validates key file (type, project_id, private_key_id, private_key, client_email)
                                    ↓
            KMS encrypts private_key → stored in DynamoDB (status: "pending")
                                    ↓
                    Member clicks "Test Connection"
                                    ↓
        ┌───────────────────────────────────────────────────────┐
        │ 1. Decrypt private key (KMS)                           │
        │ 2. Create self-signed JWT (iss=client_email, RS256)    │
        │ 3. POST /oauth2/token (exchange JWT for access token)  │
        │ 4. GET /billingAccounts/.../projects (Project ID)      │
        │ 5. Update status → "connected"                         │
        └───────────────────────────────────────────────────────┘
```

### 3.3 AWS Connection Flow (Unchanged)

```
Member enters 12-digit Account ID → Deploys CloudFormation template
    → STS AssumeRole → ce:GetCostAndUsage → status: "connected"
```

---

## 4. Unified Cost Data Pipeline

### 4.1 Data Retrieval per Provider

| Provider | API | Authentication | Response Format |
|----------|-----|---------------|-----------------|
| AWS | `ce:GetCostAndUsage` | STS AssumeRole | ResultsByTime → Groups → Metrics |
| Azure | `Microsoft.CostManagement/query` | OAuth2 Bearer token | Rows: [cost, date, serviceName, currency] |
| GCP | Cloud Billing API / BigQuery | JWT Bearer token | BillingAccount → Project → Services |

### 4.2 Common Normalized Schema

```json
{
  "date": "2026-01-15",
  "service_name": "Virtual Machines",
  "cost_amount": 45.23,
  "currency": "USD",
  "cloud_provider": "azure",
  "account_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
}
```

### 4.3 Dashboard Aggregation

```
Per-provider cost retrieval (parallel)
            ↓
    Cost Normalizer (transform to common schema)
            ↓
    ┌───────┼───────┐
    ↓       ↓       ↓
  AWS     Azure    GCP
 total    total   total
    ↓       ↓       ↓
    └───────┼───────┘
            ↓
    Total Cloud Spend + Provider Breakdown (%)
            ↓
    Cache in Cost_Cache_Table
            ↓
    Render: Combined summary + Provider pie chart + Filter toggles
```

### 4.4 Filtering & Display Rules

- Only accounts with `connectionStatus: "connected"` contribute to cost calculations
- Accounts with "pending" or "failed" status show a warning indicator
- If one provider's API fails, others still return data (graceful degradation)
- Provider color coding: AWS (orange), Azure (blue), GCP (red)

---

## 5. Multi-Cloud Optimization Tips

### 5.1 Knowledge Base Structure

```
knowledge-base/
├── aws-cost-optimization-tips.json     (existing, 32+ tips)
├── azure-cost-optimization-tips.json   (new)
└── gcp-cost-optimization-tips.json     (new)
```

### 5.2 Daily Tips Sync (EventBridge + Lambda)

| Aspect | Detail |
|--------|--------|
| Schedule | Daily at 02:00 UTC (configurable) |
| Trigger | EventBridge scheduled rule |
| Source | S3 knowledge base JSON files |
| Upsert logic | Compare by (service + tipId), update only changed tips |
| Removed tips | Marked `deprecated: true` (never deleted) |
| Failure handling | If one provider fails, continue with others |
| Logging | Summary: tips added, updated, deprecated, errors |

### 5.3 Member Tips Display

- Members see only tips for providers they have connected
- Tips grouped by Cloud_Provider with provider-specific tabs
- Admin can filter/manage tips per provider

---

## 6. Data Models (Extended)

### 6.1 Accounts Table (`MemberPortal-Accounts`)

| Attribute | Type | Description |
|-----------|------|-------------|
| memberEmail | String (PK) | Member's email |
| accountId | String (SK) | AWS: 12-digit, Azure: Subscription UUID, GCP: Project ID |
| cloudProvider | String | "aws" / "azure" / "gcp" (defaults to "aws" for legacy) |
| connectionStatus | String | "pending" / "connected" / "failed" |
| credentials | Map | Encrypted provider-specific credentials |
| addedAt | String | ISO 8601 timestamp |
| lastTestedAt | String | Last successful connection test |

**Credentials Map:**

| Provider | Fields Stored |
|----------|--------------|
| AWS | (none — uses STS AssumeRole with roleName) |
| Azure | tenantId, clientId, encryptedClientSecret (KMS) |
| GCP | clientEmail, projectId, privateKeyId, encryptedPrivateKey (KMS) |

### 6.2 Tips Table (`ViewMyBill-CostOptimizationTips`)

| Attribute | Type | Description |
|-----------|------|-------------|
| service | String (PK) | Service name |
| tipId | String (SK) | Unique tip ID (e.g., "azure-vm-001") |
| cloudProvider | String | "aws" / "azure" / "gcp" |
| category | String | Tip category |
| title | String | Short title |
| description | String | Detailed recommendation |
| deprecated | Boolean | True if removed from source |
| lastSyncedAt | String | Last sync timestamp |

### 6.3 Cost Cache Table

- **Cache key format:** `{memberEmail}#{cloudProvider}#{accountId}#{dateRange}`
- Ensures same accountId across different providers produces distinct cache entries

---

## 7. API Changes

### 7.1 Member Handler (Extended Routes)

| Method | Path | Change | Description |
|--------|------|--------|-------------|
| POST | /members/accounts | Modified | Accept `cloudProvider`, route to provider-specific validation |
| PUT | /members/accounts | New | Update credentials (e.g., add Azure Client Secret) |
| POST | /members/accounts/test | Modified | Dispatch to correct connector based on `cloudProvider` |
| GET | /members/accounts | Modified | Return `cloudProvider`, backfill "aws" for legacy |
| GET | /members/dashboard-data | Modified | Aggregate cost data across all providers |
| POST | /members/accounts/ai-query | Modified | Include multi-cloud context in AI prompt |

### 7.2 Admin Handler (Extended Routes)

| Method | Path | Change | Description |
|--------|------|--------|-------------|
| GET | /admin/tips | Modified | Accept `?cloudProvider=` filter |
| POST | /admin/tips | Modified | Require `cloudProvider` field |
| GET | /admin/tips-sync/status | New | Per-provider sync status + last timestamp |

### 7.3 Input Validation Rules

| Provider | Field | Format |
|----------|-------|--------|
| AWS | accountId | Exactly 12 digits (`^\d{12}$`) |
| Azure | subscriptionId | UUID (`^[0-9a-f]{8}-...-[0-9a-f]{12}$`) |
| Azure | tenantId | UUID (same format) |
| GCP | projectId | 6-30 chars, lowercase alphanumeric + hyphens (`^[a-z][a-z0-9-]{4,28}[a-z0-9]$`) |

---

## 8. Security Model (Multi-Cloud Extension)

| Layer | Mechanism |
|-------|-----------|
| Credential Encryption | AWS KMS with dedicated key (Azure secrets + GCP private keys) |
| Decryption Scope | Only at connection-test or cost-retrieval time; plaintext discarded immediately |
| API Response Security | Sensitive credentials never returned in responses |
| KMS Key Policy | Restricted to Member Portal Lambda execution role only |
| KMS Failure | Returns generic 500 error; detailed error logged internally |
| Input Validation | Provider-specific format validation on all write operations |
| Backward Compatibility | Legacy records without `cloudProvider` default to "aws" |
| Authentication | Existing JWT token required for all multi-cloud operations |

---

## 9. AI Agent Multi-Cloud Context

### 9.1 Enhanced AI Prompt Context

When a member sends an AI query, the system now includes:
- List of connected cloud providers and their account identifiers
- Provider-specific cost data scoped to the relevant provider
- Instructions for the model to provide cloud-specific recommendations

### 9.2 AI Behavior Rules

| Scenario | AI Response |
|----------|-------------|
| Member asks about a connected provider | Scope context to that provider's accounts |
| Member asks about an unconnected provider | Inform them no accounts are connected, suggest connecting |
| General cost question | Include data from all connected providers |
| Optimization question | Provide provider-specific recommendations |

---

## 10. Frontend Changes

### 10.1 Member Portal

| Element | Description |
|---------|-------------|
| Add Account Modal | Provider selection step (3 cards: AWS, Azure, GCP with logos) |
| Provider-Specific Forms | AWS: 12-digit ID, Azure: Subscription/Tenant/Client IDs, GCP: Project ID + file upload |
| Accounts List | Provider icon + color coding next to each account |
| Identifier Labels | "Account ID" (AWS), "Subscription ID" (Azure), "Project ID" (GCP) |
| Dashboard Header | Summary count of connected accounts per provider |
| Dashboard Chart | Provider breakdown pie chart (% spend per provider) |
| Filter Toggle | Filter cost data by Cloud_Provider |
| Connection Instructions | Provider-specific setup guides (downloadable scripts) |

### 10.2 Admin Panel

| Element | Description |
|---------|-------------|
| Tip Creation Form | "Cloud Provider" dropdown (AWS, Azure, GCP) |
| Tips List | Provider tabs/filter controls |
| Sync Status | Per-provider last sync timestamp + status indicator |

---

## 11. Backward Compatibility Guarantees

| Aspect | Guarantee |
|--------|-----------|
| Existing AWS accounts | Continue working without any changes |
| Legacy records (no `cloudProvider`) | Default to "aws" in all read operations |
| CloudFormation template generation | Unchanged for AWS accounts |
| AWS connection test | Same behavior and response format |
| AWS cost retrieval | Same STS AssumeRole + Cost Explorer flow |
| AWS-only members | Same dashboard experience + provider icons |
| Existing API endpoints | No breaking changes |
| Error messages | Existing AWS errors unchanged; new providers use same format |

---

## 12. Error Handling

### 12.1 Provider Connection Errors

| Scenario | Provider | HTTP | User Message |
|----------|----------|------|--------------|
| Invalid Service Principal | Azure | 400 | "Verify credentials and 'Cost Management Reader' role" |
| Expired Client Secret | Azure | 400 | "Generate a new secret in Azure AD" |
| Insufficient permissions | Azure | 400 | "Verify 'Cost Management Reader' role on subscription" |
| Invalid service account key | GCP | 400 | "Verify key file and 'Billing Account Viewer' role" |
| Billing not enabled | GCP | 400 | "Ensure billing is enabled for this project" |
| KMS decryption failure | Any | 500 | "Unable to access credentials. Contact support." |
| Provider API timeout | Any | 504 | "Connection timed out. Try again." |
| Provider API rate limit | Any | 429 | "Rate limit reached. Wait and retry." |
| Invalid cloudProvider | Any | 400 | "Supported values: aws, azure, gcp" |
| Duplicate account | Any | 409 | "Account already connected" |
| Malformed GCP key file | GCP | 400 | "Required fields: type, project_id, private_key_id, private_key, client_email" |

### 12.2 Graceful Degradation

- If one provider's API fails during dashboard load, other providers still return data
- Tips sync continues processing remaining providers if one fails
- Failed accounts excluded from cost calculations (warning shown to user)

---

## 13. Infrastructure Changes

### 13.1 New/Modified Lambda Functions

| Function | Change | Memory | Timeout |
|----------|--------|--------|---------|
| aws-bill-analyzer-member-api | Extended (multi-cloud connectors) | 256 MB | 120s |
| aws-bill-analyzer-admin-api | Extended (provider filter) | 128 MB | 30s |
| Tips Sync Lambda | Extended (Azure + GCP sources) | 128 MB | 60s |

### 13.2 New Dependencies (Member Handler Lambda)

| Package | Purpose |
|---------|---------|
| PyJWT | GCP JWT signing (already present for member auth) |
| cryptography | RS256 key signing for GCP |
| requests / urllib3 | Azure OAuth2 + Cost Management API calls |

### 13.3 New AWS Resources

| Resource | Purpose |
|----------|---------|
| KMS Key (multi-cloud-credentials) | Encrypt Azure/GCP credentials |
| EventBridge Rule (tips-sync-daily) | Trigger daily tips sync at 02:00 UTC |
| S3 objects (knowledge-base/) | azure-cost-optimization-tips.json, gcp-cost-optimization-tips.json |

### 13.4 DynamoDB Table Changes

| Table | Change |
|-------|--------|
| MemberPortal-Accounts | Add `cloudProvider` (String) + `credentials` (Map) attributes |
| ViewMyBill-CostOptimizationTips | Add `cloudProvider` (String) + `deprecated` (Boolean) + `lastSyncedAt` (String) |
| Cost_Cache_Table | Extended cache key format (includes cloudProvider) |

---

## 14. Module Structure

```
member-handler/
├── lambda_function.py              (extended: multi-cloud routing)
├── cost_normalizer.py              (new: unified cost transformation)
├── connectors/
│   ├── __init__.py
│   ├── base_connector.py           (new: ProviderConnector interface)
│   ├── aws_connector.py            (refactored from existing logic)
│   ├── azure_connector.py          (new: OAuth2 + Cost Management)
│   └── gcp_connector.py            (new: JWT + Cloud Billing)
knowledge-base/
├── aws-cost-optimization-tips.json (existing)
├── azure-cost-optimization-tips.json (new)
└── gcp-cost-optimization-tips.json   (new)
```

---

## 15. Key Design Decisions

| # | Decision | Rationale |
|---|----------|-----------|
| 1 | Provider Connector Pattern | Isolates provider-specific logic; adding future providers (Oracle, Alibaba) requires only a new connector module |
| 2 | Credentials in DynamoDB (KMS-encrypted) | Avoids separate secrets store; leverages existing table; KMS provides envelope encryption |
| 3 | Backward-compatible schema | Zero disruption for existing members; no migration needed |
| 4 | Cost Normalizer as separate module | Single responsibility; testable independently; reusable across dashboard + AI |
| 5 | Daily tips sync (not real-time) | Tips are curated content, not live data; daily is sufficient; reduces complexity |
| 6 | Cloud Billing API over BigQuery for GCP | Simpler setup (no billing export required); BigQuery as optional enhancement |
| 7 | Existing AWS flow unchanged | Risk mitigation; proven flow stays stable; multi-cloud is additive only |
