# Ascend PRL — single MIX kernel production source

**Target:** Ascend 910B4 / 910C, CANN **9.0.0**, Linux/aarch64. This source tree builds **one** NPU kernel: `kernel/pearl_hlc2_mix.asc`. The production miner frontends are `ascend_prl_kryptex` and `ascend_prl_k1`.

## Pipeline

- One `__global__ __mix__(1, 2)` kernel launch per strip, with **one AIC and two AIVs per group**. GRID is 20 (`src/pearl_pipeline.h`).
- AIC computes INT8×INT8→INT32 matrix products; the two AIVs consume alternating bands, perform folding and keyed BLAKE3 Vector64, and write per-core hit results.
- AIC→AIV and AIV→AIC use hardware `CrossCoreSetFlag`/`CrossCoreWaitFlag` **mode 2**, flag IDs **8** and **9**. There is no producer/consumer GM flag polling.
- **BUFS=4** (fixed), **VEC2X=2** (fixed), **rank=128**, **K=4096**, **32 folds**. The host strip queue depth is controlled independently by `PEARL_PIPE_DEPTH` (default 4).
- Two host B buffers and pinned strip/result buffers retain upload/compute overlap. The NPU partial-result ring is reused only after paired AIV acknowledgements.

## Build

Prerequisites: aarch64 Linux, CANN 9.0.0 Ascend C toolkit including its CMake modules, ACL runtime/driver for the target NPU, `gcc` (AArch64 NEON/crypto), `make`, `cmake`, `cargo`/Rust and Pearl proof sources (`pearl-blake3` and `zk-pow` in `/root/pearl-rust`; see `proof-ffi/Cargo.toml`). Install BLAKE3 C sources through Cargo (used by the CPU miner).

```bash
cd ascend_prl-main
bash scripts/build.sh
```

If CANN 9.0.0 is installed elsewhere, set `CANN_HOME=/your/cann-9.0.0` when invoking `scripts/build.sh`. The build generates `build/libpearl_hlc2.so`, `build/libpearl_proof.so`, `build/ascend_prl_kryptex`, and `build/ascend_prl_k1`.

## Run

```bash
export WALLET='prl1...your_wallet'
export POOL='pool.example.org'
export PORT='7000'
export ASCEND_RT_VISIBLE_DEVICES='0'
bash scripts/launch.sh
```

To target an explicitly compiled frontend: `BIN=./build/ascend_prl_k1 bash scripts/launch.sh`. Each miner device gets its own process and `prl-dev*.log`. Stop the corresponding miner process to shut it down. The launcher can optionally use the DCMI coexistence guard (requires `make guard`). Do not use a downloaded upstream binary or unrelated container image as a substitute for this locally built MIX kernel.

## Runtime and compatibility limits

- The host must supply `n_hi=64` (`nrows=2`), as the kernel uses the 64-lane Vector BLAKE3 path without scalar fallback.
- Flag IDs 8 and 9 avoid the Matmul high-level API's reserved IDs for the *single* Matmul object. If the number of Matmul objects or the CANN/architecture changes, review flag reservations again.
- AIV0 and AIV1 **both** participate in every mode-2 signal, including the no-work AIV in the final odd band pair. The ring has four buffers and uses two pair groups in flight.
- CANN 9.0.0 compiler/runtime compatibility and Matmul workspace requirements must be checked on the actual Ascend target. A source archive alone cannot establish successful device compilation, bit-exact pool verification, or higher iter/s.
- Keep the unsalted/salted certificate version handling in `src/prep.c`: this is the **pool proof protocol** and not an obsolete NPU kernel.

Public API references: [CANN inter-core synchronization](https://asc.gitcode.com/api/SIMD-API/basic_api/sync_control/inter_core_sync/CrossCoreSetFlag_ISASI.html), [MIX synchronization modes](https://asc.gitcode.com/api/SIMD-API/basic_api/sync_control/inter_core_sync/inter_core_sync_overview.html).

## License

MIT, see `LICENSE`. Use only with hardware and pool resources you are authorized to use.
