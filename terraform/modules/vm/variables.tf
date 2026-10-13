variable "name" {
  description = "Instance name (also used to derive the data disk name)."
  type        = string
}

variable "zone" {
  description = "GCP zone, e.g. \"us-central1-a\"."
  type        = string
}

variable "environment" {
  description = "dev or prod, used for labels."
  type        = string
}

variable "subnetwork_id" {
  description = "Subnetwork self_link/id from the network module."
  type        = string
}

variable "machine_type" {
  description = "Compute Engine machine type. Keep it cheap for a classroom VM."
  type        = string
  default     = "e2-small"
}

variable "boot_image" {
  description = "Boot disk image."
  type        = string
  default     = "debian-cloud/debian-12"
}

variable "disk_type" {
  description = "Persistent disk type for the data disk."
  type        = string
  default     = "pd-balanced"
}

variable "disk_size_gb" {
  description = "Size in GB of the data disk."
  type        = number
  default     = 10
}

variable "disk_device_name" {
  description = "Device name used both by the attached_disk block and the startup script to find /dev/disk/by-id/google-<name>."
  type        = string
  default     = "datos"
}

variable "container_name" {
  description = "Docker container name used by the startup script."
  type        = string
  default     = "servicio-patron"
}

variable "container_image" {
  description = "Container image to run, e.g. \"<region>-docker.pkg.dev/PROJECT_ID/infra-cloud-template/app:v1\". Empty = class 2: no Docker, the VM installs nginx on port 80."
  type        = string
  default     = ""
}

variable "app_port" {
  description = "Port exposed by the container and opened in the firewall."
  type        = number
  default     = 8080
}

variable "service_account_email" {
  description = "Service account attached to the VM (needs roles/artifactregistry.reader to pull private images). null = Compute Engine default service account."
  type        = string
  default     = null
}

variable "container_entrypoint" {
  description = "Overrides the image ENTRYPOINT (\"\" = keep it). Anvil needs \"anvil\" so it is PID 1 and gets the stop signal."
  type        = string
  default     = ""
}

variable "container_args" {
  description = "Arguments appended after the image, e.g. [\"--host\", \"0.0.0.0\", \"--state\", \"/data/anvil-state.json\", \"--state-interval\", \"5\"]."
  type        = list(string)
  default     = []
}

variable "data_uid" {
  description = "If > 0, chown the data disk to this uid before starting (Anvil/Foundry runs as 1000). 0 = leave it owned by root."
  type        = number
  default     = 0
}

variable "spot" {
  description = "Spot VM: ~60-90% cheaper, but GCP can stop it at any time. Fine for dev and class demos, not for prod."
  type        = bool
  default     = false
}

variable "nginx_title" {
  description = "Class 2, no container image: title of the page nginx serves. Changing it changes the startup script, so the plan replaces the VM (the data disk stays)."
  type        = string
  default     = "Probando nginx para servir un sitio web"
}
