#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Photonizer: 수동 이미지 분류 프로그램 (Python + PySide6)

요구사항 요약
- 중앙에 현재 이미지를 보여주는 GUI 뷰어 (작으면 확대, 크면 축소, 비율 유지)
- jpg, png, gif, webp 지원 (애니메이션 gif/webp도 가능한 한 지원)
- 프로그램과 같은 폴더의 targets.txt에서 입력을 읽어옴
    * 첫 번째 유효한 라인: 분류 대상 이미지 폴더 (source)
    * 이후 라인들: "단축키 = 이동대상폴더" 형식 (구분자는 =, :, ->, 탭 등 다양하게 허용)
- 우측에 단축키와 폴더 목록을 안내
- 단축키를 누르면 현재 이미지를 해당 폴더로 순수 파일 이동(shutil.move)
- z 키로 마지막 이동을 되돌리기(원위치) 및 되돌린 이미지를 현재 타겟으로 설정
- 메타데이터 손상 없이 파일만 이동 (파일 내용 가공 없음)

사용법
1) Python 3.9+ 권장. 의존성 설치:
   pip install PySide6

2) 스크립트와 같은 폴더에 targets.txt 생성. 예시:
   ----------------------------------------
   # 첫 유효 라인은 소스 폴더 (상대/절대 경로 모두 가능)
   ./inbox

   # 이후는 "키 = 폴더" 형식 (구분자 '=', ':', '->', 탭, 공백 하나 등 허용)
   a = ./cats
   s: ./dogs
   d -> ./others
   1	./numbers
   ----------------------------------------
   주의: 'z' 키는 되돌리기(Undo)로 예약됨.

3) 실행:
   python photonizer.py

메모
- Animated WebP 지원 여부는 설치된 Qt(이미지 플러그인)에 따라 달라질 수 있습니다.
  Qt가 애니메이션 WebP를 지원하지 않는 경우, 첫 프레임 정지 이미지로 표시됩니다.
"""

from __future__ import annotations
import os
import sys
import shutil
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from PySide6.QtCore import Qt, QSize, QTimer
from PySide6.QtGui import QPixmap, QImageReader, QKeySequence, QAction, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QLabel,
    QHBoxLayout,
    QVBoxLayout,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QMessageBox,
    QFileDialog,
    QSplitter,
    QStatusBar,
    QAbstractItemView,
)
from PySide6.QtGui import QMovie

SUPPORTED_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
RESERVED_KEYS = {"z"}


def human_path(p: Path, base: Path) -> str:
    try:
        return str(p.relative_to(base))
    except Exception:
        return str(p)


def fit_size(content: QSize, box: QSize) -> QSize:
    """content(원본)와 box(라벨 크기)를 받아, 비율을 유지하며 box에 맞게 축소/확대한 크기 반환"""
    if content.width() <= 0 or content.height() <= 0 or box.width() <= 0 or box.height() <= 0:
        return QSize(0, 0)
    rw = box.width() / content.width()
    rh = box.height() / content.height()
    r = min(rw, rh)
    return QSize(max(1, int(content.width() * r)), max(1, int(content.height() * r)))


@dataclass
class Target:
    key: str
    dir: Path


class ScaledImageLabel(QLabel):
    """애니메이션/정지 이미지 모두를 지원하는 스케일 라벨"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAlignment(Qt.AlignCenter)
        self.setMinimumSize(200, 200)
        self._orig_pixmap: Optional[QPixmap] = None
        self._movie: Optional[QMovie] = None
        self._current_path: Optional[Path] = None

    def clear_content(self):
        if self._movie:
            self._movie.stop()
            self._movie.deleteLater()
        self._movie = None
        self._orig_pixmap = None
        self.setMovie(None)
        self.setPixmap(QPixmap())

    def show_image(self, path: Path):
        self._current_path = path
        self.clear_content()

        suffix = path.suffix.lower()
        if suffix in {".gif", ".webp"}:
            # 애니메이션 우선 시도(QMovie). 지원 안하면 정지로 fallback
            movie = QMovie(str(path))
            if movie.isValid():
                self._movie = movie
                # 첫 프레임 사이즈 기반으로 스케일
                movie.jumpToFrame(0)
                target = fit_size(movie.currentImage().size(), self.size())
                if target.width() > 0 and target.height() > 0:
                    movie.setScaledSize(target)
                self.setMovie(movie)
                movie.start()
                return
            # fallback to static

        # 정지 이미지 로딩(QImageReader, EXIF 회전 자동 적용)
        reader = QImageReader(str(path))
        reader.setAutoTransform(True)
        image = reader.read()
        if image.isNull():
            self.setText("이미지를 불러올 수 없습니다:\n" + str(path))
            return
        pm = QPixmap.fromImage(image)
        self._orig_pixmap = pm
        scaled = pm.scaled(self.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.setPixmap(scaled)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._movie:
            # 현재 프레임 기준으로 적정 크기 재계산
            frame_size = self._movie.currentImage().size()
            if frame_size.isValid():
                target = fit_size(frame_size, self.size())
                if target.width() > 0 and target.height() > 0:
                    self._movie.setScaledSize(target)
        elif self._orig_pixmap:
            scaled = self._orig_pixmap.scaled(self.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.setPixmap(scaled)


class Photonizer(QMainWindow):
    def __init__(self, base_dir: Path):
        super().__init__()
        self.base_dir = base_dir
        self.setWindowTitle("Photonizer beta")
        self.resize(1200, 800)

        # 상태
        self.source_dir: Path = base_dir
        self.targets: Dict[str, Target] = {}
        self.images: List[Path] = []
        self.index: int = 0
        self.history: List[Tuple[Path, Path]] = []  # (original_path, moved_to_path)

        # UI
        self.viewer = ScaledImageLabel()
        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["키", "대상 폴더"])
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionMode(QAbstractItemView.NoSelection)
        self.table.setFocusPolicy(Qt.NoFocus)

        right_box = QVBoxLayout()
        right_box.addWidget(QLabel("이동 대상 (단축키 → 폴더)"))
        right_box.addWidget(self.table)
        right_widget = QWidget()
        right_widget.setLayout(right_box)

        splitter = QSplitter()
        splitter.addWidget(self.viewer)
        splitter.addWidget(right_widget)
        splitter.setSizes([900, 300])
        self.setCentralWidget(splitter)

        self.status = QStatusBar()
        self.setStatusBar(self.status)

        # 메뉴/액션(옵션)
        open_action = QAction("다른 targets.txt 열기...", self)
        open_action.triggered.connect(self.open_targets_dialog)
        self.menuBar().addAction(open_action)

        # targets.txt 로드 & 단축키 준비
        try:
            self.load_from_targets_file(self.base_dir / "targets.txt")
        except Exception as e:
            QMessageBox.critical(self, "targets.txt 오류", f"targets.txt 로딩 중 오류:\n{e}")

        self.refresh_table()
        self.load_images()
        self.update_view()

        # Undo (z)
        QShortcut(QKeySequence("Z"), self, activated=self.undo_last)

    # ---------------------- 설정/입력 ----------------------
    def open_targets_dialog(self):
        path, _ = QFileDialog.getOpenFileName(self, "targets.txt 선택", str(self.base_dir), "Text Files (*.txt)")
        if not path:
            return
        try:
            self.load_from_targets_file(Path(path))
            self.refresh_table()
            self.load_images()
            self.index = 0
            self.history.clear()
            self.update_view()
        except Exception as e:
            QMessageBox.critical(self, "오류", f"불러오기 실패:\n{e}")

    def load_from_targets_file(self, path: Path):
        if not path.exists():
            raise FileNotFoundError(f"{path} 가 없습니다. 같은 폴더에 targets.txt를 만들어 주세요.")

        src_dir: Optional[Path] = None
        mappings: Dict[str, Path] = {}

        with path.open("r", encoding="utf-8") as f:
            lines = [ln.strip() for ln in f.readlines()]

        def is_valid_line(ln: str) -> bool:
            return bool(ln) and not ln.startswith("#")

        # 첫 유효 라인 = source
        i = 0
        while i < len(lines) and not is_valid_line(lines[i]):
            i += 1
        if i >= len(lines):
            raise ValueError("targets.txt에 유효한 라인이 없습니다.")
        raw_source = lines[i]
        src_dir = (self.base_dir / raw_source).expanduser().resolve() if not os.path.isabs(raw_source) else Path(raw_source).expanduser().resolve()
        i += 1

        # 이후 = key->dir
        for ln in lines[i:]:
            if not is_valid_line(ln):
                continue
            # 주석 절단
            ln = ln.split("#", 1)[0].strip()
            if not ln:
                continue

            key: Optional[str] = None
            folder: Optional[str] = None

            # 다양한 구분자 허용
            patterns = [r"^([^\s=:\->\t]+)\s*->\s*(.+)$",   # a -> path
                        r"^([^\s=:\t]+)\s*[:=]\s*(.+)$",    # a = path, a: path
                        r"^([^\s\t])\s+(.+)$",              # a path
                        r"^([^\s\t])\t(.+)$"]               # a\tpath
            for pat in patterns:
                m = re.match(pat, ln)
                if m:
                    key, folder = m.group(1).strip(), m.group(2).strip()
                    break
            if not key or not folder:
                raise ValueError(f"형식을 해석할 수 없습니다: {ln}")
            if len(key) != 1:
                raise ValueError(f"단축키는 한 글자여야 합니다: {key}")
            if key.lower() in RESERVED_KEYS:
                raise ValueError(f"'{key}' 키는 예약되어 있습니다(되돌리기). 다른 키를 사용하세요.")

            target_dir = (self.base_dir / folder).expanduser() if not os.path.isabs(folder) else Path(folder).expanduser()
            target_dir = target_dir.resolve()
            mappings[key.lower()] = target_dir

        if not src_dir.exists() or not src_dir.is_dir():
            raise NotADirectoryError(f"소스 폴더가 올바르지 않습니다: {src_dir}")

        # 폴더 생성(없으면)
        for d in mappings.values():
            d.mkdir(parents=True, exist_ok=True)

        self.source_dir = src_dir
        self.targets = {k: Target(k, v) for k, v in mappings.items()}

        # 단축키 갱신
        self.install_target_shortcuts()

    def install_target_shortcuts(self):
        # 기존 shortcut은 Qt가 알아서 GC하지만, 참조 유지를 위해 self에 보관
        if not hasattr(self, "_shortcuts"):
            self._shortcuts: List[QShortcut] = []
        for sc in getattr(self, "_shortcuts", []):
            sc.setParent(None)
        self._shortcuts = []

        for key, tgt in self.targets.items():
            sc = QShortcut(QKeySequence(key.upper()), self)
            sc.activated.connect(lambda k=key: self.move_current_to(k))
            self._shortcuts.append(sc)

    # ---------------------- 이미지 리스트/표시 ----------------------
    def load_images(self):
        self.images = []
        for entry in sorted(self.source_dir.iterdir()):
            if not entry.is_file():
                continue
            if entry.suffix.lower() in SUPPORTED_EXTS:
                self.images.append(entry.resolve())
        self.index = 0

    def update_view(self):
        if not self.images:
            self.viewer.clear_content()
            self.viewer.setText("분류할 이미지가 없습니다.\n소스: " + str(self.source_dir))
            self.status.showMessage("0 / 0")
            return
        if self.index < 0:
            self.index = 0
        if self.index >= len(self.images):
            self.index = len(self.images) - 1
        current = self.images[self.index]
        self.viewer.show_image(current)
        self.status.showMessage(f"[{self.index + 1} / {len(self.images)}]  —  {current.name}")

    # ---------------------- 이동/되돌리기 ----------------------
    def move_current_to(self, key: str):
        if not self.images:
            return
        if key not in self.targets:
            return
        src_path = self.images[self.index]
        tgt_dir = self.targets[key].dir
        dst_path = tgt_dir / src_path.name

        try:
            # 충돌 시, 고유한 이름 생성
            final_dst = self._unique_path(dst_path)
            shutil.move(str(src_path), str(final_dst))  # 순수 이동
            self.history.append((src_path, final_dst))

            # 리스트에서 제거 및 다음 이미지 표시
            del self.images[self.index]
            if self.index >= len(self.images):
                self.index = len(self.images) - 1
            # self.update_view()
            # self.status.showMessage(f"이동: {src_path.name} → {human_path(final_dst, self.base_dir)}")
            self.update_view()
            count_str = f"{self.index + 1} / {len(self.images)}" if self.images else "0 / 0"
            self.status.showMessage(f"[{count_str}] 이동: {src_path.name} → {human_path(final_dst, self.base_dir)}")

        except Exception as e:
            QMessageBox.critical(self, "이동 실패", f"파일 이동 중 오류:\n{e}")

    def _unique_path(self, path: Path) -> Path:
        if not path.exists():
            return path
        stem = path.stem
        suffix = path.suffix
        i = 1
        while True:
            cand = path.with_name(f"{stem} ({i}){suffix}")
            if not cand.exists():
                return cand
            i += 1

    def undo_last(self):
        if not self.history:
            self.status.showMessage("되돌릴 항목이 없습니다.")
            return
        orig, moved = self.history.pop()
        try:
            back_path = orig
            if back_path.exists():
                # 드물게 같은 이름이 새로 생겼다면 충돌 회피
                back_path = self._unique_path(back_path)
            shutil.move(str(moved), str(back_path))

            # 현재 위치에 되돌린 파일을 삽입하고 그걸 보이도록 함
            insert_at = max(0, self.index)
            self.images.insert(insert_at, back_path)
            self.index = insert_at
            self.update_view()
            count_str = f"{self.index + 1} / {len(self.images)}" if self.images else "0 / 0"
            self.status.showMessage(f"[{count_str}] 되돌림: {human_path(moved, self.base_dir)} → {human_path(back_path, self.base_dir)}")

        except Exception as e:
            QMessageBox.critical(self, "되돌리기 실패", f"이동 되돌리기 중 오류:\n{e}")

    # ---------------------- 우측 테이블 ----------------------
    def refresh_table(self):
        self.table.setRowCount(0)
        for key in sorted(self.targets.keys()):
            tgt = self.targets[key]
            row = self.table.rowCount()
            self.table.insertRow(row)
            self.table.setItem(row, 0, QTableWidgetItem(key))
            self.table.setItem(row, 1, QTableWidgetItem(human_path(tgt.dir, self.base_dir)))
        self.table.resizeRowsToContents()


def main():
    app = QApplication(sys.argv)
    base_dir = Path(__file__).resolve().parent
    win = Photonizer(base_dir)
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
