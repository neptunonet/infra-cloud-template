# Class 2 (IaC with Terraform): a small VPC with one subnet and the minimal
# firewall rules the rest of the template needs (SSH + the servicio patron
# port + health checks). Kept intentionally small: this is a teaching repo,
# not a production network design.

resource "google_compute_network" "this" {
  name                    = "${var.name_prefix}-vpc"
  auto_create_subnetworks = false
}

resource "google_compute_subnetwork" "this" {
  name          = "${var.name_prefix}-subnet"
  ip_cidr_range = var.subnet_cidr
  region        = var.region
  network       = google_compute_network.this.id
}

resource "google_compute_firewall" "allow_ssh" {
  name    = "${var.name_prefix}-allow-ssh"
  network = google_compute_network.this.id

  allow {
    protocol = "tcp"
    ports    = ["22"]
  }

  # Class 1-2: fine for a teaching VM reached from known IPs / IAP.
  # Tighten source_ranges in a real deployment.
  source_ranges = var.ssh_source_ranges
  target_tags   = ["ssh"]
}

resource "google_compute_firewall" "allow_app_port" {
  name    = "${var.name_prefix}-allow-app"
  network = google_compute_network.this.id

  allow {
    protocol = "tcp"
    ports    = [for p in concat([var.app_port], var.extra_ports) : tostring(p)]
  }

  # Open to the world by default (the class demos curl the VM from a laptop).
  # Narrow it with app_source_ranges for anything whose keys are public.
  source_ranges = var.app_source_ranges
  target_tags   = ["app-server"]
}

resource "google_compute_firewall" "allow_health_checks" {
  name    = "${var.name_prefix}-allow-health-checks"
  network = google_compute_network.this.id

  allow {
    protocol = "tcp"
  }

  # GCP's health-check ranges (documented, not user data).
  source_ranges = ["35.191.0.0/16", "130.211.0.0/22"]
  target_tags   = ["app-server"]
}
