output "bucket" {
  description = "Bucket de datos y modelos"
  value       = "gs://${google_storage_bucket.lluvia.name}"
}

output "datos" {
  description = "DATOS para train.py"
  value       = "gs://${google_storage_bucket.lluvia.name}/datasets/*.parquet"
}

output "destino" {
  description = "DESTINO para train.py y serve.py"
  value       = "gs://${google_storage_bucket.lluvia.name}/modelos"
}

output "cuenta_export" {
  description = "Cuenta del VPS (solo crea en datasets/)"
  value       = google_service_account.export.email
}

output "cuenta_servicio" {
  description = "Cuenta de los pods de GKE (lee todo, escribe en modelos/)"
  value       = google_service_account.servicio.email
}
