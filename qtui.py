import sys
import os
import re
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QTextEdit, QProgressBar, QFormLayout, QGroupBox, QDateTimeEdit,
    QMessageBox, QScrollArea, QSizePolicy, QCheckBox,
    QSpacerItem
)
from PySide6.QtCore import QThread, Signal, QDateTime, Qt, QUrl, QEvent
from PySide6.QtGui import QTextCursor, QFont, QColor, QTextCharFormat, QPalette, QBrush, QIcon, QDesktopServices

from src.main import run_sports_upload
import src.login as login
from utils.auxiliary_util import SportsUploaderError, get_base_path
import src.config as config


from src.info_dialog import HelpWidget

RESOURCES_SUB_DIR = "assets"

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
        self.setWindowTitle("SJTU 校园轻松跑 - Version " + config.global_version)
        self.setWindowIcon(QIcon(os.path.join(RESOURCES_FULL_PATH, "SJTURM.png")))

        # 后台线程引用（私有）
        self._thread = None
        # 关于窗口引用，防止被垃圾回收
        self._help_window = None

        self.config = {}

        self.setup_ui_style()
        self.init_ui()

        self.setGeometry(300, 100, 380, 500)
        self.setMinimumSize(380, 500)

        # 根据当前窗口宽度调整内容区域宽度
        self.adjust_content_width(self.width())
        # 启动时居中主窗口
        try:
            self.center_window()
        except Exception:
            pass

    def setup_ui_style(self):
        palette = self.palette()
        palette.setColor(QPalette.Window, QColor(255, 255, 255))
        palette.setColor(QPalette.WindowText, QColor(51, 51, 51))
        palette.setColor(QPalette.Base, QColor(255, 255, 255))
        palette.setColor(QPalette.AlternateBase, QColor(255, 255, 255))
        palette.setColor(QPalette.ToolTipBase, QColor(255, 255, 255))
        palette.setColor(QPalette.ToolTipText, QColor(51, 51, 51))
        palette.setColor(QPalette.Text, QColor(51, 51, 51))
        palette.setColor(QPalette.Button, QColor(255, 255, 255))
        palette.setColor(QPalette.ButtonText, QColor(51, 51, 51))
        palette.setColor(QPalette.BrightText, QColor("red"))
        palette.setColor(QPalette.Link, QColor(74, 144, 226))
        palette.setColor(QPalette.Highlight, QColor(74, 144, 226))
        palette.setColor(QPalette.HighlightedText, QColor(255, 255, 255))
        self.setPalette(palette)

        self.setStyleSheet("""
            QWidget, QScrollArea, QGroupBox {
                background-color: rgb(255, 255, 255);
            }

            QGroupBox {
                font-size: 12pt;
                font-weight: bold;
                margin-top: 15px;
                border: 1px solid rgb(220, 220, 220);
                border-radius: 6px;
                padding-top: 25px;
                padding-bottom: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top center;
                padding: 0 8px;
                color: rgb(74, 144, 226);
            }
            QLineEdit, QDateTimeEdit {
                background-color: rgb(255, 255, 255);
                border: 1px solid rgb(204, 204, 204);
                border-radius: 4px;
                padding: 8px;
                selection-background-color: rgb(74, 144, 226);
                color: rgb(51, 51, 51);
            }
            QLineEdit:focus, QDateTimeEdit:focus {
                border: 1px solid rgb(74, 144, 226);
            }
            QDateTimeEdit::drop-down {
                subcontrol-origin: padding;
                subcontrol-position: top right;
                width: 20px;
                border-left-width: 1px;
                border-left-color: rgb(204, 204, 204);
                border-left-style: solid;
                border-top-right-radius: 4px;
                border-bottom-right-radius: 4px;
            }
            QPushButton {
                background-color: rgb(255, 255, 255);
                color: rgb(51, 51, 51);
                border: 1px solid rgb(204, 204, 204);
                border-radius: 4px;
                padding: 8px 16px;
                min-height: 24px;
                max-height: 36px;
            }
            QPushButton:hover {
                border: 1px solid rgb(74, 144, 226);
                background-color: rgb(250, 250, 250);
            }
            QPushButton:pressed {
                background-color: rgb(240, 240, 240);
            }
            QPushButton:disabled {
                background-color: rgb(255, 255, 255);
                color: rgb(180, 180, 180);
                border: 1px solid rgb(230, 230, 230);
            }
            QProgressBar {
                border: 1px solid rgb(220, 220, 220);
                border-radius: 4px;
                text-align: center;
                background-color: rgb(255, 255, 255);
                color: rgb(51, 51, 51);
                max-height: 20px;
            }
            QProgressBar::chunk {
                background-color: rgb(74, 144, 226);
                border-radius: 4px;
            }
            QTextEdit {
                background-color: rgb(245, 245, 247);
                border: 1px solid rgb(220, 220, 220);
                border-radius: 4px;
                padding: 8px;
                color: rgb(51, 51, 51);
            }
            QScrollArea {
                border: none;
            }
            QCheckBox {
                spacing: 5px;
                color: rgb(51, 51, 51);
            }
            QCheckBox::indicator {
                width: 16px;
                height: 16px;
                border-radius: 3px;
                border: 1px solid rgb(204, 204, 204);
                background-color: rgb(255, 255, 255);
            }
            QCheckBox::indicator:checked {
                background-color: rgb(74, 144, 226);
                border: 1px solid rgb(74, 144, 226);
            }
            QCheckBox::indicator:disabled {
                border: 1px solid rgb(230, 230, 230);
                background-color: rgb(255, 255, 255);
            }
            QFormLayout QLabel {
                padding-top: 8px;
                padding-bottom: 8px;
                color: rgb(102, 102, 102);
            }
            #startButton {
                background-color: rgb(76, 175, 80);
                color: white;
                border: 1px solid rgb(76, 175, 80);
            }
            #startButton:hover {
                background-color: rgb(67, 160, 71);
                border: 1px solid rgb(67, 160, 71);
            }
            #startButton:pressed {
                background-color: rgb(56, 142, 60);
            }
            #stopButton {
                background-color: rgb(220, 53, 69);
                color: white;
                border: 1px solid rgb(220, 53, 69);
            }
            #stopButton:hover {
                background-color: rgb(179, 43, 56);
                border: 1px solid rgb(179, 43, 56);
            }
            #stopButton:pressed {
                background-color: rgb(140, 34, 44);
            }
            QLabel#getCookieLink {
                color: rgb(74, 144, 226);
                text-decoration: underline;
                padding: 0;
            }
            QLabel#getCookieLink:hover {
                color: rgb(52, 120, 198);
            }
        """)

    def init_ui(self):
        top_h_layout = QHBoxLayout()
        top_h_layout.setContentsMargins(20, 20, 20, 20)
        top_h_layout.setSpacing(0)

        self.center_widget = QWidget()
        main_layout = QVBoxLayout(self.center_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        self.scroll_area = QScrollArea()
        self.scroll_content = QWidget()
        scroll_layout = QVBoxLayout(self.scroll_content)
        scroll_layout.setContentsMargins(0, 0, 0, 0)
        scroll_layout.setSpacing(20)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setWidget(self.scroll_content)

        main_layout.addWidget(self.scroll_area)

        user_group = QGroupBox("用户配置")
        user_form_layout = QFormLayout()
        user_form_layout.setVerticalSpacing(15)
        user_form_layout.setContentsMargins(15, 15, 15, 15)

        self.username_input = QLineEdit()
        self.username_input.setPlaceholderText("Jaccount用户名")
        self.password_input = QLineEdit()
        self.password_input.setPlaceholderText("密码")
        self.password_input.setEchoMode(QLineEdit.Password)

        user_form_layout.addRow("用户名:", self.username_input)
        user_form_layout.addRow("密码:", self.password_input)
        user_group.setLayout(user_form_layout)
        scroll_layout.addWidget(user_group)

        action_button_layout = QHBoxLayout()
        action_button_layout.setSpacing(12)
        self.start_button = QPushButton("一键跑步")
        self.start_button.setObjectName("startButton")
        self.start_button.clicked.connect(self.start_upload)
        action_button_layout.addWidget(self.start_button)

        self.stop_button = QPushButton("停止")
        self.stop_button.setObjectName("stopButton")
        self.stop_button.setEnabled(False)
        self.stop_button.clicked.connect(self.stop_upload)
        action_button_layout.addWidget(self.stop_button)

        self.info_button = QPushButton("关于")
        self.info_button.clicked.connect(self.show_info_dialog)
        action_button_layout.addWidget(self.info_button)

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

    def center_window(self):
        """将主窗口居中到主显示器的可用区域中心。"""
        try:
            screen = QApplication.primaryScreen()
            if screen is None:
                return
            available = screen.availableGeometry()

            fg = self.frameGeometry()
            fg.moveCenter(available.center())
            self.move(fg.topLeft())
        except Exception:
            return

    def get_settings_from_ui(self):
        """从UI获取当前配置并返回字典"""
        try:
            username = self.username_input.text().strip()
            password = self.password_input.text()

            current_config = {
                "USER_ID": username,
                "PASSWORD": password,
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

            # START_TIME_EPOCH_MS 由后端生成，不从 UI 获取

            if not current_config["USER_ID"] or not current_config["PASSWORD"]:
                raise ValueError("用户名和密码不能为空。")

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
            return

        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.info_button.setEnabled(False)
        self.username_input.setEnabled(False)
        self.password_input.setEnabled(False)

        # 调用 login.py 获取 session，使用 UI 中的用户名/密码
        try:
            username = current_config_to_send.get("USER_ID")
            password = current_config_to_send.get("PASSWORD")
            session = login.login(username, password)
            current_config_to_send["SESSION"] = session
            # USER_ID 即 Jaccount 用户名
            current_config_to_send["USER_ID"] = username
        except Exception as e:
            self.log_output_text(f"登录失败: {e}", "error")
            QMessageBox.critical(self, "登录失败", str(e))
            self.start_button.setEnabled(True)
            self.stop_button.setEnabled(False)
            self.username_input.setEnabled(True)
            self.password_input.setEnabled(True)
            self.info_button.setEnabled(True)
            return

        self._thread = WorkerThread(current_config_to_send)
        self._thread.progress_update.connect(self.update_progress)
        self._thread.log_output.connect(self.log_output_text)
        self._thread.finished.connect(self.upload_finished)
        self._thread.start()

    def stop_upload(self):
        """请求工作线程停止。"""
        if self._thread and self._thread.isRunning():
            self._thread.requestInterruption()
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
            format.setForeground(QColor("#DC3545"))
        elif level == "warning":
            format.setForeground(QColor("#FFA500"))
        elif level == "success":
            format.setForeground(QColor("#4CAF50"))
        else:
            format.setForeground(QColor("#333333"))

        # 如果是进度类短消息（例如: 已完成1/25），尝试替换最后一行以便在同一行更新
        try:
            if re.match(r"^已完成\d+/\d+", message):
                # 选择最后一段文本（最后一个 block）并检查是否包含“已完成”关键词
                doc = self.log_output_area.document()
                last_block = doc.lastBlock()
                if last_block.isValid() and "已完成" in last_block.text():
                    # 选中最后一个 block 并替换
                    cursor.movePosition(QTextCursor.End)
                    cursor.select(QTextCursor.BlockUnderCursor)
                    cursor.removeSelectedText()
                    # 插入新的进度信息（不额外换行），随后插入换行字符
                    cursor.insertText(f"[{level.upper()}] {message}\n", format)
                    self.log_output_area.ensureCursorVisible()
                    return
        except Exception:
            # 如果替换失败，退回到普通追加方式
            pass

        cursor.insertText(f"[{level.upper()}] {message}\n", format)
        self.log_output_area.ensureCursorVisible()

    def upload_finished(self, success, message):
        """上传任务完成后的处理"""
        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self.info_button.setEnabled(True)
        self.username_input.setEnabled(True)
        self.password_input.setEnabled(True)

        self.progress_bar.setValue(100)

        if success:
            self.status_label.setText("状态: 上传成功！")
            self.log_output_text(f"操作完成: {message}", "success")
            QMessageBox.information(self, "上传结果", message)
        else:
            self.status_label.setText("状态: 上传失败！")
            self.log_output_text(f"操作失败: {message}", "error")

        self._thread = None


    def show_info_dialog(self):
        """显示关于对话框（非模态）。

        使用 HelpWidget，作为非模态窗口显示，并保留对实例的引用以防止被垃圾回收。
        当窗口关闭时清理引用。
        """
        try:
            # 如果已有关于窗口实例：
            # - 若窗口仍可见，则激活并返回；
            # - 若已被隐藏/关闭但引用未清理，则清理引用并继续创建新的实例
            existing = getattr(self, "_help_window", None)
            if existing is not None:
                try:
                    if existing.isVisible():
                        try:
                            existing.activateWindow()
                            existing.raise_()
                        except Exception:
                            pass
                        return
                    else:
                        # 已存在但不可见，尝试移除事件过滤并清理引用以便重新创建
                        try:
                            existing.removeEventFilter(self)
                        except Exception:
                            pass
                        self._help_window = None
                except Exception:
                    self._help_window = None

            # 创建 HelpWidget 实例并以非模态方式显示
            self._help_window = HelpWidget()
            self._help_window.setWindowModality(Qt.WindowModality.NonModal)
            try:
                self._help_window.installEventFilter(self)
            except Exception:
                pass

            def _on_help_destroyed():
                try:
                    if getattr(self, "_help_window", None) is not None:
                        self._help_window = None
                except Exception:
                    self._help_window = None

            try:
                self._help_window.destroyed.connect(_on_help_destroyed)
            except Exception:
                pass

            # 显示窗口（非模态）
            self._help_window.show()

        except Exception as e:
            # 记录异常并弹出对话框，不影响后台线程
            self.log_output_text(f"无法显示关于窗口: {e}", "error")
            QMessageBox.warning(self, "显示失败", f"无法显示关于窗口: {e}")

    def eventFilter(self, watched, event):
        """拦截 HelpWidget 的 Close/Hide 事件，清理保存的引用以允许再次打开。"""
        try:
            if watched is getattr(self, "_help_window", None):
                # 使用数值来避免某些静态类型检查器对 QEvent 枚举成员的误报
                ev_type = event.type()
                if ev_type in (19, 5):  # 19 = Close, 5 = Hide
                    try:
                        watched.removeEventFilter(self)
                    except Exception:
                        pass
                    self._help_window = None
        except Exception:
            pass

        return super().eventFilter(watched, event)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    ui = SportsUploaderUI()
    ui.show()
    sys.exit(app.exec())