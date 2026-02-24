/**
 * Cloud Migration Command Center – Example Terraform Infrastructure
 *
 * This template illustrates the target AWS architecture for the CMCC application.
 * Demonstrates VPC setup, RDS (PostgreSQL), ECS Fargate services, and KMS encryption.
 *
 * NOTE: This is a reference template for portfolio / demo purposes.
 *       Adjust variables and resource sizes before deploying to production.
 */

terraform {
  required_version = ">= 1.6"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

# ─── Variables ────────────────────────────────────────────────────────────────

variable "environment" {
  description = "Deployment environment (development, staging, production)"
  type        = string
  default     = "development"
}

variable "aws_region" {
  description = "Primary AWS region (use us-gov-west-1 for ITAR workloads)"
  type        = string
  default     = "us-east-1"
}

variable "db_password" {
  description = "Master password for the RDS instance"
  type        = string
  sensitive   = true
}

variable "openai_api_key" {
  description = "OpenAI API key for KLO embeddings"
  type        = string
  sensitive   = true
  default     = ""
}

# ─── Provider ─────────────────────────────────────────────────────────────────

provider "aws" {
  region = var.aws_region
}

# ─── KMS Key (Encryption at Rest) ─────────────────────────────────────────────

resource "aws_kms_key" "cmcc" {
  description             = "Cloud Migration Command Center – encryption key"
  deletion_window_in_days = 30
  enable_key_rotation     = true

  tags = {
    Name        = "cmcc-kms-key"
    Environment = var.environment
    Application = "CloudMigrationCommandCenter"
  }
}

resource "aws_kms_alias" "cmcc" {
  name          = "alias/cmcc-${var.environment}"
  target_key_id = aws_kms_key.cmcc.key_id
}

# ─── VPC ──────────────────────────────────────────────────────────────────────

resource "aws_vpc" "cmcc" {
  cidr_block           = "10.0.0.0/16"
  enable_dns_hostnames = true
  enable_dns_support   = true

  tags = {
    Name        = "cmcc-vpc"
    Environment = var.environment
  }
}

resource "aws_subnet" "private" {
  count             = 2
  vpc_id            = aws_vpc.cmcc.id
  cidr_block        = cidrsubnet("10.0.0.0/16", 8, count.index)
  availability_zone = data.aws_availability_zones.available.names[count.index]

  tags = {
    Name = "cmcc-private-${count.index}"
    Tier = "private"
  }
}

resource "aws_subnet" "public" {
  count                   = 2
  vpc_id                  = aws_vpc.cmcc.id
  cidr_block              = cidrsubnet("10.0.0.0/16", 8, count.index + 10)
  availability_zone       = data.aws_availability_zones.available.names[count.index]
  map_public_ip_on_launch = true

  tags = {
    Name = "cmcc-public-${count.index}"
    Tier = "public"
  }
}

data "aws_availability_zones" "available" {
  state = "available"
}

resource "aws_internet_gateway" "cmcc" {
  vpc_id = aws_vpc.cmcc.id
  tags   = { Name = "cmcc-igw" }
}

# ─── Security Groups ──────────────────────────────────────────────────────────

resource "aws_security_group" "backend" {
  name        = "cmcc-backend-sg"
  description = "Allow HTTP from ALB to FastAPI backend"
  vpc_id      = aws_vpc.cmcc.id

  ingress {
    from_port   = 8000
    to_port     = 8000
    protocol    = "tcp"
    cidr_blocks = ["10.0.0.0/16"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_security_group" "frontend" {
  name        = "cmcc-frontend-sg"
  description = "Allow HTTPS from internet to Streamlit frontend"
  vpc_id      = aws_vpc.cmcc.id

  ingress {
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    from_port   = 8501
    to_port     = 8501
    protocol    = "tcp"
    cidr_blocks = ["10.0.0.0/16"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_security_group" "rds" {
  name        = "cmcc-rds-sg"
  description = "Allow PostgreSQL from ECS tasks only"
  vpc_id      = aws_vpc.cmcc.id

  ingress {
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [aws_security_group.backend.id]
  }
}

# ─── RDS (PostgreSQL) ─────────────────────────────────────────────────────────

resource "aws_db_subnet_group" "cmcc" {
  name       = "cmcc-db-subnet-group"
  subnet_ids = aws_subnet.private[*].id
}

resource "aws_db_instance" "cmcc" {
  identifier             = "cmcc-postgres-${var.environment}"
  engine                 = "postgres"
  engine_version         = "16"
  instance_class         = "db.t3.medium"
  allocated_storage      = 20
  max_allocated_storage  = 200
  storage_encrypted      = true
  kms_key_id             = aws_kms_key.cmcc.arn
  db_name                = "migration_cmd_center"
  username               = "cmcc_admin"
  password               = var.db_password
  vpc_security_group_ids = [aws_security_group.rds.id]
  db_subnet_group_name   = aws_db_subnet_group.cmcc.name
  multi_az               = var.environment == "production" ? true : false
  deletion_protection    = var.environment == "production" ? true : false
  backup_retention_period = 7
  skip_final_snapshot    = var.environment != "production"

  tags = {
    Name        = "cmcc-rds"
    Environment = var.environment
  }
}

# ─── ECS Cluster ──────────────────────────────────────────────────────────────

resource "aws_ecs_cluster" "cmcc" {
  name = "cmcc-${var.environment}"

  setting {
    name  = "containerInsights"
    value = "enabled"
  }

  tags = {
    Name        = "cmcc-cluster"
    Environment = var.environment
  }
}

# ─── ECR Repositories ─────────────────────────────────────────────────────────

resource "aws_ecr_repository" "backend" {
  name                 = "cmcc-backend"
  image_tag_mutability = "MUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }

  encryption_configuration {
    encryption_type = "KMS"
    kms_key         = aws_kms_key.cmcc.arn
  }
}

resource "aws_ecr_repository" "frontend" {
  name                 = "cmcc-frontend"
  image_tag_mutability = "MUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }

  encryption_configuration {
    encryption_type = "KMS"
    kms_key         = aws_kms_key.cmcc.arn
  }
}

# ─── Secrets Manager ─────────────────────────────────────────────────────────

resource "aws_secretsmanager_secret" "cmcc_config" {
  name       = "cmcc/${var.environment}/config"
  kms_key_id = aws_kms_key.cmcc.arn

  tags = {
    Environment = var.environment
    Application = "CloudMigrationCommandCenter"
  }
}

# ─── CloudTrail (Audit Logging) ───────────────────────────────────────────────

resource "aws_s3_bucket" "audit_logs" {
  bucket        = "cmcc-audit-logs-${var.environment}-${data.aws_caller_identity.current.account_id}"
  force_destroy = false

  tags = {
    Name        = "cmcc-audit-logs"
    Environment = var.environment
    Purpose     = "ImmutableAuditTrail"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "audit_logs" {
  bucket = aws_s3_bucket.audit_logs.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = aws_kms_key.cmcc.arn
    }
  }
}

resource "aws_cloudtrail" "cmcc" {
  name                          = "cmcc-audit-trail-${var.environment}"
  s3_bucket_name                = aws_s3_bucket.audit_logs.bucket
  include_global_service_events = true
  is_multi_region_trail         = true
  enable_log_file_validation    = true
  kms_key_id                    = aws_kms_key.cmcc.arn

  tags = {
    Name        = "cmcc-cloudtrail"
    Environment = var.environment
  }

  depends_on = [aws_s3_bucket.audit_logs]
}

data "aws_caller_identity" "current" {}

# ─── Outputs ─────────────────────────────────────────────────────────────────

output "rds_endpoint" {
  description = "RDS PostgreSQL connection endpoint"
  value       = aws_db_instance.cmcc.endpoint
  sensitive   = true
}

output "ecr_backend_url" {
  description = "ECR URL for backend Docker image"
  value       = aws_ecr_repository.backend.repository_url
}

output "ecr_frontend_url" {
  description = "ECR URL for frontend Docker image"
  value       = aws_ecr_repository.frontend.repository_url
}

output "kms_key_id" {
  description = "KMS key ID for application encryption"
  value       = aws_kms_key.cmcc.key_id
}

output "ecs_cluster_name" {
  description = "ECS cluster name"
  value       = aws_ecs_cluster.cmcc.name
}
