# Class 1: Compute Engine instance + a SEPARATE persistent disk, attached
# and mounted by the startup script. Class 2 runs it with no container_image:
# the startup script installs nginx instead of Docker (same VM you built by
# hand, now as code). The disk outlives the VM on purpose:
# that is the whole "stateful vs stateless" lesson.

resource "google_compute_disk" "data" {
  name = "${var.name}-data"
  type = var.disk_type
  zone = var.zone
  size = var.disk_size_gb
}

resource "google_compute_instance" "this" {
  name         = var.name
  machine_type = var.machine_type
  zone         = var.zone

  boot_disk {
    initialize_params {
      image = var.boot_image
      size  = 20
      type  = "pd-standard"
    }
  }

  attached_disk {
    source      = google_compute_disk.data.id
    device_name = var.disk_device_name
  }

  network_interface {
    subnetwork = var.subnetwork_id

    access_config {
      # Ephemeral public IP: needed for `curl http://<IP>:8080` in class 1.
    }
  }

  metadata_startup_script = templatefile("${path.module}/startup-script.sh.tpl", {
    disk_device_name     = var.disk_device_name
    container_name       = var.container_name
    app_port             = var.app_port
    image                = var.container_image
    registry_host        = split("/", var.container_image)[0]
    container_entrypoint = var.container_entrypoint
    container_args       = var.container_args
    data_uid             = var.data_uid
    nginx_index = templatefile("${path.module}/nginx-index.html.tpl", {
      title       = var.nginx_title
      name        = var.name
      zone        = var.zone
      environment = var.environment
    })
  })

  # Without a service account the VM has no credentials and cannot pull a
  # private Artifact Registry image. null = Compute Engine default account.
  service_account {
    email  = var.service_account_email
    scopes = ["cloud-platform"]
  }

  tags = ["ssh", "app-server"]

  labels = {
    environment = var.environment
    managed_by  = "opentofu"
  }

  # Spot: much cheaper, GCP may stop it any time (it comes back on `start`).
  scheduling {
    provisioning_model          = var.spot ? "SPOT" : "STANDARD"
    preemptible                 = var.spot
    automatic_restart           = var.spot ? false : true
    on_host_maintenance         = var.spot ? "TERMINATE" : "MIGRATE"
    instance_termination_action = var.spot ? "STOP" : null
  }

  allow_stopping_for_update = true
}
