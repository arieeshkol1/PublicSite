# Implementation Plan: Terraform IaC Integration

## Overview

Add Terraform HCL code generation as a first-class alternative to CloudFormation across the SlashMyBill platform. Implementation follows the existing Member_Handler Lambda architecture with a new `hcl_generator` Python package and a unified API endpoint (`POST /members/terraform/generate`). The frontend adds "Download Terraform" buttons alongside existing controls.

## Tasks

- [x] 1. Set up HCL Generator package structure and core serialization
  - [x] 1.1 Create the `hcl_generator` package with core HCL serialization primitives
    - Create `member-handler/hcl_generator/__init__.py` exporting `generate_hcl()`
    - Create `member-handler/hcl_generator/core.py` with `HclBlock`, `HclDocument`, `escape_hcl_string()`, `render_provider_block()`
    - Implement 2-space indentation rendering, block nesting, attribute serialization
    - Implement HCL string escaping for quotes, backslashes, `${` and `%{` interpolation sequences
    - _Requirements: 7.1, 7.4, 7.5_

  - [x] 1.2 Create the Terraform identifier converter module
    - Create `member-handler/hcl_generator/identifiers.py` with `to_terraform_identifier()`
    - Convert AWS resource IDs (e.g., `i-0abc123def`, `vol-xxx`, `eipalloc-xxx`) to valid Terraform identifiers matching `[a-z][a-z0-9_-]*`
    - Ensure deterministic output (same input always produces same identifier)
    - _Requirements: 7.6_

  - [x]* 1.3 Write property test for HCL string escaping correctness
    - **Property 3: HCL String Escaping Correctness**
    - **Validates: Requirements 7.4**

  - [x]* 1.4 Write property test for Terraform identifier validity
    - **Property 4: Terraform Identifier Validity**
    - **Validates: Requirements 7.6**

- [x] 2. Implement cross-account role Terraform generation
  - [x] 2.1 Create the cross-account template generator
    - Create `member-handler/hcl_generator/cross_account.py` with `generate_cross_account_template()`
    - Generate `terraform { required_providers {} }` block with AWS provider version constraint
    - Generate `variable` blocks for `account_id` and `platform_account_id` with defaults
    - Generate `aws_iam_role` resource with trust policy including `sts:ExternalId` condition (SHA-256 of member email)
    - Generate `aws_iam_role_policy_attachment` for ReadOnlyAccess
    - Generate `aws_iam_role_policy` for inline billing/action permissions
    - Generate `output` block exposing role ARN
    - Include `provider "aws"` block with region and `assume_role` configuration
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 7.7_

  - [x] 2.2 Create the cross-account Terraform module ZIP generator
    - Implement `generate_cross_account_module()` returning a ZIP archive bytes
    - Generate `main.tf` with role resource, policy attachment, and inline policy
    - Generate `variables.tf` with `account_id` (required), `platform_account_id` (default), `external_id` (required, sensitive)
    - Generate `outputs.tf` with `role_arn` and `role_name`
    - Generate `README.md` with usage examples
    - Populate `external_id` default with SHA-256 hash of requesting member email
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7_

  - [x]* 2.3 Write property test for ExternalId SHA-256 correctness
    - **Property 2: ExternalId SHA-256 Correctness**
    - **Validates: Requirements 1.2, 2.6**

  - [x]* 2.4 Write property test for provider block correctness
    - **Property 10: Provider Block Correctness**
    - **Validates: Requirements 7.7**

- [x] 3. Implement optimization action HCL generators
  - [x] 3.1 Create the action HCL generator module with dispatch logic
    - Create `member-handler/hcl_generator/actions.py` with `generate_action_hcl()` and `SUPPORTED_ACTION_TYPES`
    - Implement dispatch based on `action_type` to individual generator functions
    - Include header comment with action description, timestamp, account ID, and review warning in every generated file
    - _Requirements: 3.8, 3.9_

  - [x] 3.2 Implement resize EC2 action generator
    - Generate `aws_instance` resource with recommended instance type
    - Generate `import {}` block referencing the existing instance ID
    - _Requirements: 3.1_

  - [x] 3.3 Implement delete EBS and release EIP action generators
    - Generate `removed {}` block (Terraform 1.7+) for EBS volume with destroy comment
    - Generate `removed {}` block for `aws_eip` with allocation ID
    - _Requirements: 3.2, 3.3_

  - [x] 3.4 Implement S3 lifecycle rule action generator
    - Generate `aws_s3_bucket_lifecycle_configuration` resource with transition and expiration rules
    - Generate `import {}` block for the bucket
    - _Requirements: 3.4_

  - [x] 3.5 Implement create schedule action generator
    - Generate `aws_scheduler_schedule` resources for start and stop events with cron expressions
    - _Requirements: 3.5_

  - [x] 3.6 Implement apply tags and create budget action generators
    - Generate target resource with recommended tags plus `import {}` block for tag actions
    - Generate `aws_budgets_budget` resource with amount, time period, and notification thresholds for budget actions
    - _Requirements: 3.6, 3.7_

  - [x]* 3.7 Write property test for header comment completeness
    - **Property 5: Header Comment Completeness**
    - **Validates: Requirements 3.8**

  - [x]* 3.8 Write property test for action type to resource mapping
    - **Property 6: Action Type to Resource Mapping**
    - **Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7**

- [x] 4. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 5. Implement waste action and commitment generators
  - [x] 5.1 Create the waste action generator module
    - Create `member-handler/hcl_generator/waste.py` with `generate_waste_action_hcl()`
    - Implement EBS volume waste action: `aws_ebs_volume` resource with current attributes + `import {}` block
    - Implement EIP waste action: `aws_eip` resource with current attributes + `import {}` block
    - Implement load balancer waste action: `aws_lb` or `aws_elb` resource + `import {}` block
    - Include step-by-step comment block explaining import-then-destroy workflow (init → plan → apply → remove → apply)
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5_

  - [x] 5.2 Add AWS API integration for fetching current resource attributes
    - Implement STS AssumeRole to Customer_Account via Cross_Account_Role
    - Query EC2/EBS/ELB APIs to populate resource definitions accurately
    - Handle API failures with descriptive error responses
    - _Requirements: 4.6_

  - [x] 5.3 Create the RI/SP commitment snippet generator
    - Create `member-handler/hcl_generator/commitments.py` with `generate_commitment_snippet()`
    - Generate commented HCL documenting commitment details (type, term, payment option, savings, instance family)
    - Generate active `aws_budgets_budget` resource with monthly granularity and committed amount as limit
    - Generate budget notification rules at 80% and 100% thresholds with member email as subscriber
    - Include comment explaining RI/SP must be purchased via Console/CLI
    - Generate separate commented sections for each option (1-year vs 3-year, payment types)
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5_

  - [x]* 5.4 Write property test for waste action import structure
    - **Property 7: Waste Action Import Structure**
    - **Validates: Requirements 4.1, 4.2, 4.3, 4.4, 4.5**

  - [x]* 5.5 Write property test for RI/SP budget tracking generation
    - **Property 8: RI/SP Budget Tracking Generation**
    - **Validates: Requirements 5.2, 5.3, 5.5**

- [x] 6. Implement the Terraform API endpoint
  - [x] 6.1 Add the `/members/terraform/generate` route to Member_Handler Lambda
    - Add `'POST /members/terraform/generate': handle_terraform_generate` to the routes dict in `lambda_function.py`
    - Implement `handle_terraform_generate(event)` with authentication, body parsing, account ownership verification
    - Dispatch to appropriate generator based on `actionType` (cross-account-role, cross-account-module, optimization actions, waste actions, ri-sp-commitment)
    - Return file content with `Content-Disposition: attachment` header and appropriate content type
    - Return 400 for missing required fields, 403 for unauthorized accounts, 400 for unsupported action types
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7_

  - [x] 6.2 Integrate backward-compatible CloudFormation template generation
    - Ensure existing `handle_generate_template` continues to return CloudFormation YAML when format is "cloudformation" or unspecified
    - _Requirements: 1.6, 1.7_

  - [x]* 6.3 Write property test for account ownership enforcement
    - **Property 9: Account Ownership Enforcement**
    - **Validates: Requirements 8.5**

  - [x]* 6.4 Write unit tests for API endpoint validation and error handling
    - Test missing actionType returns 400
    - Test missing accountId for account-specific actions returns 400
    - Test invalid accountId format returns 400
    - Test unsupported action type returns 400 with descriptive message
    - Test unauthenticated request returns 401
    - _Requirements: 8.7_

- [x] 7. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 8. Implement frontend Terraform download integration
  - [x] 8.1 Add `downloadTerraform()` function to Members Frontend
    - Implement `downloadTerraform(actionType, accountId, actionParams)` in `members/members.js`
    - Call `POST /members/terraform/generate` with authentication header
    - Trigger browser file download from the response blob
    - _Requirements: 6.2_

  - [x] 8.2 Add "Download Terraform" buttons to optimization action cards
    - Render a "Download Terraform" button alongside the existing "Execute" button on each action card
    - Wire click handler to call `downloadTerraform()` with the action's type and parameters
    - Display loading indicator while request is in progress, disable repeated clicks
    - Display tooltip/message for unsupported action types when API returns error
    - _Requirements: 6.1, 6.5, 6.6_

  - [x] 8.3 Add "Download Terraform" option to account connection page
    - Add "Download Terraform" button alongside existing "Download CloudFormation" button
    - Wire click to request template with format "terraform" and trigger `.tf` file download
    - _Requirements: 6.3, 6.4_

- [x] 9. Implement HCL round-trip parsing and final property tests
  - [x] 9.1 Implement `HclDocument.parse()` and `ActionDefinition.from_hcl()` for round-trip verification
    - Add `parse()` classmethod to `HclDocument` that parses HCL string back into structured blocks
    - Add `from_hcl()` classmethod to `ActionDefinition` that reconstructs action definition from parsed HCL
    - _Requirements: 7.3_

  - [x]* 9.2 Write property test for HCL serialization round-trip
    - **Property 1: HCL Serialization Round-Trip**
    - **Validates: Requirements 7.3**

- [x] 10. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- Unit tests validate specific examples and edge cases
- The HCL Generator uses Python (matching the existing Member_Handler Lambda)
- Frontend changes use vanilla JavaScript (matching the existing Members Frontend)
- No Terraform state management is implemented — the platform only generates downloadable `.tf` files

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2"] },
    { "id": 1, "tasks": ["1.3", "1.4", "2.1"] },
    { "id": 2, "tasks": ["2.2", "2.3", "2.4", "3.1"] },
    { "id": 3, "tasks": ["3.2", "3.3", "3.4", "3.5", "3.6"] },
    { "id": 4, "tasks": ["3.7", "3.8", "5.1", "5.3"] },
    { "id": 5, "tasks": ["5.2", "5.4", "5.5"] },
    { "id": 6, "tasks": ["6.1"] },
    { "id": 7, "tasks": ["6.2", "6.3", "6.4"] },
    { "id": 8, "tasks": ["8.1"] },
    { "id": 9, "tasks": ["8.2", "8.3", "9.1"] },
    { "id": 10, "tasks": ["9.2"] }
  ]
}
```
