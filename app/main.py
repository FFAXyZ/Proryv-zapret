"""ПРОРЫВ — чёрно-белый минималистичный лаунчер zapret."""
from __future__ import annotations
import os
import queue
import subprocess
import threading
import time
import traceback
import webbrowser
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox

from PIL import ImageTk

from .config import APP_NAME, APP_VERSION, THEME, GITHUB_RELEASES_PAGE, base_dir, zapret_dir
from . import zapret_manager as zm
from . import icons as app_icons
from . import fonts as app_fonts

BG, BG2, CARD = THEME["bg"], THEME["bg2"], THEME["card"]
FG, MUTED = THEME["fg"], THEME["muted"]
BORDER, TRACK = THEME["card_border"], THEME["track"]


# ---------- widgets ----------

class MonoButton(tk.Canvas):
    """Плоская монохромная кнопка с hover-анимацией (Canvas чтобы красиво)."""
    def __init__(self, master, text, command=None, primary=False, width=200, height=44,
                 font=None, icon=None):
        super().__init__(master, width=width, height=height, highlightthickness=0,
                         bg=BG, bd=0)
        self._text = text
        self._cmd = command
        self._primary = primary
        self._icon = icon  # PhotoImage или None (ссылку держим здесь)
        self._bw, self._bh = width, height
        self._hover = 0.0  # 0..1 анимация
        self._target = 0.0
        self._animating = False
        self._font = font or ("Segoe UI", 11, "bold" if primary else "normal")
        self.bind("<Enter>", lambda e: self._set_target(1.0))
        self.bind("<Leave>", lambda e: self._set_target(0.0))
        self.bind("<Button-1>", lambda e: command() if command else None)
        self._draw()  # один статичный кадр, без бесконечного цикла

    def _colors(self):
        t = self._hover
        if self._primary:
            # белая кнопка: hover -> чуть серая
            bg = self._mix("#FFFFFF", "#CFCFCF", t)
            fg = "#000000"
            brd = bg
        else:
            bg = self._mix("#161618", "#232326", t)
            fg = "#F5F5F5"
            brd = self._mix("#2A2A2D", "#4A4A4E", t)
        return bg, fg, brd

    @staticmethod
    def _mix(a, b, t):
        def hx(s): return tuple(int(s[i:i+2], 16) for i in (1, 3, 5))
        A, B = hx(a), hx(b)
        C = tuple(int(A[i] + (B[i]-A[i])*t) for i in range(3))
        return "#%02x%02x%02x" % C

    def _set_target(self, t):
        self._target = t
        if not self._animating:
            self._animating = True
            self._tick()

    def _tick(self):
        # кадры идут ТОЛЬКО пока идёт переход hover; в покое — тишина, без моргания
        step = 0.18
        if self._hover < self._target:
            self._hover = min(self._target, self._hover + step)
        elif self._hover > self._target:
            self._hover = max(self._target, self._hover - step)
        self._draw()
        if abs(self._hover - self._target) > 0.001:
            self.after(30, self._tick)
        else:
            self._hover = self._target
            self._draw()
            self._animating = False

    def _draw(self):
        self.delete("all")
        bg, fg, brd = self._colors()
        r = 10
        self.create_rounded(2, 2, self._bw-2, self._bh-2, r, fill=bg, outline=brd, width=1)
        tx = self._bw // 2
        if self._icon is not None:
            try:
                iw = self._icon.width()
                ix = 20 + iw // 2
                self.create_image(ix, self._bh // 2, image=self._icon)
                tx = self._bw // 2 + (ix + iw // 2 - 14) // 2
            except Exception:
                pass
        self.create_text(tx, self._bh//2, text=self._text, fill=fg, font=self._font)

    def create_rounded(self, x1, y1, x2, y2, r, **kw):
        pts = [x1+r,y1, x2-r,y1, x2,y1, x2,y1+r, x2,y2-r, x2,y2, x2-r,y2, x1+r,y2, x1,y2, x1,y2-r, x1,y1+r, x1,y1, x1+r,y1]
        return self.create_polygon(pts, smooth=True, **kw)

    def set_text(self, t):
        if t != self._text:
            self._text = t
            self._draw()

    def set_icon(self, img):
        self._icon = img
        self._draw()


class AnimatedBar(tk.Canvas):
    """Тонкий прогресс-бар: determinate + shimmer в indeterminate."""
    def __init__(self, master, width=640, height=8):
        super().__init__(master, width=width, height=height, highlightthickness=0, bg=BG)
        self._bw, self._bh = width, height
        self._frac = 0.0
        self._ind = False
        self._pos = 0.0
        self._animating = False
        self._draw()  # один статичный кадр

    def set(self, done, total):
        was_ind = self._ind
        self._ind = False
        if total and total > 0:
            self._frac = max(0.0, min(1.0, done / total))
        else:
            self._frac = 0.0
        self._draw()
        if was_ind:
            self._animating = False

    def indeterminate(self, on=True):
        self._ind = on
        if on and not self._animating:
            self._animating = True
            self._tick()
        elif not on:
            self._animating = False
            self._draw()

    def _tick(self):
        if not self._ind:  # выключили посреди анимации — стоп, без лишних кадров
            self._animating = False
            self._draw()
            return
        self._pos = (self._pos + 0.02) % 1.2
        self._draw()
        self.after(40, self._tick)

    def _draw(self):
        self.delete("all")
        w, h = self._bw, self._bh
        self.create_rounded(0, 1, w, h-1, 4, fill=TRACK, outline="")
        if self._ind:
            bw = w * 0.3
            x = self._pos * w - bw/2
            self.create_rounded(max(0,x), 1, min(w,x+bw), h-1, 4, fill="#FFFFFF", outline="")
        elif self._frac > 0:
            self.create_rounded(0, 1, max(8, w*self._frac), h-1, 4, fill="#FFFFFF", outline="")

    def create_rounded(self, x1, y1, x2, y2, r, **kw):
        return self.create_rectangle(x1, y1, x2, y2, **kw)


# ---------- app ----------

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"{APP_NAME} — обход блокировок")
        self.geometry("730x880")
        self.minsize(700, 840)
        self.configure(bg=BG)
        # Семейства шрифтов (Unbounded/Manrope, иначе Segoe UI).
        self.TF, self.BF = app_fonts.resolve()
        try:
            import tkinter.font as _tkfont
            _fams = set(_tkfont.families())
            if self.TF not in _fams:
                self.TF = "Segoe UI"
            if self.BF not in _fams:
                self.BF = "Segoe UI"
        except Exception:
            pass
        self._ui_queue: queue.Queue = queue.Queue()
        self._stop_autopick = threading.Event()
        self._status_on = False
        self._last_ui_state = None
        self._build()
        self._poll_queue()
        self._tick_status()
        self.after(80, self._dark_titlebar)
        self.after(600, self._startup_checks)

    def _dark_titlebar(self):
        """Верхняя панель в цвет лаунчера: тёмная тема + чёрный заголовок (Windows 10/11)."""
        try:
            import ctypes
            hwnd = self.winfo_id()
            use_dark = ctypes.c_int(1)
            try:
                ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(use_dark), 4)
            except Exception:
                pass
            try:
                caption = ctypes.c_int(0x000C0B0B)  # #0B0B0C в формате COLORREF
                ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 35, ctypes.byref(caption), 4)
            except Exception:
                pass
        except Exception:
            pass

    # ----- layout -----
    def _build(self):
        root = tk.Frame(self, bg=BG)
        root.pack(fill="both", expand=True, padx=28, pady=14)

        # шапка: логотип-плашка + название
        head = tk.Frame(root, bg=BG)
        head.pack(fill="x")
        try:
            self._logo_img = ImageTk.PhotoImage(app_icons.render_logo(56))
            self._win_icon = ImageTk.PhotoImage(app_icons.render_logo(32))
            try:
                self.iconphoto(True, self._win_icon)
            except Exception:
                pass
            tk.Label(head, image=self._logo_img, bg=BG).pack(side="left")
        except Exception:
            self._logo_img = None
        titlebox = tk.Frame(head, bg=BG)
        titlebox.pack(side="left", padx=(14, 0))
        tk.Label(titlebox, text=APP_NAME, font=(self.TF, 27, "bold"),
                 fg="#FFFFFF", bg=BG, anchor="w").pack(anchor="w")
        tk.Label(titlebox, text="обход блокировок", font=(self.BF, 11),
                 fg=MUTED, bg=BG, anchor="w").pack(anchor="w")
        right = tk.Frame(head, bg=BG)
        right.pack(side="right", anchor="e")
        tk.Label(right, text=f"v{APP_VERSION}", font=("Consolas", 10), fg=MUTED, bg=BG).pack(anchor="e")

        # баннер обновления
        self.banner = tk.Frame(root, bg="#FFFFFF", padx=14, pady=10)
        self.banner_text = tk.Label(self.banner, text="", font=(self.BF, 10, "bold"),
                                    fg="#000000", bg="#FFFFFF")
        self.banner_text.pack(side="left", fill="x", expand=True)
        MonoButton(self.banner, text="Обновить", command=self.on_install,
                   primary=True, width=130, height=34,
                    font=(self.BF, 10, "bold")).pack(side="right")
        # скрыт по умолчанию (pack_forget)

        # статус-карточка
        card = tk.Frame(root, bg=CARD, highlightbackground=BORDER, highlightthickness=1,
                        padx=18, pady=14)
        card.pack(fill="x", pady=(10, 8))
        top = tk.Frame(card, bg=CARD)
        top.pack(fill="x")
        self.dot = tk.Canvas(top, width=26, height=26, bg=CARD, highlightthickness=0)
        self.dot.pack(side="left")
        self.lbl_state = tk.Label(top, text="ВЫКЛЮЧЕНО", font=(self.TF, 16, "bold"),
                                  fg=FG, bg=CARD)
        self.lbl_state.pack(side="left", padx=(8, 0))
        self.lbl_ver = tk.Label(top, text="zapret: не установлен", font=("Consolas", 10),
                                fg=MUTED, bg=CARD)
        self.lbl_ver.pack(side="right")
        self.lbl_strat = tk.Label(card, text="стратегия: —", font=(self.BF, 11),
                                  fg=MUTED, bg=CARD, anchor="w")
        self.lbl_strat.pack(fill="x", pady=(6, 0))
        self.lbl_svc = tk.Label(card, text="", font=(self.BF, 9), fg=MUTED, bg=CARD, anchor="w")
        self.lbl_svc.pack(fill="x")

        # прогресс
        self.bar = AnimatedBar(root, width=660, height=8)
        self.bar.pack(fill="x", pady=(2, 4))
        self.lbl_progress = tk.Label(root, text="Готов к работе", font=(self.BF, 9),
                                     fg=MUTED, bg=BG, anchor="w")
        self.lbl_progress.pack(fill="x")

        # главные кнопки (с векторными иконками)
        grid = tk.Frame(root, bg=BG)
        grid.pack(fill="x", pady=(10, 4))
        _W, _B = (255, 255, 255, 255), (0, 0, 0, 255)

        def _ico(name, px, color):
            try:
                return ImageTk.PhotoImage(app_icons.render(name, px, color))
            except Exception:
                return None

        self._ico_dl = _ico("download", 20, _B)    # на белой кнопке — чёрная
        self._ico_play = _ico("play", 20, _W)
        self._ico_pause = _ico("pause", 20, _W)
        self._ico_spark = _ico("spark", 20, _W)
        self._ico_stop = _ico("stop", 18, _W)
        self._ico_power = _ico("power", 18, _W)
        _big = (self.BF, 11, "bold")
        _mid = (self.BF, 10)
        self.btn_install = MonoButton(grid, text="Установить", command=self.on_install,
                                      primary=True, width=210, height=48,
                                      font=_big, icon=self._ico_dl)
        self.btn_install.grid(row=0, column=0, padx=(0, 10))
        self.btn_toggle = MonoButton(grid, text="Включить", command=self.on_toggle,
                                     width=210, height=48,
                                     font=_big, icon=self._ico_play)
        self.btn_toggle.grid(row=0, column=1, padx=(0, 10))
        self.btn_auto = MonoButton(grid, text="Автоподбор", command=self.on_autopick,
                                   width=210, height=48,
                                   font=_big, icon=self._ico_spark)
        self.btn_auto.grid(row=0, column=2)
        # вторая строка
        grid2 = tk.Frame(root, bg=BG)
        grid2.pack(fill="x", pady=(2, 4))
        self.btn_stop = MonoButton(grid2, text="Остановить", command=self.on_stop,
                                   width=210, height=42, font=_mid, icon=self._ico_stop)
        self.btn_stop.grid(row=0, column=0, padx=(0, 10))
        self.btn_svc = MonoButton(grid2, text="В автозапуск", command=self.on_service_install,
                                  width=210, height=42, font=_mid, icon=self._ico_power)
        self.btn_svc.grid(row=0, column=1, padx=(0, 10))
        self.btn_svc_rm = MonoButton(grid2, text="Убрать службу", command=self.on_service_remove,
                                     width=210, height=42, font=_mid)
        self.btn_svc_rm.grid(row=0, column=2)

        # стратегии
        sf = tk.Frame(root, bg=BG)
        sf.pack(fill="x", pady=(8, 0))
        tk.Label(sf, text="СТРАТЕГИЯ", font=(self.BF, 9, "bold"), fg=MUTED, bg=BG).pack(side="left")
        MonoButton(sf, text="↻", command=self.refresh_strategies, width=40, height=30,
                   font=("Segoe UI", 12)).pack(side="right")
        listf = tk.Frame(root, bg=BG)
        listf.pack(fill="both", expand=True, pady=(4, 4))
        self.strat_list = tk.Listbox(listf, bg="#101012", fg=FG, selectbackground="#FFFFFF",
                                     selectforeground="#000000", font=("Consolas", 11),
                                     highlightthickness=1, highlightbackground=BORDER,
                                     relief="flat", activestyle="none", height=6)
        self.strat_list.pack(side="left", fill="both", expand=True)
        sb = tk.Scrollbar(listf, command=self.strat_list.yview)
        sb.pack(side="right", fill="y")
        self.strat_list.config(yscrollcommand=sb.set)
        self.strat_list.bind("<Double-Button-1>", lambda e: self.on_toggle())

        # низ: лог + опции
        optf = tk.Frame(root, bg=BG)
        optf.pack(fill="x")
        self.var_autoupd = tk.BooleanVar(value=bool(zm.get_setting("auto_update", True)))
        cb = tk.Checkbutton(optf, text="Автообновление запрета при выходе новой версии",
                            variable=self.var_autoupd, command=self._save_opts,
                            bg=BG, fg=MUTED, selectcolor=BG, activebackground=BG,
                            font=(self.BF, 9))
        cb.pack(side="left")
        link = tk.Label(optf, text="GitHub ↗", font=(self.BF, 9, "underline"),
                        fg=FG, bg=BG, cursor="hand2")
        link.pack(side="right")
        link.bind("<Button-1>", lambda e: webbrowser.open(GITHUB_RELEASES_PAGE))

        self.log = tk.Text(root, bg="#0E0E10", fg="#D9D9D9", font=("Consolas", 9),
                           highlightthickness=1, highlightbackground=BORDER,
                           relief="flat", height=6, state="disabled")
        self.log.pack(fill="both", expand=False, pady=(6, 0))

        foot = tk.Frame(root, bg=BG)
        foot.pack(fill="x", pady=(8, 0))
        MonoButton(foot, text="Открыть папку", command=self.on_open_folder,
                   width=160, height=34, font=(self.BF, 9)).pack(side="left")
        MonoButton(foot, text="Проверить обновление", command=self.on_check_update,
                   width=200, height=34, font=(self.BF, 9)).pack(side="left", padx=(10, 0))
        tk.Label(foot, text="WinDivert требует антивирус-исключение",
                 font=(self.BF, 8), fg=MUTED, bg=BG).pack(side="right")

    # ----- animation -----
    def _draw_dot(self):
        # Точка рисуется только при смене состояния — статично, без пульса-моргания.
        self.dot.delete("all")
        if self._status_on:
            self.dot.create_oval(5, 5, 21, 21, fill="#FFFFFF", outline="")
        else:
            self.dot.create_oval(6, 6, 20, 20, fill="", outline="#555558", width=2)

    def _tick_status(self):
        try:
            on = zm.is_running()
            lv = zm.get_local_version()
            act = zm.get_active_strategy()
            installed = bool(zm.is_installed())
            try:
                svc = zm.service_status()
            except Exception:
                svc = ""
            state = (on, lv, act, svc, installed)
            if state != self._last_ui_state:
                # Обновляем виджеты только если что-то реально изменилось.
                self._last_ui_state = state
                self._status_on = on
                self._draw_dot()
                self._sync_install_button()
                self.lbl_state.config(text="ВКЛЮЧЕНО" if on else "ВЫКЛЮЧЕНО")
                self.btn_toggle.set_text("Выключить" if on else "Включить")
                self.btn_toggle.set_icon(self._ico_pause if on else self._ico_play)
                self.lbl_ver.config(text=f"zapret: {lv}" if lv else "zapret: не установлен")
                self.lbl_strat.config(text=f"стратегия: {act}" if act else "стратегия: —")
                self.lbl_svc.config(text=svc)
        except Exception:
            pass
        self.after(3000, self._tick_status)

    # ----- log / queue -----
    def say(self, s):
        self._ui_queue.put(("log", s))

    def _poll_queue(self):
        try:
            while True:
                kind, *rest = self._ui_queue.get_nowait()
                if kind == "log":
                    self._append_log(rest[0])
                elif kind == "progress":
                    self.lbl_progress.config(text=rest[0])
                elif kind == "bar":
                    self.bar.set(*rest)
                elif kind == "bar_ind":
                    self.bar.indeterminate(rest[0])
                elif kind == "banner":
                    self._show_banner(rest[0])
                elif kind == "refresh":
                    self.refresh_strategies()
                elif kind == "msg":
                    title, text = rest
                    messagebox.showinfo(title, text)
        except queue.Empty:
            pass
        self.after(120, self._poll_queue)

    def _append_log(self, s):
        self.log.config(state="normal")
        self.log.insert("end", f"[{time.strftime('%H:%M:%S')}] {s}\n")
        self.log.see("end")
        self.log.config(state="disabled")

    def _show_banner(self, tag):
        for w in self.banner_text.master.pack_slaves():
            pass
        self.banner_text.config(text=f"Доступна новая версия запрета: {tag}  —  обновитесь в один клик")
        try:
            self.banner.pack(fill="x", pady=(0, 4))
        except Exception:
            pass

    def _hide_banner(self):
        try:
            self.banner.pack_forget()
        except Exception:
            pass

    def _save_opts(self):
        zm.set_setting("auto_update", bool(self.var_autoupd.get()))

    # ----- actions -----
    def _need_admin_warn(self, strict=False):
        if not zm.is_admin() and strict:
            messagebox.showwarning(
                "Нужны права администратора",
                "Запуск обхода и установка службы требуют прав администратора.\n\n"
                "Закройте приложение и запустите его правой кнопкой → «Запуск от имени администратора».")
            return True
        return False

    def on_open_folder(self):
        p = zapret_dir()
        p.mkdir(parents=True, exist_ok=True)
        try:
            os.startfile(str(p))
        except Exception:
            subprocess.Popen(["explorer", str(p)])

    def _sync_install_button(self):
        """Кнопка «Установить» видна только пока запрета нет на ПК."""
        try:
            if zm.is_installed():
                self.btn_install.grid_remove()
                self.btn_toggle.grid(row=0, column=0, padx=(0, 10))
                self.btn_auto.grid(row=0, column=1)
            else:
                self.btn_install.grid(row=0, column=0, padx=(0, 10))
                self.btn_toggle.grid(row=0, column=1, padx=(0, 10))
                self.btn_auto.grid(row=0, column=2)
        except Exception:
            pass

    def refresh_strategies(self):
        self.strat_list.delete(0, "end")
        strs = zm.list_strategies()
        act = zm.get_active_strategy()
        for s in strs:
            mark = "● " if s == act else "○ "
            self.strat_list.insert("end", mark + s)
        if not strs:
            self.strat_list.insert("end", "— стратегии не найдены, нажмите «Установить» —")
        self._sync_install_button()
        self._append_log(f"Найдено стратегий: {len(strs)}")

    def selected_strategy(self) -> str | None:
        try:
            sel = self.strat_list.curselection()
            if not sel:
                strs = zm.list_strategies()
                return strs[0] if strs else None
            txt = self.strat_list.get(sel[0])
            return txt[2:] if txt.startswith(("● ", "○ ")) else txt
        except Exception:
            return None

    # --- install / update ---
    def on_install(self):
        self._hide_banner()
        self.bar.indeterminate(True)
        self.lbl_progress.config(text="Проверка последней версии…")
        threading.Thread(target=self._install_worker, daemon=True).start()

    def _install_worker(self):
        q = self._ui_queue
        try:
            q.put(("progress", "Запрос к GitHub API…"))
            rel = zm.get_latest_release()
            tag, url, size = rel["tag"], rel["zip_url"], rel["size"]
            q.put(("log", f"Последняя версия на GitHub: {tag} ({size//1024} КБ)"))
            if zm.is_installed() and not zm.is_update_available(tag):
                q.put(("progress", "У вас уже последняя версия"))
                q.put(("bar_ind", False))
                q.put(("msg", APP_NAME, f"У вас уже последняя версия запрета: {tag}"))
                return
            if zm.is_running():
                q.put(("log", "Останавливаю текущий обход перед обновлением…"))
                zm.stop_all()
            q.put(("bar_ind", False))

            def prog(done, total):
                q.put(("bar", done, total))
                if total:
                    q.put(("progress", f"Скачивание… {done//1024//1024} / {max(1,total//1024//1024)} МБ"))
                else:
                    q.put(("progress", f"Скачивание… {done//1024} КБ"))

            zm.download_and_install(url, tag, progress_cb=prog,
                                    status_cb=lambda s: q.put(("log", s)))
            q.put(("bar", 1, 1))
            q.put(("progress", f"Готово: {tag}"))
            q.put(("log", f"Установка завершена: {tag}"))
            q.put(("refresh",))
        except Exception as e:
            q.put(("bar_ind", False))
            q.put(("progress", "Ошибка установки"))
            q.put(("log", f"ОШИБКА: {e}"))
            q.put(("log", traceback.format_exc(limit=3)))
        finally:
            q.put(("bar_ind", False))

    # --- on/off ---
    def on_toggle(self):
        if zm.is_running():
            self.on_stop()
            return
        strat = self.selected_strategy()
        if not strat:
            messagebox.showinfo(APP_NAME, "Сначала нажмите «Установить», чтобы скачать запрет.")
            return
        if self._need_admin_warn(strict=True):
            return
        self.say(f"Включаю: {strat} …")
        threading.Thread(target=self._start_worker, args=(strat,), daemon=True).start()

    def _start_worker(self, strat):
        q = self._ui_queue
        try:
            q.put(("bar_ind", True))
            ok = zm.start_strategy(strat)
            q.put(("bar_ind", False))
            q.put(("bar", 1 if ok else 0, 1))
            if ok:
                q.put(("log", f"Включено: {strat}"))
                q.put(("progress", f"Включено: {strat}"))
            else:
                q.put(("log", "winws не detected. Попробуйте другую стратегию или запустите от администратора."))
                q.put(("progress", "Не удалось включить — попробуйте другую стратегию"))
            q.put(("refresh",))
        except Exception as e:
            q.put(("bar_ind", False))
            q.put(("log", f"ОШИБКА запуска: {e}"))

    def on_stop(self):
        self.say("Останавливаю…")
        threading.Thread(target=self._stop_worker, daemon=True).start()

    def _stop_worker(self):
        q = self._ui_queue
        try:
            ok = zm.stop_all()
            q.put(("log", "Остановлено." if ok else "Процессы остановлены (проверьте вручную)."))
            q.put(("progress", "Остановлено"))
            q.put(("bar", 0, 1))
            q.put(("refresh",))
        except Exception as e:
            q.put(("log", f"ОШИБКА остановки: {e}"))

    # --- autopick ---
    def on_autopick(self):
        if not zm.is_installed():
            messagebox.showinfo(APP_NAME, "Сначала установите запрет (кнопка «Установить»).")
            return
        if self._need_admin_warn(strict=True):
            return
        strs = zm.list_strategies()
        if not strs:
            messagebox.showwarning(APP_NAME, "Стратегии не найдены.")
            return
        # ограничиваем перебор чтобы не гонять 20 стратегий по минуте: берём все, но autopick сам выйдет раньше при идеале
        self._stop_autopick.clear()
        self.bar.indeterminate(True)
        self.say(f"Автоподбор: проверяю {len(strs)} стратегий…")
        threading.Thread(target=self._autopick_worker, args=(strs,), daemon=True).start()

    def _autopick_worker(self, strs):
        q = self._ui_queue
        try:
            def prog(i, total):
                q.put(("bar", i, total))
                q.put(("progress", f"Автоподбор {i}/{total}…"))
            best, details = zm.autopick(
                strs,
                status_cb=lambda s: q.put(("log", s)),
                progress_cb=prog,
                stop_event=self._stop_autopick,
            )
            q.put(("bar_ind", False))
            if best:
                d = details.get(best, {})
                q.put(("log", f"★ Лучшая стратегия: {best} (доступно {d.get('ok')}, {d.get('avg_ms')} мс)"))
                q.put(("progress", f"Автоподбор готов: {best}"))
                q.put(("msg", APP_NAME, f"Наилучшее подключение: {best}\nОно уже включено."))
            else:
                q.put(("log", "Автоподбор: ни одна стратегия не прошла проверку."))
                q.put(("progress", "Автоподбор не нашёл рабочую стратегию"))
                q.put(("msg", APP_NAME, "Ни одна стратегия не прошла проверку.\nПопробуйте позже или смените сеть/DNS."))
            q.put(("refresh",))
        except Exception as e:
            q.put(("bar_ind", False))
            q.put(("log", f"ОШИБКА автоподбора: {e}"))

    # --- service ---
    def on_service_install(self):
        strat = self.selected_strategy() or zm.get_active_strategy()
        if not strat:
            messagebox.showinfo(APP_NAME, "Выберите стратегию в списке.")
            return
        threading.Thread(target=self._svc_inst_worker, args=(strat,), daemon=True).start()

    def _svc_inst_worker(self, strat):
        q = self._ui_queue
        ok, msg = zm.install_service(strat)
        q.put(("log", msg))
        q.put(("progress", msg))
        if not ok:
            q.put(("msg", APP_NAME, msg))

    def on_service_remove(self):
        threading.Thread(target=lambda: (
            self._ui_queue.put(("log", zm.remove_service()[1])),), daemon=True).start()

    # --- update check ---
    def on_check_update(self):
        threading.Thread(target=self._check_update_worker, daemon=True).start()

    def _check_update_worker(self, silent=False):
        q = self._ui_queue
        try:
            rel = zm.get_latest_release()
            tag = rel["tag"]
            local = zm.get_local_version()
            if not zm.is_installed():
                q.put(("log", f"Запрет не установлен. Последняя на GitHub: {tag}"))
                if not silent:
                    q.put(("banner", tag))
                return
            if zm.is_update_available(tag):
                q.put(("log", f"Доступно обновление: {local} → {tag}"))
                q.put(("banner", tag))
                if zm.get_setting("auto_update", True) and not silent:
                    q.put(("log", "Автообновление включено — скачиваю…"))
                    self.on_install()
                elif not silent:
                    q.put(("msg", APP_NAME, f"Доступна новая версия запрета: {tag}\nТекущая: {local}"))
            else:
                q.put(("log", f"У вас последняя версия: {local}"))
                if not silent:
                    q.put(("msg", APP_NAME, f"У вас последняя версия: {local}"))
        except Exception as e:
            q.put(("log", f"Не удалось проверить обновление: {e}"))

    def _startup_checks(self):
        self.refresh_strategies()
        self.say(f"Папка данных: {base_dir()}")
        if not zm.is_installed():
            self.say("Запрет не найден — нажмите «Установить».")
        else:
            self.say(f"Установлен запрет {zm.get_local_version()}")
        threading.Thread(target=self._check_update_worker, kwargs={"silent": True},
                         daemon=True).start()


def main():
    # Ставим красивые шрифты до создания окна (нужен админ; иначе тихо Segoe UI).
    try:
        app_fonts.ensure_fonts()
    except Exception:
        pass
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
