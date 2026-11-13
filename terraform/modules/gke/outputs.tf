output "cluster_name" {
  value = google_container_cluster.this.name
}

output "endpoint" {
  value     = google_container_cluster.this.endpoint
  sensitive = true
}

# Sale del clúster y no de las variables: así quien lo use (el vínculo workloadIdentityUser de envs/dev) espera a que
# el clúster exista. El pool <proyecto>.svc.id.goog nace con el primer clúster que lo pide; armado con las variables, el
# vínculo se creaba en paralelo y fallaba con «Identity Pool does not exist» (primera sesión de GKE del TF, 13/11).
output "workload_pool" {
  description = "Pool de identidades de Workload Identity (vacío si está apagado)."
  value       = try(google_container_cluster.this.workload_identity_config[0].workload_pool, "")
}
