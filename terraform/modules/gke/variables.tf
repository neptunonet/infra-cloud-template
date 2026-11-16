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

variable "project_id" {
  description = "Proyecto de GCP (para el workload pool <proyecto>.svc.id.goog)."
  type        = string
}

variable "workload_identity" {
  description = "Workload Identity: los pods usan cuentas de GCP vinculadas a su cuenta de Kubernetes, sin claves."
  type        = bool
  default     = true
}

variable "monitoreo_componentes" {
  description = "Componentes que GKE manda a Cloud Monitoring. SYSTEM_COMPONENTS es gratis; los demás (kube-state-metrics, etc.) se cobran."
  type        = list(string)
  default     = ["SYSTEM_COMPONENTS"]
}

variable "managed_prometheus" {
  description = "Managed Service for Prometheus de Google (se cobra por muestra). El TF usa kube-prometheus dentro del clúster."
  type        = bool
  default     = false
}
