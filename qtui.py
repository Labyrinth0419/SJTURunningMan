import sys
import json
import os
import datetime
import time
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QTextEdit, QProgressBar, QFormLayout, QGroupBox, QDateTimeEdit,
    QMessageBox, QScrollArea, QSizePolicy, QCheckBox,
    QSpacerItem
)
from PySide6.QtCore import QThread, Signal, QDateTime, Qt, QUrl
from PySide6.QtGui import QTextCursor, QFont, QColor, QTextCharFormat, QPalette, QBrush, QIcon, QDesktopServices

from src.main import run_sports_upload
from src.utils import SportsUploaderError, get_base_path

# Minimal config support migrated here so file src/config_manager.py can be removed.
CONFIGS_DIR = os.path.join(get_base_path(), "configs")


from src.help_dialog import HelpDialog

RESOURCES_SUB_DIR = "assets"
CONFIGS_SUB_DIR = "configs"

RESOURCES_FULL_PATH = os.path.join(get_base_path(), RESOURCES_SUB_DIR)

class WorkerThread(QThread):
    """
    工作线程，用于在后台执行跑步数据上传任务，避免UI冻结。
    """
    progress_update = Signal(int, int, str)
    log_output = Signal(str, str)
    finished = Signal(bool, str)

    def __init__(self, config_data):
        super().__init__()
        self.config_data = config_data

    def run(self):
        success = False
        message = "任务已完成。"
        try:
            success, message = run_sports_upload(
                self.config_data,
                progress_callback=self.progress_callback,
                log_cb=self.log_callback,
                stop_check_cb=self.isInterruptionRequested
            )
        except SportsUploaderError as e:
            self.log_output.emit(f"任务中断: {e}", "error")
            message = str(e)
            success = False
        except Exception as e:
            self.log_output.emit(f"发生未预期的错误: {e}", "error")
            message = f"未预期的错误: {e}"
            success = False
        finally:
            if self.isInterruptionRequested() and not success:
                 self.finished.emit(False, "任务已手动终止。")
            else:
                 self.finished.emit(success, message)

    def progress_callback(self, current, total, message):
        self.progress_update.emit(current, total, message)

    def log_callback(self, message, level):
        self.log_output.emit(message, level)


class SportsUploaderUI(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("SJTU 体育跑步上传工具")
        self.setWindowIcon(QIcon(os.path.join(RESOURCES_FULL_PATH, "SJTURM.png")))

        self.thread = None
        self.config = {}

        self.setup_ui_style()
        self.init_ui()

        self.setGeometry(100, 100, 300, 500)
        self.setMinimumSize(300, 500)

        # 根据当前窗口宽度调整内容区域宽度
        self.adjust_content_width(self.width())

    def setup_ui_style(self):
        """设置UI的整体样式，改为白色背景和Fluent设计。"""
        palette = self.palette()
        palette.setColor(QPalette.Window, QColor(255, 255, 255))
        palette.setColor(QPalette.WindowText, QColor(30, 30, 30))
        palette.setColor(QPalette.Base, QColor(255, 255, 255))
        # 将 AlternateBase 设置为白色，移除灰色背景
        palette.setColor(QPalette.AlternateBase, QColor(255, 255, 255))
        palette.setColor(QPalette.ToolTipBase, QColor(255, 255, 255))
        palette.setColor(QPalette.ToolTipText, QColor(30, 30, 30))
        palette.setColor(QPalette.Text, QColor(30, 30, 30))
        # 使用白色按钮背景以避免灰色感
        palette.setColor(QPalette.Button, QColor(255, 255, 255))
        palette.setColor(QPalette.ButtonText, QColor(30, 30, 30))
        palette.setColor(QPalette.BrightText, QColor("red"))
        palette.setColor(QPalette.Link, QColor(0, 120, 212))
        palette.setColor(QPalette.Highlight, QColor(0, 120, 212))
        palette.setColor(QPalette.HighlightedText, QColor(255, 255, 255))
        self.setPalette(palette)

        self.setStyleSheet("""
            /* 强制全局背景为白色，移除任何灰色背景 */
            QWidget, QScrollArea, QGroupBox {
                background-color: rgb(255, 255, 255);
            }

            QGroupBox {
                font-size: 11pt;
                font-weight: bold;
                margin-top: 10px;
                border: 1px solid rgb(220, 220, 220);
                border-radius: 8px;
                padding-top: 20px;
                padding-bottom: 5px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top center;
                padding: 0 5px;
                color: rgb(0, 120, 212);
            }
            QLineEdit, QDateTimeEdit {
                background-color: rgb(255, 255, 255);
                border: 1px solid rgb(220, 220, 220);
                border-radius: 5px;
                padding: 5px;
                selection-background-color: rgb(0, 120, 212);
                color: rgb(30, 30, 30);
            }
            QDateTimeEdit::drop-down {
                subcontrol-origin: padding;
                subcontrol-position: top right;
                width: 20px;
                border-left-width: 1px;
                border-left-color: rgb(220, 220, 220);
                border-left-style: solid;
                border-top-right-radius: 5px;
                border-bottom-right-radius: 5px;
            }
            QPushButton {
                background-color: rgb(0, 120, 212);
                color: white;
                border-radius: 5px;
                padding: 8px 15px;
                font-weight: bold;
                min-height: 28px;
            }
            QPushButton:hover {
                background-color: rgb(0, 96, 173);
            }
            QPushButton:pressed {
                background-color: rgb(0, 77, 140);
            }
            QPushButton:disabled {
                /* 移除灰色背景，禁用状态使用白色背景并保持灰色文本以示区分 */
                background-color: rgb(255, 255, 255);
                color: rgb(106, 106, 106);
            }
            QProgressBar {
                border: 1px solid rgb(220, 220, 220);
                border-radius: 5px;
                text-align: center;
                /* 进度条背景改为白色，去掉灰色 */
                background-color: rgb(255, 255, 255);
                color: rgb(30, 30, 30);
            }
            QProgressBar::chunk {
                background-color: rgb(0, 120, 212);
                border-radius: 5px;
            }
            QTextEdit {
                background-color: rgb(255, 255, 255);
                border: 1px solid rgb(220, 220, 220);
                border-radius: 5px;
                padding: 5px;
                color: rgb(30, 30, 30);
            }
            QScrollArea {
                border: none;
            }
            QCheckBox {
                spacing: 5px;
                color: rgb(30, 30, 30);
            }
            QCheckBox::indicator {
                width: 16px;
                height: 16px;
                border-radius: 3px;
                border: 1px solid rgb(142, 142, 142);
                /* 去除略灰的背景色，使用白色 */
                background-color: rgb(255, 255, 255);
            }
            QCheckBox::indicator:checked {
                background-color: rgb(0, 120, 212);
                border: 1px solid rgb(0, 120, 212);
            }
            QCheckBox::indicator:disabled {
                border: 1px solid rgb(204, 204, 204);
                /* 去掉灰色背景，使用白色 */
                background-color: rgb(255, 255, 255);
            }
            QFormLayout QLabel {
                padding-top: 5px;
                padding-bottom: 5px;
            }
            #startButton {
                background-color: rgb(76, 175, 80);
            }
            #startButton:hover {
                background-color: rgb(67, 160, 71);
            }
            #startButton:pressed {
                background-color: rgb(56, 142, 60);
            }
            #stopButton {
                background-color: rgb(220, 53, 69);
                color: white;
            }
            #stopButton:hover {
                background-color: rgb(179, 43, 56);
            }
            #stopButton:pressed {
                background-color: rgb(140, 34, 44);
            }
            QLabel#getCookieLink {
                color: rgb(0, 120, 212);
                text-decoration: underline;
                padding: 0;
            }
            QLabel#getCookieLink:hover {
                color: rgb(0, 96, 173);
            }
        """)

    def init_ui(self):
        top_h_layout = QHBoxLayout()
        top_h_layout.setContentsMargins(0, 0, 0, 0)
        top_h_layout.setSpacing(0)

        self.center_widget = QWidget()
        main_layout = QVBoxLayout(self.center_widget)
        # 保留一点下边距（8px），其余边距为 0
        main_layout.setContentsMargins(0, 0, 0, 8)
        main_layout.setSpacing(0)

        self.scroll_area = QScrollArea()
        self.scroll_content = QWidget()
        scroll_layout = QVBoxLayout(self.scroll_content)
        # 去除滚动内容区域的外部空白
        scroll_layout.setContentsMargins(0, 0, 0, 0)
        scroll_layout.setSpacing(0)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setWidget(self.scroll_content)

        main_layout.addWidget(self.scroll_area)

        user_group = QGroupBox("用户配置")
        user_form_layout = QFormLayout()

        cookie_prompt_layout = QHBoxLayout()
        cookie_label = QLabel("Cookie:")
        get_cookie_link = QLabel('<a href="#" id="getCookieLink">获取</a>')
        get_cookie_link.setOpenExternalLinks(False)
        get_cookie_link.linkActivated.connect(self.open_cookie_help_url)

        cookie_prompt_layout.addWidget(cookie_label)
        cookie_prompt_layout.addWidget(get_cookie_link)
        cookie_prompt_layout.addStretch(1)

        cookie_container_widget = QWidget()
        cookie_container_widget.setLayout(cookie_prompt_layout)
        user_form_layout.addRow(cookie_container_widget)

        self.keepalive_input = QLineEdit()
        self.keepalive_input.setPlaceholderText("keepalive=... (从浏览器复制)")
        self.jsessionid_input = QLineEdit()
        self.jsessionid_input.setPlaceholderText("JSESSIONID=... (从浏览器复制)")

        user_form_layout.addRow("Keepalive:", self.keepalive_input)
        user_form_layout.addRow("JSESSIONID:", self.jsessionid_input)

        self.user_id_input = QLineEdit()
        self.user_id_input.setPlaceholderText("你的用户ID")
        user_form_layout.addRow("用户ID:", self.user_id_input)
        user_group.setLayout(user_form_layout)
        scroll_layout.addWidget(user_group)

        # 路线与参数由代码内部控制，不在 GUI 中显示

        time_group = QGroupBox("跑步时间配置")
        time_layout = QVBoxLayout()
        self.use_current_time_checkbox = QCheckBox("使用当前时间")
        self.use_current_time_checkbox.setChecked(True)
        self.use_current_time_checkbox.toggled.connect(self.toggle_time_input)

        self.start_datetime_input = QDateTimeEdit()
        self.start_datetime_input.setCalendarPopup(True)
        self.start_datetime_input.setDateTime(QDateTime.currentDateTime())
        self.start_datetime_input.setDisplayFormat("yyyy-MM-dd HH:mm:ss")
        self.start_datetime_input.setEnabled(False)

        time_layout.addWidget(self.use_current_time_checkbox)
        time_layout.addWidget(QLabel("或手动设置开始时间:"))
        time_layout.addWidget(self.start_datetime_input)
        time_group.setLayout(time_layout)
        scroll_layout.addWidget(time_group)

        # 配置保存/加载功能从界面移除

        action_button_layout = QHBoxLayout()
        self.start_button = QPushButton("开始上传")
        self.start_button.setObjectName("startButton")
        self.start_button.clicked.connect(self.start_upload)
        action_button_layout.addWidget(self.start_button)

        self.stop_button = QPushButton("停止")
        self.stop_button.setObjectName("stopButton")
        self.stop_button.setEnabled(False)
        self.stop_button.clicked.connect(self.stop_upload)
        action_button_layout.addWidget(self.stop_button)

        self.help_button = QPushButton("帮助")
        self.help_button.clicked.connect(self.show_help_dialog)
        action_button_layout.addWidget(self.help_button)

        scroll_layout.addLayout(action_button_layout)

        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        scroll_layout.addWidget(self.progress_bar)

        self.status_label = QLabel("状态: 待命")
        scroll_layout.addWidget(self.status_label)
        self.log_output_area = QTextEdit()
        self.log_output_area.setReadOnly(True)
        self.log_output_area.setFont(QFont("Monospace", 9))
        self.log_output_area.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        scroll_layout.addWidget(self.log_output_area)

        # 直接将 center_widget 加入布局，移除左右的 spacer 以消除外部空白
        top_h_layout.addWidget(self.center_widget)

        self.setLayout(top_h_layout)

    def resizeEvent(self, event):
        """
        槽函数，用于处理窗口大小调整事件。
        根据窗口宽度调整内部内容区域的最大宽度。
        """
        super().resizeEvent(event)
        self.adjust_content_width(event.size().width())

    def adjust_content_width(self, window_width):
        """
        根据给定的窗口宽度，计算并设置 center_widget 的固定宽度。
        """
        # 不强制很大的最小宽度，使用窗口宽度的 90% 或最大 600 的限制
        calculated_width = int(min(window_width * 0.9, 600))
        # 保证最小为 280，以适配窄窗口（比如 300px）
        calculated_width = max(280, calculated_width)
        self.center_widget.setFixedWidth(calculated_width)

    def toggle_time_input(self, checked):
        """根据QCheckBox状态切换时间输入框的启用/禁用状态"""
        self.start_datetime_input.setEnabled(not checked)
        if checked:
            self.start_datetime_input.setDateTime(QDateTime.currentDateTime())

    def open_cookie_help_url(self):
        """打开获取 Cookie 的帮助页面链接"""
        QDesktopServices.openUrl(QUrl("https://pe.sjtu.edu.cn/phone/#/indexPortrait"))


    def load_settings_to_ui(self, filename):
        self.setWindowTitle(f"SJTU 体育跑步上传工具 - [{os.path.basename(filename)}]")

        full_cookie = self.config.get("COOKIE", "")
        keepalive_val = ""
        jsessionid_val = ""
        parts = full_cookie.split(';')
        for part in parts:
            part = part.strip()
            if part.startswith("keepalive="):
                keepalive_val = part.replace("keepalive=", "")
            elif part.startswith("JSESSIONID="):
                jsessionid_val = part.replace("JSESSIONID=", "")

            self.keepalive_input.setText(keepalive_val)
            self.jsessionid_input.setText(jsessionid_val)
            self.user_id_input.setText(self.config.get("USER_ID", ""))

        start_time_ms = self.config.get("START_TIME_EPOCH_MS", None)
        if start_time_ms is not None:
            dt = QDateTime.fromMSecsSinceEpoch(start_time_ms)
            self.start_datetime_input.setDateTime(dt)
            self.use_current_time_checkbox.setChecked(False)
            self.start_datetime_input.setEnabled(True)
        else:
            self.use_current_time_checkbox.setChecked(True)
            self.start_datetime_input.setEnabled(False)
            self.start_datetime_input.setDateTime(QDateTime.currentDateTime())

    def get_settings_from_ui(self):
        """从UI获取当前配置并返回字典"""
        try:
            keepalive = self.keepalive_input.text().strip()
            jsessionid = self.jsessionid_input.text().strip()
            combined_cookie = ""
            if keepalive:
                combined_cookie += f"keepalive={keepalive}"
            if jsessionid:
                if combined_cookie:
                    combined_cookie += "; "
                combined_cookie += f"JSESSIONID={jsessionid}"

            current_config = {
                "COOKIE": combined_cookie,
                "USER_ID": self.user_id_input.text(),
                "START_LATITUDE": float(self.config.get("START_LATITUDE", 31.031599)),
                "START_LONGITUDE": float(self.config.get("START_LONGITUDE", 121.442938)),
                "END_LATITUDE": float(self.config.get("END_LATITUDE", 31.0264)),
                "END_LONGITUDE": float(self.config.get("END_LONGITUDE", 121.4551)),
                "RUNNING_SPEED_MPS": round(1000.0 / (3.5 * 60), 3),
                "INTERVAL_SECONDS": int(self.config.get("INTERVAL_SECONDS", 3)),
                "HOST": "pe.sjtu.edu.cn",
                "UID_URL": "https://pe.sjtu.edu.cn/sports/my/uid",
                "MY_DATA_URL": "https://pe.sjtu.edu.cn/sports/my/data",
                "POINT_RULE_URL": "https://pe.sjtu.edu.cn/api/running/point-rule",
                "UPLOAD_URL": "https://pe.sjtu.edu.cn/api/running/result/upload"
            }

            if self.use_current_time_checkbox.isChecked():
                current_config["START_TIME_EPOCH_MS"] = None
            else:
                current_config["START_TIME_EPOCH_MS"] = self.start_datetime_input.dateTime().toMSecsSinceEpoch()

            if not current_config["COOKIE"] or not current_config["USER_ID"]:
                raise ValueError("Cookie (keepalive 和 JSESSIONID) 和 用户ID 不能为空。")

            return current_config

        except ValueError as e:
            raise ValueError(f"输入错误: {e}")
        except Exception as e:
            raise Exception(f"获取配置时发生未知错误: {e}")

    def start_upload(self):
        self.log_output_area.clear()
        self.progress_bar.setValue(0)
        self.status_label.setText("状态: 准备中...")
        self.log_output_text("准备开始上传...", "info")

        try:
            current_config_to_send = self.get_settings_from_ui()
        except (ValueError, Exception) as e:
            self.log_output_text(f"配置错误: {e}", "error")
            self.status_label.setText("状态: 错误")
            QMessageBox.critical(self, "配置错误", str(e))
            return

        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.use_current_time_checkbox.setEnabled(False)
        self.start_datetime_input.setEnabled(False)
        self.help_button.setEnabled(False)
        self.keepalive_input.setEnabled(False)
        self.jsessionid_input.setEnabled(False)
        self.user_id_input.setEnabled(False)

        self.thread = WorkerThread(current_config_to_send)
        self.thread.progress_update.connect(self.update_progress)
        self.thread.log_output.connect(self.log_output_text)
        self.thread.finished.connect(self.upload_finished)
        self.thread.start()

    def stop_upload(self):
        """请求工作线程停止。"""
        if self.thread and self.thread.isRunning():
            self.thread.requestInterruption()
            self.log_output_text("已发送停止请求，请等待任务清理并退出...", "warning")
            self.stop_button.setEnabled(False)
            self.status_label.setText("状态: 正在停止...")
        else:
            self.log_output_text("没有运行中的任务可以停止。", "info")


    def update_progress(self, current, total, message):
        """更新进度条和状态信息"""
        self.progress_bar.setMaximum(total)
        self.progress_bar.setValue(current)
        self.status_label.setText(f"状态: {message}")

    def log_output_text(self, message, level="info"):
        """将日志信息添加到文本区域，并根据级别着色"""
        cursor = self.log_output_area.textCursor()
        cursor.movePosition(QTextCursor.End)

        format = QTextCharFormat()
        if level == "error":
            format.setForeground(QColor("red"))
        elif level == "warning":
            format.setForeground(QColor("#FFA500"))
        elif level == "success":
            format.setForeground(QColor("green"))
        else:
            format.setForeground(QColor("#1e1e1e"))

        cursor.insertText(f"[{level.upper()}] {message}\n", format)
        self.log_output_area.ensureCursorVisible()

    def upload_finished(self, success, message):
        """上传任务完成后的处理"""
        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self.use_current_time_checkbox.setEnabled(True)
        self.start_datetime_input.setEnabled(not self.use_current_time_checkbox.isChecked())
        self.help_button.setEnabled(True)
        self.keepalive_input.setEnabled(True)
        self.jsessionid_input.setEnabled(True)
        self.user_id_input.setEnabled(True)

        self.progress_bar.setValue(100)

        if success:
            self.status_label.setText("状态: 上传成功！")
            self.log_output_text(f"操作完成: {message}", "success")
            QMessageBox.information(self, "上传结果", message)
        else:
            self.status_label.setText("状态: 上传失败！")
            self.log_output_text(f"操作失败: {message}", "error")
            QMessageBox.critical(self, "上传结果", f"上传失败: {message}")

        self.thread = None

    def show_help_dialog(self):
        """显示帮助对话框。"""
        help_dialog = HelpDialog(self, markdown_relative_path=os.path.join(RESOURCES_SUB_DIR, "help.md"))
        help_dialog.exec()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    ui = SportsUploaderUI()
    ui.show()
    sys.exit(app.exec())