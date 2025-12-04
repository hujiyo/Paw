#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""颜色选择器 - 帮助选择 Logo 颜色"""

import sys
import os

# Windows UTF-8 支持
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    os.environ['PYTHONIOENCODING'] = 'utf-8'

def main():
    logo_line = "██████╗  █████╗  ██╗    ██╗"
    
    print("\n" + "=" * 60)
    print("  ANSI 256 色板 - 橘粉色系选择器")
    print("=" * 60 + "\n")
    
    # 粉橘色系候选
    print("【粉橘色系】")
    for i in range(202, 220):
        print(f"\033[38;5;{i}m{logo_line}\033[0m  <- {i}")
    
    print("\n【浅粉色系】")
    for i in range(217, 226):
        print(f"\033[38;5;{i}m{logo_line}\033[0m  <- {i}")
    
    print("\n【暖珊瑚色系】")
    for i in range(166, 182):
        print(f"\033[38;5;{i}m{logo_line}\033[0m  <- {i}")
    
    print("\n【完整 Logo 预览 - 推荐色号】")
    candidates = [209, 210, 211, 216, 217, 173, 174, 180, 215, 224, 225]
    
    logo = [
        "██████╗    █████╗   ██╗    ██╗",
        "██╔══██╗  ██╔══██╗  ██║ █╗ ██║",
        "██████╔╝  ███████║  ██║███╗██║",
        "██╔═══╝   ██╔══██║  ╚███╔███╔╝",
        "╚═╝       ╚═╝  ╚═╝   ╚══╝╚══╝ ",
    ]
    
    for c in candidates:
        print(f"\n--- 色号 {c} ---")
        for line in logo:
            print(f"\033[38;5;{c}m{line}\033[0m")
    
    print("\n" + "=" * 60)
    print("  选好后告诉我色号，我帮你改")
    print("=" * 60 + "\n")

if __name__ == "__main__":
    main()
