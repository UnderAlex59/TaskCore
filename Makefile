SHELL := /bin/sh

PROJECT_NAME ?= task-platform
HELM_CHART ?= deploy/helm/task-platform
HELM_NAMESPACE ?= task-platform
HELM_VALUES ?=

.PHONY: backend-lint backend-test frontend-lint frontend-test frontend-build check docker-build compose-up compose-down helm-lint helm-template helm-install helm-uninstall

backend-lint:
	cd backend && ruff check . && ruff format --check . && mypy .

backend-test:
	cd backend && pytest

frontend-lint:
	cd frontend && npm run lint && npm run typecheck

frontend-test:
	cd frontend && npm run test -- --run

frontend-build:
	cd frontend && npm run build

check: backend-lint backend-test frontend-lint frontend-test frontend-build

docker-build:
	docker build -t $(PROJECT_NAME)-backend:local backend
	docker build -t $(PROJECT_NAME)-frontend:local frontend

compose-up:
	docker compose up --build -d

compose-down:
	docker compose down

helm-lint:
	helm lint $(HELM_CHART)

helm-template:
	helm template $(PROJECT_NAME) $(HELM_CHART) $(HELM_VALUES)

helm-install:
	helm upgrade --install $(PROJECT_NAME) $(HELM_CHART) -n $(HELM_NAMESPACE) --create-namespace $(HELM_VALUES)

helm-uninstall:
	helm uninstall $(PROJECT_NAME) -n $(HELM_NAMESPACE)

