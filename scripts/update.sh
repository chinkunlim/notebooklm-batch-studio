#!/usr/bin/env bash
# 用途：後期一鍵更新（核心規則 14，docs/standards/env/install_and_update.md §3）。
#   1. git pull --ff-only：只快轉，有本機修改或分歧時直接停止，不會合併或覆蓋。
#   2. agentctl setup --install：依 uv.lock 同步依賴。
#   3. 網頁伺服器仍在執行時停止（遷移資料庫前必須先關伺服器）。
#   4. 用 SQLite backup API 備份資料庫到 DATA_DIR/backups/db-<時間>/app.db。
#   5. alembic upgrade head：向下相容的資料庫遷移。
#   6. init-data：補建缺少的學習資料夾。
# 不會讀寫 .env，也不會刪除 DATA_DIR 內任何檔案。
# 用法：./scripts/update.sh            （含 git pull）
#       ./scripts/update.sh --no-pull  （程式已是最新，只做依賴、備份與遷移）
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_DIR"

# 印出步驟標題。參數：$1 標題文字。
step() {
  printf '\n==> %s\n' "$1"
}

if [[ "${1:-}" != "--no-pull" ]]; then
  step "取得最新程式（只快轉）"
  git pull --ff-only
fi

step "同步鎖定版本的依賴"
python3 scripts/agentctl.py setup --install

step "檢查網頁伺服器是否已停止"
PORT="$(uv run python -c 'from notebooklm_batch_studio.config.settings import load_config; print(load_config().http_port)')"
server_running() {
  curl -s -o /dev/null --max-time 2 "http://127.0.0.1:${PORT}/api/status"
}
if server_running; then
  echo "❌ 網頁伺服器仍在 http://127.0.0.1:${PORT} 執行。請先關閉它，再重新執行 ./scripts/update.sh --no-pull"
  exit 1
fi

step "備份資料庫"
uv run python - <<'PY'
"""Back up the SQLite database into DATA_DIR/backups before migrating (no-op for other databases)."""
import sqlite3
from datetime import datetime
from pathlib import Path

from notebooklm_batch_studio.config.settings import load_config

cfg = load_config()
url = cfg.database_url
if not url.startswith("sqlite:///"):
    print("ℹ️ 非 SQLite 資料庫，請自行用資料庫工具備份。")
else:
    src = Path(url.removeprefix("sqlite:///"))
    if not src.is_file():
        print("ℹ️ 尚無資料庫檔案，略過備份。")
    else:
        dest_dir = cfg.data_dir / "backups" / f"db-{datetime.now():%Y%m%d-%H%M%S}"
        dest_dir.mkdir(parents=True, exist_ok=False)
        dest = dest_dir / src.name
        with sqlite3.connect(src) as source, sqlite3.connect(dest) as target:
            source.backup(target)
        print(f"✅ 已備份：{dest}")
PY

step "資料庫遷移到最新版"
uv run alembic upgrade head

step "補建學習資料夾"
uv run notebooklm-batch-studio init-data

printf '\n✅ 更新完成。啟動網頁：uv run notebooklm-batch-studio-web\n'
