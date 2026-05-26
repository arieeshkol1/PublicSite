# Requirements Document

## Introduction

SlashMyBill currently generates CloudFormation templates for cross-account IAM role provisioning and provides "Execute" actions for optimization recommendations (resize EC2, delete EBS, release EIPs, add S3 lifecycle rules, create schedules, apply tags, create budgets). Many enterprise customers use Terraform as their Infrastructure-as-Code engine and cannot adopt CloudFormation-based workflows. This feature adds Terraform HCL code generation as a first-class alternative across the platform: cross-account role setup, optimization action execution, waste action exports, and RI/SP commitment documentation. All Terraform code is generated server-side by the Member_Handler Lambda and delivered as downloadable `.tf` files.

## Glossary

- **Platform_Account**: The SlashMyBill AWS account (991105135552) where all platform infrastructure runs
- **Customer_Account**: An AWS account connected to SlashMyBill via a cross-account IAM role
- **Cross_Account_Role**: The IAM role `SlashMyBill-{accountId}` deployed in each Customer_Account, assumed by Platform_Account Lambdas using STS with ExternalId = SHA256(memberEmail)
- **Member_Handler**: The existing Lambda `aws-bill-analyzer-member-api` that handles all member API routes
- **Members_Frontend**: The vanilla JavaScript frontend at `members/members.js` that renders the member portal UI
- **HCL**: HashiCorp Configuration Language — the declarative syntax used by Terraform to define infrastructure resources
- **TF_File**: A file with `.tf` extension containing valid HCL code that Terraform can plan and apply
- **Terraform_Module**: A reusable, self-contained package of Terraform configuration that encapsulates related resources with input variables and outputs
- **Terraform_Import**: The `terraform import` command that brings existing infrastructure under Terraform state management without recreating resources
- **Import_Block**: A Terraform 1.5+ `import {}` block in HCL that declaratively specifies resources to import during `terraform plan`
- **Optimization_Action**: A platform-recommended change to reduce AWS costs (resize instance, delete volume, release EIP, add lifecycle rule, create schedule, apply tag, create budget)
- **Waste_Action**: A destructive optimization action that removes unused resources (delete EBS volume, release Elastic IP, delete idle load balancer)
- **RI_SP_Commitment**: A Reserved Instance or Savings Plan purchase commitment that cannot be provisioned via Terraform but can be documented and tracked via budget resources
- **HCL_Generator**: The server-side Python module responsible for translating optimization action parameters into valid Terraform HCL code

## Requirements

### Requirement 1: Cross-Account Role Terraform Template Generation

**User Story:** As a member, I want to download a Terraform file as an alternative to CloudFormation for setting up the cross-account IAM role, so that I can provision the SlashMyBill access role using my existing Terraform workflow.

#### Acceptance Criteria

1. WHEN a member requests a cross-account template with format set to "terraform", THE Member_Handler SHALL generate a valid TF_File containing an `aws_iam_role` resource with the same trust policy, managed policy attachments, and inline policy permissions as the equivalent CloudFormation template.
2. WHEN generating the Terraform cross-account template, THE Member_Handler SHALL include the `sts:ExternalId` condition in the assume role policy using the SHA-256 hash of the member email, matching the CloudFormation template behavior.
3. WHEN generating the Terraform cross-account template, THE Member_Handler SHALL include Terraform `variable` blocks for `account_id` and `platform_account_id` with default values populated from the member context.
4. WHEN generating the Terraform cross-account template, THE Member_Handler SHALL include an `output` block exposing the role ARN, matching the CloudFormation Outputs section.
5. WHEN generating the Terraform cross-account template, THE Member_Handler SHALL include a `terraform { required_providers {} }` block specifying the AWS provider with a minimum version constraint.
6. WHEN a member requests a cross-account template with format set to "cloudformation" or with no format specified, THE Member_Handler SHALL return the existing CloudFormation YAML template without modification.
7. THE Member_Handler SHALL return the Terraform template as a downloadable file named `SlashMyBill-{accountId}.tf` with content type `application/octet-stream`.

### Requirement 2: Cross-Account Role Terraform Module

**User Story:** As a member, I want a reusable Terraform module for the SlashMyBill cross-account role, so that I can integrate it into my organization's module registry and provision access across multiple accounts consistently.

#### Acceptance Criteria

1. WHEN a member requests the Terraform module, THE Member_Handler SHALL return a ZIP archive containing `main.tf`, `variables.tf`, `outputs.tf`, and a `README.md` file.
2. THE Terraform_Module `variables.tf` SHALL define input variables for: `account_id` (required, string), `platform_account_id` (string, default "991105135552"), and `external_id` (required, sensitive string).
3. THE Terraform_Module `main.tf` SHALL create an `aws_iam_role` resource, an `aws_iam_role_policy_attachment` for ReadOnlyAccess, and an `aws_iam_role_policy` for the inline billing and action permissions.
4. THE Terraform_Module `outputs.tf` SHALL export `role_arn` and `role_name` as outputs.
5. THE Terraform_Module `README.md` SHALL include usage examples showing how to call the module with required variables and how to reference the outputs.
6. WHEN generating the module, THE Member_Handler SHALL populate the `external_id` variable default with the SHA-256 hash of the requesting member's email.
7. THE Member_Handler SHALL return the module ZIP archive named `slashmybill-cross-account-module.zip` with content type `application/zip`.

### Requirement 3: Optimization Action Terraform Download

**User Story:** As a member, I want to download Terraform HCL code for each optimization action the platform recommends, so that I can apply cost-saving changes through my Terraform pipeline instead of direct API execution.

#### Acceptance Criteria

1. WHEN a member requests a Terraform download for a resize EC2 action, THE HCL_Generator SHALL produce a TF_File containing an `aws_instance` resource definition with the recommended instance type and an Import_Block referencing the existing instance ID.
2. WHEN a member requests a Terraform download for a delete EBS volume action, THE HCL_Generator SHALL produce a TF_File containing a `removed {}` block (Terraform 1.7+) for the volume resource with a comment explaining the volume will be destroyed on apply.
3. WHEN a member requests a Terraform download for a release Elastic IP action, THE HCL_Generator SHALL produce a TF_File containing a `removed {}` block for the `aws_eip` resource with the allocation ID.
4. WHEN a member requests a Terraform download for an S3 lifecycle rule action, THE HCL_Generator SHALL produce a TF_File containing an `aws_s3_bucket_lifecycle_configuration` resource with the recommended transition and expiration rules, plus an Import_Block for the bucket.
5. WHEN a member requests a Terraform download for a create schedule action, THE HCL_Generator SHALL produce a TF_File containing `aws_scheduler_schedule` resources for the start and stop events with the specified cron expressions.
6. WHEN a member requests a Terraform download for an apply tags action, THE HCL_Generator SHALL produce a TF_File containing the target resource with the recommended tags, plus an Import_Block to adopt the existing resource.
7. WHEN a member requests a Terraform download for a create budget action, THE HCL_Generator SHALL produce a TF_File containing an `aws_budgets_budget` resource with the specified amount, time period, and notification thresholds.
8. THE HCL_Generator SHALL include a header comment in every generated TF_File with: the action description, the generation timestamp, the target account ID, and a warning that the file should be reviewed before applying.
9. IF the optimization action type is not supported for Terraform generation, THEN THE Member_Handler SHALL return an error indicating the action type is not yet available for Terraform export.

### Requirement 4: Waste Action Terraform Export with Import

**User Story:** As a member, I want to export waste actions as Terraform code with import blocks, so that I can bring existing resources under Terraform management before destroying them through my IaC pipeline.

#### Acceptance Criteria

1. WHEN a member clicks "Download as Terraform" on a waste action, THE HCL_Generator SHALL produce a TF_File containing both the resource definition and an Import_Block that maps the resource to its AWS identifier.
2. WHEN generating Terraform for a delete EBS volume waste action, THE HCL_Generator SHALL include the `aws_ebs_volume` resource with all current attributes (size, type, AZ, tags) and an `import { id = "vol-xxx" }` block, plus a comment instructing the user to run `terraform apply` followed by removing the resource block and re-applying to destroy.
3. WHEN generating Terraform for a release EIP waste action, THE HCL_Generator SHALL include the `aws_eip` resource with current attributes and an `import { id = "eipalloc-xxx" }` block.
4. WHEN generating Terraform for a delete idle load balancer waste action, THE HCL_Generator SHALL include the `aws_lb` resource (or `aws_elb` for Classic) with current attributes and the corresponding Import_Block.
5. THE HCL_Generator SHALL include a step-by-step comment block at the top of each waste action TF_File explaining the import-then-destroy workflow: (1) terraform init, (2) terraform plan to verify import, (3) terraform apply to import, (4) remove the resource block, (5) terraform apply to destroy.
6. WHEN generating waste action Terraform, THE HCL_Generator SHALL query the current resource attributes from the Customer_Account via the Cross_Account_Role to populate the resource definition accurately.

### Requirement 5: RI/SP Commitment Terraform Snippets

**User Story:** As a member, I want Terraform snippets that document my RI/SP commitment decisions and create tracking budgets, so that I can maintain an IaC record of commitments even though Terraform cannot purchase them directly.

#### Acceptance Criteria

1. WHEN a member requests a Terraform snippet for an RI/SP commitment recommendation, THE HCL_Generator SHALL produce a TF_File containing commented HCL that documents the commitment details (type, term, payment option, estimated savings, instance family or compute type).
2. WHEN generating an RI/SP commitment snippet, THE HCL_Generator SHALL include an active (uncommented) `aws_budgets_budget` resource configured to track the commitment spend with monthly granularity and the committed amount as the budget limit.
3. WHEN generating an RI/SP commitment snippet, THE HCL_Generator SHALL include budget notification rules at 80% and 100% thresholds with the member email as the subscriber.
4. THE HCL_Generator SHALL include a comment block explaining that RI/SP purchases must be made through the AWS Console or CLI, and that the budget resource serves as a tracking and alerting mechanism.
5. WHEN the commitment recommendation includes multiple options (1-year vs 3-year, All Upfront vs No Upfront), THE HCL_Generator SHALL generate separate commented sections for each option with the corresponding budget configuration, allowing the member to uncomment their chosen option.

### Requirement 6: Terraform Download UI Integration

**User Story:** As a member, I want a "Download Terraform" button alongside existing action controls in the UI, so that I can easily access the Terraform alternative for any supported action.

#### Acceptance Criteria

1. WHEN the Members_Frontend renders an optimization action card, THE Members_Frontend SHALL display a "Download Terraform" button alongside the existing "Execute" button.
2. WHEN a member clicks the "Download Terraform" button, THE Members_Frontend SHALL call the Member_Handler API endpoint and trigger a browser file download of the returned TF_File.
3. WHEN the Members_Frontend renders the account connection page, THE Members_Frontend SHALL display a "Download Terraform" option alongside the existing "Download CloudFormation" button.
4. WHEN a member clicks "Download Terraform" on the account connection page, THE Members_Frontend SHALL request the template with format "terraform" and trigger a browser download of the resulting `.tf` file.
5. WHILE a Terraform download request is in progress, THE Members_Frontend SHALL display a loading indicator on the button and disable repeated clicks.
6. IF the Member_Handler returns an error indicating the action type is not supported for Terraform, THEN THE Members_Frontend SHALL display a tooltip or message explaining that Terraform export is not yet available for this action type.

### Requirement 7: HCL Code Generation Engine

**User Story:** As a platform developer, I want a server-side HCL generation module that produces valid, well-formatted Terraform code from action parameters, so that all Terraform outputs are consistent and syntactically correct.

#### Acceptance Criteria

1. THE HCL_Generator SHALL produce syntactically valid HCL that passes `terraform fmt` without modifications.
2. THE HCL_Generator SHALL produce HCL that passes `terraform validate` when a valid AWS provider is configured.
3. FOR ALL supported action types, generating HCL then parsing the output back into structured data SHALL produce an equivalent action definition (round-trip property for the HCL serializer).
4. THE HCL_Generator SHALL escape special characters in string values (quotes, backslashes, interpolation sequences) according to HCL string literal rules.
5. THE HCL_Generator SHALL use consistent indentation (2 spaces) and block formatting across all generated files.
6. WHEN generating resource names, THE HCL_Generator SHALL produce valid Terraform identifiers using only lowercase letters, digits, underscores, and hyphens, derived from the resource's AWS identifier.
7. THE HCL_Generator SHALL include a `provider "aws"` block with the `region` and `assume_role` configuration pointing to the Cross_Account_Role in the Customer_Account.
8. IF an action parameter contains a value that cannot be represented in HCL, THEN THE HCL_Generator SHALL return a generation error with a description of the unsupported value.

### Requirement 8: Terraform API Endpoint

**User Story:** As a platform developer, I want a dedicated API endpoint for Terraform generation requests, so that the frontend and future integrations have a clean interface for requesting Terraform code.

#### Acceptance Criteria

1. WHEN a member sends a POST request to `/members/terraform/generate`, THE Member_Handler SHALL authenticate the request, validate the action parameters, invoke the HCL_Generator, and return the generated TF_File content.
2. WHEN a member sends a POST request to `/members/terraform/generate` with `actionType` set to "cross-account-role", THE Member_Handler SHALL generate the cross-account role Terraform template for the specified account.
3. WHEN a member sends a POST request to `/members/terraform/generate` with `actionType` set to "cross-account-module", THE Member_Handler SHALL generate and return the Terraform module ZIP archive.
4. WHEN a member sends a POST request to `/members/terraform/generate` with `actionType` set to an optimization action type, THE Member_Handler SHALL generate the corresponding action Terraform code using the provided action parameters.
5. THE Member_Handler SHALL validate that the member owns the target account before generating Terraform code for any account-specific action.
6. WHEN the generation succeeds, THE Member_Handler SHALL return the file content with appropriate headers for browser download (`Content-Disposition: attachment; filename=...`).
7. IF the request body is missing required fields (actionType, accountId for account-specific actions), THEN THE Member_Handler SHALL return a 400 error with a descriptive message.

