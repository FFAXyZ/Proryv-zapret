"""Ядро: скачивание zapret, версии, запуск/остановка, служба, автоподбор."""
from __future__ import annotations
import ctypes
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
import zipfile
from pathlib import Path
from typing import Callable, Optional

import requests

from .config import (
    AUTOPICK_TARGETS,
    GITHUB_API_LATEST,
    base_dir,
    data_file,
    zapret_dir,
)

# ---------------- helpers ----------------

def is_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def _hidden_kwargs() -> dict:
    """Флаги чтобы консольные утилиты (sc, tasklist, taskkill) не мигали окном."""
    kw: dict = {}
    try:
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        kw["startupinfo"] = si
    except Exception:
        pass
    try:
        kw["creationflags"] = subprocess.CREATE_NO_WINDOW
    except Exception:
        pass
    return kw


def _capture(cmd: list[str], timeout: int = 15) -> str:
    """Запуск консольной команды без вспышки окна, весь вывод строкой."""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True,
                           timeout=timeout, **_hidden_kwargs())
        return (r.stdout or "") + (r.stderr or "")
    except Exception:
        return ""


def _load_data() -> dict:
    try:
        return json.loads(data_file().read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_data(d: dict) -> None:
    try:
        data_file().write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


def get_active_strategy() -> Optional[str]:
    return _load_data().get("active_strategy")


def set_active_strategy(name: Optional[str]) -> None:
    d = _load_data()
    d["active_strategy"] = name
    _save_data(d)


def get_setting(key: str, default=True):
    return _load_data().get(key, default)


def set_setting(key: str, value) -> None:
    d = _load_data()
    d[key] = value
    _save_data(d)


def get_local_version() -> Optional[str]:
    """Версия установленного запрета: сначала .service/version.txt, потом data.json."""
    try:
        vf = zapret_dir() / ".service" / "version.txt"
        if vf.exists():
            t = vf.read_text(encoding="utf-8", errors="ignore").strip()
            if t:
                return t
    except Exception:
        pass
    v = _load_data().get("zapret_version")
    return v or None


def set_local_version(v: str) -> None:
    d = _load_data()
    d["zapret_version"] = v
    _save_data(d)


def is_installed() -> bool:
    z = zapret_dir()
    if not z.exists():
        return False
    bats = list(z.glob("general*.bat")) + list(z.glob("discord*.bat"))
    winws = z / "bin" / "winws.exe"
    return bool(bats) and winws.exists()


# ---------------- GitHub ----------------

def get_latest_release(timeout: int = 15) -> dict:
    """Возвращает {tag, zip_url, size, body}. Бросает исключение при ошибке сети."""
    r = requests.get(GITHUB_API_LATEST, timeout=timeout, headers={"User-Agent": "PRORYV-Launcher"})
    r.raise_for_status()
    j = r.json()
    tag = (j.get("tag_name") or "").strip()
    assets = j.get("assets") or []
    zip_url, size = None, 0
    # предпочитаем .zip
    for a in assets:
        name = (a.get("name") or "").lower()
        if name.endswith(".zip"):
            zip_url = a.get("browser_download_url")
            size = a.get("size", 0)
            break
    if not zip_url and assets:
        zip_url = assets[0].get("browser_download_url")
        size = assets[0].get("size", 0)
    if not zip_url:
        raise RuntimeError("В релизе не найден файл для скачивания")
    return {"tag": tag, "zip_url": zip_url, "size": size, "body": j.get("body") or ""}


def _norm_tag(t: str) -> str:
    t = (t or "").strip().lower()
    t = t.lstrip("v")
    return t


def is_update_available(latest_tag: str) -> bool:
    local = get_local_version()
    if not local:
        return True
    return _norm_tag(local) != _norm_tag(latest_tag)


# ---------------- install / update ----------------

def download_and_install(
    zip_url: str,
    tag: str,
    progress_cb: Optional[Callable[[int, int], None]] = None,
    status_cb: Optional[Callable[[str], None]] = None,
) -> Path:
    """Скачивает zip релиза, распаковывает в zapret_dir (с зачисткой, сохраняя *-user.txt). Возвращает путь."""
    zdir = zapret_dir()

    def say(s: str):
        if status_cb:
            try:
                status_cb(s)
            except Exception:
                pass

    say("Подключение к GitHub…")
    tmp = Path(tempfile.gettempdir()) / f"proryv_zapret_{int(time.time())}.zip"
    with requests.get(zip_url, stream=True, timeout=60, headers={"User-Agent": "PRORYV-Launcher"}) as r:
        r.raise_for_status()
        total = int(r.headers.get("Content-Length") or 0)
        done = 0
        with open(tmp, "wb") as f:
            for chunk in r.iter_content(chunk_size=1024 * 256):
                if not chunk:
                    continue
                f.write(chunk)
                done += len(chunk)
                if progress_cb:
                    try:
                        progress_cb(done, total)
                    except Exception:
                        pass
    say("Распаковка…")

    # сохраняем пользовательские списки
    backup = {}
    try:
        for p in (zdir / "lists").glob("*-user.txt"):
            backup[p.name] = p.read_bytes()
    except Exception:
        pass

    # чистим старую папку (кроме бэкапа в памяти)
    for child in list(zdir.iterdir()):
        try:
            if child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink()
        except Exception:
            pass

    with zipfile.ZipFile(tmp, "r") as zf:
        # в архиве обычно одна корневая папка zapret-discord-youtube-X.Y.Z/
        members = zf.namelist()
        # распаковываем во временную папку, потом переносим содержимое корня
        tmpdir = Path(tempfile.mkdtemp(prefix="proryv_unpack_"))
        zf.extractall(tmpdir)
        # находим корень: папка с general.bat или bin/
        root = tmpdir
        cands = [p for p in tmpdir.iterdir() if p.is_dir()]
        for c in cands:
            if (c / "general.bat").exists() or (c / "bin").exists():
                root = c
                break
        for item in root.iterdir():
            dest = zdir / item.name
            if item.is_dir():
                shutil.copytree(item, dest, dirs_exist_ok=True)
            else:
                shutil.copy2(item, dest)
        shutil.rmtree(tmpdir, ignore_errors=True)
    try:
        tmp.unlink(missing_ok=True)
    except Exception:
        pass

    # возвращаем пользовательские списки
    try:
        if backup:
            (zdir / "lists").mkdir(exist_ok=True)
            for name, data in backup.items():
                fp = zdir / "lists" / name
                if not fp.exists():
                    fp.write_bytes(data)
    except Exception:
        pass

    # снимаем Zone.Identifier (аналог "Разблокировать" в свойствах)
    try:
        for p in zdir.rglob("*:Zone.Identifier"):
            p.unlink(missing_ok=True)
    except Exception:
        pass

    set_local_version(tag)
    say(f"Установлена версия {tag}")
    return zdir


# ---------------- strategies ----------------

STRATEGY_EXCLUDE = {"service.bat", "check_updates.bat"}

def list_strategies() -> list[str]:
    z = zapret_dir()
    if not z.exists():
        return []
    out = []
    for p in sorted(z.glob("*.bat")):
        n = p.name
        if n.lower().startswith("service"):
            continue
        if n in STRATEGY_EXCLUDE:
            continue
        # стратегии — это general*.bat, discord*.bat, youtube*.bat
        ln = n.lower()
        if ln.startswith("general") or ln.startswith("discord") or ln.startswith("youtube"):
            out.append(n)
    return out


def _run_hidden(cmd: list[str], cwd: Optional[Path] = None) -> subprocess.Popen:
    si = subprocess.STARTUPINFO()
    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    creation = subprocess.CREATE_NO_WINDOW
    return subprocess.Popen(
        cmd, cwd=str(cwd) if cwd else None,
        startupinfo=si, creationflags=creation,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL,
        shell=False,
    )


def kill_winws() -> None:
    try:
        subprocess.run(["taskkill", "/F", "/IM", "winws.exe"],
                       capture_output=True, timeout=10, **_hidden_kwargs())
    except Exception:
        pass
    # добиваем через psutil если есть
    try:
        import psutil
        for p in psutil.process_iter(["name"]):
            try:
                if (p.info.get("name") or "").lower() == "winws.exe":
                    p.kill()
            except Exception:
                pass
    except Exception:
        pass


def _winreg_service_names() -> list[str]:
    """Имена всех служб из реестра (без вспышек консоли)."""
    try:
        import winreg
        names = []
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                            r"SYSTEM\CurrentControlSet\Services") as root:
            i = 0
            while True:
                try:
                    names.append(winreg.EnumKey(root, i))
                except OSError:
                    break
                i += 1
        return names
    except Exception:
        return []


def _service_imagepath(name: str) -> str:
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                            rf"SYSTEM\CurrentControlSet\Services\{name}") as k:
            v, _ = winreg.QueryValueEx(k, "ImagePath")
            return str(v or "")
    except Exception:
        return ""


def _service_state_code(name: str) -> Optional[int]:
    """Цифровой код STATE службы (4=запущена, 1=остановлена), независимо от языка Windows."""
    out = _capture(["sc", "query", name])
    m = re.search(r"STATE\s*:\s*(\d+)", out)
    return int(m.group(1)) if m else None


_SCAN_CACHE: dict = {"ts": 0.0, "name": None}


def find_winws_service() -> Optional[str]:
    """Имя службы обхода: сначала 'zapret', иначе ищем по ImagePath с winws.exe."""
    if _service_imagepath("zapret"):
        return "zapret"
    now = time.time()
    if now - _SCAN_CACHE["ts"] < 60 and _SCAN_CACHE["name"]:
        if _service_imagepath(_SCAN_CACHE["name"]):
            return _SCAN_CACHE["name"]
    for n in _winreg_service_names():
        try:
            if "winws.exe" in _service_imagepath(n).lower():
                _SCAN_CACHE.update(ts=now, name=n)
                return n
        except Exception:
            continue
    _SCAN_CACHE.update(ts=now, name=None)
    return None


def is_running() -> bool:
    # 1) процесс winws.exe
    try:
        import psutil
        for p in psutil.process_iter(["name"]):
            try:
                if (p.info.get("name") or "").lower() == "winws.exe":
                    return True
            except Exception:
                continue
    except Exception:
        if "winws.exe" in _capture(["tasklist", "/FI", "IMAGENAME eq winws.exe"]):
            return True
    # 2) служба обхода запущена (любое имя)
    try:
        svc = find_winws_service()
        if svc and _service_state_code(svc) == 4:
            return True
    except Exception:
        pass
    return False


def start_strategy(bat_name: str) -> bool:
    """Запускает стратегию (ручной режим через bat). Требует прав администратора."""
    z = zapret_dir()
    bat = z / bat_name
    if not bat.exists():
        raise FileNotFoundError(f"Стратегия не найдена: {bat_name}")
    kill_winws()
    time.sleep(0.6)
    # запуск bat скрыто
    _run_hidden(["cmd", "/c", str(bat)], cwd=z)
    time.sleep(2.5)
    set_active_strategy(bat_name)
    return is_running()


def stop_all() -> bool:
    kill_winws()
    for svc in ("zapret", "WinDivert", "WinDivert14"):
        try:
            subprocess.run(["sc", "stop", svc], capture_output=True, timeout=10,
                           **_hidden_kwargs())
        except Exception:
            pass
    time.sleep(1.0)
    if is_running():
        kill_winws()
        time.sleep(0.8)
    set_active_strategy(None)
    return not is_running()


# ---------------- service (автозапуск) ----------------

def _extract_winws_args(bat_path: Path) -> Optional[str]:
    """Из bat-файла достаёт строку аргументов winws.exe (как делает service.bat)."""
    try:
        text = bat_path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        try:
            text = bat_path.read_text(encoding="cp866", errors="ignore")
        except Exception:
            return None
    # ищем строку с winws.exe
    for line in text.splitlines():
        if "winws.exe" in line.lower():
            # убираем start /min, кавычки, %~dp0
            s = line.strip()
            # пример: start "zapret" /min "%~dp0bin\winws.exe" --wf-tcp=... ...
            idx = s.lower().find("winws.exe")
            args = s[idx + len("winws.exe"):].strip().strip('"')
            base = str(zapret_dir() / "bin" / "winws.exe")
            # раскрываем переменные путей
            args = args.replace("%~dp0", str(zapret_dir()) + "\\")
            args = args.replace("@path", str(zapret_dir()))
            args = re.sub(r"\s+", " ", args)
            return f'"{base}" {args}'.strip()
    return None


def install_service(bat_name: str) -> tuple[bool, str]:
    """Ставит стратегию в автозапуск (служба zapret). Возвращает (ok, message)."""
    if not is_admin():
        return False, "Нужны права администратора. Перезапустите приложение от имени администратора."
    z = zapret_dir()
    bat = z / bat_name
    if not bat.exists():
        return False, f"Файл не найден: {bat_name}"
    binpath = _extract_winws_args(bat)
    if not binpath:
        return False, "Не удалось прочитать параметры стратегии из .bat файла."
    # удаляем старую службу
    subprocess.run(["sc", "stop", "zapret"], capture_output=True, timeout=15,
                   **_hidden_kwargs())
    subprocess.run(["sc", "delete", "zapret"], capture_output=True, timeout=15,
                   **_hidden_kwargs())
    time.sleep(1.0)
    r = subprocess.run(["sc", "create", "zapret", f"binPath= {binpath}", "start= auto"],
                       capture_output=True, text=True, timeout=20, **_hidden_kwargs())
    if r.returncode != 0 and "1073" not in (r.stdout + r.stderr):
        return False, f"Не удалось создать службу: {(r.stdout + r.stderr)[:300]}"
    r2 = subprocess.run(["sc", "start", "zapret"], capture_output=True, text=True,
                        timeout=20, **_hidden_kwargs())
    if r2.returncode != 0:
        return False, f"Служба создана, но не запустилась: {(r2.stdout + r2.stderr)[:300]}"
    set_active_strategy(bat_name)
    set_setting("service_strategy", bat_name)
    return True, f"Стратегия «{bat_name}» установлена в автозапуск."


def remove_service() -> tuple[bool, str]:
    if not is_admin():
        return False, "Нужны права администратора."
    for svc in ("zapret", "WinDivert"):
        subprocess.run(["sc", "stop", svc], capture_output=True, timeout=15,
                       **_hidden_kwargs())
    time.sleep(1.0)
    for svc in ("zapret", "WinDivert"):
        subprocess.run(["sc", "delete", svc], capture_output=True, timeout=15,
                       **_hidden_kwargs())
    kill_winws()
    set_active_strategy(None)
    return True, "Службы zapret и WinDivert удалены."


def service_status() -> str:
    """Статус обхода и WinDivert: проверка по реестру + цифровому коду STATE."""
    try:
        svc = find_winws_service()
        if svc:
            code = _service_state_code(svc)
            s1 = f"Служба {svc}: запущена" if code == 4 else f"Служба {svc}: остановлена"
        else:
            s1 = "Автозапуск: не установлен"
    except Exception:
        s1 = "Автозапуск: неизвестно"
    try:
        if _service_imagepath("WinDivert"):
            wd = _service_state_code("WinDivert")
            s2 = "WinDivert: активен" if wd == 4 else "WinDivert: остановлен"
        else:
            s2 = "WinDivert: нет"
    except Exception:
        s2 = ""
    return f"{s1}  •  {s2}" if s2 else s1


# ---------------- connectivity test / autopick ----------------

def check_targets(timeout: int = 8) -> dict:
    """Проверяет доступность целей, возвращает {name: (ok, ms)}."""
    res = {}
    for name, url in AUTOPICK_TARGETS:
        t0 = time.perf_counter()
        try:
            r = requests.get(url, timeout=timeout, headers={"User-Agent": "PRORYV-check"},
                             allow_redirects=True)
            ms = int((time.perf_counter() - t0) * 1000)
            ok = r.status_code < 500
            res[name] = (ok, ms if ok else -1)
        except Exception:
            res[name] = (False, -1)
    return res


def score_check(res: dict) -> tuple[int, float]:
    ok = sum(1 for v in res.values() if v[0])
    times = [v[1] for v in res.values() if v[0] and v[1] >= 0]
    avg = sum(times) / len(times) if times else 9999.0
    return ok, avg


def autopick(
    strategies: list[str],
    status_cb: Optional[Callable[[str], None]] = None,
    progress_cb: Optional[Callable[[int, int], None]] = None,
    stop_event=None,
) -> tuple[Optional[str], dict]:
    """Перебирает стратегии: запускает каждую, меряет цели, выбирает лучшую и оставляет включённой."""
    def say(s: str):
        if status_cb:
            try:
                status_cb(s)
            except Exception:
                pass

    best, best_score, details = None, (-1, 1e9), {}
    total = len(strategies)
    for i, strat in enumerate(strategies):
        if stop_event is not None and getattr(stop_event, "is_set", lambda: False)():
            break
        say(f"Проверка {i+1}/{total}: {strat}")
        try:
            kill_winws()
            time.sleep(0.8)
            _run_hidden(["cmd", "/c", str(zapret_dir() / strat)], cwd=zapret_dir())
            time.sleep(4.0)  # даём winws подняться и прогреть соединение
            res = check_targets()
            ok, avg = score_check(res)
            details[strat] = {"ok": ok, "avg_ms": round(avg, 1), "res": res}
            say(f"{strat}: доступно {ok}/{len(AUTOPICK_TARGETS)}, ~{int(avg)} мс" if ok else f"{strat}: недоступно")
            if (ok, -avg) > (best_score[0], -best_score[1]):
                best, best_score = strat, (ok, avg)
                # ранний выход: всё доступно и быстро
                if ok == len(AUTOPICK_TARGETS) and avg < 1500:
                    if progress_cb:
                        try:
                            progress_cb(i + 1, total)
                        except Exception:
                            pass
                    break
        except Exception as e:
            details[strat] = {"ok": 0, "avg_ms": -1, "error": str(e)[:200]}
        if progress_cb:
            try:
                progress_cb(i + 1, total)
            except Exception:
                pass
    # оставляем лучшую включённой
    if best:
        kill_winws()
        time.sleep(0.8)
        _run_hidden(["cmd", "/c", str(zapret_dir() / best)], cwd=zapret_dir())
        time.sleep(2.0)
        set_active_strategy(best)
        say(f"Выбрано: {best}")
    else:
        kill_winws()
    return best, details
