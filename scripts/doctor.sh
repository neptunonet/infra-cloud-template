#!/usr/bin/env bash
# `make doctor`: checks the tools the course needs, from the repo root.
# REQUIRED tools make it exit 1; OPTIONAL ones only print a hint (most of them
# have a docker fallback in the Makefile). It changes nothing on your machine.
set -u

missing=0
ok()   { printf '  [ok]   %-14s %s\n' "$1" "$2"; }
warn() { printf '  [--]   %-14s %s\n' "$1" "$2"; }
bad()  { printf '  [FAIL] %-14s %s\n' "$1" "$2"; missing=1; }
ver()  { "$@" 2>/dev/null | head -n1; }

echo "Repo"
if [ -f Makefile ] && [ -d app ] && [ -d helm/charts ]; then ok "repo root" "$(pwd)"; else bad "repo root" "run make doctor from the root of the repo (where Makefile is)"; fi

echo "Required"
command -v git >/dev/null && ok git "$(ver git --version)" || bad git "install git"
if command -v docker >/dev/null; then
  if docker info >/dev/null 2>&1; then ok docker "$(ver docker --version)"
  else bad docker "installed but the daemon does not answer: start Docker Desktop / 'sudo systemctl start docker', or add your user to the docker group"; fi
  docker compose version >/dev/null 2>&1 && ok "docker compose" "$(ver docker compose version)" || bad "docker compose" "install the compose v2 plugin (curl -fsSL https://get.docker.com | sh installs it)"
else
  bad docker "install Docker (Windows: Docker Desktop + WSL2)"
fi
command -v uv >/dev/null && ok uv "$(ver uv --version)" || bad uv "needed for make test: curl -LsSf https://astral.sh/uv/install.sh | sh"

echo "Optional (by class)"
command -v forge >/dev/null && ok forge "$(ver forge --version)" || warn forge "contracts/ only: not needed, make test-contracts uses the Foundry docker image"
if command -v tofu >/dev/null; then ok tofu "$(ver tofu version)"; elif command -v terraform >/dev/null; then ok terraform "$(ver terraform version)"; else warn "tofu/terraform" "class 2: install OpenTofu (https://opentofu.org) or Terraform >= 1.6"; fi
command -v gcloud >/dev/null && ok gcloud "$(ver gcloud --version)" || warn gcloud "classes 1-4 and 8 in GCP: https://cloud.google.com/sdk/docs/install"
command -v kubectl >/dev/null && ok kubectl "$(kubectl version --client 2>/dev/null | head -n1)" || warn kubectl "class 5+: https://kubernetes.io/docs/tasks/tools/"
command -v helm >/dev/null && ok helm "$(ver helm version --short)" || warn helm "class 5+: https://helm.sh/docs/intro/install/"
command -v k3d >/dev/null && ok k3d "$(ver k3d version)" || warn k3d "class 5+ local cluster: https://k3d.io"
command -v k6 >/dev/null && ok k6 "$(ver k6 version)" || warn k6 "class 6/8: not needed, make loadtest uses the grafana/k6 docker image"

echo "Machine"
if command -v docker >/dev/null && docker info >/dev/null 2>&1; then
  root=$(docker info --format '{{.DockerRootDir}}' 2>/dev/null)
  read -r free_gb free_pct < <(df -Pk "${root:-/}" 2>/dev/null | awk 'NR==2 {print int($4/1024/1024), int(100*$4/$2)}')
  if [ -n "${free_gb:-}" ] && { [ "$free_gb" -lt 10 ] || [ "$free_pct" -lt 15 ]; }; then
    warn disk "${free_gb} GB (${free_pct}%) free for Docker: k3d needs ~10 GB and, below ~15% free, its node gets a disk-pressure taint and pods stay Pending (see K3D_ARGS in the Makefile)"
  elif [ -n "${free_gb:-}" ]; then ok disk "${free_gb} GB (${free_pct}%) free for Docker"; fi
fi
for port in 8080 8081 8090 8545; do
  if (exec 3<>"/dev/tcp/127.0.0.1/$port") 2>/dev/null; then
    warn "port $port" "already in use (another container? docker ps). Free it or use APP_PORT=18080 make compose-up"
  else ok "port $port" "free"; fi
done

echo
if [ "$missing" -eq 0 ]; then echo "doctor: everything required is installed."; else echo "doctor: fix the [FAIL] lines above first."; fi
exit "$missing"
