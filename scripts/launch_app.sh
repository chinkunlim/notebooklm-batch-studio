#!/bin/zsh
# 用途：一鍵開啟 Gemini Notebook 學習工作室。
#   1. 網頁伺服器沒在執行時，在背景啟動它（log 寫到 DATA_DIR/logs/launcher.log）。
#   2. 等伺服器回應 /api/status。
#   3. 用 Google Chrome 的 App 模式全螢幕開啟：沒有網址列、分頁、書籤（專注模式）。
#      沒有 Chrome 時改用預設瀏覽器開啟。
# 由 scripts/build_mac_app.sh 包成「Gemini Notebook 學習工作室.app」，雙擊即可；也可直接執行本檔。
set -u

PROJECT_DIR="${0:A:h:h}"
ENV_FILE="$PROJECT_DIR/.env"

# 讀取 .env 中的一個設定值（只讀，不修改 .env）。
# 參數：$1 設定名稱、$2 預設值。輸出：設定值。
env_value() {
  local value=""
  [[ -f "$ENV_FILE" ]] && value=$(grep -E "^$1=" "$ENV_FILE" | tail -1 | cut -d= -f2- | tr -d '"' | tr -d "'")
  print -r -- "${value:-$2}"
}

PORT=$(env_value HTTP_PORT 8768)
URL="http://127.0.0.1:$PORT"
DATA_DIR=$(env_value DATA_DIR "$HOME/Desktop/projects-data/notebooklm-batch-studio")
DATA_DIR="${DATA_DIR/#\~/$HOME}"
[[ "$DATA_DIR" == /* ]] || DATA_DIR="$PROJECT_DIR/$DATA_DIR"  # .env 可寫相對於專案的路徑
LOG_DIR="${DATA_DIR:A}/logs"
mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/launcher.log"

# 回傳 0 代表伺服器已經回應。
server_up() {
  curl -s -o /dev/null --max-time 2 -w '%{http_code}' "$URL/api/status" | grep -q '^200$'
}

# 找到 uv（從 Finder 啟動時 PATH 很短，所以逐一檢查常見位置）。
find_uv() {
  local candidate
  for candidate in "$(command -v uv 2>/dev/null)" "$HOME/.local/bin/uv" /opt/homebrew/bin/uv /usr/local/bin/uv; do
    [[ -n "$candidate" && -x "$candidate" ]] && { print -r -- "$candidate"; return 0; }
  done
  return 1
}

print -r -- "$(date '+%F %T') launcher: start, url=$URL" >> "$LOG"
if ! server_up; then
  UV=$(find_uv) || {
    print -r -- "$(date '+%F %T') launcher: uv not found" >> "$LOG"
    osascript -e 'display alert "找不到 uv" message "請先依 00 init_dev_env 的 SOP 安裝 uv。"'
    exit 1
  }
  print -r -- "$(date '+%F %T') launcher: starting server with $UV" >> "$LOG"
  (cd "$PROJECT_DIR" && nohup "$UV" run notebooklm-batch-studio web >> "$LOG" 2>&1 &)
  for _ in {1..60}; do
    server_up && break
    sleep 1
  done
fi

if ! server_up; then
  print -r -- "$(date '+%F %T') launcher: server did not answer within 60s" >> "$LOG"
  osascript -e "display alert \"學習工作室沒有啟動\" message \"請查看 $LOG\""
  exit 1
fi

CHROME="/Applications/Google Chrome.app"
if [[ -d "$CHROME" ]]; then
  # 獨立的 Chrome 設定檔，才能確保以 App 視窗開啟，不會併入平常的瀏覽視窗。
  PROFILE="$HOME/Library/Application Support/GeminiNotebookStudio/chrome-profile"
  mkdir -p "$PROFILE"
  open -na "$CHROME" --args --app="$URL" --start-fullscreen --user-data-dir="$PROFILE" \
    --no-first-run --no-default-browser-check
  print -r -- "$(date '+%F %T') launcher: opened Chrome app window" >> "$LOG"
else
  open "$URL"
  print -r -- "$(date '+%F %T') launcher: opened default browser" >> "$LOG"
fi
