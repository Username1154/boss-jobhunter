"""
B***平台适配器 — 消息扫描、简历投递、HR聊天
需要用户提供浏览器Cookie来维持会话
"""
import json
import time
import random
import hashlib
import re
from pathlib import Path
from datetime import datetime
from urllib.parse import urlencode

import requests

BASE_DIR = Path(__file__).parent

with open(BASE_DIR / "config.json", "r", encoding="utf-8") as f:
    CONFIG = json.load(f)
with open(BASE_DIR / "user_profile.json", "r", encoding="utf-8") as f:
    PROFILE = json.load(f)


# ============================================================
# API端点
# ============================================================

BASE_URL = "https://www.zhipin.com"
WAPI = f"{BASE_URL}/wapi"

ENDPOINTS = {
    # 聊天
    "chat_list": f"{WAPI}/zpchat/geekChat/list",            # 获取聊天列表
    "chat_history": f"{WAPI}/zpchat/geekChat/history",       # 获取聊天记录
    "chat_send": f"{WAPI}/zpchat/geekChat/send",             # 发送消息
    "chat_unread": f"{WAPI}/zpchat/geekChat/unreadCount",    # 未读消息数

    # 岗位
    "job_search": f"{WAPI}/zpgeek/search/joblist.json",      # 搜索岗位
    "job_detail": f"{WAPI}/zpgeek/job/detail.json",          # 岗位详情
    "job_recommend": f"{WAPI}/zpgeek/home/recommend/joblist.json",  # 推荐岗位
    "job_apply": f"{WAPI}/zpgeek/geek/start.json",           # 投递简历（打招呼）
    "job_apply_status": f"{WAPI}/zpgeek/boss/job/status.json",  # 投递状态

    # 公司
    "company_info": f"{WAPI}/zpgeek/company/page.json",      # 公司主页
    "company_jobs": f"{WAPI}/zpgeek/company/job/list.json",  # 公司在招岗位

    # 用户
    "geek_info": f"{WAPI}/zpgeek/geek/info.json",            # 求职者信息
    "geek_resume": f"{WAPI}/zpgeek/resume/attachment.json",  # 简历附件

    # 地理位置
    "city_sites": f"{WAPI}/zpgeek/common/data/citySites.json",
}


# ============================================================
# 会话管理
# ============================================================

class BossZhipinSession:
    """B***会话管理"""

    def __init__(self, cookies_dict: dict = None):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "Referer": "https://www.zhipin.com/web/geek/chat",
            "Origin": "https://www.zhipin.com",
            "Connection": "keep-alive",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
        })

        self.cookies = {}
        self.uid = None
        self.geek_info = None
        self.applied_jobs = set()
        self.conversations = {}

        if cookies_dict:
            self.load_cookies(cookies_dict)

        self._load_local_data()

    def load_cookies(self, cookies_dict: dict):
        """加载cookie"""
        self.cookies = cookies_dict
        for key, value in cookies_dict.items():
            self.session.cookies.set(key, value, domain=".zhipin.com")

    def export_cookies(self) -> dict:
        """导出当前cookie"""
        return dict(self.session.cookies.get_dict())

    def is_authenticated(self) -> bool:
        """检查是否已登录"""
        try:
            resp = self.session.get(ENDPOINTS["geek_info"], timeout=10)
            data = resp.json()
            if data.get("code") == 0:
                self.geek_info = data.get("zpData", {})
                self.uid = self.geek_info.get("userId") or self.geek_info.get("encryptUserId")
                return True
            return False
        except Exception:
            return False

    def _load_local_data(self):
        """加载本地数据（已投递记录、对话记录）"""
        applied_path = BASE_DIR / "data" / "applied.json"
        conv_path = BASE_DIR / "data" / "conversations.json"
        blacklist_path = BASE_DIR / "data" / "blacklist.json"

        if applied_path.exists():
            with open(applied_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                self.applied_jobs = set(data.get("job_ids", []))

        if conv_path.exists():
            with open(conv_path, "r", encoding="utf-8") as f:
                self.conversations = json.load(f)

        if blacklist_path.exists():
            with open(blacklist_path, "r", encoding="utf-8") as f:
                self.blacklist = set(json.load(f).get("companies", []))
        else:
            self.blacklist = set()

    def _save_local_data(self):
        """保存本地数据"""
        applied_path = BASE_DIR / "data" / "applied.json"
        conv_path = BASE_DIR / "data" / "conversations.json"
        blacklist_path = BASE_DIR / "data" / "blacklist.json"

        with open(applied_path, "w", encoding="utf-8") as f:
            json.dump({"job_ids": list(self.applied_jobs), "updated": datetime.now().isoformat()}, f, ensure_ascii=False, indent=2)

        with open(conv_path, "w", encoding="utf-8") as f:
            json.dump(self.conversations, f, ensure_ascii=False, indent=2)

        with open(blacklist_path, "w", encoding="utf-8") as f:
            json.dump({"companies": list(self.blacklist), "updated": datetime.now().isoformat()}, f, ensure_ascii=False, indent=2)


# ============================================================
# 消息扫描
# ============================================================

    def scan_messages(self) -> list:
        """扫描未读/最近消息"""
        try:
            resp = self.session.get(ENDPOINTS["chat_list"], timeout=15)
            data = resp.json()
            if data.get("code") != 0:
                return []

            chat_list = data.get("zpData", {}).get("list", [])
            new_messages = []

            for chat in chat_list:
                boss_id = chat.get("bossId") or chat.get("encryptBossId")
                boss_name = chat.get("bossName") or chat.get("name", "HR")
                company = chat.get("brandName") or chat.get("companyName", "未知公司")
                job_title = chat.get("jobName") or chat.get("title", "")

                # 检查是否有新消息
                last_msg = chat.get("lastMsg", {})
                last_text = last_msg.get("text", "") if isinstance(last_msg, dict) else str(last_msg)
                last_time = chat.get("lastMsgTime", 0)

                conv_key = str(boss_id)
                if conv_key in self.conversations:
                    prev_time = self.conversations[conv_key].get("last_msg_time", 0)
                    if last_time <= prev_time:
                        continue

                new_messages.append({
                    "boss_id": boss_id,
                    "boss_name": boss_name,
                    "company": company,
                    "job_title": job_title,
                    "last_message": last_text,
                    "last_time": last_time,
                    "chat_id": chat.get("chatId") or chat.get("encryptChatId"),
                    "raw": chat,
                })

                # 更新对话记录
                self.conversations[conv_key] = {
                    "boss_name": boss_name,
                    "company": company,
                    "job_title": job_title,
                    "last_msg_time": last_time,
                    "updated": datetime.now().isoformat(),
                }

            self._save_local_data()
            return new_messages

        except Exception as e:
            print(f"[扫描消息失败] {e}")
            return []

    def get_chat_history(self, boss_id: str) -> list:
        """获取与某HR的聊天记录"""
        try:
            params = {"bossId": boss_id}
            resp = self.session.get(ENDPOINTS["chat_history"], params=params, timeout=10)
            data = resp.json()
            if data.get("code") != 0:
                return []
            return data.get("zpData", {}).get("messages", [])
        except Exception:
            return []


# ============================================================
# 消息发送
# ============================================================

    def send_message(self, boss_id: str, text: str) -> bool:
        """向HR发送消息"""
        try:
            payload = {
                "bossId": boss_id,
                "text": text,
                "msgType": 1,  # 文本消息
            }
            resp = self.session.post(ENDPOINTS["chat_send"], json=payload, timeout=10)
            data = resp.json()
            if data.get("code") == 0:
                print(f"[发送成功] → {boss_id}: {text[:50]}...")
                return True
            else:
                print(f"[发送失败] {data.get('message', '未知错误')}")
                return False
        except Exception as e:
            print(f"[发送异常] {e}")
            return False


# ============================================================
# 岗位搜索与投递
# ============================================================

    def search_jobs(self, keyword: str = "品牌策划", city: str = "东莞", page: int = 1) -> list:
        """搜索岗位"""
        city_code = self._get_city_code(city)
        params = {
            "query": keyword,
            "city": city_code,
            "page": page,
            "pageSize": 15,
        }
        try:
            resp = self.session.get(ENDPOINTS["job_search"], params=params, timeout=15)
            data = resp.json()
            if data.get("code") != 0:
                return []
            jobs = data.get("zpData", {}).get("jobList", [])

            parsed_jobs = []
            for job in jobs:
                parsed_jobs.append({
                    "job_id": job.get("jobId") or job.get("encryptJobId"),
                    "title": job.get("jobName", ""),
                    "company": job.get("brandName") or job.get("companyName", ""),
                    "salary": job.get("salaryDesc", ""),
                    "city": job.get("cityName", city),
                    "experience": job.get("jobExperience", ""),
                    "education": job.get("jobDegree", ""),
                    "description": job.get("jobDescription", ""),
                    "company_info": {
                        "industry": job.get("brandIndustry", ""),
                        "scale": job.get("brandScaleName", ""),
                        "stage": job.get("brandStageName", ""),
                    },
                    "hr_info": {
                        "name": job.get("bossName", ""),
                        "title": job.get("bossTitle", ""),
                        "active_status": job.get("bossOnline", ""),
                    },
                    "boss_id": job.get("encryptBossId") or job.get("bossId"),
                    "lid": job.get("lid"),
                })
            return parsed_jobs
        except Exception as e:
            print(f"[搜索岗位失败] {e}")
            return []

    def apply_job(self, job_info: dict, greeting: str = None) -> bool:
        """投递简历（发送打招呼消息）"""
        job_id = job_info.get("job_id")
        boss_id = job_info.get("boss_id")

        if job_id in self.applied_jobs:
            print(f"[已投递] {job_info.get('company')} - {job_info.get('title')}，跳过")
            return False

        if not greeting:
            from resume_engine import generate_boss_greeting
            greeting = generate_boss_greeting(
                job_info.get("description", ""),
                job_info.get("title", ""),
                job_info.get("company", ""),
            )

        # 发送打招呼消息 = 投递简历
        success = self.send_message(boss_id, greeting)
        if success:
            self.applied_jobs.add(job_id)
            self._save_local_data()
            print(f"[投递成功] {job_info.get('company')} - {job_info.get('title')}")
        return success

    def get_job_detail(self, job_id: str) -> dict:
        """获取岗位详情"""
        try:
            params = {"jobId": job_id}
            resp = self.session.get(ENDPOINTS["job_detail"], params=params, timeout=10)
            data = resp.json()
            if data.get("code") != 0:
                return {}
            detail = data.get("zpData", {})
            return {
                "description": detail.get("jobDetail", ""),
                "address": detail.get("address", ""),
                "business_zone": detail.get("businessZone", ""),
            }
        except Exception:
            return {}

    def _get_city_code(self, city_name: str) -> str:
        """获取城市代码"""
        city_map = {
            "东莞": "101280100", "深圳": "101280600", "广州": "101280100",
            "北京": "101010100", "上海": "101020100", "杭州": "101210100",
        }
        return city_map.get(city_name, "101280100")


# ============================================================
# 批量操作
# ============================================================

    def scan_and_reply(self) -> dict:
        """扫描新消息并生成回复"""
        from responder import generate_reply, should_ask_questions

        messages = self.scan_messages()
        results = {"scanned": len(messages), "replied": 0, "details": []}

        for msg in messages:
            boss_id = msg["boss_id"]
            company_info = msg.get("company", "")
            job_title = msg.get("job_title", "")

            # 获取聊天记录
            history = self.get_chat_history(boss_id)

            # 生成回复
            reply_result = generate_reply(msg["last_message"], history, company_info, job_title)
            reply_text = reply_result["reply"]

            # 检查是否需要追加反问
            followup = should_ask_questions(history)
            if followup["should_ask"]:
                reply_text += "\n\n另外，" + "\n".join(followup["questions"])

            # 发送回复
            if CONFIG["auto_reply"]:
                # 加随机延迟，模拟人类
                delay = random.randint(CONFIG["reply_delay_min"], CONFIG["reply_delay_max"])
                print(f"[延迟{delay}s后回复]")
                time.sleep(delay)

                success = self.send_message(boss_id, reply_text)
                if success:
                    results["replied"] += 1
                    results["details"].append({
                        "boss_name": msg["boss_name"],
                        "company": company_info,
                        "scenario": reply_result["scenario"],
                        "reply": reply_text[:100],
                        "sent": True,
                    })
            else:
                results["details"].append({
                    "boss_name": msg["boss_name"],
                    "company": company_info,
                    "scenario": reply_result["scenario"],
                    "reply": reply_text,
                    "sent": False,
                })

        return results

    def scan_and_apply(self, keywords: list = None) -> dict:
        """扫描岗位并投递"""
        from filter import filter_jobs, format_evaluation_report

        if keywords is None:
            keywords = CONFIG["job_preferences"]["titles"][:3]

        all_jobs = []
        for kw in keywords:
            jobs = self.search_jobs(keyword=kw, city=PROFILE["expected_city"])
            all_jobs.extend(jobs)
            time.sleep(random.uniform(2, 5))  # 搜索间隔

        # 去重
        seen = set()
        unique_jobs = []
        for job in all_jobs:
            if job["job_id"] not in seen:
                seen.add(job["job_id"])
                unique_jobs.append(job)

        # 过滤
        filtered = filter_jobs(unique_jobs)

        # 自动投递
        results = {
            "total_scanned": len(unique_jobs),
            "strong_matches": len(filtered["strong_matches"]),
            "good_matches": len(filtered["good_matches"]),
            "auto_applied": 0,
            "skipped": len(filtered["skip"]),
            "details": [],
        }

        daily_limit = CONFIG["max_daily_applications"]
        applied_today = 0

        for job in filtered["auto_apply"]:
            if applied_today >= daily_limit:
                break

            evaluation = job.get("_evaluation", {})
            print(f"\n{format_evaluation_report(job)}")

            success = self.apply_job(job)
            if success:
                applied_today += 1
                results["auto_applied"] += 1
                results["details"].append({
                    "company": job["company"],
                    "title": job["title"],
                    "score": evaluation.get("score", 0),
                    "applied": True,
                })

            time.sleep(random.uniform(8, 20))  # 投递间隔，避免风控

        results["details"].sort(key=lambda x: x.get("score", 0), reverse=True)
        return results


# ============================================================
# 工具函数
# ============================================================

def parse_cookie_string(cookie_str: str) -> dict:
    """解析cookie字符串为字典"""
    cookies = {}
    for item in cookie_str.split(";"):
        item = item.strip()
        if "=" in item:
            key, value = item.split("=", 1)
            cookies[key.strip()] = value.strip()
    return cookies


def save_cookies_from_browser(cookie_str: str, filepath: str = None):
    """保存从浏览器复制的cookie"""
    cookies = parse_cookie_string(cookie_str)
    if filepath is None:
        filepath = BASE_DIR / "data" / "cookies.json"
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(cookies, f, ensure_ascii=False, indent=2)
    print(f"Cookie已保存到 {filepath}")
    return cookies


if __name__ == "__main__":
    # 测试：需要先设置cookie
    cookie_path = BASE_DIR / "data" / "cookies.json"
    if cookie_path.exists():
        with open(cookie_path, "r", encoding="utf-8") as f:
            cookies = json.load(f)
        session = BossZhipinSession(cookies)
        if session.is_authenticated():
            print("✓ 登录成功")
            msgs = session.scan_messages()
            print(f"扫描到 {len(msgs)} 条消息")
        else:
            print("✗ 登录失败，请更新cookie")
    else:
        print("请先在 data/cookies.json 中设置B***的cookie")
        print("获取方法：F12 → Application → Cookies → 复制 __zp_stoken__, zp_token 等关键cookie")
