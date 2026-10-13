output "repository_url" {
  description = "e.g. REGION-docker.pkg.dev/PROJECT_ID/REPOSITORY_ID"
  value       = "${var.region}-docker.pkg.dev/${var.project_id}/${var.repository_id}"
}

output "repository_id" {
  value = google_artifact_registry_repository.this.repository_id
}
