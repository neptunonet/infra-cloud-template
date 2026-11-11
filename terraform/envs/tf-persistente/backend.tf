# State propio, separado del de envs/dev: destruir el clúster nunca toca este state.
terraform {
  backend "gcs" {
    # bucket = "<project-id>-tfstate"  # comes from backend.hcl (see backend.hcl.example)
    prefix = "infra-cloud-template/tf-persistente"
  }
}
