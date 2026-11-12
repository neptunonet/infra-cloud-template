# Class 5 (Kubernetes with GKE): a small, ZONAL (not regional -> cheaper,
# one control plane) cluster with a single small node pool. This is a
# classroom cluster: e2-small nodes, no autoscaling to a large max, so
# nobody accidentally burns budget.

resource "google_container_cluster" "this" {
  name     = var.name
  location = var.zone

  # We manage the node pool separately (below) so we can size/label it
  # explicitly instead of using the GKE-managed default pool.
  remove_default_node_pool = true
  initial_node_count       = 1

  network    = var.network_id
  subnetwork = var.subnetwork_id

  # Classroom cluster: keep the API reachable without extra networking setup.
  deletion_protection = false

  release_channel {
    channel = "REGULAR"
  }

  # Workload Identity (TF): cada pod usa la cuenta de GCP vinculada a su cuenta de Kubernetes, sin claves JSON. Sin
  # esto los pods heredan la cuenta de los nodos (la de Compute por defecto, que tiene roles/editor del proyecto).
  dynamic "workload_identity_config" {
    for_each = var.workload_identity ? [1] : []
    content {
      workload_pool = "${var.project_id}.svc.id.goog"
    }
  }
}

resource "google_container_node_pool" "primary" {
  name     = "${var.name}-pool"
  cluster  = google_container_cluster.this.name
  location = var.zone

  node_count = var.node_count

  node_config {
    machine_type = var.machine_type
    disk_size_gb = 30
    disk_type    = "pd-standard"

    oauth_scopes = [
      "https://www.googleapis.com/auth/cloud-platform",
    ]

    labels = {
      environment = var.environment
      managed_by  = "opentofu"
    }

    # Los pods ven el servidor de metadatos de GKE, que les da la identidad de su cuenta de Kubernetes (y no la del
    # nodo). Un pod sin vínculo no tiene credenciales de GCP.
    dynamic "workload_metadata_config" {
      for_each = var.workload_identity ? [1] : []
      content {
        mode = "GKE_METADATA"
      }
    }
  }

  autoscaling {
    min_node_count = var.min_node_count
    max_node_count = var.max_node_count
  }

  management {
    auto_repair  = true
    auto_upgrade = true
  }
}
