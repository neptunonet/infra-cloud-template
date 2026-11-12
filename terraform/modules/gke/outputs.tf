output "cluster_name" {
  value = google_container_cluster.this.name
}

output "endpoint" {
  value     = google_container_cluster.this.endpoint
  sensitive = true
}

output "workload_pool" {
  description = "Pool de identidades de Workload Identity (vacío si está apagado)."
  value       = var.workload_identity ? "${var.project_id}.svc.id.goog" : ""
}
