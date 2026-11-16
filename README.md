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
| `.github/workflows/data-validate.yml` | CI，push 時自動驗證 | 開發者 |

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
| `sensory` | 八個感官維度，1 低、3 中、5 高 | 門檻建議 ≥4 才算「要避開」 |
| `story.experience` | 我會經歷甚麼 | 第一人稱，事實不得由 AI 改寫 |
| `story.prep` | 我可以怎樣準備 | 同上 |
| `point.x/y` | 底圖像素座標 | 換底圖必須同步換算 |
| `access` | 無障礙與現場條件 | **`null` 代表未核實**，見下 |
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

## 常見問題

**`pip: command not found`**：用 `python3 -m pip`，或建虛擬環境 `python3 -m venv .venv && source .venv/bin/activate`。

**雙擊 index.html 一片空白**：現在資料靠 `fetch` 讀取，`file://` 會被瀏覽器擋住。用 `python3 serve.py` 開啟 `http://127.0.0.1:端口`。

**改了座標但點跑掉**：`map_ref` 要與頂層一致，換底圖時全部 17 筆都要按新圖重新換算。

## 版本

`2026.11.1`｜最後更新 2026-11-16｜access 欄位待公園核實
