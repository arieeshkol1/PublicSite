# Bugfix Requirements Document

## Introduction

The waste scan endpoint (POST /members/actions/scan) consistently returns HTTP 503 "Service Unavailable" for accounts with many resources because the scan takes 40-90 seconds to complete, exceeding the API Gateway hard 30-second integration timeout. The Lambda itself has a 300-second timeout and sufficient memory (2048MB), but API Gateway's limit cannot be increased. This bug affects all members with accounts containing 15+ resources across multiple regions, making the waste scan feature unusable for them.

The fix converts the synchronous scan into an asynchronous pattern: the initial request returns immediately with a `scanId`, the Lambda invokes itself asynchronously to perform the actual scan, and the frontend polls a new status endpoint until results are ready.

## Bug Analysis

### Current Behavior (Defect)

1.1 WHEN a waste scan request (POST /members/actions/scan) takes longer than 30 seconds to complete THEN the system returns HTTP 503 "Service Unavailable" because API Gateway terminates the connection before the Lambda finishes processing

1.2 WHEN an account has many resources (e.g., 15+ EC2 instances across multiple regions requiring 7 category checks) THEN the system consistently times out because the scan requires 40-90 seconds to evaluate all resource categories (EIPs, EBS volumes, Load Balancers, S3 buckets, EC2 instances, RDS instances, EBS snapshots)

1.3 WHEN the scan times out at the API Gateway level THEN the system loses all scan progress and returns no partial results to the user, despite the Lambda continuing to execute in the background

### Expected Behavior (Correct)

2.1 WHEN a waste scan request (POST /members/actions/scan) is initiated THEN the system SHALL return immediately (within 2-3 seconds) with a `scanId` (UUID) and HTTP 200, regardless of how long the actual scan will take

2.2 WHEN the frontend receives a `scanId` THEN the system SHALL provide a status polling endpoint (GET /members/actions/scan-status?scanId=X) that returns the current scan status ("in_progress", "complete", or "failed") and results when complete

2.3 WHEN the scan is initiated THEN the system SHALL invoke the scan processing asynchronously (Lambda Event invocation) so that the full scan runs without API Gateway timeout constraints

2.4 WHEN the frontend polls for scan status and the scan is complete THEN the system SHALL return the full scan results in the same format as the previous synchronous response (cards, findings, totalSavings, scannedAccounts, scannedAt)

2.5 WHEN the frontend polls for scan status and the scan is still in progress THEN the system SHALL return the current status with an optional progress indicator (e.g., current category being scanned)

2.6 WHEN the async scan invocation fails or the scan does not complete within 60 seconds of polling THEN the system SHALL return a "failed" status with an appropriate error message

### Unchanged Behavior (Regression Prevention)

3.1 WHEN a scan completes successfully (via the new async pattern) THEN the system SHALL CONTINUE TO return results in the same format with 7 category cards (EIPs, EBS volumes, Load Balancers, S3 buckets, EC2 instances, RDS instances, EBS snapshots), findings array, and totalSavings

3.2 WHEN the GET /members/actions/last-scan endpoint is called THEN the system SHALL CONTINUE TO return the last completed scan results for the member

3.3 WHEN a scan is initiated THEN the system SHALL CONTINUE TO verify account ownership, check credits, and validate the authentication token before starting the scan

3.4 WHEN accounts with few resources are scanned (completing in under 30 seconds) THEN the system SHALL CONTINUE TO produce correct and complete scan results

3.5 WHEN the scan evaluates tips against collected service data THEN the system SHALL CONTINUE TO use the same tip evaluation logic, deduplication, and sorting as the current implementation

---

## Bug Condition (Formal)

```pascal
FUNCTION isBugCondition(X)
  INPUT: X of type ScanRequest
  OUTPUT: boolean
  
  // Returns true when the scan duration exceeds API Gateway's 30-second timeout
  RETURN scanDuration(X.accountIds, X.regions, X.resourceCount) > 30 seconds
END FUNCTION
```

### Property: Fix Checking

```pascal
// Property: Fix Checking - Async scan returns immediately
FOR ALL X WHERE isBugCondition(X) DO
  result ← POST /members/actions/scan(X)
  ASSERT result.statusCode = 200
  ASSERT result.body.scanId IS NOT NULL
  ASSERT responseTime(result) < 5 seconds
  
  // Eventually completes via polling
  finalResult ← pollUntilComplete(result.body.scanId, timeout=60s)
  ASSERT finalResult.status = "complete"
  ASSERT finalResult.cards IS NOT NULL
  ASSERT finalResult.totalSavings IS NOT NULL
END FOR
```

### Property: Preservation Checking

```pascal
// Property: Preservation Checking - Results format unchanged
FOR ALL X WHERE NOT isBugCondition(X) DO
  ASSERT F(X).cards FORMAT = F'(X).cards FORMAT
  ASSERT F(X).findings FORMAT = F'(X).findings FORMAT
  ASSERT F(X).totalSavings = F'(X).totalSavings
END FOR
```
