# InclusiveGo 共融智遊｜場地資料包

海洋公園海濱樂園 17 個設施的資料契約，供行程規劃、行前故事與地圖使用。

**資料只有一份**：`data/facilities.json`。`index.html` 啟動時讀取它，不再內嵌副本。

## 檔案與分工

| 路徑 | 內容 | 誰會改 |
|---|---|---|
| `data/facilities.json` | 17 筆設施資料（唯一來源） | 公園同事、團隊 |
| `schema/facilities.schema.json` | 欄位規則（型別、範圍、必填） | 開發者 |
| `scripts/validate.py` | 驗證腳本 | 開發者 |
| `serve.py` | 本地伺服器（開站前先驗證） | 開發者 |
| `index.html` | 前端單頁 | 開發者 |
| `solver/planner.py` | 行程求解器（純函數） | 開發者 |
| `tests/test_planner.py` | 求解器不變量測試 | 開發者 |
| `.github/workflows/data-validate.yml` | CI，push 時驗證資料並跑測試 | 開發者 |

## 三個指令

```bash
pip install -r requirements.txt   # 首次
python3 scripts/validate.py      # 驗證資料
python3 serve.py                 # 驗證通過後開站
```

## 一筆資料長這樣

```json
{
  "id": "crocodile_park",
  "name": "鱷園",
  "zone": "正門外",
  "duration": { "min": 10, "max": 15, "approx": false },
  "sensory": { "sound": 1, "light": 3, "crowd": 1, "enclosed": 3,
               "smell": 1, "cold": 3, "wet": 1, "motion": 1 },
  "story": { "experience": "我會進入一個較小的動物展館……", "prep": "我可以戴帽……" },
  "point": { "x": 540, "y": 1460, "map_ref": "waterfront-base-1" },
  "access": { "step_free": null, "quiet_room": null, "queue_required": null,
              "exit_ease": null, "staff_interaction": null },
  "walk_min": 1,
  "legacy_rank": 0
}
```

## 欄位說明

| 欄位 | 意思 | 注意 |
|---|---|---|
| `id` | 穩定識別碼，snake_case | 發布後不改，改名等於換一個景點 |
| `zone` | 所屬區域 | 必須是四個區域之一，求解器按此分區 |
| `duration.min/max` | 建議停留時間（分鐘） | 要有數值，不能是「10–15 分鐘」這種文字 |
| `duration.approx` | 是否約數 | 原資料寫「約」的填 `true` |
| `sensory` | 八個感官維度，1 低、3 中、5 高（名義 1–5，實務只用 1/3/5） | 判準見 [`docs/sensory-rubric.md`](docs/sensory-rubric.md) |
| `story.experience` | 我會經歷甚麼 | 第一人稱，事實不得由 AI 改寫 |
| `story.prep` | 我可以怎樣準備 | 同上 |
| `point.x/y` | 底圖像素座標 | 換底圖必須同步換算 |
| `access` | 無障礙與現場條件 | **`null` 代表未核實**，見下 |
| `walk_min` | 由所屬區域入口沿動線步行至本站的累計分鐘 | 區內按 `legacy_rank` 遞增；求解器步行時間由此推算 |
| `legacy_rank` | 原 MVP 固定次序 | 只供對照，求解器不得使用 |

## `null` 是甚麼意思

`access` 的五個欄位全部是 `null`，意思是**尚未核實**，不是「沒有」。

介面遇到 `null` 必須顯示「未確認」，不能當成 `false`。把「不知道」講成「不行」，會讓使用者白白放棄一個其實可行的景點。

## 改資料的流程

1. 只改 `data/facilities.json`，不要動 `index.html`。
2. 跑 `python3 scripts/validate.py`，看到「0 個錯誤」才繼續。
3. 跑 `python3 serve.py`，開站實際看畫面。
4. `git add`、`git commit`、`git push`，CI 會再驗一次。

驗證不通過時，`serve.py` 會直接拒絕啟動，並指出是第幾筆、哪個欄位出錯。

## 求解器

```bash
python3 -m solver.planner --budget 240 --avoid sound,crowd --handling avoid-high --rest 45 --meal snack
python3 -m unittest discover -s tests -v
```

`--handling` 四種：`avoid-high`（剔 ≥5）、`avoid-medium`（剔 ≥4，「中」保留）、`warn-only`（全部保留只提醒）、`decide-later`（不剔除）。`--priority` 三種：`low-stimulation`、`less-walking`、`more-interest`。

輸出包含每一站的理由、休息與用餐插入位置、以及被排除的景點與原因。區域順序固定（正門外 → 夢幻水都 → 亞洲動物天地 → 威威天地），不會跳區回頭。

實測：p95 延遲 0.3 毫秒，跨區動態規劃轉移 75 次。

感官門檻的判準與改動理由見 [`docs/sensory-rubric.md`](docs/sensory-rubric.md)；四個避開模式（含 `warn-only` 與 `decide-later` 的唯一差別）見 [`docs/handling-semantics.md`](docs/handling-semantics.md)；一鍵重現（驗證＋測試＋固定輸入雜湊＋穩健度數字＋前端語法）跑 `bash scripts/reproduce.sh`。

感官估值有多不確定、哪幾格在支撐路線，跑 `python3 scripts/sim_sensory.py`；結果寫在 [`docs/sensory-robustness.md`](docs/sensory-robustness.md)。報告裡的數字有回歸護欄：`python3 scripts/sim_check.py` 會比對 `scripts/expected_sim.json`，數字變了這一步就紅。

## 前端如何取得路線

`serve.py` 提供 `POST /api/plan`，頁面不再自行排序，只負責顯示求解結果。

```
POST /api/plan
{
  "budget_min": 240,
  "triggers": ["sound", "crowd"],
  "handling": "avoid-high",
  "rest_interval": 45,
  "priority": "low-stimulation",
  "meal": "snack",
  "candidates": ["鱷園", "樹懶與好友", "..."]
}
```

回應包含 `stops`（含每站理由）、`breaks`、`planned_minutes`、`walk_minutes`、`duration_range`、`warnings`、`excluded`。

`planned_minutes` 的組成是四段相加：站點停留（平均 `duration`）＋ 步行 ＋ 休息 ＋ 用餐。`duration_range` 只算站點停留的最短／最長，不含步行與休息，因此摘要卡分開顯示「停留／步行／休息／用餐」，合計才是 `planned_minutes`。

步行時間的算法：每區按固定動線走，走過的路都算，故一區只需計「走到該區最深一站」的 `walk_min`；跨區再加 `zone_walk`（預設 8 分鐘）。

`zone_walk` 是**假設值**，未經實測，因此做成可調參數：請求可選傳 `"zone_walk": 12`，CLI 可用 `--zone-walk 12`，不傳則用 8。這樣可以用不同假設重跑同一情境，看「選站結果會不會變」——若 4／6／8／10／12 分鐘下選出的站點相同，結論就對這個假設不敏感。對照表由 `python3 scripts/sensitivity.py` 產生。

前端行為：提交問卷後自動請求路線；切換景點會重新求解；摘要卡顯示選中站數、預計分鐘、休息次數、未納入清單與排除原因。若未以 `serve.py` 啟動（例如直接雙擊 `index.html`），會顯示提示並暫時按舊次序排列。

測試：`python3 -m unittest discover -s tests -v`（33 條，含端點測試）。

## 常見問題

**`pip: command not found`**：用 `python3 -m pip`，或建虛擬環境 `python3 -m venv .venv && source .venv/bin/activate`。

**雙擊 index.html 一片空白**：現在資料靠 `fetch` 讀取，`file://` 會被瀏覽器擋住。用 `python3 serve.py` 開啟 `http://127.0.0.1:端口`。

**改了座標但點跑掉**：`map_ref` 要與頂層一致，換底圖時全部 17 筆都要按新圖重新換算。

## 版本

`2026.11.1`｜最後更新 2026-11-16｜access 欄位待公園核實
