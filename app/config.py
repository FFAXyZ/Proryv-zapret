"""ПРОРЫВ — общие константы и пути."""
from __future__ import annotations
import os
from pathlib import Path

APP_NAME = "ПРОРЫВ"
APP_VERSION = "1.0.0"
APP_EXE = "Proryv.exe"

GITHUB_OWNER = "Flowseal"
GITHUB_REPO = "zapret-discord-youtube"
GITHUB_API_LATEST = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases/latest"
GITHUB_RELEASES_PAGE = f"https://github.com/{GITHUB_OWNER}/{GITHUB_REPO}/releases/latest"

# Куда кладём zapret и настройки (чтобы не требовать прав на запись в Program Files)
def base_dir() -> Path:
    local = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    p = Path(local) / "PRORYV"
    p.mkdir(parents=True, exist_ok=True)
    return p

def zapret_dir() -> Path:
    p = base_dir() / "zapret"
    p.mkdir(parents=True, exist_ok=True)
    return p

def data_file() -> Path:
    return base_dir() / "data.json"

def log_file() -> Path:
    return base_dir() / "proryv.log"

# Цели для автоподбора (быстрые, лёгкие, показательные)
AUTOPICK_TARGETS = [
    ("YouTube", "https://www.youtube.com/generate_204"),
    ("Discord", "https://discord.com/api/v9/gateway"),
    ("Google", "https://www.google.com/generate_204"),
    ("Cloudflare", "https://www.cloudflare.com/cdn-cgi/trace"),
    ("Steam", "https://store.steampowered.com/"),
]

# Чёрно-белая тема
THEME = {
    "bg": "#0B0B0C",
    "bg2": "#131315",
    "card": "#161618",
    "card_border": "#2A2A2D",
    "fg": "#F5F5F5",
    "muted": "#9C9CA3",
    "accent": "#FFFFFF",      # белый акцент
    "accent_fg": "#000000",   # текст на белой кнопке
    "outline": "#333336",
    "green": "#FFFFFF",       # в ч/б дизайне "вкл" = белая точка
    "red": "#555558",
    "track": "#232326",
}
