variable "name" {
  description = "Cluster name."
  type        = string
}

variable "zone" {
  description = "GCP zone for a zonal (single control plane) cluster. Cheaper than a regional cluster."
  type        = string
}

variable "environment" {
  description = "dev or prod, used for node labels."
  type        = string
}

variable "network_id" {
  type = string
}

variable "subnetwork_id" {
  type = string
}

variable "machine_type" {
  description = "Cheap machine type for classroom nodes."
  type        = string
  default     = "e2-small"
}

variable "node_count" {
  description = "Initial node count in the pool."
  type        = number
  default     = 1
}

variable "min_node_count" {
  type    = number
  default = 1
}

variable "max_node_count" {
  description = "Cap so nobody's HPA experiment (class 6/8) burns the budget."
  type        = number
  default     = 3
}
