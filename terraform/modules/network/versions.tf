# Same provider constraint as terraform/envs/*, so validating this module on
# its own does not pull a different major version of the google provider.
terraform {
  required_version = ">= 1.6"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
}
