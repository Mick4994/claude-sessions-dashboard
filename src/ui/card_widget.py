# ruff: noqa: E501, N802
"""Expanded session card: dot | title+subtitle+progress+cwd | percent."""

from __future__ import annotations

import datetime as _dt
import os

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QAction, QColor, QFont
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QProgressBar,
    QVBoxLayout,
)

from ..collector.models import Session
from .indicator_widget import IndicatorDot


def _context_color(pct: float, *, warn: float = 70.0, crit: float = 85.0) -> QColor:
    if pct >= crit:
        return QColor("#EF4444")
    if pct >= warn:
        return QColor("#EAB308")
    return QColor("#22C55E")


def _format_pct(p: float) -> str:
    if p >= 99.5:
        return "100%"
    return f"{p:.0f}%"


def _shorten_cwd(cwd: str) -> str:
    if not cwd:
        return ""
    return "/".join(cwd.replace("\\", "/").split("/")[-3:])


def _cw_log(tag: str, msg: str) -> None:
    """card_widget.py 专用日志，落 %TEMP%/csd_click_debug.log。"""
    try:
        _p = os.environ.get("TEMP", ".") + os.sep + "csd_click_debug.log"
        with open(_p, "a", encoding="utf-8") as _f:
            _f.write(f"{_dt.datetime.now():%H:%M:%S.%f} [cw:{tag}] {msg}\n")
    except Exception:
        pass


def _format_terminal_label(t: dict, is_paired: bool, paired_hwnd: int | None) -> str:
    """构造 QMenuAction 文本：✓/空格 + PID + 标题 + class/尺寸。"""
    _title = t.get("title") or "(无标题)"
    if len(_title) > 40:
        _title = _title[:37] + "..."
    _pid = t.get("pid", 0)
    _cls = t.get("class", "")
    _w = t.get("width", 0)
    _h = t.get("height", 0)
    _check = "✓" if is_paired else " "
    _pid_str = f"PID {_pid}"
    return f"{_check} {_pid_str:<10}  {_title}    [{_cls}, {_w}×{_h}]"


class SessionCard(QFrame):
    """Expanded card widget for one Claude Code session."""

    clicked = Signal(str)  # session_id
    pairRequested = Signal(str, int, str, str)  # session_id, hwnd, title, class_name
    unpairRequested = Signal(str)  # session_id
    # 携带 Session 对象，让 MainWindow 能直接查 title/subtitle 过滤终端
    listTerminalsRequested = Signal(object)  # session

    def __init__(self, session: Session, *, parent=None) -> None:
        super().__init__(parent)
        self.session = session
        self.setObjectName("SessionCard")
        self.setStyleSheet(
            "#SessionCard { background: transparent; }"
            'QLabel[role="subtitle"] { color: rgba(180,180,190,0.85); }'
            'QLabel[role="cwd"] { color: rgba(140,140,150,0.7); font-size: 10px; }'
            'QLabel[role="percent"] { font-weight: bold; }'
            "QProgressBar { background: rgba(255,255,255,0.08); border: none; height: 6px; border-radius: 3px; }"
            "QProgressBar::chunk { border-radius: 3px; }"
        )

        self.dot = IndicatorDot(session.status, size_px=10)

        self.title_label = QLabel(session.title or "(untitled)")
        self.title_label.setStyleSheet("color: #E6E6EA;")

        self.subtitle_label = QLabel(session.subtitle or "")
        self.subtitle_label.setProperty("role", "subtitle")
        self.subtitle_label.setTextFormat(Qt.PlainText)
        f = QFont()
        f.setPointSize(9)
        self.subtitle_label.setFont(f)

        pct_color = _context_color(session.context_pct)
        self.percent_label = QLabel(_format_pct(session.context_pct))
        self.percent_label.setProperty("role", "percent")
        self.percent_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.percent_label.setStyleSheet(f"color: {pct_color.name()}; font-size: 12px;")

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(int(session.context_pct))
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(6)
        self.progress.setStyleSheet(
            f"QProgressBar {{ background: rgba(255,255,255,0.08); border: none; height: 6px; border-radius: 3px; }}"
            f"QProgressBar::chunk {{ background-color: {pct_color.name()}; border-radius: 3px; }}"
        )

        cwd_label = QLabel(_shorten_cwd(session.cwd))
        cwd_label.setProperty("role", "cwd")
        cwd_label.setWordWrap(False)
        cwd_label.setTextFormat(Qt.PlainText)

        left = QVBoxLayout()
        left.setContentsMargins(0, 0, 0, 0)
        left.setSpacing(2)
        left.addWidget(self.title_label)
        left.addWidget(self.subtitle_label)
        left.addWidget(self.progress)
        left.addWidget(cwd_label)

        right = QVBoxLayout()
        right.setContentsMargins(0, 0, 0, 0)
        right.setSpacing(0)
        right.addWidget(self.percent_label, 0, Qt.AlignRight)
        right.addStretch(1)

        outer = QHBoxLayout(self)
        outer.setContentsMargins(8, 6, 8, 6)
        outer.setSpacing(8)
        outer.addWidget(self.dot, 0, Qt.AlignTop)
        outer.addLayout(left, 1)
        outer.addLayout(right, 0)

        self.setFixedHeight(78)
        self.setCursor(Qt.PointingHandCursor)
        self._orig_stylesheet = self.styleSheet()
        # 终端列表（按 session 过滤后）+ 元数据
        self._terminals: list[dict] = []
        self._fallback_to_all: bool = False
        self._paired_hwnd: int | None = None
        self._is_paired: bool = False
        self._paired_dot = None  # 在 set_paired() 第一次调用时初始化

    def enterEvent(self, ev) -> None:
        self.setStyleSheet(
            self._orig_stylesheet
            + " #SessionCard { background: rgba(255,255,255,0.06); border-radius: 6px; }"
        )
        super().enterEvent(ev)

    def leaveEvent(self, ev) -> None:
        self.setStyleSheet(self._orig_stylesheet)
        super().leaveEvent(ev)

    def update_session(self, session: Session) -> None:
        self.session = session
        self.dot.set_status(session.status)
        self.title_label.setText(session.title or "(untitled)")
        self.subtitle_label.setText(session.subtitle or "")
        pct_color = _context_color(session.context_pct)
        self.percent_label.setText(_format_pct(session.context_pct))
        self.percent_label.setStyleSheet(f"color: {pct_color.name()}; font-size: 12px;")
        self.progress.setValue(int(session.context_pct))
        self.progress.setStyleSheet(
            f"QProgressBar {{ background: rgba(255,255,255,0.08); border: none; height: 6px; border-radius: 3px; }}"
            f"QProgressBar::chunk {{ background-color: {pct_color.name()}; border-radius: 3px; }}"
        )

    def mousePressEvent(self, ev) -> None:
        if ev.button() == Qt.LeftButton:
            self.clicked.emit(self.session.id)
        super().mousePressEvent(ev)

    # ---- pairing state visual indicator ----
    def set_paired(self, paired: bool, title: str = "") -> None:
        """设置卡片右上角的"已配对"小圆点 + tooltip。"""
        if getattr(self, "_paired_dot", None) is None:
            self._init_paired_indicator()
        self._paired_dot.setVisible(paired)
        if paired:
            self.setToolTip(f"已配对 → {title}" if title else "已配对")
        else:
            self.setToolTip("")

    def _init_paired_indicator(self) -> None:
        # 小圆点叠在卡片右上角，亮黄表示已手动配对
        from PySide6.QtWidgets import QLabel
        self._paired_dot = QLabel("●", self)
        self._paired_dot.setStyleSheet(
            "color: #FACC15; font-size: 12px; background: transparent;"
        )
        self._paired_dot.setFixedSize(14, 14)
        self._paired_dot.move(self.width() - 16, 4)
        self._paired_dot.setVisible(False)

    def resizeEvent(self, ev) -> None:
        super().resizeEvent(ev)
        if getattr(self, "_paired_dot", None) is not None:
            self._paired_dot.move(self.width() - 16, 4)

    # ---- right-click context menu ----
    def contextMenuEvent(self, ev) -> None:
        _sid = self.session.id
        _cw_log("cm", f"enter sid={_sid} title={self.session.title!r} subtitle={self.session.subtitle!r}")
        # 通知主窗口：菜单要开了，leaveEvent 不要收
        _top = self.window()
        if hasattr(_top, "set_menu_open"):
            _top.set_menu_open(True)
        try:
            # parent 设成主窗口而不是 self（卡片）：
            # collector 每 2s 轮询会触发 _rebuild -> deleteLater() 卡片，
            # 卡片若作为菜单 parent 会被一起回收，Qt 自动 dismiss 弹出的菜单。
            menu = QMenu(_top)
            # 请求父组件按 session 过滤 + 查配对后回填终端列表
            self.listTerminalsRequested.emit(self.session)
            _cw_log(
                "cm",
                f"after listTerminalsRequested: terminals={len(self._terminals)} "
                f"fallback_to_all={self._fallback_to_all} paired_hwnd={self._paired_hwnd}",
            )

            if self._fallback_to_all:
                _hdr = menu.addAction(
                    f"（无匹配项，显示全部 {len(self._terminals)} 个终端）"
                )
                _hdr.setEnabled(False)
            else:
                _hdr = menu.addAction(
                    f"配对到终端（{len(self._terminals)} 个匹配）"
                )
                _hdr.setEnabled(False)
            menu.addSeparator()

            for t in self._terminals:
                _is_paired_here = (t["hwnd"] == self._paired_hwnd)
                _act = QAction(
                    _format_terminal_label(t, _is_paired_here, self._paired_hwnd),
                    menu,
                )
                _act.setCheckable(True)
                _act.setChecked(_is_paired_here)
                # 点击已勾选项：不重复配对，只关闭菜单（Qt 会自动 toggle checked，
                # 但 paired_hwnd 未变，下次打开菜单时勾选会恢复）
                # 点击未勾选项：触发配对
                if _is_paired_here:
                    _act.triggered.connect(lambda _checked=False: None)
                else:
                    _act.triggered.connect(
                        lambda _checked=False, tw=t: self.pairRequested.emit(
                            self.session.id, tw["hwnd"], tw["title"], tw["class"]
                        )
                    )
                _cw_log(
                    "cm",
                    f"  add item hwnd={t['hwnd']} pid={t['pid']} cls={t['class']} "
                    f"title={t['title'][:30]!r} paired={_is_paired_here}",
                )
                menu.addAction(_act)

            menu.addSeparator()
            # 取消配对
            if self._is_paired:
                _unpair = menu.addAction("取消配对")
                _unpair.triggered.connect(
                    lambda _checked=False: self.unpairRequested.emit(self.session.id)
                )
            _chosen = menu.exec(ev.globalPos())
            if _chosen is not None:
                # 用户选了某项（不包括 separator / header）
                _cw_log("cm", f"user picked: {_chosen.text()!r}")
            else:
                _cw_log("cm", f"menu closed without selection")
        finally:
            # 菜单关了，恢复 leaveEvent 行为；如鼠标仍在外则启动一次收起计时
            if hasattr(_top, "set_menu_open"):
                _top.set_menu_open(False)
            if hasattr(_top, "collapse_after_menu"):
                # 用 QTimer.singleShot 0 延后到事件循环下一拍，避免和 exec 退出事件打架
                QTimer.singleShot(0, _top.collapse_after_menu)

    def set_terminals(
        self,
        terminals: list[dict],
        fallback_to_all: bool,
        paired_hwnd: int | None,
        is_paired: bool,
    ) -> None:
        """由父组件在 listTerminalsRequested 后回调注入终端列表 + 元数据。"""
        self._terminals = list(terminals)
        self._fallback_to_all = bool(fallback_to_all)
        self._paired_hwnd = paired_hwnd
        self._is_paired = bool(is_paired)
        # 更新右上角小圆点
        _title = ""
        for _t in self._terminals:
            if _t["hwnd"] == self._paired_hwnd:
                _title = _t.get("title", "")
                break
        self.set_paired(self._is_paired, _title)