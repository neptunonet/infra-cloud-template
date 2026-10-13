# Class 3 (Docker) / class 4 (CI/CD): where `ci.yml` pushes images built
# from app/, model/ and pow/ using Workload Identity Federation (no JSON
# keys, see the .github/workflows).

resource "google_artifact_registry_repository" "this" {
  location      = var.region
  repository_id = var.repository_id
  description   = "Docker images for the catedra repo template (servicio patron, model, pow)."
  format        = "DOCKER"

  labels = {
    managed_by = "opentofu"
  }
}
