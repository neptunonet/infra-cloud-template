variable "project_id" {
  description = "GCP project id. No default on purpose: never hardcode it."
  type        = string
}

variable "region" {
  description = "GCP region. The course uses us-central1 (Iowa) everywhere."
  type        = string
  default     = "us-central1"
}

variable "ar_repository" {
  description = "Artifact Registry repository with the course images (created in class 3, not managed here)."
  type        = string
  default     = "infra-cloud-template"
}
