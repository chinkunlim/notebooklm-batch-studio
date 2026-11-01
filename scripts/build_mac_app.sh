#!/bin/zsh
# 用途：產生「~/Applications/Gemini Notebook 學習工作室.app」，雙擊就執行 scripts/launch_app.sh。
# 可以把產生的 App 拖到 Dock。專案資料夾搬家後，重新執行本檔即可。
set -euo pipefail

PROJECT_DIR="${0:A:h:h}"
LAUNCHER="$PROJECT_DIR/scripts/launch_app.sh"
APP="$HOME/Applications/Gemini Notebook 學習工作室.app"

chmod +x "$LAUNCHER"
mkdir -p "$HOME/Applications"
rm -rf "$APP"
# 登入 shell（-l）才會載入 PATH；輸出導向 /dev/null 並放到背景，App 才會立刻結束、不會卡住。
osacompile -o "$APP" -e "do shell script \"/bin/zsh -l \" & quoted form of \"$LAUNCHER\" & \" > /dev/null 2>&1 &\""
print -r -- "已建立：$APP"
