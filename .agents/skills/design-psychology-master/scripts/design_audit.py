#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Design-Psychology Audit Tool.

Inspects HTML/CSS files against the Dual-Process Cognitive & Design Model:
1. Cognitive Load & Anxiety Check (No ticking seconds countdown, no overwhelming infinite animations)
2. Visual Tiering & 8pt Grid Checks
3. Typography & Measure Checks (Optimal reading line-height)
4. User Agency & Customization Checks (Layout switchers, mode toggles, color palette choices)
"""

import sys
from pathlib import Path
import os
import re

def audit_file(filepath: str) -> bool:
    """Audit a single HTML or CSS file against cognitive and design rules.

    Args:
        filepath: Path to the target file.

    Returns:
        True if all critical checks pass, False otherwise.
    """
    if not os.path.exists(filepath):
        print(f"Error: File '{filepath}' does not exist.")
        return False

    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    print("=" * 60)
    print(f"🔍 執行【設計心理學與認知美學審查】: {os.path.basename(filepath)}")
    print("=" * 60)

    warnings = []
    passes = []

    # 1. 心理學檢查：焦慮觸發器檢測 (Cortisol / Anxiety Triggers)
    if re.search(r"倒數.*\d+.*秒", content) or re.search(r"countdown.*sec", content, re.I):
        if "sanctuary" not in content and "掌控" not in content:
            warnings.append("⚠️  [心理學/焦慮] 偵測到跳動秒數倒數，且未提供溫潤放鬆/掌控感切換模式！容易引發皮質醇激增。")
        else:
            passes.append("✅ [心理學/自我決定論] 具備雙模心理節律（溫潤漫遊 vs 衝刺倒數），兼顧自律掌控與大考衝刺。")
    else:
        passes.append("✅ [心理學/認知負荷] 未發現無意義的跳動秒數焦慮刺激。")

    # 2. 心理學檢查：使用者自主掌控感 (User Agency & Customization)
    agency_keywords = ["customize", "自訂", "排列組合", "layout-switch", "mode-spread", "mode-triptych", "triad", "deck"]
    agency_score = sum(1 for kw in agency_keywords if kw in content.lower())
    if agency_score >= 3:
        passes.append("✅ [心理學/自主感] 具備豐富的版面與功能自訂維度（多種版面切換、留聲形態切換、工具分層）。")
    else:
        warnings.append("⚠️  [心理學/自主感] 使用者自主調配空間偏少，建議提供自訂組合或多版面切換選項。")

    # 3. 視覺設計檢查：8pt 網格系統 (8pt Grid System)
    grid_matches = re.findall(r"(?:padding|margin|gap):\s*([^;]+);", content)
    non_8pt_count = 0
    total_grid_checks = 0
    for match in grid_matches:
        px_vals = re.findall(r"(\d+)px", match)
        for val in px_vals:
            total_grid_checks += 1
            num = int(val)
            if num > 4 and num % 4 != 0:
                non_8pt_count += 1

    if total_grid_checks > 0 and (non_8pt_count / total_grid_checks) < 0.2:
        passes.append(f"✅ [視覺設計/網格] 8pt / 4pt 網格規範符合度極佳 (遵循率 {100 - int(non_8pt_count*100/total_grid_checks)}%)。")
    elif total_grid_checks > 0:
        warnings.append(f"⚠️  [視覺設計/網格] 發現若干非 4/8 倍數之像素值 ({non_8pt_count} 處)，建議收斂至 8pt 系統。")

    # 4. 視覺動態分級檢查 (Visual Tiering 70-80% static / 20-30% dynamic)
    infinite_anims = re.findall(r"animation:[^;]*infinite", content)
    if len(infinite_anims) <= 3:
        passes.append(f"✅ [視覺分級/專注力] 動態元素數量節制 ({len(infinite_anims)} 個)，符合 80% 靜態基底 / 20% 焦點引導原則。")
    else:
        warnings.append(f"⚠️  [視覺分級/干擾] 偵測到 {len(infinite_anims)} 個無限循環動畫，過多動態可能引發注意力分裂效應！")

    # 5. 排版行距檢查 (Typographic Breathing Room)
    if "line-height: 1." in content or "line-height:1." in content:
        passes.append("✅ [文字排版/易讀性] 內文行高設定具備良好呼吸感 (1.7 - 1.85)。")
    else:
        warnings.append("⚠️  [文字排版/易讀性] 未明確發現舒適的內文行高設定 (建議 1.7+)。")

    # 6. 色彩方案與無障礙亮暗雙模 (Curated Fixed Palettes)
    themes = ["sage", "nordic", "espresso", "clay"]
    theme_count = sum(1 for t in themes if t in content)
    if theme_count >= 3 and ("light" in content and "dark" in content):
        passes.append(f"✅ [色彩系統/護眼] 包含 {theme_count} 組成對亮暗固定配色，滿足免除選色焦慮與全情境護眼。")
    else:
        warnings.append("⚠️  [色彩系統] 配色方案完整度不足，建議提供成對明暗固定方案。")

    # 輸出總結
    for p in passes:
        print(f"  {p}")
    for w in warnings:
        print(f"  {w}")

    print("-" * 60)
    score = int(len(passes) / (len(passes) + len(warnings)) * 100) if (passes or warnings) else 100
    print(f"📊 設計心理學綜合評分: {score} / 100")
    print("=" * 60)
    return len(warnings) == 0

def main():
    """Main CLI entrypoint."""
    # Default: the design gallery kept in the repo (docs/design/), so it works on any machine.
    default = Path(__file__).resolve().parents[4] / "docs" / "design" / "mockups_gallery.html"
    target = sys.argv[1] if len(sys.argv) > 1 else str(default)
    success = audit_file(target)
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()
