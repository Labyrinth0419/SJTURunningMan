import time
import datetime
from src.api_client import get_authorization_token_and_rules, upload_running_data
from src.data_generator import generate_running_data_payload
from src.utils import log_output, SportsUploaderError, get_current_epoch_ms

def run_sports_upload(config, progress_callback=None, log_cb=None, stop_check_cb=None):
    """
    核心的跑步数据生成和上传逻辑，接收配置字典和进度回调函数。
    progress_callback: 接收 (current_value, max_value, message)
    log_cb: 接收 (message, level)
    stop_check_cb: 一个函数，调用时返回True表示请求停止
    """
    log_output("--- Starting Sports Upload Process ---", callback=log_cb)

    if stop_check_cb and stop_check_cb():
        log_output("任务被请求停止，正在退出...", "warning", log_cb)
        return False, "任务已停止。"

    auth_token_for_upload = None
    required_signpoints = []

    try:
        log_output("步骤 1/3: 获取认证信息...", callback=log_cb)
        if progress_callback: progress_callback(10, 100, "获取认证信息和跑步规则...")

        if stop_check_cb and stop_check_cb():
            log_output("任务被请求停止，正在退出...", "warning", log_cb)
            return False, "任务已停止。"

        # 获取认证令牌
        auth_token_for_upload, _ = get_authorization_token_and_rules(config, log_cb=log_cb, stop_check_cb=stop_check_cb)

    except SportsUploaderError as e:
        log_output(f"身份验证失败: {e}", "error", log_cb)
        return False, str(e)
    except Exception as e:
        log_output(f"未知错误: {e}", "error", log_cb)
        return False, str(e)

    if stop_check_cb and stop_check_cb():
        log_output("任务被请求停止，正在退出...", "warning", log_cb)
        return False, "任务已停止。"

    log_output("\n步骤 2/3: 生成跑步数据...", callback=log_cb)
    if progress_callback: progress_callback(40, 100, "生成跑步数据...")
    running_data_payload = None
    total_dist = 0
    total_dur = 0
    try:
        running_data_payload, total_dist, total_dur = generate_running_data_payload(
            config,
            required_signpoints,
            {},
            log_cb=log_cb,
            stop_check_cb=stop_check_cb
        )

    except SportsUploaderError as e:
        log_output(f"生成跑步数据失败: {e}", "error", log_cb)
        return False, str(e)
    except Exception as e:
        log_output(f"未知错误: {e}", "error", log_cb)
        return False, str(e)

    if stop_check_cb and stop_check_cb():
        log_output("任务被请求停止，正在退出...", "warning", log_cb)
        return False, "任务已停止。"

    if running_data_payload and auth_token_for_upload:
        log_output("\n步骤 3/3: 上传跑步数据...", callback=log_cb)
        if progress_callback: progress_callback(70, 100, "准备上传跑步数据...")
        try:
            if stop_check_cb and stop_check_cb():
                log_output("任务被请求停止，正在退出...", "warning", log_cb)
                return False, "任务已停止。"

            log_output("尝试上传跑步数据...", callback=log_cb)
            if progress_callback: progress_callback(90, 100, "上传数据...")

            response = upload_running_data(
                config,
                auth_token_for_upload,
                running_data_payload,
                log_cb=log_cb,
                stop_check_cb=stop_check_cb
            )

            if response.get('code') == 0 and response.get('data'):
                log_output("上传成功！", callback=log_cb)
                if progress_callback: progress_callback(100, 100, "上传成功！")
                return True, "上传成功！"
            elif response.get('code') == 0:
                # 简短警告，在 GUI 中显示为 [Warring]
                log_output("[Warring] 上传未完全成功，不会计入总里程", "warning", log_cb)
                if progress_callback: progress_callback(100, 100, "上传完成")
                return False, "上传未完全成功，不会计入总里程"
            else:
                log_output("上传失败", "error", log_cb)
                if progress_callback: progress_callback(100, 100, "上传失败！")
                return False, f"上传失败，响应代码: {response.get('code', 'N/A')}"
        except SportsUploaderError as e:
            log_output(f"上传失败: {e}", "error", log_cb)
            if progress_callback: progress_callback(100, 100, "上传失败！")
            return False, str(e)
        except Exception as e:
            log_output(f"未知错误: {e}", "error", log_cb)
            if progress_callback: progress_callback(100, 100, "上传失败！")
            return False, str(e)
    else:
        log_output("数据生成或认证失败，上传被跳过。", "error", log_cb)
        if progress_callback: progress_callback(100, 100, "上传被跳过！")
        return False, "数据生成或认证失败，上传被跳过。"