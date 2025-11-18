# =========================
# CONFIG
# =========================

# Change this to your registry if needed (e.g. docker.io/thomasreina)
REGISTRY := ghcr.io/thomasreina

# Logical app name (used in image names)
APP_NAME := trade-signals-app

BACKEND_IMAGE := $(REGISTRY)/$(APP_NAME)-backend
FRONTEND_IMAGE := $(REGISTRY)/$(APP_NAME)-frontend

# TAG defaults to current git short SHA; falls back to 'dev' if git not available
TAG ?= $(shell git rev-parse --short HEAD 2>/dev/null || echo dev)

# Kubernetes config
K8S_NAMESPACE ?= trade-signals
K8S_CONTEXT ?= 

SHELL := /bin/bash


# =========================
# LOCAL DEV (NO DOCKER)
# =========================

.PHONY: run-backend
run-backend:
	cd backend && uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

.PHONY: run-frontend
run-frontend:
	cd frontend && npm install && npm run dev


# =========================
# DOCKER BUILD & RUN LOCALLY
# =========================

.PHONY: docker-build-backend
docker-build-backend:
	docker build -t $(BACKEND_IMAGE):$(TAG) -f docker/backend.Dockerfile .

.PHONY: docker-build-frontend
docker-build-frontend:
	docker build -t $(FRONTEND_IMAGE):$(TAG) -f docker/frontend.Dockerfile .

.PHONY: docker-build-all
docker-build-all: docker-build-backend docker-build-frontend

.PHONY: docker-run-backend
docker-run-backend:
	docker run --rm -p 8000:8000 $(BACKEND_IMAGE):$(TAG)

.PHONY: docker-run-frontend
docker-run-frontend:
	docker run --rm -p 80:80 $(FRONTEND_IMAGE):$(TAG)


# If you have docker-compose.yml in ./docker
.PHONY: compose-up
compose-up:
	cd docker && docker compose up --build

.PHONY: compose-down
compose-down:
	cd docker && docker compose down


# =========================
# PUSH IMAGES
# =========================

.PHONY: docker-push-backend
docker-push-backend:
	docker push $(BACKEND_IMAGE):$(TAG)

.PHONY: docker-push-frontend
docker-push-frontend:
	docker push $(FRONTEND_IMAGE):$(TAG)

.PHONY: docker-push-all
docker-push-all: docker-push-backend docker-push-frontend


# =========================
# KUBERNETES DEPLOY (MANUAL)
# =========================

.PHONY: k8s-apply
k8s-apply:
	@if [ -n "$(K8S_CONTEXT)" ]; then \
	  kubectl --context $(K8S_CONTEXT) apply -n $(K8S_NAMESPACE) -f k8s/; \
	else \
	  kubectl apply -n $(K8S_NAMESPACE) -f k8s/; \
	fi

# Update images in existing deployments to the new TAG
.PHONY: k8s-set-images
k8s-set-images:
	@if [ -n "$(K8S_CONTEXT)" ]; then \
	  kubectl --context $(K8S_CONTEXT) -n $(K8S_NAMESPACE) set image deployment/backend backend=$(BACKEND_IMAGE):$(TAG); \
	  kubectl --context $(K8S_CONTEXT) -n $(K8S_NAMESPACE) set image deployment/frontend frontend=$(FRONTEND_IMAGE):$(TAG); \
	else \
	  kubectl -n $(K8S_NAMESPACE) set image deployment/backend backend=$(BACKEND_IMAGE):$(TAG); \
	  kubectl -n $(K8S_NAMESPACE) set image deployment/frontend frontend=$(FRONTEND_IMAGE):$(TAG); \
	fi

.PHONY: k8s-rollout-status
k8s-rollout-status:
	@if [ -n "$(K8S_CONTEXT)" ]; then \
	  kubectl --context $(K8S_CONTEXT) -n $(K8S_NAMESPACE) rollout status deployment/backend; \
	  kubectl --context $(K8S_CONTEXT) -n $(K8S_NAMESPACE) rollout status deployment/frontend; \
	else \
	  kubectl -n $(K8S_NAMESPACE) rollout status deployment/backend; \
	  kubectl -n $(K8S_NAMESPACE) rollout status deployment/frontend; \
	fi


# =========================
# ONE-SHOT DEPLOY
# =========================

# Build → Push → Update K8s images → Wait for rollout
.PHONY: deploy
deploy: docker-build-all docker-push-all k8s-set-images k8s-rollout-status
	@echo "Deployed $(TAG) to namespace $(K8S_NAMESPACE)"


# =========================
# UTILITY
# =========================

.PHONY: print-config
print-config:
	@echo "REGISTRY        = $(REGISTRY)"
	@echo "APP_NAME        = $(APP_NAME)"
	@echo "BACKEND_IMAGE   = $(BACKEND_IMAGE)"
	@echo "FRONTEND_IMAGE  = $(FRONTEND_IMAGE)"
	@echo "TAG             = $(TAG)"
	@echo "K8S_NAMESPACE   = $(K8S_NAMESPACE)"
	@echo "K8S_CONTEXT     = $(K8S_CONTEXT)"
