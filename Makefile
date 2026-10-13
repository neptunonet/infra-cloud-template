# Common targets for the course repo template. Run them from the repo root.
# Nothing here touches a cloud account. `make` alone lists the targets.
#
# Variables you can override:  make build TAG=v1   make tf-validate TF=terraform
#   TAG          image tag for local builds            (default: local)
#   TF           tofu or terraform                     (default: tofu if installed)
#   K3D_CLUSTER  name of the local k3d cluster         (default: infra-cloud)
#   FOUNDRY_IMAGE / K6_IMAGE  docker fallbacks when forge / k6 are not installed

PYTHON        ?= 3.12
TAG           ?= local
TF            ?= $(shell command -v tofu >/dev/null 2>&1 && echo tofu || echo terraform)
K3D_CLUSTER   ?= infra-cloud
FOUNDRY_IMAGE ?= ghcr.io/foundry-rs/foundry:stable
K6_IMAGE      ?= grafana/k6:2.3.0
# Extra flags for k3d cluster create. Disk almost full (pods Pending with a
# disk-pressure taint)? Free space first; as a last resort use:
#   make k3d-up K3D_ARGS="--k3s-arg '--kubelet-arg=eviction-hard=imagefs.available<2%,nodefs.available<2%@all'"
K3D_ARGS      ?=
# Charts and images are discovered from the tree, so removing a folder
# (for example model/ or pow/) does not break these targets.
CHARTS        := $(notdir $(wildcard helm/charts/*))
IMAGES        := $(foreach d,app model pow,$(if $(wildcard $(d)/Dockerfile),$(d))) anvil-exporter
TF_ROOTS      := envs/dev envs/prod modules/network modules/vm modules/artifact-registry modules/gke
PYTEST        := uv run --python $(PYTHON) --with-requirements requirements.txt --with pytest --with httpx pytest -q

.DEFAULT_GOAL := help
.PHONY: help doctor test test-app test-model test-pow test-exporter test-contracts \
        build build-app build-model build-pow build-exporter \
        compose-up compose-down compose-reset compose-anvil-up compose-anvil-down compose-anvil-reset \
        tf-fmt tf-validate helm-lint helm-template k3d-up k3d-images k3d-down loadtest clean

help: ## list the targets
	@grep -E '^[a-z0-9-]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  make %-20s %s\n", $$1, $$2}'

doctor: ## check the tools you need (run it first)
	@./scripts/doctor.sh

# --- tests -------------------------------------------------------------------
test: test-app test-model test-pow test-exporter test-contracts ## every test suite

test-app: ## pytest of the servicio patron (class 1)
	cd app && $(PYTEST)

test-model: ## pytest of the example model server (model/)
	@if [ -d model ]; then cd model && $(PYTEST); else echo "skip: no model/ folder"; fi

test-pow: ## pytest of the PoW baseline node
	@if [ -d pow ]; then cd pow && $(PYTEST); else echo "skip: no pow/ folder"; fi

test-exporter: ## pytest of the Anvil exporter (class 6)
	cd observability/anvil-exporter && $(PYTEST)

test-contracts: ## forge fmt --check + forge test, like contracts.yml (Foundry docker image if forge is not installed)
	@if command -v forge >/dev/null 2>&1; then \
	  cd contracts && forge fmt --check && forge test -vv; \
	else \
	  echo "forge not found: using $(FOUNDRY_IMAGE)"; \
	  docker run --rm -u "$$(id -u):$$(id -g)" -e HOME=/tmp -v "$$PWD:/w" -w /w/contracts \
	    --entrypoint sh $(FOUNDRY_IMAGE) -c 'forge fmt --check && forge test -vv'; \
	fi

# --- images ------------------------------------------------------------------
build: $(addprefix build-,$(filter-out anvil-exporter,$(IMAGES))) build-exporter ## docker build of every image (tag TAG, default local)

build-app: ## app:TAG (servicio patron)
	docker build -t app:$(TAG) ./app

build-model: ## model:TAG
	docker build -t model:$(TAG) ./model

build-pow: ## pow:TAG
	docker build -t pow:$(TAG) ./pow

build-exporter: ## anvil-exporter:TAG
	docker build -t anvil-exporter:$(TAG) ./observability/anvil-exporter

# --- docker compose ----------------------------------------------------------
compose-up: ## servicio patron on :8080 (waits until healthy)
	docker compose -f compose/docker-compose.yml up -d --build --wait

compose-down: ## stop it, KEEP the data volume
	docker compose -f compose/docker-compose.yml down

compose-reset: ## stop it and DELETE its data volume
	docker compose -f compose/docker-compose.yml down -v

compose-anvil-up: ## Anvil :8545 + servicio patron :8080 (waits until healthy)
	docker compose -f compose/docker-compose.anvil.yml up -d --build --wait

compose-anvil-down: ## stop them, KEEP the chain and the data
	docker compose -f compose/docker-compose.anvil.yml down

compose-anvil-reset: ## stop them and DELETE the chain and the data
	docker compose -f compose/docker-compose.anvil.yml down -v

# --- terraform / opentofu -----------------------------------------------------
tf-fmt: ## tofu|terraform fmt -check (TF=...)
	cd terraform && $(TF) fmt -recursive -check

tf-validate: ## init -backend=false + validate on every root (offline)
	@set -e; for r in $(TF_ROOTS); do \
	  echo "== $$r"; \
	  (cd terraform/$$r && $(TF) init -backend=false -input=false >/dev/null && $(TF) validate); \
	done

# --- helm / kubernetes ---------------------------------------------------------
helm-lint: ## helm lint of every chart, GKE values and k3s values
	@set -e; for c in $(CHARTS); do \
	  helm lint helm/charts/$$c; \
	  helm lint helm/charts/$$c -f helm/charts/$$c/values-k3s.yaml; \
	done

helm-template: ## render every chart (no cluster needed)
	@set -e; for c in $(CHARTS); do \
	  helm template $$c helm/charts/$$c > /dev/null; \
	  helm template $$c helm/charts/$$c -f helm/charts/$$c/values-k3s.yaml > /dev/null; \
	  echo "ok: $$c"; \
	done

k3d-up: ## local Kubernetes (k3s in docker), 1 server + 1 agent
	k3d cluster create $(K3D_CLUSTER) --agents 1 --wait $(K3D_ARGS)

k3d-images: build ## build and copy the images into the k3d cluster
	k3d image import $(addsuffix :$(TAG),$(IMAGES)) -c $(K3D_CLUSTER)

k3d-down: ## delete the local cluster (and its volumes)
	k3d cluster delete $(K3D_CLUSTER)

# --- load test ----------------------------------------------------------------
# Examples: make loadtest TARGET=model MODEL_URL=http://localhost:8081 SLEEP=0.05
loadtest: ## k6 against localhost (docker grafana/k6 if k6 is not installed)
	@envs="-e TARGET=$(or $(TARGET),servicio-patron) -e SLEEP=$(or $(SLEEP),1)"; \
	[ -n "$(MODEL_URL)" ] && envs="$$envs -e MODEL_URL=$(MODEL_URL)"; \
	[ -n "$(SERVICIO_PATRON_URL)" ] && envs="$$envs -e SERVICIO_PATRON_URL=$(SERVICIO_PATRON_URL)"; \
	if command -v k6 >/dev/null 2>&1; then k6 run $$envs loadtest/k6-script.js; \
	else docker run --rm --network host -v "$$PWD/loadtest:/scripts:ro" $(K6_IMAGE) run $$envs /scripts/k6-script.js; fi

clean: ## delete caches and local terraform dirs (never your data)
	find . -name "__pycache__" -o -name ".pytest_cache" -o -name ".ruff_cache" | xargs rm -rf
	for r in $(TF_ROOTS); do rm -rf terraform/$$r/.terraform; done
	rm -rf contracts/out contracts/cache
