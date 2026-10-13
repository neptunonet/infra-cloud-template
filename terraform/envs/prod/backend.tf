# Class 2: state is kept remote so `plan`/`apply` in CI and on a
# laptop see the same state. Fill in the bucket name via -backend-config or
# a backend.hcl that is NOT committed (it would hardcode a project-specific
# bucket name).
terraform {
  backend "gcs" {
    # bucket = "<project-id>-tfstate"  # comes from backend.hcl (see backend.hcl.example)
    prefix = "infra-cloud-template/prod"
  }
}
