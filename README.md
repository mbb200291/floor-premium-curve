# Floor Premium Curve

研究台灣集合住宅「垂直高度」對成交單價的影響，將樓層轉換為估計離地高度（AGL），並以同建案／同戶別 stack 的成交價格做內部標準化，估計住宅的高度價格溢價曲線。

## 研究問題

核心指標：

> **Height Premium Curve**：相對於同一可比較住宅群組的基準單價，不同地板離地高度的成交價格溢價（%）。

第一階段以 AGL（Above Ground Level，離地高度）為主：

```
height_agl_m = (floor - 1) * assumed_floor_height_m
```

預設樓高為 3.2 m。後續若取得建物座標與 DEM，可另外研究 ASL（Above Sea Level，地板海拔）。

## 資料來源

正式資料源使用內政部不動產交易實價查詢服務網 Open Data：

- 買賣案件 CSV ZIP：`https://plvr.land.moi.gov.tw/opendata/lvr_landAcsv.zip`
- 預售屋案件 CSV ZIP：`https://plvr.land.moi.gov.tw/opendata/lvr_landBcsv.zip`
- 政府資料開放平臺：
  - https://data.gov.tw/dataset/25119
  - https://data.gov.tw/dataset/6215

內政部批次資料每月 1、11、21 日發布。

### Pilot snapshot

為了先驗證整條分析流程，repo 內保留一份公開鏡像的預售屋快照：

- 1,200 筆
- 交易日期：民國 111/11/01–111/11/10（2022-11-01–2022-11-10）
- 18 個縣市
- 原始鏡像：`CGUIM-BigDataAnalysis/BigDataCGUIM/EMBA_BigData/AllPreData.csv`
- 原資料來源為實價登錄 Open Data

這份資料只用來做方法與程式的 pilot；正式結論應以完整、多期的內政部資料重跑。

## Pilot 方法

1. 僅保留住宅大樓、華廈與套房等集合住宅。
2. 排除無法解析樓層／總樓層／單價的資料。
3. 排除備註包含親友、特殊關係、毛胚屋等明顯特殊交易。
4. 從「棟及號」解析同建案內的戶別 stack，例如：
   - `C-6F號`、`C-10F號` → stack = `C`
   - `A07-06F號` → stack = `A07`
5. 嚴格分析僅保留同 stack 至少 3 筆、且至少 3 個不同樓層的群組。
6. 每筆成交以同 stack 的單價中位數標準化：

```
premium_pct = (unit_price / stack_median_unit_price - 1) * 100
```

7. 以樓層／估計 AGL 聚合，畫出中位價格溢價曲線。

## Pilot 結果

嚴格可比較樣本：

- 487 筆可解析同 stack 的住宅交易
- 28 個具有至少 3 個不同樓層的 comparable stacks
- 107 筆進入嚴格曲線估計

初步結果顯示，2–3 樓相對同 stack 中位單價約低 3% 左右，6 樓以上逐漸接近基準，高樓層略呈正溢價。這只是單一 10 日快照，不應解讀為全台灣最終估計。

結果檔：

- `data/processed/pilot_curve.csv`
- `results/pilot_summary.md`
- `results/pilot_curve.svg`

## 執行

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 下載內政部最新資料
python scripts/download_latest.py

# 以下載資料重跑分析
python scripts/run_analysis.py --input data/raw
```

也可直接重跑 repo 內的 pilot：

```bash
python scripts/run_analysis.py \
  --input-file data/pilot/AllPreData.csv \
  --output data/processed/pilot_curve.csv \
  --plot results/pilot_curve.svg
```

## 目前限制

- AGL 由樓層 × 假設樓高估算，尚非真實樓板高度。
- Pilot 只有單一發布期。
- 同 stack 可降低格局／朝向差異，但仍可能殘留車位、付款條件與特殊戶別差異。
- 下一步應使用多期資料，並加入建案 fixed effects、交易時間 fixed effects、非線性高度函式（spline / GAM）與信賴區間。
