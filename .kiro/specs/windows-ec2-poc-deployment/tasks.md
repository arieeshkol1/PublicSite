# Implementation Plan: Windows EC2 POC Deployment with SSM Integration

## Overview

This implementation plan converts the Windows EC2 POC deployment design into actionable coding tasks. The infrastructure files (CloudFormation template, PowerShell deployment script, and configuration scripts) already exist and need to be validated, tested, and integrated. The focus is on ensuring all components work together correctly, implementing monitoring and backup automation, and validating that the deployment meets all 25 requirements with 125 acceptance criteria.

## Tasks

- [x] 1. Validate and test CloudFormation template
  - Review infrastructure.yaml for completeness against design specifications
  - Validate YAML syntax and CloudFormation template structure
  - Verify VPC, subnet, security group, and IAM role configurations match requirements
  - Test template deployment in a clean AWS account
  - _Requirements: 1.1-1.6, 2.1-2.6, 3.1-3.6, 4.1-4.7, 11.1-11.6_

- [ ]* 1.1 Write property test for VPC network configuration
  - **Property 1: Backend Network Isolation**
  - **Validates: Requirements 4.5, 14.4**

- [ ]* 1.2 Write property test for IAM least privilege
  - **Property 11: IAM Least Privilege**
  - **Validates: Requirements 11.4, 11.5**

- [ ] 2. Validate and enhance PowerShell deployment script
  - Review deploy-poc.ps1 for error handling and validation logic
  - Add pre-deployment checks (AWS credentials, region validation, free tier limits)
  - Implement deployment status monitoring and progress reporting
  - Add post-deployment validation (instance health, SSM registration)
  - Test deployment script end-to-end
  - _Requirements: 16.1-16.5_

- [ ]* 2.1 Write property test for deployment rollback
  - **Property 16: Deployment Rollback on Failure**
  - **Validates: Requirement 16.4**

- [ ] 3. Validate and test frontend configuration script
  - Review configure-frontend.ps1 for IIS, .NET, and CloudWatch Agent installation
  - Verify CloudWatch Agent configuration JSON matches design specifications
  - Add error handling for installation failures
  - Implement service auto-recovery configuration for IIS and CloudWatch Agent
  - Test script on a clean Windows Server 2022 instance
  - _Requirements: 13.1-13.3, 24.1-24.5, 25.2, 25.4_

- [ ]* 3.1 Write property test for CloudWatch metric collection
  - **Property 4: Metric Collection Frequency**
  - **Validates: Requirements 6.1, 6.2, 6.3**

- [ ]* 3.2 Write property test for event log collection
  - **Property 5: Event Log Collection**
  - **Validates: Requirements 6.6, 6.7**

- [ ] 4. Validate and test backend configuration script
  - Review configure-backend.ps1 for SQL Server, .NET, and CloudWatch Agent installation
  - Verify SQL Server Express installation parameters and configuration
  - Verify CloudWatch Agent configuration JSON matches design specifications
  - Add error handling for installation failures
  - Implement service auto-recovery configuration for SQL Server and CloudWatch Agent
  - Test script on a clean Windows Server 2022 instance
  - _Requirements: 13.4-13.7, 23.1-23.5, 25.1, 25.2, 25.3_

- [ ] 5. Implement and test database backup automation
  - Create PowerShell backup script with SQL Server backup commands
  - Implement S3 upload with AES-256 encryption and size verification
  - Implement local backup retention (keep last 3 files)
  - Add CloudWatch Logs integration for backup success/failure logging
  - Create scheduled task for daily execution at 02:00 UTC
  - Test backup script manually and via scheduled task
  - _Requirements: 8.1-8.7, 9.1-9.5, 18.3_

- [ ]* 5.1 Write property test for backup round-trip integrity
  - **Property 8: Backup Round-Trip Integrity**
  - **Validates: Requirements 8.2, 8.3, 8.4**

- [ ]* 5.2 Write property test for local backup retention
  - **Property 9: Local Backup Retention Invariant**
  - **Validates: Requirement 8.5**

- [ ]* 5.3 Write property test for backup operation logging
  - **Property 10: Backup Operation Logging**
  - **Validates: Requirements 8.6, 8.7, 18.3**

- [ ] 6. Implement CloudWatch Alarms and SNS notifications
  - Create CloudWatch Alarms for CPU utilization (>80% for 5 minutes)
  - Create CloudWatch Alarms for memory utilization (>85% for 5 minutes)
  - Create CloudWatch Alarms for disk free space (<15% for 2 data points)
  - Create CloudWatch Alarm for CPU credit balance (<10 credits)
  - Create CloudWatch Alarm for backup failures
  - Create SNS topic for alarm notifications
  - Configure alarm actions to publish to SNS topic
  - Test alarm triggering by simulating threshold breaches
  - _Requirements: 7.1-7.4, 20.1-20.4_

- [ ]* 6.1 Write property test for CloudWatch alarm behavior
  - **Property 7: CloudWatch Alarm Behavior**
  - **Validates: Requirements 7.1, 7.2, 7.3, 7.4**

- [ ]* 6.2 Write property test for CPU credit alarm
  - **Property 20: CPU Credit Alarm**
  - **Validates: Requirement 20.3**

- [ ] 7. Implement SSM Session Manager configuration
  - Configure Session Manager preferences (S3 logging, CloudWatch logging, encryption)
  - Set idle session timeout to 20 minutes
  - Set maximum session duration to 60 minutes
  - Create CloudWatch log group for session logs
  - Test Session Manager connectivity to both instances
  - Verify session logging to CloudWatch Logs
  - _Requirements: 5.1-5.5, 22.1-22.5_

- [ ]* 7.1 Write property test for SSM registration and connectivity
  - **Property 2: SSM Registration and Connectivity**
  - **Validates: Requirements 5.1, 5.2, 5.4**

- [ ]* 7.2 Write property test for session logging
  - **Property 3: Comprehensive Session Logging**
  - **Validates: Requirements 5.5, 18.1, 18.2, 22.5**

- [ ]* 7.3 Write property test for session manager security and timeouts
  - **Property 21: Session Manager Security and Timeouts**
  - **Validates: Requirements 22.1, 22.3, 22.4**

- [ ] 8. Implement Patch Manager configuration
  - Create patch baseline for Windows Server 2022 (CriticalUpdates, SecurityUpdates)
  - Configure approval rules (Critical/Important severity, 7-day approval)
  - Create maintenance window (Sunday 02:00 UTC, 4-hour duration, 1-hour cutoff)
  - Configure maintenance window targets (Environment:POC tag)
  - Create maintenance window task (AWS-RunPatchBaseline)
  - Test patch baseline and maintenance window configuration
  - _Requirements: 10.1-10.5_

- [ ]* 8.1 Write property test for patch manager targeting
  - **Property 24: Patch Manager Targeting**
  - **Validates: Requirement 10.4**

- [ ] 9. Implement health check endpoints
  - Create frontend health check endpoint at /health (returns HTTP 200)
  - Create backend health check endpoint at /api/health (returns HTTP 200)
  - Implement database connectivity check in backend health endpoint
  - Deploy health check implementations to instances
  - Test health check endpoints via HTTPS
  - _Requirements: 17.1-17.5_

- [ ]* 9.1 Write property test for health check response
  - **Property 18: Health Check Response**
  - **Validates: Requirements 17.2, 17.4, 17.5**

- [ ] 10. Implement and test network connectivity
  - Verify frontend can resolve backend private IP via VPC DNS
  - Test HTTPS connectivity from frontend to backend on port 443
  - Test SQL Server connectivity from frontend to backend on port 1433
  - Verify backend is NOT reachable from public internet
  - Verify frontend is reachable from public internet via Elastic IP
  - Test TLS 1.2+ encryption for all connections
  - _Requirements: 14.1-14.5, 15.3-15.5_

- [ ]* 10.1 Write property test for frontend-backend connectivity
  - **Property 13: Frontend-Backend Connectivity**
  - **Validates: Requirements 14.1, 14.2, 14.3**

- [ ]* 10.2 Write property test for frontend public accessibility
  - **Property 14: Frontend Public Accessibility**
  - **Validates: Requirement 14.5**

- [ ]* 10.3 Write property test for comprehensive encryption
  - **Property 15: Comprehensive Encryption**
  - **Validates: Requirements 15.1, 15.2, 15.3, 15.4**

- [ ] 11. Implement resource tagging validation
  - Verify all EC2 instances tagged with Name, Role, Environment
  - Verify Frontend_Instance tagged with Role:WebServer
  - Verify Backend_Instance tagged with Role:AppServer
  - Verify all resources tagged with Environment:POC
  - Verify VPC, subnets, security groups have descriptive Name tags
  - _Requirements: 21.1-21.5_

- [ ]* 11.1 Write property test for comprehensive resource tagging
  - **Property 17: Comprehensive Resource Tagging**
  - **Validates: Requirements 16.5, 21.1, 21.4, 21.5**

- [ ] 12. Implement disaster recovery testing
  - Create restore script to download backup from S3
  - Test SQL Server restore from backup file with CHECKSUM validation
  - Verify database integrity after restore
  - Document restore procedure
  - Test backup compression effectiveness
  - _Requirements: 19.1-19.5_

- [ ]* 12.1 Write property test for backup restore round-trip
  - **Property 19: Backup Restore Round-Trip**
  - **Validates: Requirements 19.1, 19.2, 19.3, 19.4, 19.5**

- [ ] 13. Implement service auto-recovery configuration
  - Configure SSM Agent service for automatic restart on failure
  - Configure CloudWatch Agent service for automatic restart on failure
  - Configure SQL Server service for automatic restart on failure
  - Configure IIS service (W3SVC) for automatic restart on failure
  - Test service recovery by manually stopping services
  - Verify Elastic IP persistence across instance stop/start cycles
  - _Requirements: 25.1-25.5_

- [ ]* 13.1 Write property test for service auto-recovery
  - **Property 22: Service Auto-Recovery**
  - **Validates: Requirements 25.1, 25.2, 25.3, 25.4**

- [ ]* 13.2 Write property test for Elastic IP persistence
  - **Property 23: Elastic IP Persistence**
  - **Validates: Requirement 25.5**

- [ ] 14. Implement free tier compliance monitoring
  - Create script to check current free tier usage (EC2 hours, EBS storage, S3 storage)
  - Verify deployment uses exactly 2 t2.micro instances
  - Verify total EBS storage is 60GB or less
  - Verify exactly 1 Elastic IP allocated and associated
  - Verify no NAT Gateways or load balancers deployed
  - Document expected monthly costs and free tier limits
  - _Requirements: 12.1-12.6_

- [ ]* 14.1 Write property test for free tier compliance
  - **Property 12: Free Tier Compliance**
  - **Validates: Requirements 12.2, 12.4, 12.5, 12.6**

- [ ] 15. Implement CloudWatch dashboard
  - Create CloudWatch dashboard for POC monitoring
  - Add widgets for CPU utilization (both instances)
  - Add widgets for memory utilization (both instances)
  - Add widgets for disk free space (both instances)
  - Add widgets for CPU credit balance and usage
  - Add widgets for alarm status
  - Add widgets for backup success/failure metrics
  - Test dashboard visibility and metric updates
  - _Requirements: 6.1-6.8, 20.1-20.4_

- [ ]* 15.1 Write property test for IIS log collection
  - **Property 6: IIS Log Collection**
  - **Validates: Requirements 6.8, 18.5**

- [ ] 16. Create integration test suite
  - Write Pester tests for VPC and subnet configuration
  - Write Pester tests for security group rules
  - Write Pester tests for IAM role permissions
  - Write Pester tests for SSM registration
  - Write Pester tests for CloudWatch metrics and logs
  - Write Pester tests for S3 backup bucket configuration
  - Run full integration test suite against deployed infrastructure
  - _Requirements: All requirements_

- [ ] 17. Create deployment documentation
  - Document prerequisites (AWS account, CLI, PowerShell)
  - Document step-by-step deployment instructions
  - Document post-deployment validation steps
  - Document how to access instances via Session Manager
  - Document how to monitor via CloudWatch dashboard
  - Document backup and restore procedures
  - Document troubleshooting common issues
  - Document cost analysis and free tier compliance
  - _Requirements: 16.1-16.5_

- [ ] 18. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 19. Final validation and cleanup
  - Run complete end-to-end deployment test
  - Verify all 25 requirements with 125 acceptance criteria are met
  - Test teardown and cleanup procedures
  - Verify no resources remain after cleanup
  - Document any known limitations or issues
  - _Requirements: All requirements_

## Notes

- Tasks marked with `*` are optional property-based tests and can be skipped for faster MVP
- Each task references specific requirements for traceability
- The infrastructure files (infrastructure.yaml, deploy-poc.ps1, configure-frontend.ps1, configure-backend.ps1) already exist and need validation/testing
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- Integration tests validate the complete system behavior
- All scripts use PowerShell for Windows automation
- CloudFormation template uses YAML for infrastructure as code
