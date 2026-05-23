# Tasks: Windows/SQL Server Licensing Optimizer

## Task 1: Backend — Licensing Scan Endpoint
- [x] 1.1 Add route handler for `POST /members/licensing/scan` in `member-handler/lambda_function.py`
- [ ] 1.2 Implement permission pre-validation (STS AssumeRole + test calls for ec2:DescribeInstances, rds:DescribeDBInstances, cloudwatch:GetMetricStatistics)
- [ ] 1.3 Implement EC2 Windows instance discovery (filter platform=windows, retrieve instance specs via DescribeInstanceTypes)
- [ ] 1.4 Implement RDS SQL Server discovery (filter engine starts with sqlserver-, classify Enterprise vs Standard)
- [ ] 1.5 Implement SQL Server detection on EC2 (check tags for sql/mssql keywords + DescribeImages for AMI description)
- [ ] 1.6 Implement 30-day CloudWatch utilization analysis (CPUUtilization avg/max/p95, mem_used_percent if available)
- [ ] 1.7 Implement Compute Optimizer integration (GetEC2InstanceRecommendations, graceful fallback if not enrolled)
- [ ] 1.8 Implement pricing calculator with in-memory cache (query Pricing API for License Included, BYOL, SQL editions per unique instance type)
- [ ] 1.9 Implement Optimize CPUs recommendation engine (calculate target vCPUs from p95 CPU, find valid core counts, compute savings)
- [ ] 1.10 Implement memory-optimized instance swap recommendations (find R-family alternatives with fewer vCPUs, same memory)
- [ ] 1.11 Implement BYOL savings calculation (LI price - BYOL price per instance)
- [ ] 1.12 Implement SQL edition downgrade recommendation (Enterprise vs Standard pricing delta)
- [ ] 1.13 Implement Dedicated Host advisory recommendation (estimated savings, no exact calculation)
- [ ] 1.14 Implement report card generation (aggregate totals, group by strategy, rank by savings, per-instance breakdown)
- [ ] 1.15 Implement timeout guard (return partial results if approaching 110s)

## Task 2: API Gateway Route
- [x] 2.1 Add `POST /members/licensing/scan` to the CI/CD route creation in `.github/workflows/deploy.yml` (MEMBER_ROUTES array)
- [x] 2.2 Add route to `infrastructure/viewmybill-stack-me-central-1.yaml` CI/CD routes (UAE deployment)

## Task 3: Frontend — Optimize Licensing Wizard Card
- [ ] 3.1 Add "Optimize Licensing" card to the Act > Optimize section in `members/members.js` (alongside Resize and Cluster cards)
- [ ] 3.2 Implement account selector dropdown (reuse existing pattern from Resize wizard)
- [ ] 3.3 Implement scan trigger with progress indicator (4 phases: Discovering, Analyzing, Calculating, Generating)
- [ ] 3.4 Implement report card summary header (total instances, instances with recommendations, total savings)
- [ ] 3.5 Implement savings-by-strategy bar chart (horizontal bars showing savings per strategy)
- [ ] 3.6 Implement per-instance expandable table (instance ID, type, platform, SQL edition, current cost, best savings)
- [ ] 3.7 Implement filter controls (All / EC2 Windows / EC2 SQL / RDS SQL) and (All strategies / specific strategy)
- [ ] 3.8 Implement recommendation detail cards within each instance row (strategy, title, description, savings, deep-link)
- [ ] 3.9 Implement SQL Enterprise feature checklist modal (for edition downgrade confirmation)
- [ ] 3.10 Bump `members.js?v=XX` in `members/index.html`

## Task 4: Cross-Account Role Template Update
- [ ] 4.1 Add `ec2:DescribeImages` and `compute-optimizer:GetEC2InstanceRecommendations` to the cross-account role CloudFormation template
- [ ] 4.2 Update the template generation endpoint to include the new permissions

## Task 5: Help & Documentation
- [ ] 5.1 Add "Optimize Licensing" help topic to `members/help.js` (what it does, how to use, what permissions are needed)
- [ ] 5.2 Update `agent-action/agent-instructions.md` to reference the new wizard ("Use the Optimize Licensing wizard in Act > Optimize")
- [ ] 5.3 Bump `help.js?v=X` in `members/index.html`

## Task 6: End-to-End Testing
- [ ] 6.1 Test with account containing Windows EC2 instances (verify discovery + utilization + pricing)
- [ ] 6.2 Test with account containing RDS SQL Server instances (verify discovery + edition detection)
- [ ] 6.3 Test with account containing no Windows/SQL instances (verify empty state message)
- [ ] 6.4 Test permission validation failure (verify clear error message)
- [ ] 6.5 Test pricing calculation accuracy (compare LI vs BYOL rates against AWS pricing page)
- [ ] 6.6 Verify report card renders correctly with multiple instances and strategies
