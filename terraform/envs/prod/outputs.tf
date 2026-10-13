output "vm_external_ip" {
  description = "curl http://<this>:8080/ once the startup script finished (1-3 min)."
  value       = var.enable_vm ? module.vm[0].external_ip : null
}

output "vm_url" {
  description = "Open it once the startup script finished (1-3 min)."
  value       = var.enable_vm ? "http://${module.vm[0].external_ip}:${local.app_port}/" : null
}

output "artifact_registry_url" {
  description = "Prefix for every image: <this>/app, <this>/model, <this>/pow."
  value       = local.artifact_registry_url
}

output "gke_cluster_name" {
  value = var.enable_gke ? module.gke[0].cluster_name : null
}

output "gke_get_credentials" {
  description = "Command that points kubectl at the cluster."
  value       = var.enable_gke ? "gcloud container clusters get-credentials ${module.gke[0].cluster_name} --zone ${var.zone} --project ${var.project_id}" : null
}
