from time import sleep
import requests
import os, sys

from requests.adapters import HTTPAdapter
from requests.exceptions import RequestException
from tenacity import retry, retry_if_exception_type, wait_fixed
from utils.auxiliary_util import re_search, get_timestamp

def get_jalogin_from_authorize(session, client_id, redirect_uri, scope="profile", state="8"):
    """
    模拟浏览器访问 /oauth2/authorize 并返回最终的 /jaccount/jalogin?... URL。
    """
    authorize_url = "https://jaccount.sjtu.edu.cn/oauth2/authorize"
    params = {
        "response_type": "code",
        "scope": scope,
        "client_id": client_id,
        "state": state,
        "redirect_uri": redirect_uri,
    }
    # 发起请求并允许重定向；session 会保存 cookies
    r = session.get(authorize_url, params=params, allow_redirects=True, timeout=10)

    # 优先在重定向历史中寻找 jalogin
    for resp in (r.history + [r]):
        if "jaccount.sjtu.edu.cn/jaccount/jalogin" in resp.url:
            return resp.url

    # 兜底：从页面中提取 jalogin 链接
    m = re_search(r'''(https?://jaccount\.sjtu\.edu\.cn/jaccount/jalogin\?[^\s"'<>]+)''', r.text)
    if m:
        return m.group(1)

    raise RuntimeError("未能从 authorize 的重定向/页面中获取 jalogin URL")

# 创建一个新的 session
def _create_session():
    session = requests.Session()
    session.headers = {'Referer':'https://jaccount.sjtu.edu.cn'}
    session.mount('http://', HTTPAdapter(max_retries=3))
    session.mount('https://', HTTPAdapter(max_retries=3))
    return session

# 获得登录界面网页(html)，便于之后从中提取必要信息
@retry(retry=retry_if_exception_type(RequestException), wait=wait_fixed(3))
def _get_login_page(session, url):
    req = session.get(url)
    return req.text

# 获得验证码图片(jpeg)
@retry(retry=retry_if_exception_type(RequestException), wait=wait_fixed(3))
def _get_captcha(session, captcha_url):
    session.get(captcha_url)
    captcha_jpeg = session.get(captcha_url)
    image_path = "captcha.jpeg"
    with open(image_path, "wb") as f:
        f.write(captcha_jpeg.content)


# 调用外部模型识别验证码
def _indentify_captcha():
    captcha_solver_url = "https://geek.sjtu.edu.cn/captcha-solver/"
    image_path = "captcha.jpeg"

    with open(image_path, "rb") as f:
        files = {"image": ("captcha.jpg", f, "image/jpeg")}
        response = requests.post(captcha_solver_url, files=files)

    try:
        result = response.json().get("result")
        os.remove("captcha.jpeg")
        return result
    except Exception:
        print("验证码识别失败！")

@retry(retry=retry_if_exception_type(RequestException), wait=wait_fixed(3))
def _post_login_request(session, login_page, username, password, captcha_code):
    # 从页面中获得其他必要参数
    sid = re_search(r'sid: "(.*?)"', login_page)
    returl = re_search(r'returl:"(.*?)"', login_page)
    se = re_search(r'se: "(.*?)"', login_page)
    client = re_search(r'client: "(.*?)"', login_page)
    uuid = re_search(r'captcha\?uuid=(.*?)&t=', login_page)

    # 构建提交 data
    data = {'sid': sid, 'returl': returl, 'se': se, 'client': client, 'user': username,
            'pass': password, 'captcha': captcha_code, 'v': '', 'uuid': uuid}

    # 发起 post 请求
    session.post(
        'https://jaccount.sjtu.edu.cn/jaccount/ulogin', data = data)


    # 登录成功会在 cookies 中获得 JAAuthCookie
    cookie_names = {c.name for c in session.cookies}
    if 'JAAuthCookie' in cookie_names:
        return 0
    else:
        return -1

def login(username, password):
        session = _create_session()

        url = get_jalogin_from_authorize(
            session,
            client_id="9mqzULSXYgUYj5fPOpyL",
            redirect_uri="https://pe.sjtu.edu.cn/oauth2Login"
        )

        # 获得页面信息
        login_page = _get_login_page(session, url)

        # 立刻获得验证码请求路径，避免时间戳过期
        captcha_id = re_search(r'img.src = \'captcha\?(.*)\'', login_page) + get_timestamp() # type: ignore
        captcha_url = 'https://jaccount.sjtu.edu.cn/jaccount/captcha?' + captcha_id

        # 下载验证码图片
        _get_captcha(session, captcha_url)
        captcha_code = _indentify_captcha()

        # 获取用户名和密码
        sleep(1)
        user_info = [username, password]

        # 发起登录请求
        result = _post_login_request(session, login_page, user_info[0],user_info[1], captcha_code)

        # 判断返回结果
        if result == 0:
            return session