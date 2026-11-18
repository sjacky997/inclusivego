# 避開模式的語義（handling）

使用者在介面選「避開到哪個程度」時，實際改變的是同一件事的兩層：**誰被剔除**，以及**誰負責**。四個選項先前只寫了 friendly 名字，沒有寫清責任邊界，導致「我未確定」被誤讀成「系統會替我處理」。本文把契約寫死。

## 四個模式的行為

| handling | 剔除 | 候選評分 | 輸出提示 | 責任 |
|---|---|---|---|---|
| `avoid-high` | 感官值 ≥ 5 的站 | 正常（未剔除者） | 無 | 系統排除「強」 |
| `avoid-medium` | 感官值 ≥ 4 的站 | 正常 | 無 | 系統排除「中」及「強」 |
| `warn-only` | 不剔除 | 正常 | 「以下景點有高刺激但已保留：…」 | 系統提醒，使用者當日決定 |
| `decide-later` | 不剔除 | 正常 | 「以下景點已達高刺激門檻，未自動排除，請自行決定是否略過：…」 | 使用者決定，系統不代為判斷 |

剔除只由這一層決定；時間不足、區域順序、休息插入屬另外的硬約束，與本表無關。

## warn-only 與 decide-later 的唯一差別

兩者的**選站結果完全相同**：同一個預算、同一組觸發維度、同一個 `priority`，`stops` 的站名與次序逐位相同，`planned_minutes` 相同，`excluded` 皆為空。差別有兩處：

1. 提示措辭。`warn-only` 說「已保留」，語氣是系統已完成處理；`decide-later` 說「未自動排除，請自行決定」，把決定權交回使用者。
2. 使用者心智。前者是「我知道有風險，照走」；後者是「我還不確定，先把資訊給我」。

之所以不讓兩者行為不同：若 `decide-later` 真的延後決策，就得在輸出裡多帶一個「待決策」欄位與每站的略過按鈕，這會改動 `Plan.to_dict()` 的契約，連帶使 `scripts/expected_hashes.json` 失效。在沒有介面配合的情況下新增欄位，等於製造一個沒人消費的欄位。因此現階段把差異限定在措辭，並以測試鎖住。

## 介面文案的約束

`index.html` 的選項說明必須與上表一致。禁止的寫法包括「每站都提供略過及 Plan B」「系統會幫你處理」——後端目前不提供逐站略過，也不生成替代路線。現行文案為：

> 先建立完整路線；踩到門檻的站會標明，由你自行決定要不要略過。

這句能成立，是因為 `decide-later` 確實會在 `warnings` 列出達門檻的站名，且不剔除它們。

## 已鎖住的測試

`tests/test_planner.py::TestHandlingSemantics` 五條：

- `test_decide_later_selects_same_stops_as_warn_only`：兩種模式站名與時長逐位相同
- `test_decide_later_excludes_nothing`：`excluded` 為空
- `test_decide_later_flags_without_excluding`：提示含「請自行決定」且列出每一個高刺激站名
- `test_warn_only_and_decide_later_wording_differs`：兩者提示不可相同，否則等於同一個選項
- `test_decide_later_without_triggers_is_silent`：未勾觸發維度時不應出現待決策提示

任何改動只要讓 `decide-later` 開始剔除、或讓它靜默不提示，這五條會紅。

## 尚未做

- 未提供逐站略過（`skip`）：需要前端結果頁的互動元件，屬介面改動，不在求解器範圍。
- 未生成替代路線（Plan B）：需要以「移除某站」為條件重跑，成本約一次求解，可在 API 層加參數，但需先確認前端能顯示兩條路線。
- `decide-later` 的高刺激門檻固定跟隨 `avoid-high`（5）。若日後要讓它跟隨 `avoid-medium`，需同步改本文件與測試。
