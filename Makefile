# Frequently used commands for the agentic CLI and repo checks.
# The binary is built from the checkout to bin/agentic (gitignored, per D2).

BIN := bin/agentic

.PHONY: help build test vet fmt lint check dry-run install clean

help: ## Show available targets
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-10s\033[0m %s\n", $$1, $$2}'

build: ## Build the agentic CLI to bin/agentic
	go build -o $(BIN) ./cmd/agentic

test: ## Run Go unit tests
	go test ./...

vet: ## Run go vet
	go vet ./...

fmt: ## Format Go sources
	gofmt -w cmd internal

lint: fmt vet ## Format, then vet

check: ## Full gate: repo static checks + Go tests
	bash bin/ci-check.sh
	go test ./...

dry-run: build ## Preview an install without writing anything
	bash bin/install.sh --dry-run

install: build ## Render config into Cursor + Claude
	bash bin/install.sh --provider all

clean: ## Remove build artifacts
	rm -f $(BIN)
