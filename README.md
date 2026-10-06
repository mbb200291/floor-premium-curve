# Floor Premium Curve

研究台灣集合住宅「垂直高度」對成交單價的影響，將樓層轉換為估計離地高度（AGL），並以同建案／同戶別 stack 的成交價格做內部比較，估計住宅的高度價格溢價曲線。

## 研究問題

核心指標：

> **Height Premium Curve**：在盡量固定建案、戶別與其他條件後，不同地板離地高度的市場價格溢價。

第一階段以 AGL（Above Ground Level，離地高度）為主：

    height_agl_m = (floor - 1) * assumed_floor_height_m

預設樓高為 3.2 m。後續若取得建物座標與 DEM，可另外研究 ASL（Above Sea Level，地板海拔）。

## 分析分成兩層

### 1. Descriptive curve

先以同一建案、同一垂直戶別 stack 的單價中位數做標準化：

    premium_pct = (unit_price / stack_median_unit_price - 1) * 100

再依高度聚合。這條曲線直觀、假設少，適合先看資料形狀。

### 2. Adjusted within-stack model

另外估計：

    log(price) = stack_fixed_effect
               + linear_spline(height)
               + first_floor
               + top_floor
               + error

stack fixed effect 透過 within-stack demeaning 消除，不需要替每個 stack 建大量 dummy。標準誤以 stack 為 cluster 計算。

模型曲線以 12.8 m（約 5F）為預設 reference，輸出相對價格差與 95% CI。

## 一樓與頂樓

1F 與頂樓不直接混進一般高度曲線。

原因是 1F 常帶有庭院、獨立出入口、店面／挑高等特殊屬性；頂樓也可能有露台、挑高、屋頂熱負荷或漏水風險。如果直接混入折線，這些效果會被錯算成純高度偏好。

目前：
- descriptive 主折線排除 1F 與頂樓。
- 1F、頂樓仍完整保留在 observation data。
- fixed-effect model 同時放入 first_floor / top_floor dummy。
- 特殊樓層樣本數低於 10 時，模型仍輸出估計值，但標記為 reportable=false / insufficient_sample。

## 資料來源

正式資料源使用內政部不動產交易實價查詢服務網 Open Data：

- 買賣案件 CSV ZIP：https://plvr.land.moi.gov.tw/opendata/lvr_landAcsv.zip
- 預售屋案件 CSV ZIP：https://plvr.land.moi.gov.tw/opendata/lvr_landBcsv.zip
- 政府資料開放平臺：
  - https://data.gov.tw/dataset/25119
  - https://data.gov.tw/dataset/6215

內政部批次資料每月 1、11、21 日發布。

### Pilot snapshot

repo 內保留一份公開鏡像預售屋快照，用來驗證流程：

- 1,200 筆
- 交易日期：民國 111/11/01–111/11/10（2022-11-01–2022-11-10）
- 18 個縣市
- 原始鏡像：CGUIM-BigDataAnalysis/BigDataCGUIM/EMBA_BigData/AllPreData.csv

這份資料只用於 pilot；正式結論應以完整、多期內政部資料重跑。

## Pilot

嚴格可比較樣本：

- 487 筆可解析同 stack 的住宅交易
- 28 個 comparable stacks
- 107 筆進入 fixed-effect model
- 1F：2 筆
- 頂樓：8 筆

目前 adjusted special-floor estimate：

| Effect | n | Estimate | 95% CI | Reportable |
| --- | ---: | ---: | ---: | --- |
| 1F | 2 | 9.86% | 4.62% ~ 15.35% | No |
| Top floor | 8 | 0.35% | -2.91% ~ 3.71% | No |

兩個特殊樓層目前都沒有達到最小樣本門檻。尤其 1F 只有 2 筆，而且一般高度曲線在 0m 沒有非 1F 觀測，因此估計高度依賴模型外插；不能把 +9.9% 當成「一樓真的比較值錢」。

結果檔：

- data/processed/pilot_curve.csv：descriptive 一般樓層高度曲線
- data/processed/pilot_observations.csv：所有 comparable observations
- data/processed/pilot_special_floors.csv：特殊樓層未調整摘要
- data/processed/pilot_model_special_effects.csv：height-adjusted 1F／頂樓估計
- data/processed/pilot_model_curve.csv：fixed-effect spline 高度曲線
- results/pilot_curve.svg
- results/pilot_model_curve.svg
- results/pilot_summary.md

## 執行

    python -m venv .venv
    source .venv/bin/activate
    pip install -e ".[dev]"

    python scripts/download_latest.py --kind presale

    python scripts/run_analysis.py \
      --input-dir data/raw/latest/presale/csv \
      --kind presale

重跑 pilot：

    python scripts/run_analysis.py \
      --input-file data/pilot/AllPreData.csv \
      --output data/processed/pilot_curve.csv \
      --observations data/processed/pilot_observations.csv \
      --special-floors data/processed/pilot_special_floors.csv \
      --model-effects data/processed/pilot_model_special_effects.csv \
      --model-curve data/processed/pilot_model_curve.csv \
      --plot results/pilot_curve.svg \
      --model-plot results/pilot_model_curve.svg \
      --summary results/pilot_runtime_summary.md

測試：

    pytest

## 下一步

1. 下載多期／多年預售屋完整資料，擴大同 stack 樣本。
2. 加入交易時間 fixed effects，避免建案銷售期間調價被誤認為樓層溢價。
3. 對 spline knot、樓高假設與特殊交易篩選做 sensitivity analysis。
4. 在特殊樓層達到足夠樣本後，正式報告 height-adjusted effect。
5. 再以中古屋資料做外部驗證。

## 目前限制

- AGL 仍由樓層 × 假設樓高估算。
- Pilot 只有單一 10 日快照。
- 只在「棟及號」能嚴格辨識同一垂直戶別 stack 時比較，因此犧牲大量樣本以換取可比性。
- 車位價格揭露不完整的案件仍可能帶入偏差。
- Pilot model 的信賴區間只描述目前模型與樣本下的統計不確定性，不涵蓋資料選擇、樓高假設與 spline specification 的模型風險。
