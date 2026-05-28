import requests
from bs4 import BeautifulSoup
import re
import os

# 尝试导入 ddddocr（自动识别验证码），如果没有则回退到手动输入
try:
    import ddddocr
    OCR = ddddocr.DdddOcr(show_ad=False)
    AUTO_OCR = True
    print("[系统] ddddocr 已加载,验证码将自动识别")
except ImportError:
    OCR = None
    AUTO_OCR = False
    print("[系统] 未安装 ddddocr,验证码需手动输入（安装命令: pip install ddddocr）")

# 导入配置管理器
from config_manager import get_credentials

# ============ 配置区域 ============
BASE_URL = "https://www.chinafix.com"
LOGIN_URL = f"{BASE_URL}/member.php?mod=logging&action=login"
SIGN_URL = f"{BASE_URL}/plugin.php?id=k_misign:sign"

# 获取账户密码（首次会提示输入并保存）
USERNAME, PASSWORD = get_credentials()
if not USERNAME or not PASSWORD:
    print("\n❌ 账户信息获取失败，脚本终止")
    import os; os.system("pause")
    exit(1)

# 导入清除配置的功能
from config_manager import clear_credentials

# 通用请求头
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
    "Accept-Language": "zh-CN,zh;q=0.9",
    "Referer": SIGN_URL,
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}

# 创建会话（自动管理cookie）
session = requests.Session()
session.headers.update(HEADERS)


def decode_response(resp):
    """智能解码响应内容，Discuz! 论坛通常用 GBK 编码"""
    # 优先尝试服务器声明的编码
    if resp.encoding and resp.encoding.lower() != 'iso-8859-1':
        resp.encoding = resp.encoding
    else:
        # Discuz! 多用 GBK，用 apparent_encoding 自动检测
        resp.encoding = resp.apparent_encoding or 'gbk'
    return resp.text


def get_login_params():
    """访问登录页面，提取 formhash、seccodehash、loginhash 等动态参数"""
    print("[1] 正在访问登录页面...")
    resp = session.get(LOGIN_URL, timeout=15)
    html = decode_response(resp)

    print(f"    页面编码: {resp.encoding}")
    print(f"    页面长度: {len(html)} 字符")

    soup = BeautifulSoup(html, "html.parser")

    # ---- 提取 formhash ----
    formhash = ""
    formhash_input = soup.find("input", {"name": "formhash"})
    if formhash_input:
        formhash = formhash_input.get("value", "")
    else:
        # 备选：从页面所有 input 中搜索
        for inp in soup.find_all("input"):
            if inp.get("name") == "formhash":
                formhash = inp.get("value", "")
                break

    # 备选：用正则从原始HTML中提取（BeautifulSoup可能解析不全）
    if not formhash:
        match = re.search(r'name="formhash"\s+value="([^"]+)"', html)
        if match:
            formhash = match.group(1)
        else:
            match = re.search(r'value="([^"]+)"\s+name="formhash"', html)
            if match:
                formhash = match.group(1)

    print(f"    formhash = {formhash}")

    # ---- 提取 seccodehash ----
    seccodehash = ""
    # 方式1: 从 input 标签
    seccode_input = soup.find("input", {"name": "seccodehash"})
    if seccode_input:
        seccodehash = seccode_input.get("value", "")
    else:
        # 方式2: 正则提取
        match = re.search(r'name="seccodehash"\s+value="([^"]+)"', html)
        if match:
            seccodehash = match.group(1)
        else:
            match = re.search(r'value="([^"]+)"\s+name="seccodehash"', html)
            if match:
                seccodehash = match.group(1)
        # 方式3: 从 JS 代码中提取 seccodehash
        if not seccodehash:
            match = re.search(r'seccodehash\s*=\s*[\'"]([^\'"]+)[\'"]', html)
            if match:
                seccodehash = match.group(1)
        # 方式4: 从 span/img id 中提取 (如 id="seccode_SAH" → hash="SAH")
        if not seccodehash:
            match = re.search(r'id="seccode_([^"]+)"', html)
            if match:
                seccodehash = match.group(1)

    print(f"    seccodehash = {seccodehash}")

    # ---- 提取 seccodemodid ----
    seccodemodid = "member::logging"
    seccodemodid_input = soup.find("input", {"name": "seccodemodid"})
    if seccodemodid_input:
        seccodemodid = seccodemodid_input.get("value", seccodemodid)
    else:
        match = re.search(r'name="seccodemodid"\s+value="([^"]+)"', html)
        if match:
            seccodemodid = match.group(1)

    print(f"    seccodemodid = {seccodemodid}")

    # ---- 提取 loginhash ----
    loginhash = ""
    # 方式1: 从 form id 中提取 (loginform_XXX → XXX)
    login_form = soup.find("form", id=lambda x: x and "loginform" in str(x))
    if login_form:
        form_id = login_form.get("id", "")
        loginhash = form_id.replace("loginform_", "") if form_id else ""
    else:
        # 方式2: 正则提取
        match = re.search(r'loginform_([^"]+)', html)
        if match:
            loginhash = match.group(1)
        else:
            # 方式3: 从 JS 中的 loginhash 提取
            match = re.search(r'loginhash\s*=\s*[\'"]([^\'"]+)[\'"]', html)
            if match:
                loginhash = match.group(1)
            else:
                # 默认值
                loginhash = "LzUw2"

    print(f"    loginhash = {loginhash}")

    # ---- 构造验证码图片URL ----
    # Discuz! 验证码标准URL: misc.php?mod=seccode&idhash={seccodehash}
    # 如果 seccodehash 存在，说明登录需要验证码
    captcha_url = None
    if seccodehash:
        captcha_url = f"{BASE_URL}/misc.php?mod=seccode&idhash={seccodehash}"
        print(f"    验证码URL = {captcha_url}")
    else:
        print("    ⚠ 未检测到验证码，可能此账户登录不需要验证码")

    # ---- 调试：打印登录表单关键信息 ----
    if not formhash:
        print("    ❌ 未能提取 formhash，登录必然失败！")
        # 打印原始HTML片段供排查
        print("    HTML片段（前2000字符）:")
        print(html[:2000])

    return {
        "formhash": formhash,
        "seccodehash": seccodehash,
        "seccodemodid": seccodemodid,
        "loginhash": loginhash,
        "captcha_url": captcha_url,
    }


def download_captcha(captcha_url):
    """下载验证码图片到本地，优先用 ddddocr 自动识别，否则回退手动输入"""
    if not captcha_url:
        print("    ⚠ 无验证码URL，跳过验证码下载")
        return None, ""

    print("[2] 正在下载验证码图片...")
    try:
        resp = session.get(captcha_url, timeout=10)
        if resp.status_code != 200:
            print(f"    ❌ 验证码下载失败，状态码: {resp.status_code}")
            return None, ""

        captcha_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "captcha.png")
        with open(captcha_path, "wb") as f:
            f.write(resp.content)
        print(f"    ✅ 验证码已保存到: {captcha_path}")
        print(f"    图片大小: {len(resp.content)} bytes")

        # 自动 OCR 识别
        ocr_result = ""
        if AUTO_OCR:
            ocr_result = OCR.classification(resp.content)
            print(f"    🔍 OCR 识别结果: {ocr_result}")
        else:
            print(f"    请打开 {captcha_path} 查看验证码")

        return captcha_path, ocr_result
    except Exception as e:
        print(f"    ❌ 验证码下载异常: {e}")
        return None, ""


def do_login(formhash, seccodehash, seccodemodid, loginhash, seccodeverify):
    """执行登录POST请求"""
    print("[3] 正在提交登录请求...")

    login_submit_url = (
        f"{BASE_URL}/member.php?mod=logging&action=login"
        f"&loginsubmit=yes&handlekey=login&loginhash={loginhash}&inajax=1"
    )

    post_data = {
        "formhash": formhash,
        "referer": SIGN_URL,
        "loginfield": "username",
        "username": USERNAME,
        "smscodeverify": "",
        "password": PASSWORD,
        "questionid": "0",
        "answer": "",
        "seccodehash": seccodehash,
        "seccodemodid": seccodemodid,
        "seccodeverify": seccodeverify,
    }

    resp = session.post(
        login_submit_url,
        data=post_data,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Origin": BASE_URL,
            "Referer": LOGIN_URL,
        },
        timeout=15,
    )
    html = decode_response(resp)

    print("    登录响应:")
    # 尝试从XML CDATA中提取纯文本
    cdata_match = re.search(r'<!\[CDATA\[(.*?)\]\]>', html)
    if cdata_match:
        msg = cdata_match.group(1)
        # 去掉JS脚本部分，只留文字
        text_match = re.search(r'([^<]+)', msg)
        if text_match:
            clean_msg = text_match.group(1).strip()
            print(f"    消息: {clean_msg}")
        else:
            print(f"    原始消息: {msg[:200]}")
    else:
        print(html[:500])

    # 判断登录结果
    if "succeedhandle" in html or "登录成功" in html:
        print("    ✅ 登录成功！")
        return "success"
    elif "验证码" in html and "错误" in html:
        print("    ❌ 验证码错误")
        return "captcha_error"
    elif "密码错误" in html or "用户名或密码错误" in html:
        print("    ❌ 用户名或密码错误！")
        print("    [配置] 检测到密码错误,清除已保存的账户信息")
        clear_credentials()
        return "auth_error"
    elif "用户名不存在" in html:
        print("    ❌ 用户名不存在！")
        print("    [配置] 检测到用户名错误,清除已保存的账户信息")
        clear_credentials()
        return "auth_error"
    else:
        print("    ❌ 登录可能失败，请检查响应内容")
        # 也清除配置,因为可能是其他认证问题
        print("    [配置] 为安全起见,清除已保存的账户信息")
        clear_credentials()
        return "unknown_error"


def refresh_captcha(seccodehash):
    """刷新验证码（Discuz! 支持AJAX刷新）"""
    import random
    random_float = f"{random.random()}"
    refresh_url = f"{BASE_URL}/misc.php?mod=seccode&action=update&idhash={seccodehash}&{random_float}"
    print("    正在刷新验证码...")
    session.get(refresh_url, timeout=10)
    # 然后重新下载验证码图片
    captcha_url = f"{BASE_URL}/misc.php?mod=seccode&idhash={seccodehash}"
    return download_captcha(captcha_url)


def do_sign(formhash):
    """登录成功后执行签到 - 模拟浏览器：先访问签到页面，再触发签到动作"""
    print("[4] 正在签到...")

    # 第一步：先访问签到页面（与浏览器行为一致，设置正确的Referer）
    print("    先访问签到页面...")
    resp = session.get(SIGN_URL, timeout=15)
    html = decode_response(resp)
    print(f"    签到页面加载完成，长度: {len(html)} 字符")

    # 从签到页面重新提取最新的 formhash（登录后 formhash 可能已刷新）
    match = re.search(r'formhash=([a-f0-9]+)', html)
    if match:
        new_formhash = match.group(1)
        if new_formhash != formhash:
            print(f"    formhash 已更新: {formhash} → {new_formhash}")
            formhash = new_formhash
        else:
            print(f"    formhash 未变化: {formhash}")
    else:
        print(f"    ⚠ 未能从签到页面提取 formhash，使用登录时的值: {formhash}")

    # 第二步：触发签到动作
    # 签到URL格式: plugin.php?id=k_misign:sign&operation=qiandao&formhash={formhash}&format=empty
    sign_url = f"{BASE_URL}/plugin.php?id=k_misign:sign&operation=qiandao&formhash={formhash}&format=empty"
    print(f"    签到链接: {sign_url}")

    # AJAX模式签到（浏览器点击签到按钮时实际发出的请求）
    sign_ajax_url = f"{sign_url}&inajax=1"
    resp = session.get(sign_ajax_url, timeout=15, headers={"Referer": SIGN_URL})
    html = decode_response(resp)

    #print(f"    签到响应: {html[:300]}")

    # 解析签到结果
    if "已签到" in html or "succeed" in html.lower() or "签到成功" in html:
        print("    ✅ 签到成功！")
    elif "今日已签" in html or "已经签到" in html:
        print("    ✅ 今日已签到，无需重复签到")
    else:
        # 尝试普通模式（不带inajax参数）
        print("    AJAX模式未明确成功，尝试普通模式...")
        resp2 = session.get(sign_url, timeout=15, headers={"Referer": SIGN_URL})
        html2 = decode_response(resp2)
        if "已签到" in html2 or "签到成功" in html2:
            print("    ✅ 签到成功！")
        else:
            print(f"    签到结果（前500字）: {html2[:500]}")


# ============ 主流程 ============
def main():
    print("=" * 50)
    print("  chinafix.com 自动登录签到脚本")
    print("=" * 50)

    # 步骤1: 获取动态参数
    params = get_login_params()

    if not params["formhash"]:
        print("\n❌ 无法获取 formhash，脚本终止。请检查网络或页面结构是否变化。")
        return

    # 步骤2: 下载验证码并识别（支持重试）
    max_captcha_retry = 3
    for attempt in range(1, max_captcha_retry + 1):
        if attempt > 1:
            print(f"\n--- 验证码第 {attempt} 次尝试 ---")
            # 刷新验证码
            captcha_path, ocr_result = refresh_captcha(params["seccodehash"])
        else:
            captcha_path, ocr_result = download_captcha(params["captcha_url"])

        if captcha_path:
            if ocr_result:
                # ddddocr 自动识别成功
                seccodeverify = ocr_result
                print(f"    自动识别验证码: {seccodeverify}")
            else:
                # 未安装 ddddocr，手动输入
                print(f"\n    请查看 {captcha_path} 中的验证码图片")
                seccodeverify = input("    请输入验证码: ").strip()
        else:
            seccodeverify = ""
            if not params["seccodehash"]:
                print("    无需验证码，直接登录")
            else:
                print("    ⚠ 验证码下载失败，尝试无验证码登录（大概率失败）")

        # 步骤3: 提交登录
        result = do_login(
            params["formhash"],
            params["seccodehash"],
            params["seccodemodid"],
            params["loginhash"],
            seccodeverify,
        )

        if result == "success":
            # 步骤4: 签到
            do_sign(params["formhash"])
            return
        elif result == "captcha_error" and attempt < max_captcha_retry:
            # 如果是验证码错误且还有重试次数，继续重试
            print("    验证码错误，准备重试...")
            continue
        elif result == "auth_error":
            # 账户密码错误,清除后重新输入
            print("\n❌ 账户密码错误,已清除保存的信息")
            print("请重新输入正确的账户密码...\n")
            
            # 重新获取账户密码
            global USERNAME, PASSWORD
            USERNAME, PASSWORD = get_credentials()
            if not USERNAME or not PASSWORD:
                print("\n❌ 账户信息获取失败，脚本终止")
                return
            
            # 重新获取登录参数
            print("\n--- 使用新账户重新登录 ---")
            params = get_login_params()
            if not params["formhash"]:
                print("\n❌ 无法获取 formhash，脚本终止。")
                return
            
            # 重置尝试次数
            attempt = 0
            continue
        elif result == "rate_limit":
            # 被风控锁定,终止脚本
            print("\n⚠ 账户已被风控锁定!")
            print("请等待 15 分钟后,确认密码正确再运行脚本")
            print("[配置] 已清除保存的账户信息,下次运行需重新输入")
            return  # 直接终止
        else:
            print("\n❌ 登录失败，已达到最大重试次数或密码错误。")
            return

    print("\n❌ 登录失败，已达到最大验证码重试次数。")


if __name__ == "__main__":
    main()
    import os; os.system("pause")
