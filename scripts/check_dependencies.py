#!/usr/bin/env python3
"""check_dependencies.py - Yomitoku環境チェック"""

import sys

def check_python_version():
    """Pythonバージョン確認"""
    v = sys.version_info
    if v.major == 3 and 10 <= v.minor <= 12:
        print(f"✅ Python {v.major}.{v.minor}.{v.micro}")
        return True
    print(f"❌ Python {v.major}.{v.minor} - 3.10〜3.12が必要")
    return False

def check_pytorch():
    """PyTorch確認"""
    try:
        import torch
        print(f"✅ PyTorch {torch.__version__}")
        return True
    except ImportError:
        print("❌ PyTorch未インストール")
        print("   → pip install torch torchvision torchaudio")
        return False

def check_mps():
    """MPSバックエンド確認"""
    try:
        import torch
        if torch.backends.mps.is_available():
            print("✅ MPS利用可能")
            # MPSテスト
            try:
                x = torch.randn(10, 10, device="mps")
                print(f"   メモリ: {torch.mps.driver_allocated_memory() / 1e6:.2f} MB")
            except Exception as e:
                print(f"   ⚠️ MPSテスト警告: {e}")
            return True
        else:
            print("⚠️ MPS利用不可（CPUにフォールバック）")
            if sys.platform == "darwin":
                print("   → macOS 12.3以降とARM64 Pythonが必要")
            return True  # 警告のみ
    except Exception:
        return True

def check_yomitoku():
    """Yomitoku確認"""
    try:
        from yomitoku import DocumentAnalyzer
        print("✅ Yomitokuインストール済み")
        return True
    except ImportError:
        print("❌ Yomitoku未インストール")
        print("   → pip install yomitoku")
        return False

def check_architecture():
    """アーキテクチャ確認"""
    import platform
    machine = platform.machine()
    if machine == "arm64":
        print(f"✅ アーキテクチャ: {machine} (Apple Silicon)")
    elif machine == "x86_64" and sys.platform == "darwin":
        print(f"⚠️ アーキテクチャ: {machine} (Rosetta経由 - ARM64版Python推奨)")
    else:
        print(f"ℹ️ アーキテクチャ: {machine}")
    return True

def main():
    print("=" * 50)
    print("Yomitoku環境チェック")
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
        print("✅ 全チェック完了 - 処理を開始できます")
        print()
        print("クイックスタート:")
        print("  yomitoku ./document.pdf -f md -o output -d mps --lite")
        return 0
    else:
        print("❌ 一部チェック失敗 - 上記の指示に従ってください")
        return 1

if __name__ == "__main__":
    sys.exit(main())
