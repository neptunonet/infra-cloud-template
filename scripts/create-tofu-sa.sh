#!/usr/bin/env bash
# Class 2: a service account for OpenTofu/Terraform, used by IMPERSONATION
# (no JSON key ever leaves GCP). Run it once per project, from the repo root:
#
#   PROJECT_ID=my-project-123 ./scripts/create-tofu-sa.sh
#
# Optional: REGION (default us-central1), SA_NAME (default tofu-deployer),
# MEMBER (default user:<your active gcloud account>; a teammate can be added
# by running it again with MEMBER=user:their@mail.com).
# Safe to run twice: whatever already exists is left as is.
set -euo pipefail

: "${PROJECT_ID:?set PROJECT_ID, e.g. PROJECT_ID=my-project-123 $0}"
REGION="${REGION:-us-central1}"
SA_NAME="${SA_NAME:-tofu-deployer}"
MEMBER="${MEMBER:-user:$(gcloud config get-value account 2>/dev/null)}"
SA="${SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"
BUCKET="gs://${PROJECT_ID}-tfstate"

echo "== Project ${PROJECT_ID}, SA ${SA}, impersonated by ${MEMBER}"

echo "== APIs"
gcloud services enable --project="$PROJECT_ID" \
  iam.googleapis.com iamcredentials.googleapis.com cloudresourcemanager.googleapis.com \
  storage.googleapis.com compute.googleapis.com artifactregistry.googleapis.com

echo "== Service account"
gcloud iam service-accounts describe "$SA" --project="$PROJECT_ID" >/dev/null 2>&1 \
  || gcloud iam service-accounts create "$SA_NAME" --project="$PROJECT_ID" \
       --display-name="OpenTofu deployer"

echo "== State bucket ${BUCKET}"
gcloud storage buckets describe "$BUCKET" >/dev/null 2>&1 \
  || gcloud storage buckets create "$BUCKET" --project="$PROJECT_ID" \
       --location="$REGION" --uniform-bucket-level-access
gcloud storage buckets update "$BUCKET" --versioning

# Minimum the template needs: network + firewall + disk + VM (compute.admin),
# the image registry (artifactregistry.admin) and attaching the Compute
# default service account to the VM (iam.serviceAccountUser).
echo "== Project roles"
for role in roles/compute.admin roles/artifactregistry.admin roles/iam.serviceAccountUser; do
  gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --member="serviceAccount:$SA" --role="$role" --condition=None --format=none
done

# The state: read/write only on its own bucket, not on every bucket.
echo "== Bucket role"
gcloud storage buckets add-iam-policy-binding "$BUCKET" \
  --member="serviceAccount:$SA" --role=roles/storage.objectAdmin --format=none

# Who may act as the SA. This is what replaces the JSON key.
echo "== Impersonation for ${MEMBER}"
gcloud iam service-accounts add-iam-policy-binding "$SA" --project="$PROJECT_ID" \
  --member="$MEMBER" --role=roles/iam.serviceAccountTokenCreator --format=none

echo "== Check (IAM can take 1-2 min to propagate)"
for i in 1 2 3 4 5 6; do
  if gcloud auth print-access-token --impersonate-service-account="$SA" >/dev/null 2>&1; then
    echo "OK: impersonation works."
    cat <<EOF

Use it from terraform/envs/dev (you still need: gcloud auth application-default login):

  export GOOGLE_IMPERSONATE_SERVICE_ACCOUNT=${SA}
  # and in backend.hcl:
  impersonate_service_account = "${SA}"
EOF
    exit 0
  fi
  sleep 20
done
echo "Impersonation not ready yet: wait a minute and run the script again." >&2
exit 1
