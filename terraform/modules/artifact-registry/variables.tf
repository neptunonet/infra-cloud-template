variable "region" {
  description = "Region for the Artifact Registry repository."
  type        = string
}

variable "repository_id" {
  description = "Repository id, e.g. \"infra-cloud-template\"."
  type        = string
}

variable "project_id" {
  description = "GCP project id, only used to compose the repository_url output."
  type        = string
}
