#!/usr/bin/env bash
# Compile a Butane config under charts/apps/<chart>/ignition/ to compact,
# deterministic Ignition JSON ready for Vault storage:
#
#   scripts/render-vm-ignition.sh charts/apps/vm/ignition/pangolin-test.bnt /tmp/pangolin.ign.json
#
# The rendered JSON is NEVER committed to Git. Seed it into Vault instead:
#
#   vault kv put chaos/vm/<vm-name> ignition="$(cat /tmp/pangolin.ign.json)"
#
# Requires butane (Fedora CoreOS Config Transpiler) on PATH, or BUTANE_BIN
# pointing at the binary. CI compiles every .bnt under charts/**/ignition/
# with --strict (see .github/workflows/ci.yaml), so anything that merges
# is guaranteed to transpile.
set -euo pipefail
BUTANE="${BUTANE_BIN:-butane}"
if [[ $# -ne 2 ]]; then
  echo "usage: $0 <config.bnt> <out.json>" >&2
  exit 2
fi
"$BUTANE" --strict "$1" | jq -cS . > "$2"
echo "rendered $1 -> $2" >&2
