"""
HR聊天应答系统 — 根据HR消息内容智能生成回复
所有个人化信息从 user_profile.json 读取
"""
import json
import re
from pathlib import Path
from datetime import datetime

BASE_DIR = Path(__file__).parent

with open(BASE_DIR / "user_profile.json", "r", encoding="utf-8") as f:
    PROFILE = json.load(f)
with open(BASE_DIR / "config.json", "r", encoding="utf-8") as f:
    CONFIG = json.load(f)


# ============================================================
# 场景分类器
# ============================================================

def classify_hr_message(msg: str) -> str:
    """分析HR消息，判断属于哪种场景"""
    msg_lower = msg.lower()

    scenarios = [
        ("interview_invite", [
            "面试", "面谈", "过来聊聊", "到公司", "见一面", "线下面试", "视频面试",
            "方便过来", "有时间过来", "来我们公司",
        ]),
        ("salary_ask", [
            "期望薪资", "薪资要求", "期望薪水", "工资要求", "薪酬期望",
            "你期望多少", "要多少钱", "期望待遇",
        ]),
        ("ask_experience", [
            "工作经验", "做了多久", "做过什么", "经历", "之前做什么",
            "上一份", "离职原因", "为什么离开",
        ]),
        ("ask_portfolio", [
            "作品", "案例", "portfolio", "看看你的", "代表作",
            "发一些", "有什么项目",
        ]),
        ("greeting", [
            "你好", "您好", "hi", "hello", "在吗", "在么",
            "看了你的简历", "你的简历", "对你感兴趣",
        ]),
        ("schedule_ask", [
            "什么时候", "方便聊聊", "有空吗", "时间方便",
        ]),
        ("self_intro", [
            "我们公司", "我们是", "我们是一家", "公司主营",
        ]),
        ("rejection", [
            "不合适", "抱歉", "遗憾", "不太匹配", "暂时不考虑",
        ]),
    ]

    for scenario, keywords in scenarios:
        for kw in keywords:
            if kw in msg_lower:
                return scenario

    return "general"


# ============================================================
# 格式化工具函数
# ============================================================

def _get_client_brands_str() -> str:
    """获取客户品牌列表的格式化字符串"""
    brands = PROFILE.get("client_brands", [])
    if not brands:
        return "多个知名品牌"
    return "、".join(brands[:5])


def _get_latest_work_summary() -> str:
    """获取最近工作经历的摘要"""
    history = PROFILE.get("work_history", [])
    if not history:
        return f"我有{PROFILE['experience_years']}年行业经验"

    lines = [f"我做了{PROFILE['experience_years']}年{PROFILE.get('expected_role', ['内容策略'])[0]}，最近经历："]
    for job in history[:3]:
        highlights_str = job.get("highlights", [])
        top_highlight = highlights_str[0] if highlights_str else job.get("responsibilities", "")
        lines.append(f"• {job['company']} — {job['role']}：{top_highlight}")
    return "\n".join(lines)


def _get_portfolio_str() -> str:
    """获取作品集介绍"""
    links = PROFILE.get("personal_links", {})
    media = PROFILE.get("self_media", {})

    parts = ["好的！我的部分作品和案例："]
    if links.get("portfolio"):
        parts.append(f"• 个人作品站：{links['portfolio']}")
    if links.get("zhihu"):
        stats = links.get("zhihu_stats", "")
        parts.append(f"• 知乎「{links.get('zhihu_name', '')}」：{links['zhihu']}（{stats}）")
    if links.get("douyin"):
        parts.append(f"• 抖音：{links['douyin']}")

    highlights = PROFILE.get("career_highlights", [])
    if highlights:
        parts.append(f"• 代表项目：{'、'.join(highlights[:3])}")
    parts.append("如果需要看完整的作品集PDF，我也可以发您邮箱。")
    return "\n".join(parts)


# ============================================================
# 应答生成器
# ============================================================

def generate_reply(hr_message: str, conversation_history: list = None, company_name: str = "", job_title: str = "") -> dict:
    """根据HR消息生成回复"""
    scenario = classify_hr_message(hr_message)

    replies = {
        "greeting": _reply_greeting(job_title),
        "salary_ask": _reply_salary(),
        "interview_invite": _reply_interview(),
        "ask_experience": _reply_experience(),
        "ask_portfolio": _reply_portfolio(),
        "schedule_ask": _reply_schedule(),
        "self_intro": _reply_self_intro(),
        "rejection": _reply_rejection(),
        "general": _reply_general(),
    }

    return {
        "scenario": scenario,
        "reply": replies.get(scenario, replies["general"]),
        "timestamp": datetime.now().isoformat(),
    }


def _reply_greeting(job_title: str) -> str:
    brands = _get_client_brands_str()
    zhihu = PROFILE.get("personal_links", {}).get("zhihu", "")
    return (
        f"您好！我对{job_title if job_title else '这个'}岗位很感兴趣。"
        f"我有{PROFILE['experience_years']}年{PROFILE.get('expected_role', ['品牌策划'])[0]}经验，"
        f"服务过{brands}等品牌，擅长品牌策略、内容创意和整合营销。"
        + (f"这是我的知乎主页 {zhihu} ，" if zhihu else "") +
        f"方便的话可以详细聊聊？"
    )


def _reply_salary() -> str:
    return (
        f"基于{PROFILE['experience_years']}年经验和过往项目成果，我的期望薪资在{PROFILE.get('expected_salary', '10K-15K')}之间。"
        f"当然，具体可以根据岗位职责和整体福利来谈。"
        f"方便了解一下贵司的薪资结构吗？基础薪资和绩效的占比是怎样的？"
    )


def _reply_interview() -> str:
    questions = [
        "好的，很期待能进一步沟通。在确认面试时间之前，方便了解一下：",
        "1. 这个岗位的核心KPI或考核指标是怎样的？",
        "2. 团队目前多少人？是新增岗位还是补缺？",
        "3. 贵司的上班时间和休息制度是怎样的？（双休/单休）",
    ]
    return "\n".join(questions)


def _reply_experience() -> str:
    return _get_latest_work_summary() + "\n深度使用AI工具搭建内容生产系统，从策略到执行全链路都能cover。"


def _reply_portfolio() -> str:
    return _get_portfolio_str()


def _reply_schedule(msg: str = "") -> str:
    return "我时间比较灵活，工作日和周末都可以。您看什么时间方便？我们可以约个时间详细聊。"


def _reply_self_intro(msg: str = "", company_name: str = "") -> str:
    return (
        f"了解了，谢谢介绍。我有服务过类似行业的经验，"
        f"对这个方向很感兴趣。方便进一步了解一下这个岗位的具体工作内容和团队情况吗？"
    )


def _reply_rejection() -> str:
    return "好的，感谢您的反馈。如果后续有合适的岗位，欢迎再联系。祝工作顺利！"


def _reply_general(msg: str = "") -> str:
    return (
        f"收到，感谢您的消息。我有{PROFILE['experience_years']}年{PROFILE.get('expected_role', ['品牌策划'])[0]}经验，"
        f"从策略到执行都能负责。方便的话可以多聊聊这个岗位的具体要求？"
    )


# ============================================================
# 反问HR问题生成器
# ============================================================

def generate_followup_questions(scenario: str) -> list:
    """根据场景生成反问HR的问题"""
    question_bank = {
        "first_contact": [
            "请问这个岗位的上班时间是怎样的？双休还是单休？",
            "团队目前有多少人？岗位是新增还是替补？",
        ],
        "interview_invite": [
            "请问这个岗位的核心KPI或考核指标是怎样的？",
            "团队架构是怎样的？向谁汇报？",
            "贵司的工作时间是？双休还是大小周？",
        ],
        "salary_mentioned": [
            "方便了解一下薪资结构吗？基础薪资和绩效的占比？",
            "五险一金是按什么基数缴纳的？",
            "试用期多久？试用期薪资怎么算？",
            "年终奖一般是怎么发的？",
        ],
        "general": [
            "这个岗位日常主要负责哪些板块？",
            "贵司对这个岗位的期望是什么？比如入职3个月希望达成什么？",
        ],
    }
    return question_bank.get(scenario, question_bank["general"])


# ============================================================
# 会话状态管理
# ============================================================

def should_ask_questions(conversation_history: list) -> dict:
    """判断当前是否应该反问HR问题"""
    if not conversation_history:
        return {"should_ask": True, "questions": generate_followup_questions("first_contact")}

    asked_topics = set()
    for msg in conversation_history:
        msg_text = msg.get("text", "") if isinstance(msg, dict) else str(msg)
        if "双休" in msg_text or "单休" in msg_text:
            asked_topics.add("schedule")
        if "薪资结构" in msg_text or "KPI" in msg_text:
            asked_topics.add("salary_structure")
        if "五险一金" in msg_text or "公积金" in msg_text:
            asked_topics.add("benefits")

    pending_questions = []
    if "schedule" not in asked_topics:
        pending_questions.append("请问贵司的上班时间是？双休还是单休？")
    if "salary_structure" not in asked_topics:
        pending_questions.append("方便了解一下薪资结构吗？基础薪资和绩效的占比？")
    if "benefits" not in asked_topics:
        pending_questions.append("五险一金是按什么基数缴纳的？")

    return {
        "should_ask": len(pending_questions) > 0,
        "questions": pending_questions,
    }


# ============================================================
# 批量场景话术库
# ============================================================

RESPONSE_TEMPLATES = {
    "双休确认": "好的，双休的话很合适。那方便了解一下薪资结构和五险一金的缴纳情况吗？",
    "单休回应": "了解。单休的话，薪资方面会有相应的补偿吗？",
    "大小周回应": "明白，大小周可以接受。那方便了解一下薪资结构和KPI考核吗？",
    "薪资太低": f"感谢告知。基于我的经验和过往项目成果，我期望的薪资范围在{PROFILE.get('expected_salary', '10K-15K')}。如果贵司有调整空间，我们可以继续聊；如果没有，也不耽误您时间。",
    "薪资合适": "好的，薪资范围符合我的预期。方便约个时间进一步沟通吗？",
    "需要作品集": f"好的，我的知乎主页有部分作品：{PROFILE.get('personal_links', {}).get('zhihu', '')}。完整作品集可以发您邮箱，方便留个邮箱吗？",
    "约面试时间": "好的，我时间比较灵活。您看什么时间方便？",
    "确认面试": "收到，我会准时到。方便确认一下公司详细地址吗？",
}


if __name__ == "__main__":
    test_messages = [
        "你好，看了你的简历，对我们品牌策划岗位感兴趣吗？",
        "你的期望薪资是多少？",
        "方便过来面试吗？",
        "发一些你的作品看看",
    ]
    for msg in test_messages:
        result = generate_reply(msg, company_name="某广告公司", job_title="品牌策划")
        print(f"\nHR: {msg}")
        print(f"场景: {result['scenario']}")
        print(f"回复: {result['reply']}")
        print("-" * 50)
