# Floor Premium Curve

研究台灣集合住宅「垂直高度」對成交單價的影響，將樓層轉換為估計離地高度（AGL），並以同建案／同戶別 stack 的成交價格做內部標準化，估計住宅的高度價格溢價曲線。

## 研究問題

核心指標：

> **Height Premium Curve**：相對於同一可比較住宅群組的基準單價，不同地板離地高度的成交價格溢價（%）。

第一階段以 AGL（Above Ground Level，離地高度）為主：

    height_agl_m = (floor - 1) * assumed_floor_height_m

預設樓高為 3.2 m。後續若取得建物座標與 DEM，可另外研究 ASL（Above Sea Level，地板海拔）。

### 一樓與頂樓

一樓、頂樓不直接視為一般高度曲線的一部分：

    premium = f(height) + first_floor_effect + top_floor_effect + ...

理由是 1F 常帶有庭院、獨立出入口、店面／挑高等特殊屬性；頂樓也可能有露台、挑高、屋頂熱負荷或漏水風險。若直接混入折線，會把這些效果錯算成純高度偏好。

目前實作：
- 主折線只使用非 1F、非頂樓交易。
- 1F 與頂樓仍完整保留在 observation data。
- 圖上以獨立點呈現。
- special-floor summary 目前是同 stack 標準化後的「未扣除高度效果」數值，因此不應直接解讀成特殊樓層的因果溢價。

## 資料來源

正式資料源使用內政部不動產交易實價查詢服務網 Open Data：

- 買賣案件 CSV ZIP：https://plvr.land.moi.gov.tw/opendata/lvr_landAcsv.zip
- 預售屋案件 CSV ZIP：https://plvr.land.moi.gov.tw/opendata/lvr_landBcsv.zip
- 政府資料開放平臺：
  - https://data.gov.tw/dataset/25119
  - https://data.gov.tw/dataset/6215

內政部批次資料每月 1、11、21 日發布。

### Pilot snapshot

為了先驗證整條分析流程，repo 內保留一份公開鏡像的預售屋快照：

- 1,200 筆
- 交易日期：民國 111/11/01–111/11/10（2022-11-01–2022-11-10）
- 18 個縣市
- 原始鏡像：CGUIM-BigDataAnalysis/BigDataCGUIM/EMBA_BigData/AllPreData.csv
- 原資料來源為實價登錄 Open Data

這份資料只用來做方法與程式的 pilot；正式結論應以完整、多期的內政部資料重跑。

## Pilot 方法

1. 僅保留住宅大樓、華廈與套房等集合住宅。
2. 排除無法解析樓層／總樓層／單價的資料。
3. 排除備註包含親友、特殊關係、毛胚屋等明顯特殊交易。
4. 從「棟及號」解析同建案內的戶別 stack，例如 C-6F號、C-10F號視為 stack C。
5. 嚴格分析僅保留同 stack 至少 3 筆、且至少 3 個不同樓層的群組。
6. 每筆成交以同 stack 的單價中位數標準化：

    premium_pct = (unit_price / stack_median_unit_price - 1) * 100

7. 標記：
   - is_first_floor
   - is_top_floor
   - is_special_floor
   - floor_ratio
8. 主高度曲線排除 1F 與頂樓，再依樓層／估計 AGL 聚合。

## Pilot 結果

嚴格可比較樣本：

- 487 筆可解析同 stack 的住宅交易
- 28 個具有至少 3 個不同樓層的 comparable stacks
- 107 筆進入嚴格比較
- 97 筆屬於一般樓層，用來估計主高度曲線
- 1F：2 筆，中位未調整溢價 4.02%
- 頂樓：8 筆，中位未調整溢價 0.81%

目前 1F 樣本只有 2 筆，因此即使觀察值為正，也沒有足夠證據判定一樓有正溢價。頂樓的數值也混有「本來就位於高處」的效果；下一階段需用 spline / regression 同時估計 height、1F、top-floor effect。

結果檔：

- data/processed/pilot_curve.csv：一般樓層高度曲線
- data/processed/pilot_observations.csv：所有 comparable observations，含特殊樓層旗標
- data/processed/pilot_special_floors.csv：1F／頂樓摘要
- results/pilot_summary.md
- results/pilot_curve.svg

## 執行

    python -m venv .venv
    source .venv/bin/activate
    pip install -e ".[dev]"

    # 下載內政部最新預售屋資料
    python scripts/download_latest.py --kind presale

    # 以官方最新資料重跑
    python scripts/run_analysis.py \
      --input-dir data/raw/latest/presale/csv \
      --kind presale

重跑 repo 內的 pilot：

    python scripts/run_analysis.py \
      --input-file data/pilot/AllPreData.csv \
      --output data/processed/pilot_curve.csv \
      --observations data/processed/pilot_observations.csv \
      --special-floors data/processed/pilot_special_floors.csv \
      --plot results/pilot_curve.svg \
      --summary results/pilot_runtime_summary.md

測試：

    pytest

## 下一步

1. 下載多期／多年預售屋完整資料，擴大同 stack 樣本。
2. 估計非線性高度函式 f(height)，同時加入 is_first_floor、is_top_floor。
3. 加入交易時間 fixed effects，避免建案銷售期漲價被誤當成樓層溢價。
4. 對 1F／頂樓回報 height-adjusted effect 與 95% confidence interval。
5. 再用中古屋資料做外部驗證。

## 目前限制

- AGL 由樓層 × 假設樓高估算，尚非真實樓板高度。
- Pilot 只有單一發布期。
- 只在「棟及號」能嚴格辨識同一垂直戶別 stack 時做比較，以避免把不同朝向／格局硬混在一起，因此犧牲不少樣本。
- 現階段使用實價登錄提供的單價欄位；車位價格揭露不完整的案件仍可能帶入偏差。
