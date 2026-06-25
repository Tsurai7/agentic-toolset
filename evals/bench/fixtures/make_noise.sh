#!/usr/bin/env bash
# Deterministic noisy-log fixture for the compression benchmarks.
# Writes 200k lines of mostly-repetitive INFO output (no randomness, so the
# byte/line counts are reproducible) with a couple of WARNING lines mixed in.
set -euo pipefail
out="${1:?usage: make_noise.sh <out-file>}"
{
  seq 1 200000 | awk '{
    if ($1 == 137000) print "WARNING code=Z9X transient retry on item " $1
    else print "INFO line " $1 " processing item with some padding text here"
  }'
} > "$out"
