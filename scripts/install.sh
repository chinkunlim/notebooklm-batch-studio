#!/usr/bin/env bash
# 用途：全新安裝一鍵完成（核心規則 14，docs/standards/env/install_and_update.md §2）。
#   1. 檢查 git、uv 是否存在（缺少時給出安裝建議後停止，不做全域安裝）。
#   2. agentctl doctor --fix：啟用 git hooks、缺少 .env 時由 .env.example 建立（不覆蓋既有 .env）、建立 DATA_DIR。
#   3. agentctl setup --install：依 uv.lock 安裝專案內 .venv（以及專案內的 pnpm 依賴）。
#   4. alembic upgrade head：資料庫遷移到最新版。
#   5. init-data：建立 DATA_DIR/study 與 scratch/<種類>/。
# 用法：./scripts/install.sh
# 重複執行是安全的：每一步都只補缺，不覆蓋既有設定與資料。
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_DIR"

# 印出步驟標題。參數：$1 標題文字。
step() {
  printf '\n==> %s\n' "$1"
}

step "檢查必要工具"
command -v git >/dev/null 2>&1 || { echo "❌ 找不到 git，請先安裝 Xcode Command Line Tools：xcode-select --install"; exit 1; }
if ! command -v uv >/dev/null 2>&1; then
  echo "❌ 找不到 uv（只裝在使用者目錄，不影響系統 Python）："
  echo "   brew install uv    或    curl -LsSf https://astral.sh/uv/install.sh | sh"
  exit 1
fi

step "建立 .env、DATA_DIR 並啟用 git hooks"
python3 scripts/agentctl.py doctor --fix

step "安裝鎖定版本的依賴（全部裝在專案內）"
python3 scripts/agentctl.py setup --install

step "資料庫遷移到最新版"
uv run alembic upgrade head

step "建立學習資料夾"
uv run notebooklm-batch-studio init-data

PORT="$(uv run python -c 'from notebooklm_batch_studio.config.settings import load_config; print(load_config().http_port)')"
printf '\n✅ 安裝完成。\n'
echo "   啟動網頁：uv run notebooklm-batch-studio-web   然後開啟 http://127.0.0.1:${PORT}"
echo "   之後更新：./scripts/update.sh"
