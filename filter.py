"""
公司/岗位评估过滤器 — 自动识别坑爹公司
"""
import json
import re
from pathlib import Path

BASE_DIR = Path(__file__).parent

with open(BASE_DIR / "config.json", "r", encoding="utf-8") as f:
    CONFIG = json.load(f)


# ============================================================
# 红旗检测（自动排除）
# ============================================================

RED_FLAGS = CONFIG["red_flags"]["keywords"]
RED_FLAG_NAME_PATTERNS = CONFIG["red_flags"]["company_name_patterns"]
RED_FLAG_SALARY = CONFIG["red_flags"]["salary_structure_issues"]

# 好公司加分关键词
GREEN_FLAGS = [
    "五险一金", "双休", "年终奖", "带薪年假", "弹性工作",
    "公积金", "补充医疗", "餐补", "交通补贴", "定期体检",
    "试用期全额", "全额缴纳", "13薪", "14薪", "15薪", "16薪",
    "上市公司", "B轮", "C轮", "D轮", "已上市", "不需要融资",
    "扁平管理", "大牛", "技术氛围",
]

# 常见坑爹公司类型
BAD_COMPANY_PATTERNS = [
    (r"(?:保险|金融|理财|贷款|担保|投资|期货|证券|基金).{0,5}(?:代理|经纪|咨询|服务)", "疑似金融代理/理财公司"),
    (r"(?:直销|会销|电销|网销|电话销售)", "销售型公司包装成品牌岗"),
    (r"(?:文化传|影视传|广告传).{0,3}媒.{0,5}(?:有限)?公司", "名字可疑的文化传媒公司（需进一步确认）"),
    (r"(?:人力|劳务|外包|派遣)", "人力资源外包公司（非甲方）"),
    (r"入职.{0,5}(?:交|收|付).{0,5}(?:费|钱|押金|保证金|培训费)", "入职收费 = 骗子公司"),
    (r"(?:试用|实习).{0,5}(?:免费|无薪|无工资)", "试用期免费 = 违法"),
]


def evaluate_job(job_info: dict) -> dict:
    """评估一个岗位是否值得投递

    job_info = {
        "title": "品牌策划",
        "company": "某公司",
        "salary": "8K-12K",
        "city": "东莞",
        "experience": "3-5年",
        "education": "大专",
        "description": "...",
        "company_info": {...},
        "hr_info": {...},
    }
    """
    result = {
        "score": 50,
        "verdict": "neutral",
        "red_flags": [],
        "green_flags": [],
        "warnings": [],
        "recommendation": "",
        "auto_apply": False,
    }

    desc = job_info.get("description", "")
    company = job_info.get("company", "")
    salary = job_info.get("salary", "")
    title = job_info.get("title", "")
    company_info = job_info.get("company_info", {})
    hr_info = job_info.get("hr_info", {})

    # 1. 红旗检查（一票否决）
    desc_full = f"{title} {company} {salary} {desc}"
    for flag in RED_FLAGS:
        if flag in desc_full:
            result["red_flags"].append(f"关键词红旗: {flag}")
            result["score"] -= 30

    # 检查公司名称
    for pattern, reason in BAD_COMPANY_PATTERNS:
        if re.search(pattern, company):
            result["red_flags"].append(reason)
            result["score"] -= 25

    # 2. 薪资检查
    salary_result = evaluate_salary(salary)
    result["red_flags"].extend(salary_result.get("red_flags", []))
    result["score"] += salary_result.get("score_delta", 0)

    # 3. JD质量检查
    jd_result = evaluate_jd(desc)
    result["warnings"].extend(jd_result.get("warnings", []))
    result["green_flags"].extend(jd_result.get("green_flags", []))
    result["score"] += jd_result.get("score_delta", 0)

    # 4. 公司信息检查
    if company_info:
        company_result = evaluate_company_info(company_info)
        result["green_flags"].extend(company_result.get("green_flags", []))
        result["red_flags"].extend(company_result.get("red_flags", []))
        result["score"] += company_result.get("score_delta", 0)

    # 5. HR信息检查（HR活跃度、回复率等）
    if hr_info:
        hr_result = evaluate_hr(hr_info)
        result["score"] += hr_result.get("score_delta", 0)

    # 6. 绿色关键词加分
    for flag in GREEN_FLAGS:
        if flag in desc_full:
            result["green_flags"].append(flag)
            result["score"] += 3

    # 7. 标题匹配度
    preferred_titles = CONFIG["job_preferences"]["titles"]
    exclude_titles = CONFIG["job_preferences"]["exclude_titles"]
    title_match = any(t in title for t in preferred_titles)
    title_exclude = any(t in title for t in exclude_titles)
    if title_match:
        result["score"] += 10
    if title_exclude:
        result["score"] -= 20

    # 8. 城市匹配
    preferred_cities = CONFIG["job_preferences"]["cities"]
    city = job_info.get("city", "")
    if any(c in city for c in preferred_cities):
        result["score"] += 10
    else:
        result["score"] -= 30

    # 最终判定
    score = max(0, min(100, result["score"]))
    result["score"] = score

    if result["red_flags"]:
        result["verdict"] = "skip"
        result["recommendation"] = f"存在红旗({len(result['red_flags'])}项)，建议跳过"
        result["auto_apply"] = False
    elif score >= 75:
        result["verdict"] = "strong_match"
        result["recommendation"] = "高度匹配，建议优先投递"
        result["auto_apply"] = CONFIG["auto_apply"]
    elif score >= 60:
        result["verdict"] = "good_match"
        result["recommendation"] = "匹配度良好，可以投递"
        result["auto_apply"] = CONFIG["auto_apply"]
    elif score >= 45:
        result["verdict"] = "maybe"
        result["recommendation"] = "匹配度一般，可作为备选"
        result["auto_apply"] = False
    else:
        result["verdict"] = "skip"
        result["recommendation"] = "匹配度低，建议跳过"
        result["auto_apply"] = False

    return result


def evaluate_salary(salary_text: str) -> dict:
    """评估薪资是否合理"""
    result = {"red_flags": [], "score_delta": 0}

    if not salary_text:
        result["red_flags"].append("未标注薪资")
        result["score_delta"] -= 15
        return result

    numbers = re.findall(r"(\d+)", salary_text.replace("K", "000").replace("k", "000"))
    if len(numbers) >= 2:
        low = int(numbers[0])
        high = int(numbers[1])
        # 如果是K为单位
        if "K" in salary_text.upper() or "k" in salary_text:
            low *= 1000
            high *= 1000

        if low < CONFIG["job_preferences"]["min_salary"]:
            result["score_delta"] -= 10
        if high >= CONFIG["job_preferences"]["min_salary"] * 1.5:
            result["score_delta"] += 5

    if "面议" in salary_text and "范围" not in salary_text:
        result["red_flags"].append("薪资面议且未注明范围")

    for issue in RED_FLAG_SALARY:
        if issue in salary_text:
            result["red_flags"].append(f"薪资问题: {issue}")
            result["score_delta"] -= 20

    return result


def evaluate_jd(desc: str) -> dict:
    """评估JD质量"""
    result = {"warnings": [], "green_flags": [], "score_delta": 0}

    # JD太短 = 不专业
    if len(desc) < 100:
        result["warnings"].append("JD过于简短（<100字），岗位描述不清晰")
        result["score_delta"] -= 15
    elif len(desc) > 500:
        result["green_flags"].append("JD详细完整")
        result["score_delta"] += 10

    # 检查是否有岗位职责和任职要求
    has_responsibility = any(kw in desc for kw in ["岗位职责", "工作内容", "职责描述", "你要做", "负责"])
    has_requirement = any(kw in desc for kw in ["任职要求", "岗位要求", "我们需要", "希望你", "要求"])
    if has_responsibility and has_requirement:
        result["score_delta"] += 8

    # 纯岗位JD没有写公司情况的
    if "公司" not in desc and "我们" not in desc:
        result["warnings"].append("JD中缺乏公司介绍")

    # 识别"全能型"JD（什么都要做 = 坑）
    overload_keywords = ["独立负责", "从0到1", "搭建体系", "全盘负责", "统筹", "全面负责"]
    overload_count = sum(1 for kw in overload_keywords if kw in desc)
    if overload_count >= 3:
        result["warnings"].append("JD要求过于全面，可能是全栈打杂岗")

    return result


def evaluate_company_info(info: dict) -> dict:
    """评估公司信息"""
    result = {"green_flags": [], "red_flags": [], "score_delta": 0}

    scale = info.get("scale", "")
    industry = info.get("industry", "")
    stage = info.get("stage", "")

    # 公司规模
    if any(s in scale for s in ["100-499", "500-999", "1000-9999", "10000"]):
        result["score_delta"] += 5
    elif any(s in scale for s in ["0-20", "20-99"]):
        result["score_delta"] -= 3

    # 融资阶段
    if any(s in stage for s in ["已上市", "D轮", "C轮", "不需要融资"]):
        result["green_flags"].append(f"融资阶段: {stage}")
        result["score_delta"] += 8
    elif any(s in stage for s in ["未融资", "天使轮", "A轮"]):
        if "0-20" in scale:
            result["red_flags"].append("初创公司+小规模，风险较高")

    # 排除行业
    exclude_industries = CONFIG["job_preferences"]["exclude_industries"]
    for ei in exclude_industries:
        if ei in industry:
            result["red_flags"].append(f"排除行业: {ei}")
            result["score_delta"] -= 30

    return result


def evaluate_hr(hr_info: dict) -> dict:
    """评估HR活跃度"""
    result = {"score_delta": 0}

    # HR活跃度高 = 加分
    active_status = hr_info.get("active_status", "")
    if "今日" in active_status or "在线" in active_status:
        result["score_delta"] += 5

    reply_rate = hr_info.get("reply_rate", "")
    if reply_rate:
        try:
            rate = int(re.sub(r"[^0-9]", "", reply_rate))
            if rate >= 80:
                result["score_delta"] += 5
            elif rate < 50:
                result["score_delta"] -= 3
        except ValueError:
            pass

    return result


def filter_jobs(jobs: list) -> dict:
    """批量过滤岗位，分类返回"""
    result = {
        "strong_matches": [],
        "good_matches": [],
        "maybe": [],
        "skip": [],
        "auto_apply": [],
    }

    for job in jobs:
        evaluation = evaluate_job(job)
        job["_evaluation"] = evaluation

        verdict = evaluation["verdict"]
        if verdict == "strong_match":
            result["strong_matches"].append(job)
            if evaluation["auto_apply"]:
                result["auto_apply"].append(job)
        elif verdict == "good_match":
            result["good_matches"].append(job)
            if evaluation["auto_apply"]:
                result["auto_apply"].append(job)
        elif verdict == "maybe":
            result["maybe"].append(job)
        else:
            result["skip"].append(job)

    return result


def format_evaluation_report(job_info: dict) -> str:
    """格式化评估报告"""
    ev = job_info.get("_evaluation", {})
    lines = [
        f"【{ev.get('verdict', 'unknown')}】{job_info.get('title', '未知')} @ {job_info.get('company', '未知')}",
        f"  薪资: {job_info.get('salary', '未标注')} | 城市: {job_info.get('city', '未知')}",
        f"  评分: {ev.get('score', 0)}/100",
    ]

    if ev.get("green_flags"):
        lines.append(f"  优点: {', '.join(ev['green_flags'][:5])}")
    if ev.get("red_flags"):
        lines.append(f"  红旗: {', '.join(ev['red_flags'][:5])}")
    if ev.get("warnings"):
        lines.append(f"  注意: {', '.join(ev['warnings'][:5])}")
    lines.append(f"  建议: {ev.get('recommendation', '')}")
    return "\n".join(lines)


if __name__ == "__main__":
    test_jobs = [
        {
            "title": "品牌策划经理",
            "company": "某品牌管理有限公司",
            "salary": "12K-18K",
            "city": "东莞",
            "description": "岗位职责：1. 负责品牌全案策划 2. 整合营销传播方案制定 3. 团队管理。任职要求：5年以上品牌策划经验，熟悉快消行业。公司福利：五险一金、双休、年终奖。",
            "company_info": {"scale": "100-499人", "industry": "广告/公关/会展", "stage": "不需要融资"},
            "hr_info": {"active_status": "今日活跃", "reply_rate": "90%"},
        },
        {
            "title": "文案策划助理",
            "company": "XX保险代理有限公司",
            "salary": "面议",
            "city": "东莞",
            "description": "负责文案撰写，要求吃苦耐劳，有责任心。",
            "company_info": {"scale": "0-20人", "industry": "金融", "stage": "未融资"},
            "hr_info": {"active_status": "3天前活跃", "reply_rate": "30%"},
        },
    ]
    for job in test_jobs:
        ev = evaluate_job(job)
        job["_evaluation"] = ev
        print(format_evaluation_report(job))
        print()
