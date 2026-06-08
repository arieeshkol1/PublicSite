variable "aws_region" {
  description = "Primary AWS region for resources"
  type        = string
  default     = "us-east-1"
}

variable "environment" {
  description = "Environment name (dev, staging, prod)"
  type        = string
  default     = "prod"
}

variable "domain_name" {
  description = "Primary domain name for the website"
  type        = string
  default     = "eshkol.ai"
}

variable "s3_bucket_name" {
  description = "S3 bucket name for static website hosting"
  type        = string
  default     = "arieleshkolwebsite22feb2026"
}
