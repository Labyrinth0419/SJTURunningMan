import requests
import json
from urllib.parse import quote
from utils.auxiliary_util import log_output, SportsUploaderError

def make_request(method, url, headers, params=None, data=None, log_cb=None, stop_check_cb=None, session=None):
    """通用HTTP请求函数"""
    try:
        if stop_check_cb and stop_check_cb():
            log_output("API请求被中断。", "warning", log_cb)
            raise SportsUploaderError("任务已停止。")

        timeout_value = 15

        response = None

        # 如果提供了 session，则用它发起请求以携带 cookies
        if session is not None:
            if method.upper() == 'GET':
                response = session.get(url, headers=headers, params=params, timeout=timeout_value)
            elif method.upper() == 'POST':
                response = session.post(url, headers=headers, data=data, timeout=timeout_value)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")
        else:
            if method.upper() == 'GET':
                response = requests.get(url, headers=headers, params=params, timeout=timeout_value)
            elif method.upper() == 'POST':
                response = requests.post(url, headers=headers, data=data, timeout=timeout_value)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")

        if stop_check_cb and stop_check_cb():
            log_output("API响应已获取，但任务被中断。", "warning", log_cb)
            raise SportsUploaderError("任务已停止。")

        response.raise_for_status()
        return response.json()
    except requests.exceptions.HTTPError as e:
        log_output(f"HTTP error occurred: {e}", "error", log_cb)
        log_output(f"URL: {url}", "error", log_cb)
        if response is not None: # pyright: ignore[reportPossiblyUnboundVariable]
            log_output(f"Response status code: {response.status_code}", "error", log_cb) # pyright: ignore[reportPossiblyUnboundVariable]
            log_output(f"Response text: {response.text}", "error", log_cb) # type: ignore
            try:
                log_output(f"Response JSON (if any): {json.dumps(response.json(), indent=2)}", "error", log_cb) # type: ignore
            except json.JSONDecodeError:
                log_output(f"Response text (non-JSON): {response.text}", "error", log_cb) # type: ignore
        raise SportsUploaderError(f"HTTP Error: {e}")
    except requests.exceptions.ConnectionError as e:
        log_output(f"Connection error occurred: {e}", "error", log_cb)
        if isinstance(e.args[0], requests.packages.urllib3.exceptions.MaxRetryError) and e.args[0].reason: # type: ignore
            log_output(f"Underlying reason: {e.args[0].reason}", "error", log_cb)
        raise SportsUploaderError(f"Connection Error: {e}")
    except requests.exceptions.Timeout as e:
        log_output(f"Timeout error occurred: {e}", "error", log_cb)
        raise SportsUploaderError(f"Timeout Error: {e}")
    except requests.exceptions.RequestException as e:
        log_output(f"An unexpected error occurred: {e}", "error", log_cb)
        raise SportsUploaderError(f"Request Error: {e}")
    except json.JSONDecodeError:
        log_output(f"Failed to decode JSON from response: {response.text if response else 'No response'}", "error", log_cb) # type: ignore
        raise SportsUploaderError(f"JSON Decode Error: {response.text if response else 'No response'}") # type: ignore


def get_authorization_token_and_rules(config, log_cb=None, stop_check_cb=None):
    """
    通过GET请求获取Authorization Token，并随后获取跑步规则。
    """
    common_app_headers = {
        "Host": config["HOST"],
        "Connection": "keep-alive",
        "sec-ch-ua-platform": "\"Android\"",
        "User-Agent": "Mozilla/5.0 (Linux; Android 12; SM-S9080 Build/V417IR; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/138.0.7204.67 Safari/537.36 TaskCenterApp/3.5.0",
        "Accept": "application/json, text/plain, */*",
        "sec-ch-ua": "\"Not)A;Brand\";v=\"8\", \"Chromium\";v=\"138\", \"Android WebView\";v=\"138\"",
        "Content-Type": "application/json;charset=utf-8",
        "sec-ch-ua-mobile": "?0",
        "X-Requested-With": "edu.sjtu.infoplus.taskcenter",
        "Sec-Fetch-Site": "same-origin",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Dest": "empty",
        "Referer": "https://pe.sjtu.edu.cn/phone/",
        "Accept-Encoding": "gzip, deflate, br, zstd",
        "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
    }

    # 如果没有提供 SESSION，则继续使用 COOKIE 字符串（向后兼容）
    if not config.get("SESSION"):
        common_app_headers["Cookie"] = config.get("COOKIE", "")

    uid_response_data = make_request('GET', config['UID_URL'], common_app_headers, log_cb=log_cb, stop_check_cb=stop_check_cb, session=config.get("SESSION"))

    auth_token = None
    if uid_response_data.get('code') == 0 and 'uid' in uid_response_data.get('data', {}):
        auth_token = uid_response_data['data']['uid']
    else:
        raise SportsUploaderError(f"Failed to get Authorization Token: {uid_response_data}")

    if stop_check_cb and stop_check_cb():
        log_output("任务被请求停止，正在退出...", "warning", log_cb)
        raise SportsUploaderError("任务已停止。")

    try:
        make_request('GET', config['MY_DATA_URL'], common_app_headers, log_cb=log_cb, stop_check_cb=stop_check_cb, session=config.get("SESSION"))
    except Exception as e:
        log_output(f"获取数据失败: {e}", "warning", log_cb)

    if stop_check_cb and stop_check_cb():
        log_output("任务被请求停止，正在退出...", "warning", log_cb)
        raise SportsUploaderError("任务已停止。")

    formatted_lon_for_param = f"{config['START_LONGITUDE']:.14f}"
    formatted_lat_for_param = f"{config['START_LATITUDE']:.14f}"
    current_location_param = f"{formatted_lon_for_param},{formatted_lat_for_param}"

    referer_url_for_point_rule = f"{config['POINT_RULE_URL']}?location={quote(current_location_param, safe='')}"

    point_rule_headers = {
        "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
        "accept-language": "zh-CN,zh;q=0.9,en;q=0.8",
        "authorization": auth_token,
        "cache-control": "no-cache",
        "pragma": "no-cache",
        "sec-ch-ua": "\"Chromium\";v=\"140\", \"Not=A?Brand\";v=\"24\", \"Google Chrome\";v=\"140\"",
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": "\"Windows\"",
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin",
        "upgrade-insecure-requests": "1",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36",
        "referer": referer_url_for_point_rule,
        "Host": config["HOST"],
    }

    params_string = f"?location={quote(current_location_param, safe='')}"
    url = config["POINT_RULE_URL"]

    point_rule_response_data = make_request('GET', url + params_string, point_rule_headers, log_cb=log_cb, stop_check_cb=stop_check_cb, session=config.get("SESSION"))

    return auth_token, point_rule_response_data.get('data', {})

def upload_running_data(config, auth_token, running_data, log_cb=None, stop_check_cb=None):
    """
    上传跑步数据到服务器。
    """
    headers = {
        "Authorization": auth_token,
        "Content-Type": "application/json; charset=utf-8",
        "Host": config["HOST"],
        "Connection": "Keep-Alive",
        "Accept-Encoding": "gzip",
        "User-Agent": "okhttp/4.10.0"
    }

    if stop_check_cb and stop_check_cb():
        log_output("任务被请求停止，正在退出...", "warning", log_cb)
        raise SportsUploaderError("任务已停止。")

    response = make_request(
        'POST',
        config["UPLOAD_URL"],
        headers,
        data=json.dumps(running_data),
        log_cb=log_cb,
        stop_check_cb=stop_check_cb,
        session=config.get("SESSION")
    )
    return response