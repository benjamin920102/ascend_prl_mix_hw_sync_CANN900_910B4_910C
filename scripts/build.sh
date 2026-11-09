#!/usr/bin/env bash
# Production build: single Ascend C MIX kernel + CPU miner + proof FFI.
set -Eeuo pipefail
cd "$(dirname "$0")/.."
CANN_HOME="${CANN_HOME:-/usr/local/Ascend/cann-9.0.0}"
if [[ ! -r "$CANN_HOME/set_env.sh" ]]; then
  echo "ERROR: CANN 9.0.0 environment not found at $CANN_HOME (set CANN_HOME if installed elsewhere)." >&2
  exit 2
fi
# shellcheck disable=SC1090
source "$CANN_HOME/set_env.sh"
export ASC_MODULES="${ASC_MODULES:-$CANN_HOME/aarch64-linux/tikcpp/ascendc_kernel_cmake/asc_modules}"
if [[ ! -d "$ASC_MODULES" ]]; then
  echo "ERROR: Ascend C CMake modules unavailable: $ASC_MODULES" >&2
  exit 2
fi
for tool in make cmake gcc cargo; do
  command -v "$tool" >/dev/null || { echo "ERROR: required tool unavailable: $tool" >&2; exit 2; }
done
if [[ ! -f /root/pearl-rust/pearl-blake3/Cargo.toml || ! -f /root/pearl-rust/zk-pow/Cargo.toml ]]; then
  echo "ERROR: Pearl proof Rust sources are missing under /root/pearl-rust (see README)." >&2
  exit 2
fi
make proof
make kernel
make miner
printf '\nProduction artifacts:\n'
ls -lh build/libpearl_hlc2.so build/libpearl_proof.so build/ascend_prl_kryptex build/ascend_prl_k1
