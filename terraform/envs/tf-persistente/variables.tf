variable "project_id" {
  description = "GCP project id. No default on purpose: never hardcode it."
  type        = string
}

variable "region" {
  description = "GCP region. The course uses us-central1 (Iowa) everywhere."
  type        = string
  default     = "us-central1"
}
