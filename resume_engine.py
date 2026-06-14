"""
简历优化引擎 — 根据JD自动调整简历关键词和重点
所有个人化信息从 user_profile.json 读取
"""
import json
import re
from pathlib import Path

BASE_DIR = Path(__file__).parent

with open(BASE_DIR / "user_profile.json", "r", encoding="utf-8") as f:
    PROFILE = json.load(f)


def extract_keywords(jd_text: str) -> dict:
    """从JD中提取关键词并分类"""
    categories = {
        "hard_skills": [],
        "soft_skills": [],
        "tools": [],
        "industry": [],
        "role_type": [],
    }

    skill_map = {
        "hard_skills": [
            "品牌策略", "品牌定位", "品牌策划", "全案策划", "整合营销",
            "内容策略", "内容营销", "文案策划", "创意策划", "TVC",
            "宣传片", "短视频", "直播", "新媒体运营", "社交媒体",
            "SEO", "SEM", "信息流", "私域运营", "用户增长",
            "活动策划", "事件营销", "跨界合作", "IP联名",
            "项目管理", "团队管理", "客户对接",
        ],
        "soft_skills": [
            "沟通能力", "逻辑思维", "创意能力", "数据分析", "用户洞察",
            "策略思维", "审美能力", "抗压能力", "自驱力", "学习能力",
            "独立负责", "结果导向",
        ],
        "tools": [
            "ChatGPT", "AI", "Midjourney", "Stable Diffusion", "D-ID",
            "Photoshop", "Premiere", "剪映", "AE",
            "SEMrush", "GoogleTrends", "Ahrefs", "GoogleAds",
            "Excel", "PPT", "飞书", "企微",
        ],
        "industry": [
            "快消", "餐饮", "地产", "房地产", "零售", "医疗", "互联网",
            "食品饮料", "美妆", "3C", "家电", "汽车", "金融", "教育",
        ],
        "role_type": [
            "品牌主管", "品牌经理", "文案指导", "创意组长", "资深文案",
            "高级文案", "策划经理", "内容负责人", "品牌总监",
        ],
    }

    for category, keywords in skill_map.items():
        for kw in keywords:
            if kw.lower() in jd_text.lower():
                categories[category].append(kw)

    return categories


def extract_requirements(jd_text: str) -> dict:
    """提取JD中的硬性要求"""
    requirements = {
        "experience_years": None,
        "education": None,
        "must_have": [],
        "nice_to_have": [],
    }

    exp_match = re.search(r"(\d+)[\s-]*年.*?(经验|工作)", jd_text)
    if exp_match:
        requirements["experience_years"] = int(exp_match.group(1))

    edu_keywords = ["本科", "大专", "硕士", "博士", "学历不限"]
    for edu in edu_keywords:
        if edu in jd_text:
            requirements["education"] = edu
            break

    required_section = re.findall(r"(?:必须|要求|需要|具备)[：:]?\s*(.+?)(?:[。；;]|\n)", jd_text)
    requirements["must_have"] = required_section

    return requirements


def tailor_resume_sections(jd_text: str) -> dict:
    """根据JD调整简历各部分内容"""
    keywords = extract_keywords(jd_text)
    reqs = extract_requirements(jd_text)

    # 匹配工作经历重点
    matched_highlights = []
    for job in PROFILE.get("work_history", []):
        job_matches = []
        for h in job.get("highlights", []):
            score = 0
            for cat in ["hard_skills", "tools", "industry"]:
                for kw in keywords[cat]:
                    if kw.lower() in h.lower():
                        score += 2
            if score > 0:
                job_matches.append((score, h))
        job_matches.sort(key=lambda x: x[0], reverse=True)
        matched_highlights.append({
            "company": job["company"],
            "role": job["role"],
            "period": job["period"],
            "highlights": [h for _, h in job_matches[:3]] if job_matches else job.get("highlights", [])[:2],
            "relevance_score": sum(s for s, _ in job_matches),
        })

    matched_highlights.sort(key=lambda x: x["relevance_score"], reverse=True)

    personal_advantage = generate_personal_advantage(keywords, reqs)

    return {
        "keywords_matched": keywords,
        "requirements": reqs,
        "tailored_work_history": matched_highlights[:4],
        "personal_advantage": personal_advantage,
        "match_score": calculate_match_score(keywords, reqs),
    }


def generate_personal_advantage(keywords: dict, reqs: dict) -> str:
    """生成针对JD的个人优势描述"""
    parts = []

    exp = reqs.get("experience_years") or 5
    actual_exp = PROFILE.get("experience_years", 0)
    if actual_exp >= exp:
        parts.append(f"{actual_exp}年{PROFILE.get('expected_role', ['品牌'])[0]}经验")

    matched_skills = keywords.get("hard_skills", [])[:4]
    if matched_skills:
        parts.append(f"擅长{'、'.join(matched_skills)}")

    matched_tools = keywords.get("tools", [])[:3]
    if matched_tools:
        parts.append(f"熟练使用{'、'.join(matched_tools)}")

    matched_industry = keywords.get("industry", [])[:2]
    if matched_industry:
        parts.append(f"有{'、'.join(matched_industry)}行业服务经验")

    media = PROFILE.get("self_media", {})
    if media.get("zhihu"):
        parts.append(f"知乎{media['zhihu']}")

    return "；".join(parts) + "。"


def calculate_match_score(keywords: dict, reqs: dict) -> int:
    """计算岗位匹配度评分"""
    score = 0
    score += len(keywords["hard_skills"]) * 10
    score += len(keywords["soft_skills"]) * 3
    score += len(keywords["tools"]) * 5
    score += len(keywords["industry"]) * 8

    exp_required = reqs.get("experience_years") or 0
    if PROFILE.get("experience_years", 0) >= exp_required:
        score += 15

    edu = reqs.get("education") or ""
    if edu in ["大专", "学历不限"]:
        score += 10
    elif edu == "本科":
        score += 5

    return min(score, 100)


def generate_boss_greeting(jd_text: str, job_title: str, company_name: str) -> str:
    """生成B***打招呼话术"""
    tailored = tailor_resume_sections(jd_text)
    keywords_list = tailored["keywords_matched"]["hard_skills"][:4]
    kw_str = "、".join(keywords_list) if keywords_list else "品牌全案策划"

    brands = "、".join(PROFILE.get("client_brands", ["多个知名品牌"])[:5])
    zhihu = PROFILE.get("personal_links", {}).get("zhihu", "")
    exp_years = PROFILE.get("experience_years", 5)

    templates = [
        f"您好，看到贵司在招{job_title}，我有{exp_years}年{kw_str}经验，"
        f"服务过{brands}等品牌，做过百万曝光的传播项目。"
        + (f"这是我的知乎主页 {zhihu} ，" if zhihu else "") +
        f"期待和您聊聊。",

        f"你好，我对{job_title}这个岗位很感兴趣。我做了{exp_years}年内容策略和品牌策划，"
        f"擅长{kw_str}。深度使用AI工具搭建内容生产系统，希望能详细沟通。",

        f"您好，我做了{exp_years}年品牌内容全链路，经历过{kw_str}。"
        f"同时搭建了AI内容工厂，单人多Agent日产50+篇。看到贵司岗位比较匹配，方便聊聊吗？",
    ]

    scores = [tailored["match_score"] % 3, (tailored["match_score"] + 1) % 3, (tailored["match_score"] + 2) % 3]
    idx = scores.index(max(scores))
    return templates[idx]


def generate_tailored_resume_text(jd_text: str, job_title: str, company_name: str) -> str:
    """生成针对JD的完整简历文本"""
    tailored = tailor_resume_sections(jd_text)

    lines = []
    lines.append(f"{PROFILE.get('name', '')} | {PROFILE.get('gender', '')} | {PROFILE.get('age', '')}岁 | {PROFILE.get('experience_years', '')}年经验 | 期望城市：{PROFILE.get('expected_city', '')}")
    lines.append(f"手机：{PROFILE.get('phone', '')} | 邮箱：{PROFILE.get('email', '')}")
    zhihu = PROFILE.get("personal_links", {}).get("zhihu", "")
    zhihu_stats = PROFILE.get("personal_links", {}).get("zhihu_stats", "")
    if zhihu:
        lines.append(f"知乎：{zhihu}（{zhihu_stats}）")
    lines.append("")

    lines.append("【个人优势】")
    lines.append(tailored["personal_advantage"])
    lines.append("")

    lines.append("【工作经历】")
    for job in tailored["tailored_work_history"]:
        lines.append(f"■ {job['company']} | {job['role']} | {job['period']}")
        for h in job.get("highlights", []):
            lines.append(f"  • {h}")
        lines.append("")

    lines.append("【自媒体/个人IP】")
    media = PROFILE.get("self_media", {})
    if media.get("zhihu"):
        lines.append(f"• 知乎「{PROFILE.get('personal_links', {}).get('zhihu_name', '')}」：{media['zhihu']}")
    if media.get("wechat"):
        lines.append(f"• {media['wechat']}")
    if media.get("portfolio"):
        lines.append(f"• 作品站：{media['portfolio']}")
    lines.append("")

    lines.append("【技能工具】")
    skills = PROFILE.get("skills", [])
    if skills:
        lines.append("• " + "、".join(skills[:8]))

    return "\n".join(lines)


if __name__ == "__main__":
    sample_jd = """
    品牌策划经理
    岗位职责：
    1. 负责品牌全案策划，包括品牌定位、核心价值体系搭建
    2. 整合营销传播方案制定与执行
    3. 新媒体内容策略规划
    要求：5年以上品牌策划经验，熟悉快消行业，有团队管理经验
    """
    result = tailor_resume_sections(sample_jd)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print("\n=== 打招呼话术 ===")
    print(generate_boss_greeting(sample_jd, "品牌策划经理", "某快消公司"))
