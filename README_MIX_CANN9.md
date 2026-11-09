# CANN 9.0.0 / 910B4 / 910C: MIX 1:2 hardware synchronization port

## Status / validation level

**Source port with passing host-side protocol simulation. Not yet built or executed on actual Ascend hardware.** No claim of performance improvement or bit-exact result before an NPU test. `bisheng`, CANN SDK, hardware runtime and NPU were not installed in the environment that packaged this ZIP.

This is a direct conversion of the attached two-kernel PRL implementation. Consensus math, fixed rank=128, K=4096, 32 folds, packed B layout, vector folding, BLAKE3 Vector64 compression, hit encoding, user-facing `pearl_*` symbols, 2-slot host B upload, and 4-slot host strip queue remain. It is **NOT** an independently validated or precompiled `.so`.

## Build (your own 910B4 / 910C host)

```
cd ascend_prl-main
python3 tests/test_mix_pair_schedule.py
source /usr/local/Ascend/cann-9.0.0/set_env.sh
export ASC_MODULES=/usr/local/Ascend/cann-9.0.0/aarch64-linux/tikcpp/ascendc_kernel_cmake/asc_modules
make kernel
make proof
make miner
```

Alternative: `bash scripts/build.sh` on the original CANN 9.0.0 environment.

Original kernel sources are retained in `kernel/legacy/` only as uncompiled references. The sole compiled Ascend kernel translation unit is `kernel/pearl_hlc2_mix.asc`.

## What changed

| Component | Before | After |
|---|---|---|
| Device kernel | independent `__cube__` and `__vector__` | ONE `__mix__(1, 2)` kernel launch per strip |
| Device streams | cube `g_sC`, vector `g_sV` | one ordered compute `g_sC` (B preparation `g_sB` remains) |
| Device communication | GM `prodF/consF`, `dcci`, software polling | hardware mode-2 CrossCore Flag notifications (IDs 8 & 9) |
| Ring workspace | `GRID × BUFS × 32 × 64 × 128 × 4` bytes | unchanged, **BUFS=4**, no host memory growth |
| Scheduling | VEC2X=2 independent subqueues | paired AIV0/AIV1: group `g` holds two bands |
| Read-safety | AIV GM flag when last partial copied | AIV mode-2 ACK after MTE2→S fence for final partial |
| Host exports | pool's unchanged `pearl_*` ABI | same API and hit layout |

### Mode-2 protocol

* Each AIC processes its original `lc` band lane (`band = lc + iter*GRID`). AIC group `g` computes two bands `2g`, `2g+1` into slots `(2g) % 4` and `(2g+1) % 4`. A partially full last group is allowed.
* When all the group's matmul partials have been stored to GM, AIC calls `CrossCoreSetFlag<0x2, PIPE_FIX>(8)`, notifying **both** local AIVs.
* Each AIV calls `CrossCoreWaitFlag<0x2>(8)`, loads all 32 partial tensors, and calls `CrossCoreSetFlag<0x2, PIPE_MTE2>(9)` after its last MTE2 load has been fenced. The AIV then continues the unchanged fold / Vector64 BLAKE3 on private UB.
* Before AIC overwrites slots previously occupied by group `g-2`, it calls `CrossCoreWaitFlag<0x2>(9)`. Mode 2 waits until **both** AIVs have acknowledged. AIC drains the final outstanding 1-2 ACKs before returning.
* When a lane has an odd number of bands, AIV1 still waits for notification and acknowledges it, but performs no data copy or hash for the absent band. This prevents a mode-2 deadlock.
* No GM flags or polling in the compiled kernel. Intermediate `part` tensors **still traverse GM**, as mode-2 hardware flags only replace the notifications; they are not a direct AIC→AIV tensor transport.

### Flag allocation

The kernel has exactly one high-level Matmul object. On A2/dav-2201 the Matmul object's internal ID usage occupies IDs 0-1; our mode-2 IDs 8 (ready) and 9 (consumed) do not overlap them. `SyncAll` is not used. If additional Matmul objects or APIs are added in future, re-check their flag ID allocation. Hardware flag counters are bounded (15), and this protocol keeps at most two groups outstanding.

### Physical group index

AIC and AIV share the built-in MIX group index `block_idx`. The AIV's `GetSubBlockIdx()` is 0 or 1 and determines which band in the pair it processes. The original per-vector result indices are `sub * GRID + block_idx`. This intentionally does not assume the `GetBlockIdx()` return convention is identical across CANN versions.

## Critical limitations and tradeoffs

1. **No real CANN compilation/hardware test performed**. Use the exact installed CANN headers/runtime to confirm `__mix__(1,2)`, `__kfc_workspace__`, `CrossCoreSetFlag`, and Matmul compatibility. The original Makefile targets `dav-2201`.
2. **Potential slowdown**: two bands must finish on Cube before the corresponding AIV pair begins; the independent two-stream cross-strip overlap is replaced by ordered mixed tasks. Removing the high GM-spin latency does not guarantee higher iter/s. Benchmark whole pipeline, not isolated matmul throughput.
3. **No direct AIC→AIV SRAM transfer**: both still use the shared global-memory `part` ring. The 910B4/910C target does not provide 950's shared SSBuffer feature.
4. Mode-2 notifications are local to each AIC/AIV group; **do not** raise `GRID` past the physical concurrently schedulable group count without checking scheduling constraints. The submitted project uses `GRID=20`.
5. Test at small and odd `nbands` first, then the actual workload. Check transcript/target verification **bit for bit** and GPU/NPU hangs before any production mining. A timeout is not a valid solution and should not be ignored.
6. Revalidate flag ID reservations if changing Matmul template/config or moving to newer hardware/CANN versions.

## Suggested NPU test sequence

1. `make kernel` and confirm only **one** `pearl_hlc2_mix` kernel is compiled and launched.
2. Run a tiny instance with `nbands=1`, then `3`, `20`, `21`, `40`, `41`, `80` to exercise idle cores, odd pair, exact and multi-wrap tails. Compare diagnostic transcript with a known-good build and verified CPU reference; strict byte equality is required.
3. Check a full scan with the same B input, key/target and seeds against the original implementation; compare `hitStrip`, `hitTile`, proof and pool acceptance.
4. Profile whole-pipeline iter/s and AIC/AIV stalls. Compare against the source's two-kernel baseline under identical conditions (same `GRID`, `BUFS=4`, `VEC2X=2`).
5. Monitor runtime errors and kernel timeouts; do not conflate software protocol simulation with hardware proof.

## References (verified public documentation)

- CANN 9.0 mixed operator manual (lower-level AIC / AIV implementation): https://www.hiascend.com/doc_center/source/en/CANNCommunityEdition/900/programug/Ascendcopdevg/atlas_ascendc_10_0050.html
- Hardware CrossCore flag modes / Matmul flag reservations: https://asc.gitcode.com/api/SIMD-API/basic_api/sync_control/inter_core_sync/CrossCoreSetFlag_ISASI.html
- Hardware group modes and flag constraints: https://asc.gitcode.com/api/SIMD-API/basic_api/sync_control/inter_core_sync/inter_core_sync_overview.html
- Ascend C mix Matmul workspace qualifier: https://asc.gitcode.com/guide/programming_guide/language_extension/simd_builtin_keywords.html
