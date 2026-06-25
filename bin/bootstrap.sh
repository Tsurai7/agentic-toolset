#!/usr/bin/env bash
# One-command setup: install every dependency, then install the config.
#
#   bin/bootstrap.sh                 # deps + install for all providers
#   bin/bootstrap.sh --provider cursor
#
# Core deps (git, python3, node, gh) are required. lean-ctx and rtk are
# best-effort enhancements — a failure there warns but does not abort.
set -euo pipefail

AGENTIC_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROVIDER="all"
[[ "${1:-}" == "--provider" && -n "${2:-}" ]] && PROVIDER="$2"

log()  { printf '[bootstrap] %s\n' "$*"; }
warn() { printf '[bootstrap] WARN %s\n' "$*"; }

if [[ "$(uname -s)" != "Darwin" ]]; then
  warn "This bootstrap targets macOS/Homebrew. On other systems, install"
  warn "git, python3, node, gh, lean-ctx, rtk yourself, then run bin/install.sh."
  exit 1
fi

# 1. Homebrew
if ! command -v brew >/dev/null 2>&1; then
  log "installing Homebrew"
  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
  eval "$(/opt/homebrew/bin/brew shellenv 2>/dev/null || /usr/local/bin/brew shellenv)"
fi

brew_install() {
  local formula="$1" name="${2:-$1}"
  if brew list "$name" >/dev/null 2>&1; then
    log "$name already installed"
  else
    log "installing $name"
    brew install "$formula"
  fi
}

# 2. Required deps
brew_install git
if command -v python3 >/dev/null 2>&1; then
  log "python3 already available"
else
  log "installing python"
  brew install python
fi
brew_install node
brew_install gh
brew_install ast-grep

# 3. Optional enhancements (best-effort)
brew_install rtk || warn "rtk install failed — skipping (it is optional)"

if brew list lean-ctx >/dev/null 2>&1; then
  log "lean-ctx already installed"
else
  log "installing lean-ctx (tap yvgude/lean-ctx)"
  brew tap yvgude/lean-ctx 2>/dev/null || true
  brew install yvgude/lean-ctx/lean-ctx \
    || warn "lean-ctx install failed — if it is an 'untrusted tap', run: brew trust yvgude/lean-ctx && brew install yvgude/lean-ctx/lean-ctx"
fi

# no-mistakes: clean-PR gate (go install). See integrations/no-mistakes/.
if command -v no-mistakes >/dev/null 2>&1; then
  log "no-mistakes already installed"
else
  brew list go >/dev/null 2>&1 || brew install go
  if command -v go >/dev/null 2>&1; then
    log "installing no-mistakes (go install)"
    if go install github.com/kunchenguid/no-mistakes/cmd/no-mistakes@latest; then
      gobin="$(go env GOBIN)"; [[ -z "$gobin" ]] && gobin="$(go env GOPATH)/bin"
      command -v no-mistakes >/dev/null 2>&1 \
        || warn "no-mistakes installed to ${gobin} — add it to PATH (e.g. export PATH=\"${gobin}:\$PATH\")"
    else
      warn "no-mistakes install failed — skipping (it is optional)"
    fi
  else
    warn "go not available — skipping no-mistakes"
  fi
fi

# 4. Install the config
log "running install.sh --provider ${PROVIDER}"
bash "${AGENTIC_ROOT}/bin/install.sh" --provider "$PROVIDER"

# 5. Verify
bash "${AGENTIC_ROOT}/bin/doctor.sh" --deep || true

log "done — restart Cursor / Claude to pick up changes"
