#!/usr/bin/env bash
set -euo pipefail

: "${OPENSHELL_OIDC_CLIENT_SECRET:?Set OPENSHELL_OIDC_CLIENT_SECRET}"

gateway="github-actions"
workspace="default"
template="github-agent"
repo="openshift-online/hypershell"
sandbox="github-agent-$(date +%Y%m%d%H%M%S)"

openshell gateway add \
  --name "$gateway" \
  --oidc-issuer "$OIDC_ISSUER" \
  --oidc-client-id "$OPENSHELL_OIDC_CLIENT_ID" \
  --oidc-audience "$OIDC_AUDIENCE" \
  "$GATEWAY_URL"

cleanup() {
  openshell -g "$gateway" \
    --workspace "$workspace" \
    sandbox delete "$sandbox" || true
}
trap cleanup EXIT

openshell -g "$gateway" \
  --workspace "$workspace" \
  sandbox create \
  --name "$sandbox" \
  --template "$template" \
  --provider "enmaas-claude" \
  --provider "github" \
  --no-auto-providers \
  --detach \
  -- sleep infinity

openshell -g "$gateway" \
  --workspace "$workspace" \
  sandbox exec -n "$sandbox" \
  -- bash -lc 'mkdir -p /sandbox/output && cd /sandbox && gh repo clone '"$repo"' repo'

openshell -g "$gateway" \
  --workspace "$workspace" \
  sandbox exec -n "$sandbox" \
  -- bash -lc 'cd /sandbox/repo && claude -p "Write a concise summary of this repository. Focus on what it does, how it is organized, and how someone might get started." > /sandbox/output/result.md'

mkdir -p ./output

openshell -g "$gateway" \
  --workspace "$workspace" \
  sandbox download "$sandbox" \
  "/sandbox/output" \
  "./output"
