"""
求职自动化主循环 — 10分钟扫描一次，自动投递+回复
用法: python main.py
"""
import json
import time
import random
import signal
import sys
from pathlib import Path
from datetime import datetime, timedelta

BASE_DIR = Path(__file__).parent

with open(BASE_DIR / "config.json", "r", encoding="utf-8") as f:
    CONFIG = json.load(f)

from zhipin import BossZhipinSession
from responder import generate_reply, should_ask_questions
from filter import evaluate_job, filter_jobs, format_evaluation_report
from resume_engine import generate_boss_greeting


# ============================================================
# 日志系统
# ============================================================

LOG_FILE = BASE_DIR / "data" / "run.log"

def log(msg: str, level: str = "INFO"):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] [{level}] {msg}"
    print(line)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")


# ============================================================
# 统计追踪
# ============================================================

class Stats:
    def __init__(self):
        self.path = BASE_DIR / "data" / "stats.json"
        self.data = self._load()

    def _load(self):
        if self.path.exists():
            with open(self.path, "r", encoding="utf-8") as f:
                return json.load(f)
        return {
            "started_at": datetime.now().isoformat(),
            "cycles": 0,
            "total_applications": 0,
            "total_replies": 0,
            "interviews_got": 0,
            "daily": {},
        }

    def save(self):
        self.data["updated_at"] = datetime.now().isoformat()
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)

    def record_application(self):
        self.data["total_applications"] += 1
        today = datetime.now().strftime("%Y-%m-%d")
        if today not in self.data["daily"]:
            self.data["daily"][today] = {"applications": 0, "replies": 0}
        self.data["daily"][today]["applications"] += 1

    def record_reply(self):
        self.data["total_replies"] += 1
        today = datetime.now().strftime("%Y-%m-%d")
        if today not in self.data["daily"]:
            self.data["daily"][today] = {"applications": 0, "replies": 0}
        self.data["daily"][today]["replies"] += 1

    def daily_application_count(self) -> int:
        today = datetime.now().strftime("%Y-%m-%d")
        return self.data.get("daily", {}).get(today, {}).get("applications", 0)


# ============================================================
# 主循环
# ============================================================

class JobHunter:
    def __init__(self):
        self.session = None
        self.stats = Stats()
        self.running = True
        self.scan_interval = CONFIG["scan_interval_seconds"]

        # 注册信号处理
        signal.signal(signal.SIGINT, self._shutdown)
        signal.signal(signal.SIGTERM, self._shutdown)

    def _shutdown(self, signum, frame):
        log("收到退出信号，正在安全退出...")
        self.running = False

    def _init_session(self) -> bool:
        """初始化Boss直聘会话"""
        cookie_path = BASE_DIR / "data" / "cookies.json"
        if not cookie_path.exists():
            log("未找到Cookie文件！请在 data/cookies.json 中设置Boss直聘Cookie", "ERROR")
            log("获取方法：浏览器登录zhipin.com → F12 → Application → Cookies → 复制所有cookie值", "INFO")
            return False

        with open(cookie_path, "r", encoding="utf-8") as f:
            cookies = json.load(f)

        self.session = BossZhipinSession(cookies)
        if self.session.is_authenticated():
            log("Boss直聘登录成功 ✓")
            return True
        else:
            log("Cookie已过期！请重新从浏览器复制Cookie", "ERROR")
            return False

    def scan_messages(self):
        """扫描HR消息并回复"""
        log("扫描HR消息中...")
        messages = self.session.scan_messages()

        if not messages:
            log("没有新消息")
            return

        log(f"发现 {len(messages)} 条新消息/新对话")

        for msg in messages:
            boss_id = msg["boss_id"]
            boss_name = msg["boss_name"]
            company = msg.get("company", "未知")
            job_title = msg.get("job_title", "")
            last_msg = msg["last_message"]

            log(f"  [{boss_name}] {company} - {last_msg[:60]}...")

            # 检查黑名单
            if company in self.session.blacklist:
                log(f"  公司在黑名单中，跳过")
                continue

            # 获取聊天历史
            history = self.session.get_chat_history(boss_id)

            # 生成回复
            reply_result = generate_reply(last_msg, history, company, job_title)
            reply_text = reply_result["reply"]

            # 追加反问
            followup = should_ask_questions(history)
            if followup["should_ask"]:
                reply_text += "\n\n" + "\n".join(followup["questions"])

            log(f"  场景: {reply_result['scenario']} → 回复: {reply_text[:80]}...")

            # 发送回复
            if CONFIG["auto_reply"]:
                delay = random.randint(CONFIG["reply_delay_min"], CONFIG["reply_delay_max"])
                time.sleep(delay)
                self.session.send_message(boss_id, reply_text)
                self.stats.record_reply()

    def scan_jobs(self):
        """扫描岗位并投递"""
        today_count = self.stats.daily_application_count()
        daily_limit = CONFIG["max_daily_applications"]

        if today_count >= daily_limit:
            log(f"今日已投递 {today_count}/{daily_limit}，达到上限，跳过岗位扫描")
            return

        log(f"扫描岗位中（今日已投递 {today_count}/{daily_limit}）...")

        keywords = CONFIG["job_preferences"]["titles"]
        # 随机选择2-3个关键词搜索，避免每次都搜所有
        search_kw = random.sample(keywords, min(3, len(keywords)))
        log(f"  搜索关键词: {search_kw}")

        all_jobs = []
        for kw in search_kw:
            jobs = self.session.search_jobs(keyword=kw, city=CONFIG["job_preferences"]["cities"][0])
            all_jobs.extend(jobs)
            time.sleep(random.uniform(3, 6))

        # 去重
        seen = set()
        unique_jobs = []
        for job in all_jobs:
            jid = job.get("job_id")
            if jid and jid not in seen and jid not in self.session.applied_jobs:
                seen.add(jid)
                unique_jobs.append(job)

        log(f"  去重后 {len(unique_jobs)} 个新岗位")

        # 评估过滤
        filtered = filter_jobs(unique_jobs)
        log(f"  强匹配: {len(filtered['strong_matches'])}, 好匹配: {len(filtered['good_matches'])}, 备选: {len(filtered['maybe'])}, 跳过: {len(filtered['skip'])}")

        # 显示跳过的理由
        for job in filtered["skip"][:3]:
            ev = job.get("_evaluation", {})
            flags = ev.get("red_flags", [])
            if flags:
                log(f"  ✗ {job.get('company', '?')}: {', '.join(flags[:2])}")

        # 自动投递
        auto_apply_list = filtered["auto_apply"]
        remaining = daily_limit - today_count
        auto_apply_list = auto_apply_list[:remaining]

        if not auto_apply_list:
            log("没有需要自动投递的岗位")
            return

        log(f"准备自动投递 {len(auto_apply_list)} 个岗位...")

        for job in auto_apply_list:
            if self.stats.daily_application_count() >= daily_limit:
                break

            ev = job.get("_evaluation", {})
            log(f"\n{format_evaluation_report(job)}")

            greeting = generate_boss_greeting(
                job.get("description", ""),
                job.get("title", ""),
                job.get("company", ""),
            )

            success = self.session.apply_job(job, greeting)
            if success:
                self.stats.record_application()

            # 投递间隔（重要！避免风控）
            delay = random.uniform(15, 40)
            log(f"等待 {delay:.0f}秒...")
            time.sleep(delay)

    def print_status(self):
        """打印当前状态"""
        today = datetime.now().strftime("%Y-%m-%d")
        daily = self.stats.data.get("daily", {}).get(today, {})
        print(f"""
╔══════════════════════════════════════╗
║        求职自动化运行中              ║
╠══════════════════════════════════════╣
║  运行周期: {self.stats.data['cycles']:>5}                     ║
║  今日投递: {daily.get('applications', 0):>5} / {CONFIG['max_daily_applications']:<3}               ║
║  今日回复: {daily.get('replies', 0):>5}                     ║
║  累计投递: {self.stats.data['total_applications']:>5}                     ║
║  累计回复: {self.stats.data['total_replies']:>5}                     ║
║  扫描间隔: {self.scan_interval}s ({self.scan_interval // 60}分钟)           ║
╚══════════════════════════════════════╝
""")

    def run_once(self):
        """执行一次扫描循环"""
        start = time.time()
        cycle = self.stats.data["cycles"] + 1
        self.stats.data["cycles"] = cycle
        self.stats.save()

        log(f"===== 第 {cycle} 轮扫描 =====")

        try:
            self.scan_messages()
        except Exception as e:
            log(f"消息扫描异常: {e}", "ERROR")

        try:
            if CONFIG["auto_apply"]:
                self.scan_jobs()
        except Exception as e:
            log(f"岗位扫描异常: {e}", "ERROR")

        elapsed = time.time() - start
        log(f"本轮耗时 {elapsed:.0f}秒")
        self.print_status()

    def run(self):
        """主循环"""
        log("=" * 50)
        log("求职自动化系统启动")
        log("=" * 50)

        if not self._init_session():
            log("无法初始化会话，请先配置Cookie后重新运行", "ERROR")
            log("1. 浏览器打开 zhipin.com 并登录", "INFO")
            log("2. F12 → Application → Cookies → 复制所有cookie", "INFO")
            log("3. 运行: python -c \"from zhipin import save_cookies_from_browser; save_cookies_from_browser('你的cookie字符串')\"", "INFO")
            return

        self.print_status()
        log(f"扫描间隔: {self.scan_interval}秒 ({self.scan_interval // 60}分钟)")
        log(f"自动投递: {'开' if CONFIG['auto_apply'] else '关'}")
        log(f"自动回复: {'开' if CONFIG['auto_reply'] else '关'}")
        log(f"每日投递上限: {CONFIG['max_daily_applications']}")
        log("按 Ctrl+C 停止运行\n")

        while self.running:
            try:
                self.run_once()
            except Exception as e:
                log(f"扫描循环异常: {e}", "ERROR")
                import traceback
                traceback.print_exc()

            if self.running:
                next_run = datetime.now() + timedelta(seconds=self.scan_interval)
                log(f"下次扫描: {next_run.strftime('%H:%M:%S')}")
                # 分段sleep，每30秒检查一次是否要退出
                for _ in range(self.scan_interval // 30):
                    if not self.running:
                        break
                    time.sleep(30)
                # 剩余秒数
                remaining = self.scan_interval % 30
                if remaining > 0 and self.running:
                    time.sleep(remaining)

        log("求职自动化系统已停止")
        self.stats.save()


# ============================================================
# CLI入口
# ============================================================

def print_usage():
    print("""
求职自动化系统 - 使用说明
==========================

首次使用:
  1. 浏览器打开 zhipin.com 并登录
  2. F12 → Application → Cookies → 复制所有cookie
  3. 运行: python main.py --set-cookie "你的cookie字符串"

日常运行:
  python main.py                    # 正常模式（10分钟扫描）
  python main.py --once             # 只扫描一次
  python main.py --interval 300     # 自定义间隔（5分钟=300秒）
  python main.py --no-auto-apply    # 只回复消息，不自动投递
  python main.py --no-auto-reply    # 只投递，不自动回复
  python main.py --status           # 查看统计

配置:
  编辑 config.json 可以调整:
  - job_preferences: 岗位偏好（城市、薪资、行业等）
  - scan_interval_seconds: 扫描间隔
  - max_daily_applications: 每日投递上限
  - red_flags: 公司红旗关键词
""")


def main():
    import argparse

    parser = argparse.ArgumentParser(description="求职自动化系统")
    parser.add_argument("--once", action="store_true", help="只运行一次扫描")
    parser.add_argument("--interval", type=int, default=None, help="扫描间隔（秒）")
    parser.add_argument("--no-auto-apply", action="store_true", help="不自动投递")
    parser.add_argument("--no-auto-reply", action="store_true", help="不自动回复")
    parser.add_argument("--set-cookie", type=str, default=None, help="设置Boss直聘Cookie")
    parser.add_argument("--status", action="store_true", help="查看运行统计")
    parser.add_argument("--dry-run", action="store_true", help="试运行（不实际发送）")

    args = parser.parse_args()

    # 设置Cookie
    if args.set_cookie:
        from zhipin import save_cookies_from_browser
        save_cookies_from_browser(args.set_cookie)
        print("Cookie已保存，现在可以运行 python main.py 启动系统")
        return

    # 查看统计
    if args.status:
        stats = Stats()
        print(json.dumps(stats.data, ensure_ascii=False, indent=2))
        return

    # 覆盖配置
    if args.interval:
        CONFIG["scan_interval_seconds"] = args.interval
    if args.no_auto_apply:
        CONFIG["auto_apply"] = False
    if args.no_auto_reply:
        CONFIG["auto_reply"] = False
    if args.dry_run:
        CONFIG["auto_apply"] = False
        CONFIG["auto_reply"] = False
        print("[试运行模式] 不会实际发送消息或投递")

    hunter = JobHunter()
    hunter.scan_interval = CONFIG["scan_interval_seconds"]

    if args.once:
        if not hunter._init_session():
            return
        hunter.run_once()
    else:
        hunter.run()


if __name__ == "__main__":
    main()
