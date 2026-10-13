variable "name_prefix" {
  description = "Prefix used to name every resource in this module (e.g. \"infra-cloud-dev\")."
  type        = string
}

variable "region" {
  description = "GCP region for the subnet."
  type        = string
}

variable "subnet_cidr" {
  description = "CIDR range for the single subnet."
  type        = string
  default     = "10.10.0.0/24"
}

variable "app_port" {
  description = "TCP port the servicio patron / model / pow node listens on."
  type        = number
  default     = 8080
}

variable "ssh_source_ranges" {
  description = "Source IP ranges allowed to SSH into instances tagged \"ssh\"."
  type        = list(string)
  default     = ["0.0.0.0/0"]
}

variable "extra_ports" {
  description = "More TCP ports to open to the internet on app-server VMs, e.g. [8081] for the model or [8545] for Anvil. Prefer an SSH tunnel for anything that is not a demo."
  type        = list(number)
  default     = []
}

variable "app_source_ranges" {
  description = "Source ranges allowed on app_port/extra_ports (allow-app). Narrow it (e.g. [\"<your-ip>/32\"]) for anything like an Anvil RPC whose keys are public."
  type        = list(string)
  default     = ["0.0.0.0/0"]
}
