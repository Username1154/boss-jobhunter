"""
全平台求职Agent — Boss直聘 + 猎聘 + 前程无忧
需要浏览器（Edge/Chrome），基于DrissionPage + Chrome CDP
用法: python multi_hunter.py --city 深圳 --max-apply 20
"""
import sys
import json
import time
import random
import re
import hashlib
import os
import socket
import subprocess
from pathlib import Path
from datetime import datetime, timedelta

BASE_DIR = Path(__file__).parent
sys.path.insert(0, str(BASE_DIR))

from filter import evaluate_job, format_evaluation_report
from resume_engine import generate_boss_greeting, tailor_resume_sections
from responder import generate_reply, classify_hr_message, should_ask_questions

# ============================================================
# 配置
# ============================================================

with open(BASE_DIR / "config.json", "r", encoding="utf-8") as f:
    CONFIG = json.load(f)
with open(BASE_DIR / "user_profile.json", "r", encoding="utf-8") as f:
    PROFILE = json.load(f)

# 求职方向（根据 user_profile.json 中的 expected_role 自动生成）
JOB_DIRECTIONS = [
    {
        "name": role,
        "keywords": [role] + CONFIG.get("job_preferences", {}).get("titles", [])[:3],
        "cities": CONFIG.get("job_preferences", {}).get("cities", ["深圳"]),
    }
    for role in PROFILE.get("expected_role", ["品牌策划"])[:3]
]

# AI HR检测关键词
AI_HR_PATTERNS = [
    "我是AI", "智能助手", "机器人", "自动回复", "AI小助手",
    "系统将根据", "自动匹配", "智能推荐", "AI筛选",
    "请回复", "回复数字", "请选择", "请输入",
]

# 猎聘/前程无忧 城市代码
CITY_CODES_51JOB = {"深圳": "040000", "广州": "030200", "东莞": "030800", "杭州": "080200"}
CITY_CODES_LIEPIN = {"深圳": "050090", "广州": "050020", "东莞": "050040", "杭州": "060020"}

# 前程无忧当前有反爬问题(403)，暂时禁用
ENABLE_51JOB = False


# ============================================================
# Chrome管理
# ============================================================

def launch_browser():
    """启动浏览器调试模式（优先Edge，备选Chrome）"""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    result = sock.connect_ex(('127.0.0.1', 9222))
    sock.close()

    if result == 0:
        print("[浏览器] 调试模式已在运行")
        return True

    browser_paths = [
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    ]

    browser_exe = None
    for p in browser_paths:
        if os.path.exists(p):
            browser_exe = p
            break

    if not browser_exe:
        print("[错误] 未找到浏览器，请安装Edge或Chrome")
        return False

    user_data = os.path.expandvars(r"%TEMP%\edge-job-hunt")
    cmd = f'"{browser_exe}" --remote-debugging-port=9222 --user-data-dir="{user_data}" --no-first-run --no-default-browser-check'
    print(f"[浏览器] 启动: {browser_exe}")
    subprocess.Popen(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(5)
    return True


# ============================================================
# 猎聘操作
# ============================================================

class LiepinHunter:
    def __init__(self, page):
        self.page = page
        self.applied = set()
        self._load_applied()

    def _load_applied(self):
        p = BASE_DIR / "data" / "applied_liepin.json"
        if p.exists():
            with open(p, "r", encoding="utf-8") as f:
                self.applied = set(json.load(f).get("ids", []))

    def _save_applied(self):
        p = BASE_DIR / "data" / "applied_liepin.json"
        with open(p, "w", encoding="utf-8") as f:
            json.dump({"ids": list(self.applied), "updated": datetime.now().isoformat()}, f)

    def search_jobs(self, keyword: str, city: str = "深圳", page: int = 1) -> list:
        """搜索猎聘岗位"""
        city_code = CITY_CODES_LIEPIN.get(city, "050090")
        url = f"https://www.liepin.com/zhaopin/?key={keyword}&dqs={city_code}&curPage={page}"
        print(f"  [猎聘] 搜索: {keyword} @ {city}")

        try:
            self.page.get(url)
            time.sleep(random.uniform(4, 6))
            for _ in range(3):
                self.page.scroll.to_bottom()
                time.sleep(1)

            js_code = '''
                var jobs = [];
                var cards = document.querySelectorAll('.job-card-pc-container');
                for (var i = 0; i < cards.length; i++) {
                    var card = cards[i];
                    var link = card.querySelector('a[href*="shtml"]');
                    if (!link) continue;
                    var text = card.innerText.split(String.fromCharCode(10)).filter(function(l) {
                        var t = l.trim();
                        return t && t !== String.fromCharCode(183);
                    });
                    var full = text.join(' ');
                    var salaryMatch = full.match(/\\d+\\.?\\d*-?\\d*\\.?\\d*[kK]/);
                    var idMatch = link.href.match(/\\/(\\d+)\\.shtml/) || link.href.match(/jobid=(\\d+)/);
                    jobs.push({
                        title: text[0] || '',
                        location: text[1] || '',
                        salary: salaryMatch ? salaryMatch[0] : '',
                        company: text.length > 7 ? (text[7] || '') : '',
                        link: link.href || '',
                        id: idMatch ? idMatch[1] : ''
                    });
                }
                return JSON.stringify(jobs);
            '''
            raw = self.page.run_js(js_code)
            raw_jobs = json.loads(raw)

            jobs = []
            for j in raw_jobs:
                job_id = j.get("id") or hashlib.md5(f"{j.get('company','')}{j.get('title','')}".encode()).hexdigest()[:12]
                if job_id and job_id not in self.applied and j.get("title"):
                    jobs.append({
                        "job_id": job_id,
                        "title": j["title"],
                        "company": j["company"],
                        "salary": j["salary"],
                        "city": j.get("location", city),
                        "link": j["link"],
                        "platform": "猎聘",
                    })

            print(f"    找到 {len(jobs)} 个新岗位")
            return jobs
        except Exception as e:
            print(f"    搜索失败: {e}")
            return []

    def get_job_detail(self, job: dict) -> dict:
        """获取岗位详情"""
        try:
            self.page.get(job["link"])
            time.sleep(2)
            desc_el = self.page.ele(".job-description") or self.page.ele(".job-detail") or self.page.ele(".content-word")
            desc = desc_el.text.strip() if desc_el else ""
            job["description"] = desc[:2000]
            return job
        except Exception:
            job["description"] = ""
            return job

    def apply(self, job: dict) -> bool:
        """投递猎聘岗位"""
        if job["job_id"] in self.applied:
            return False

        try:
            apply_btn = self.page.ele("text:立即投递") or self.page.ele("text:申请职位") or self.page.ele(".apply-btn")
            if apply_btn:
                apply_btn.click()
                time.sleep(2)
                resume_select = self.page.ele(".resume-select") or self.page.ele("text:选择简历")
                if resume_select:
                    first = self.page.ele(".resume-item:first-child") or self.page.ele(".resume-card:first-child")
                    if first:
                        first.click()
                        time.sleep(1)
                confirm_btn = self.page.ele("text:确认") or self.page.ele("text:投递") or self.page.ele(".confirm-btn")
                if confirm_btn:
                    confirm_btn.click()
                    time.sleep(2)
                self.applied.add(job["job_id"])
                self._save_applied()
                print(f"    ✓ 已投递: {job['company']} - {job['title']}")
                return True
            else:
                print(f"    - 未找到投递按钮: {job['company']}")
                return False
        except Exception as e:
            print(f"    ✗ 投递失败: {e}")
            return False

    def check_messages(self) -> list:
        """检查猎聘消息"""
        try:
            self.page.get("https://www.liepin.com/im/")
            time.sleep(3)
            messages = []
            msg_items = self.page.eles(".message-item") or self.page.eles(".chat-item") or []
            for item in msg_items[:10]:
                try:
                    name_el = item.ele(".name") or item.ele(".contact-name")
                    msg_el = item.ele(".last-message") or item.ele(".message-text")
                    time_el = item.ele(".time") or item.ele(".message-time")
                    name = name_el.text.strip() if name_el else "未知"
                    text = msg_el.text.strip() if msg_el else ""
                    msg_time = time_el.text.strip() if time_el else ""
                    messages.append({
                        "sender": name,
                        "text": text,
                        "time": msg_time,
                        "platform": "猎聘",
                    })
                except Exception:
                    continue
            return messages
        except Exception:
            return []


# ============================================================
# 前程无忧操作
# ============================================================

class Job51Hunter:
    def __init__(self, page):
        self.page = page
        self.applied = set()
        self._load_applied()

    def _load_applied(self):
        p = BASE_DIR / "data" / "applied_51job.json"
        if p.exists():
            with open(p, "r", encoding="utf-8") as f:
                self.applied = set(json.load(f).get("ids", []))

    def _save_applied(self):
        p = BASE_DIR / "data" / "applied_51job.json"
        with open(p, "w", encoding="utf-8") as f:
            json.dump({"ids": list(self.applied), "updated": datetime.now().isoformat()}, f)

    def search_jobs(self, keyword: str, city: str = "深圳", page: int = 1) -> list:
        """搜索51job岗位"""
        city_code = CITY_CODES_51JOB.get(city, "040000")
        url = f"https://we.51job.com/pc/search?keyword={keyword}&city={city_code}&page={page}"
        print(f"  [51job] 搜索: {keyword} @ {city}")

        try:
            self.page.get(url)
            time.sleep(random.uniform(3, 5))
            jobs = []
            job_cards = self.page.eles(".joblist-item") or self.page.eles(".job-item") or []
            for card in job_cards[:20]:
                try:
                    title_el = card.ele(".job-title") or card.ele(".jname") or card.ele("h3")
                    company_el = card.ele(".company-name") or card.ele(".cname")
                    salary_el = card.ele(".salary") or card.ele(".sal")
                    link_el = card.ele("a")
                    title = title_el.text.strip() if title_el else ""
                    company = company_el.text.strip() if company_el else ""
                    salary = salary_el.text.strip() if salary_el else ""
                    link = link_el.attr("href") if link_el else ""
                    job_id = hashlib.md5(f"51{company}{title}".encode()).hexdigest()[:12]
                    if job_id and job_id not in self.applied:
                        jobs.append({
                            "job_id": job_id,
                            "title": title,
                            "company": company,
                            "salary": salary,
                            "city": city,
                            "link": link,
                            "platform": "前程无忧",
                        })
                except Exception:
                    continue
            print(f"    找到 {len(jobs)} 个新岗位")
            return jobs
        except Exception as e:
            print(f"    搜索失败: {e}")
            return []

    def apply(self, job: dict) -> bool:
        """投递51job岗位"""
        if job["job_id"] in self.applied:
            return False
        try:
            self.page.get(job["link"])
            time.sleep(2)
            apply_btn = self.page.ele("text:立即申请") or self.page.ele("text:申请职位") or self.page.ele(".btn-apply")
            if apply_btn:
                apply_btn.click()
                time.sleep(2)
                confirm_btn = self.page.ele("text:确定") or self.page.ele("text:提交") or self.page.ele(".btn-submit")
                if confirm_btn:
                    confirm_btn.click()
                    time.sleep(2)
                self.applied.add(job["job_id"])
                self._save_applied()
                print(f"    ✓ 已投递: {job['company']} - {job['title']}")
                return True
            else:
                return False
        except Exception as e:
            print(f"    ✗ 投递失败: {e}")
            return False


# ============================================================
# AI HR对话处理
# ============================================================

def is_ai_hr(text: str) -> bool:
    """检测是否为AI HR"""
    for pattern in AI_HR_PATTERNS:
        if pattern in text:
            return True
    if re.match(r"^(您好|你好|亲|尊敬的).{0,20}(系统|自动|匹配|推荐|筛选)", text):
        return True
    if re.search(r"回复\s*\d+|请\s*(输入|选择|点击|发送)", text):
        return True
    return False


def handle_ai_hr(text: str) -> str:
    """处理AI HR的消息，给出能通过AI筛选的回复"""
    exp_years = PROFILE.get("experience_years", 5)
    brands = "、".join(PROFILE.get("client_brands", ["多个知名品牌"])[:5])
    portfolio = PROFILE.get("personal_links", {}).get("portfolio", "")
    zhihu = PROFILE.get("personal_links", {}).get("zhihu", "")
    zhihu_name = PROFILE.get("personal_links", {}).get("zhihu_name", "")
    latest_job = PROFILE.get("work_history", [{}])[0] if PROFILE.get("work_history") else {}
    latest_company = latest_job.get("company", "某公司")
    latest_role = latest_job.get("role", "某岗位")

    if any(kw in text for kw in ["薪资", "期望", "薪水", "待遇"]):
        return f"{PROFILE.get('expected_salary', '10K-15K')}，具体可以面议"
    if any(kw in text for kw in ["到岗", "入职", "最快", "到职"]):
        return "随时可以到岗"
    if any(kw in text for kw in ["经验", "工作", "做过"]):
        highlights = "、".join([h for job in PROFILE.get("work_history", [])[:2] for h in job.get("highlights", [])[:1]])
        return f"{exp_years}年{PROFILE.get('expected_role', ['品牌策划'])[0]}经验，最近在{latest_company}做{latest_role}（{highlights}），也独立搭建了AI内容工厂（多Agent流水线日产50+篇）"
    if any(kw in text for kw in ["优势", "擅长", "特点"]):
        skills = "、".join(PROFILE.get("skills", [])[:5])
        return f"{skills}。{exp_years}年经验，服务过{brands}等品牌。" + (f"个人作品站：{portfolio} ，知乎/抖音：{zhihu_name}" if portfolio else "")
    if any(kw in text for kw in ["离职", "离开", "上一份"]):
        return "寻求更好的发展平台，希望将经验与AI技术结合创造更大价值"
    if any(kw in text for kw in ["学历", "专业", "毕业"]):
        return f"{PROFILE.get('school', '')}，{PROFILE.get('major', '')}，{PROFILE.get('education', '')}。{exp_years}年实际工作经验远超学历所能体现的价值"
    if any(kw in text for kw in ["城市", "地点", "base"]):
        return f"目前在{PROFILE.get('location', '')}，可以随时到{PROFILE.get('expected_city', '')}"
    if any(kw in text for kw in ["英语", "英文"]):
        return "可以阅读英文文档和英文网站内容，借助AI翻译工具可以进行英文商务沟通"
    if any(kw in text for kw in ["作品", "案例", "portfolio", "项目", "链接"]):
        portfolio_line = f"这是我的个人作品站：{portfolio}。" if portfolio else ""
        zhihu_line = f"知乎「{zhihu_name}」" if zhihu_name else ""
        return f"{portfolio_line}{zhihu_line}期待进一步沟通。"

    # 通用回复
    portfolio_line = f"个人作品站：{portfolio}，" if portfolio else ""
    zhihu_line = f"知乎/抖音：{zhihu_name}" if zhihu_name else ""
    return f"我对这个岗位很感兴趣。{exp_years}年{PROFILE.get('expected_role', ['品牌策划'])[0]}经验，深度使用AI工具搭建内容生产系统。{portfolio_line}{zhihu_line}，期待进一步沟通。"


def handle_human_hr(text: str, company: str, job: str) -> str:
    """处理真人HR的消息"""
    result = generate_reply(text, company_name=company, job_title=job)
    return result["reply"]


# ============================================================
# 主循环
# ============================================================

def main():
    import argparse
    parser = argparse.ArgumentParser(description="全平台求职Agent — 猎聘 + 前程无忧 + Boss直聘聊天")
    parser.add_argument("--once", action="store_true", help="只跑一轮")
    parser.add_argument("--direction", type=int, default=0, help="求职方向: 0=全部 1/2/3=第N个方向")
    parser.add_argument("--city", type=str, default="深圳", help="首选城市")
    parser.add_argument("--max-apply", type=int, default=20, help="最大投递数")
    parser.add_argument("--chat-only", action="store_true", help="只处理消息不搜索")
    parser.add_argument("--apply-only", action="store_true", help="只搜索投递不检查消息")
    args = parser.parse_args()

    print("=" * 60)
    print("  全平台求职Agent启动")
    print(f"  支持平台: 猎聘 + 前程无忧 + Boss直聘(聊天)")
    print("=" * 60)

    if not launch_browser():
        return

    from DrissionPage import ChromiumPage
    page = ChromiumPage(9222)
    print("[浏览器] 已连接\n")

    directions = JOB_DIRECTIONS
    if args.direction > 0 and args.direction <= len(directions):
        directions = [directions[args.direction - 1]]

    liepin = LiepinHunter(page)
    job51 = Job51Hunter(page)

    total_applied = 0
    total_messages = 0

    for direction in directions:
        print(f"\n{'='*60}")
        print(f"  方向: {direction['name']}")
        print(f"{'='*60}")

        cities = args.city.split(",") if "," in args.city else [args.city]

        for city in cities:
            for keyword in direction["keywords"][:2]:
                if total_applied >= args.max_apply:
                    print(f"\n已达到投递上限({args.max_apply})，停止搜索")
                    break

                # 猎聘搜索+投递
                if not args.chat_only:
                    jobs = liepin.search_jobs(keyword, city)
                    for job in jobs:
                        if total_applied >= args.max_apply:
                            break
                        job = liepin.get_job_detail(job)
                        evaluation = evaluate_job(job)
                        job["_evaluation"] = evaluation
                        if evaluation["score"] >= 55 and not evaluation["red_flags"]:
                            print(f"  [{evaluation['score']}分] {job['title']} @ {job['company']}")
                            success = liepin.apply(job)
                            if success:
                                total_applied += 1
                            time.sleep(random.uniform(8, 15))
                        else:
                            flags = evaluation.get("red_flags", [])
                            if flags:
                                print(f"  [跳过 {evaluation['score']}分] {job['company']}: {', '.join(flags[:2])}")

                # 前程无忧（当前有反爬问题，已临时禁用）
                if ENABLE_51JOB and not args.chat_only:
                    jobs = job51.search_jobs(keyword, city)
                    for job in jobs:
                        if total_applied >= args.max_apply:
                            break
                        evaluation = evaluate_job(job)
                        job["_evaluation"] = evaluation
                        if evaluation["score"] >= 55 and not evaluation["red_flags"]:
                            print(f"  [{evaluation['score']}分] {job['title']} @ {job['company']}")
                            success = job51.apply(job)
                            if success:
                                total_applied += 1
                            time.sleep(random.uniform(8, 15))

                if total_applied >= args.max_apply:
                    break
            if total_applied >= args.max_apply:
                break

    # 检查猎聘消息
    if not args.apply_only:
        print(f"\n{'='*60}")
        print("  检查新消息")
        print(f"{'='*60}")
        msgs = liepin.check_messages()
        for msg in msgs:
            total_messages += 1
            text = msg["text"]
            sender = msg["sender"]
            is_ai = is_ai_hr(text)
            tag = "[AI]" if is_ai else "[真人]"
            print(f"  {tag} {sender}: {text[:80]}...")
            reply = handle_ai_hr(text) if is_ai else handle_human_hr(text, sender, "")
            print(f"    → {reply[:80]}...")

    # 统计
    print(f"\n{'='*60}")
    print(f"  本轮完成")
    print(f"  投递: {total_applied}个岗位")
    print(f"  消息: {total_messages}条")
    print(f"{'='*60}")

    log_entry = {
        "time": datetime.now().isoformat(),
        "applied": total_applied,
        "messages": total_messages,
    }
    log_path = BASE_DIR / "data" / "auto_hunt_log.json"
    logs = []
    if log_path.exists():
        with open(log_path, "r", encoding="utf-8") as f:
            logs = json.load(f)
    logs.append(log_entry)
    with open(log_path, "w", encoding="utf-8") as f:
        json.dump(logs, f, ensure_ascii=False, indent=2)

    print("\n完成。")


if __name__ == "__main__":
    main()
