#!/usr/bin/env python3
"""check_dependencies.py - YomiToku 環境チェック (v0.13.0 / PyTorch 2.6+ 想定)"""

import re
import sys
from importlib import metadata


def _parse_version(v: str) -> tuple[int, ...]:
    nums = [int(x) for x in re.findall(r"\d+", v)[:3]]
    while len(nums) < 3:
        nums.append(0)
    return tuple(nums)


def check_python_version() -> bool:
    v = sys.version_info
    if v.major == 3 and 10 <= v.minor <= 13:
        print(f"[OK] Python {v.major}.{v.minor}.{v.micro}")
        return True
    print(f"[NG] Python {v.major}.{v.minor} - 3.10〜3.13 が必要")
    return False


def check_architecture() -> bool:
    import platform

    machine = platform.machine()
    if machine == "arm64":
        print(f"[OK] アーキテクチャ: {machine} (Apple Silicon)")
    elif machine == "x86_64" and sys.platform == "darwin":
        print(f"[!] アーキテクチャ: {machine} (Rosetta経由 - ARM64版Python推奨)")
    else:
        print(f"[i] アーキテクチャ: {machine}")
    return True


def check_pytorch() -> bool:
    try:
        import torch
    except ImportError:
        print("[NG] PyTorch 未インストール")
        print("    -> pip install torch torchvision torchaudio")
        return False

    version = torch.__version__
    if _parse_version(version) >= (2, 6, 0):
        print(f"[OK] PyTorch {version} (>=2.6 を満たす)")
        return True
    print(f"[NG] PyTorch {version} は v0.13.0 要件 (>=2.6) を満たさない")
    print("    -> uv tool upgrade yomitoku  (依存の torch も上がる)")
    return False


def check_mps() -> bool:
    try:
        import torch
    except ImportError:
        return True  # PyTorch 自体のチェックは別関数

    if not torch.backends.mps.is_built():
        if sys.platform == "darwin":
            print("[!] MPS バックエンドがビルドに含まれていない")
        else:
            print("[i] MPS は Apple Silicon 専用")
        return True

    if torch.backends.mps.is_available():
        print("[OK] MPS 利用可能")
        try:
            x = torch.randn(10, 10, device="mps")
            del x  # 使用済み
            mem_mb = torch.mps.driver_allocated_memory() / 1e6
            print(f"    メモリ: {mem_mb:.2f} MB")
        except Exception as e:
            print(f"    [!] MPS テスト警告: {e}")
        return True

    # available=False でも警告のみ。CPU フォールバックで動作する。
    import platform

    mac_ver = platform.mac_ver()[0] or "?"
    print(f"[!] MPS 利用不可 (CPUフォールバック)")
    print(f"    macOS: {mac_ver}")
    if mac_ver.startswith("26"):
        print("    macOS 26 (Tahoe) + PyTorch 2.12 では既知の互換性問題で MPS=False になる")
        print("    -> CPU 推論 (--lite -d cpu) で動作させる")
    else:
        print("    -> macOS 14.0以降 + ARM64 Python が必要")
    return True


def check_yomitoku() -> bool:
    try:
        version = metadata.version("yomitoku")
    except metadata.PackageNotFoundError:
        print("[NG] YomiToku 未インストール")
        print("    -> uv tool install 'yomitoku[extract]' --python 3.13")
        return False

    if _parse_version(version) >= (0, 13, 0):
        print(f"[OK] YomiToku {version} (>=0.13.0)")
        return True

    print(f"[!] YomiToku {version} は古い (>=0.13.0 推奨)")
    print("    -> uv tool upgrade yomitoku")
    return True  # 致命傷ではない


def main() -> int:
    print("=" * 50)
    print("YomiToku 環境チェック (v0.13.0 想定)")
    print("=" * 50)

    checks = [
        check_python_version(),
        check_architecture(),
        check_pytorch(),
        check_mps(),
        check_yomitoku(),
    ]

    print("=" * 50)
    if all(checks):
        print("[OK] 全チェック完了 - 処理を開始できます")
        print()
        print("クイックスタート:")
        try:
            import torch

            device = "mps" if torch.backends.mps.is_available() else "cpu --lite"
        except ImportError:
            device = "cpu --lite"
        print(f"  yomitoku ./document.pdf -f md -o output -d {device}")
        return 0
    print("[NG] 一部チェック失敗 - 上記の指示に従ってください")
    return 1


if __name__ == "__main__":
    sys.exit(main())
