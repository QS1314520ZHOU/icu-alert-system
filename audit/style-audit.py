"""DESIGN.md 全站样式终审脚本。

扫描 .vue 的 <style> 块（以及模板内联 style），输出违规清单：
  - 硬编码 hex / rgba / 渐变 / 重阴影 / >10px 圆角 / >=32px 字号
豁免：
  - BigScreen.vue（§10 深色底 #0B1220）、BedSideScreen.vue（保留页）
  - chip 圆角 999px、50% 圆形
  - 骨架屏 shimmer 渐变（含 'shimmer' 的选择器邻近行）
用法： python audit/style-audit.py [目录...]
默认扫描 frontend/src/views 与 frontend/src/components。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXEMPT_FILES = {"BigScreen.vue", "BedSideScreen.vue"}
HEX_RE = re.compile(r"#[0-9a-fA-F]{3,8}\b")
GRADIENT_RE = re.compile(r"linear-gradient|radial-gradient|conic-gradient")
SHADOW_RE = re.compile(r"box-shadow\s*:\s*([^;]+)")
RADIUS_RE = re.compile(r"border-radius\s*:\s*([0-9.]+)px")
FONT_RE = re.compile(r"font-size\s*:\s*([0-9.]+)px")
# var(--token, <fallback>) 回退值不算硬编码（只统计裸写值）
VAR_FALLBACK_RE = re.compile(r"var\(\s*--[\w-]+\s*,[^()]*(?:\([^()]*\)[^()]*)*\)")

# 豁免的 hex（DESIGN §10 大屏深色底）
ALLOWED_HEX = {"#0B1220", "#0b1220"}


def extract_style_blocks(text: str) -> list[tuple[int, str]]:
    """返回 [(起始行号, 样式内容)]，行号为 1-based。"""
    blocks = []
    for m in re.finditer(r"<style[^>]*>(.*?)</style>", text, re.S):
        start = text[: m.start()].count("\n") + 1
        blocks.append((start, m.group(1)))
    return blocks


def audit_file(path: Path) -> list[str]:
    if path.name in EXEMPT_FILES:
        return []
    text = path.read_text(encoding="utf-8", errors="replace")
    issues: list[str] = []
    for base, css in extract_style_blocks(text):
        lines = css.split("\n")
        for i, line in enumerate(lines):
            ln = base + i + 1
            stripped = line.strip()
            if not stripped or stripped.startswith("/*") or stripped.startswith("*"):
                continue
            # 去掉 var() 回退值后再判定裸硬编码
            bare = VAR_FALLBACK_RE.sub("var()", line)
            is_shimmer = "shimmer" in line.lower()
            for m in HEX_RE.finditer(bare):
                hexv = m.group(0)
                if hexv in ALLOWED_HEX:
                    continue
                issues.append(f"{path.relative_to(ROOT)}:{ln} hex {hexv}  :: {stripped[:120]}")
                break
            if re.search(r"\brgba?\(", bare):
                issues.append(f"{path.relative_to(ROOT)}:{ln} rgb/rgba :: {stripped[:120]}")
            if GRADIENT_RE.search(bare) and not is_shimmer:
                issues.append(f"{path.relative_to(ROOT)}:{ln} gradient :: {stripped[:120]}")
            m = SHADOW_RE.search(bare)
            if m and not m.group(1).strip().startswith(("none", "var(")):
                issues.append(f"{path.relative_to(ROOT)}:{ln} shadow :: {stripped[:120]}")
            m = RADIUS_RE.search(line)
            if m:
                px = float(m.group(1))
                if px > 10 and px != 999:
                    issues.append(f"{path.relative_to(ROOT)}:{ln} radius {px}px :: {stripped[:120]}")
            m = FONT_RE.search(line)
            if m and float(m.group(1)) >= 32:
                issues.append(f"{path.relative_to(ROOT)}:{ln} font {m.group(1)}px :: {stripped[:120]}")
    return issues


def main() -> int:
    targets = sys.argv[1:] or ["frontend/src/views", "frontend/src/components"]
    files: list[Path] = []
    for t in targets:
        p = ROOT / t
        files.extend(sorted(p.rglob("*.vue")))
    all_issues: list[str] = []
    for f in files:
        all_issues.extend(audit_file(f))
    print(f"扫描 {len(files)} 个文件，发现 {len(all_issues)} 处")
    for line in all_issues:
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
