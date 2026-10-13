variable "project_id" {
  description = "GCP project id. No default on purpose: never hardcode it."
  type        = string
}

variable "region" {
  description = "GCP region. The course uses us-central1 (Iowa) everywhere."
  type        = string
  default     = "us-central1"
}

variable "zone" {
  description = "GCP zone inside the region."
  type        = string
  default     = "us-central1-a"
}

variable "servicio_patron_image" {
  description = "Image the VM runs, e.g. <region>-docker.pkg.dev/PROJECT_ID/infra-cloud-template/app:v1 (class 3 onward). Empty = class 2: the VM serves nginx on port 80."
  type        = string
  default     = ""
}

variable "app_port" {
  type    = number
  default = 8080
}

variable "app_source_ranges" {
  description = "Source ranges allowed on app_port (firewall rule allow-app). Narrow it, e.g. [\"<your-ip>/32\"], for anything like an Anvil RPC."
  type        = list(string)
  default     = ["0.0.0.0/0"]
}

variable "enable_artifact_registry" {
  description = "Create the Artifact Registry repository infra-cloud-template. ONE env per project creates it (dev by default); a second one would fail with 409 already exists."
  type        = bool
  default     = false
}

variable "enable_vm" {
  description = "Create the VM + data disk of classes 1-2."
  type        = bool
  default     = false
}

variable "enable_gke" {
  description = "Create the GKE cluster (class 5 onward). It costs money while it exists: destroy it after class."
  type        = bool
  default     = true
}

variable "spot" {
  description = "Run the VM as Spot (much cheaper, GCP may stop it). Default: off in prod."
  type        = bool
  default     = false
}
