"""Красивые шрифты ПРОРЫВа с кириллицей: Unbounded (заголовки) + Manrope (текст).

Шрифты лежат в assets/fonts/*.ttf, при запуске от администратора
ставятся в систему автоматически; установщик для друзей ставит их
через секцию [Fonts] (Inno Setup).
"""
from __future__ import annotations
import ctypes
import os
import shutil
import winreg
from pathlib import Path

TITLE_FAMILY = "Unbounded"
BODY_FAMILY = "Manrope"
FALLBACK = "Segoe UI"

FILES = {
    TITLE_FAMILY: "Unbounded-Variable.ttf",
    BODY_FAMILY: "Manrope-Variable.ttf",
}

FONTS_URL = {
    TITLE_FAMILY: "https://raw.githubusercontent.com/google/fonts/main/ofl/unbounded/Unbounded%5Bwght%5D.ttf",
    BODY_FAMILY: "https://raw.githubusercontent.com/google/fonts/main/ofl/manrope/Manrope%5Bwght%5D.ttf",
}


def assets_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "assets" / "fonts"


def _win_fonts_dir() -> Path:
    return Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"


def is_installed(family: str) -> bool:
    return (_win_fonts_dir() / FILES[family]).exists()


def _broadcast_change() -> None:
    for f in FILES.values():
        try:
            ctypes.windll.gdi32.AddFontResourceW(str(_win_fonts_dir() / f))
        except Exception:
            pass
    try:
        HWND_BROADCAST, WM_FONTCHANGE = 0xFFFF, 0x001D
        ctypes.windll.user32.SendMessageW(HWND_BROADCAST, WM_FONTCHANGE, 0, 0)
    except Exception:
        pass


def ensure_fonts() -> dict[str, bool]:
    """Доустановить отсутствующие шрифты (нужен админ). Возвращает доступность."""
    from .zapret_manager import is_admin  # локальный импорт против циклов
    ok: dict[str, bool] = {}
    assets = assets_dir()
    for family, fname in FILES.items():
        if is_installed(family):
            ok[family] = True
            continue
        src = assets / fname
        if not src.exists():
            ok[family] = False
            continue
        if not is_admin():
            ok[family] = False
            continue
        try:
            shutil.copy2(src, _win_fonts_dir() / fname)
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                                r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts",
                                0, winreg.KEY_SET_VALUE) as k:
                winreg.SetValueEx(k, f"{family} (TrueType)", 0, winreg.REG_SZ, fname)
            ok[family] = True
        except Exception:
            ok[family] = False
    if any(ok.values()):
        _broadcast_change()
    return ok


def resolve() -> tuple[str, str]:
    """(семейство_заголовков, семейство_текста) с фолбэком на Segoe UI."""
    t = TITLE_FAMILY if is_installed(TITLE_FAMILY) else FALLBACK
    b = BODY_FAMILY if is_installed(BODY_FAMILY) else FALLBACK
    return t, b


def download_missing(timeout: int = 60) -> dict[str, str]:
    """Скачать ttf в assets/fonts (для разработчика)."""
    import requests
    assets = assets_dir()
    assets.mkdir(parents=True, exist_ok=True)
    res = {}
    for family, url in FONTS_URL.items():
        dest = assets / FILES[family]
        if dest.exists() and dest.stat().st_size > 50_000:
            res[family] = "уже есть"
            continue
        r = requests.get(url, timeout=timeout, headers={"User-Agent": "PRORYV"})
        r.raise_for_status()
        dest.write_bytes(r.content)
        res[family] = f"скачан ({len(r.content)//1024} КБ)"
    return res
