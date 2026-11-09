# Ascend PRL — 正式單一 MIX Kernel 原始碼

**目標環境：** Ascend 910B4／910C、CANN **9.0.0**、Linux/aarch64。本專案只編譯 `kernel/pearl_hlc2_mix.asc` 一個 NPU Kernel，不含雙 Kernel 舊版與測試程式。

## 運算架構

- `__mix__(1, 2)`：每組 **1 個 AIC + 2 個 AIV**，每個 strip 只啟動一次 Kernel；`GRID=20`。
- AIC 做 INT8×INT8→INT32 矩陣乘法；兩個 AIV 處理交錯 band 的 fold、BLAKE3 Vector64 與命中輸出。
- 同步採 `CrossCoreSetFlag`／`CrossCoreWaitFlag` 的 **mode 2**，使用 Flag ID **8、9**；不用 GM Flag 輪詢。
- 固定 **BUFS=4、VEC2X=2、RANK=128、K=4096、FOLDS=32**。Host strip queue 預設深度為 4，與 BUFS 不同。
- 保留雙 B 緩衝、pinned memory、Host 傳輸和運算重疊。

## 編譯

需要 CANN 9.0.0 Toolkit（含 Ascend C、ACL 與 CMake 模組）、AArch64 `gcc`、`make`、`cmake`、`cargo`、BLAKE3 C 原始碼，以及 `/root/pearl-rust` 下的 `pearl-blake3` 和 `zk-pow`（見 `proof-ffi/Cargo.toml`）。

```bash
cd ascend_prl-main
bash scripts/build.sh
```

CANN 安裝於別處時可設定 `CANN_HOME=/your/cann-9.0.0`。產出 `build/libpearl_hlc2.so`、`build/libpearl_proof.so`、`build/ascend_prl_kryptex`、`build/ascend_prl_k1`。

## 啟動

```bash
export WALLET='prl1...你的錢包'
export POOL='你的礦池網域'
export PORT='7000'
export ASCEND_RT_VISIBLE_DEVICES='0'
bash scripts/launch.sh
```

想指定 K1：`BIN=./build/ascend_prl_k1 bash scripts/launch.sh`。請勿下載上游舊執行檔冒充本版。`src/prep.c` 保留的不同憑證版本屬於礦池證明協定相容性，不是舊版 NPU Kernel。

## 部署注意

兩個 AIV 必須同時參加 mode-2 同步（包括奇數 band 最後一組無工作量的 AIV）。Flag 8、9 的規劃依據只有一個 Matmul 物件；若改 CANN 版本、硬體或 Matmul 物件數，必須重新確認 ID 範圍。

**狀態：** 本 ZIP 為正式執行路徑原始碼，已刪除測試與舊 Kernel，但此產出環境沒有 CANN 編譯器／910B4／910C 實機，不能宣稱已完成實機編譯、bit-exact 驗證或效能保證。正式上線前仍應在目標設備驗證。

參考：[核間同步官方文件](https://asc.gitcode.com/api/SIMD-API/basic_api/sync_control/inter_core_sync/CrossCoreSetFlag_ISASI.html)。MIT 授權見 `LICENSE`。
