# 🤖 JobHunter — 全平台自动求职，睡觉时也在投简历

> **金山齐达内** 用这个工具，从失业到拿 Offer，全程自动化。
> 知乎 60 万+ 阅读作者 | 文案 AI 工坊主理人 | [个人作品站](https://luxury-torrone-364f29.netlify.app/)

[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.10%2B-green.svg)]()

---

## 🎯 这个工具做什么

**三个招聘平台全自动求职**——自动搜索岗位 → 智能评估过滤 → 自动投递 → HR消息自动回复 → 反问关键问题 → 追踪统计。

| 平台 | 方式 | 支持功能 |
|------|------|------|
| 🟢 **B*** | API（轻量，无需浏览器） | 搜索/投递/回复/反问 |
| 🟢 **B*** | CDP浏览器（更稳定） | 搜索/投递/回复 |
| 🔵 **猎*** | 浏览器自动化 | 搜索/投递/消息检查 |
| 🟡 **前***** | 浏览器自动化 | 搜索/投递（当前反爬，暂时禁用） |

```
┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐
│ 搜索岗位  │ →  │ 智能过滤  │ →  │ 自动投递  │ →  │ 等HR回复  │
│ 3平台     │    │ 红旗检测  │    │ 定制话术  │    │           │
└──────────┘    └──────────┘    └──────────┘    └─────┬────┘
                                                      │
                                                ┌─────▼────┐
                                                │ 收到消息  │
                                                └─────┬────┘
                                                      │
                                          ┌───────────▼───────────┐
                                          │ AI 自动分析场景并回复   │
                                          │ + 自动追问双休/五险一金  │
                                          │ + 自动追问KPI/试用期    │
                                          │ + 已问过的不重复问      │
                                          └───────────────────────┘
```

## ✨ 核心功能

| 模块 | 做什么 | 亮点 |
|------|------|------|
| 🔍 **岗位搜索** | 多关键词多平台轮询搜索 | 模拟人类行为，随机间隔 |
| 🛡️ **智能过滤** | 自动识别坑爹公司 | 保险/理财/培训收费/无底薪 → 自动跳过 |
| 📊 **岗位评分** | 薪资/JD/公司/HR四维评估 | 0-100分，强匹配自动投 |
| ✉️ **自动投递** | 生成定制打招呼话术 | 根据JD关键词匹配你的经历 |
| 💬 **智能回复** | 10种HR场景分类应答 | 打招呼/问薪资/约面试/要作品/拒绝... |
| ❓ **反问系统** | 自动追问关键问题 | 双休？五险一金？KPI？试用期？ |
| 📈 **统计追踪** | 每日投递数/回复数 | 本地JSON，随时查看 |

## 🚀 快速开始

### 1. 安装

```bash
git clone https://github.com/你的用户名/boss-jobhunter.git
cd boss-jobhunter
pip install -r requirements.txt
```

### 2. 配置个人信息

```bash
# 复制模板文件
copy user_profile.example.json user_profile.json
copy config.example.json config.json
```

编辑 `user_profile.json`，填入你的真实信息：
- 姓名、年龄、学历、期望薪资
- 工作经历（公司、岗位、亮点）
- 服务过的客户品牌
- 知乎/作品集/抖音等个人链接

编辑 `config.json`，调整求职偏好：
- 目标岗位关键词
- 期望城市
- 每日投递上限（建议 20-30）
- 排除的行业/岗位

### 3. 选择模式运行

#### 模式一：B*** API（推荐入门）

```bash
# 获取 Cookie
# 1. 浏览器打开招聘网站并登录
# 2. F12 → Application → Cookies
# 3. 复制关键 cookie

python main.py --set-cookie "你的cookie字符串"

# 试运行（不实际发送）
python main.py --once --dry-run

# 正式运行（10分钟扫描一次）
python main.py
```

#### 模式二：全平台浏览器模式（B*** + 猎* + 前***）

```bash
# 需要安装浏览器驱动
pip install DrissionPage

# 先手动登录各平台（浏览器会打开）
# 然后运行：
python multi_hunter.py --city 深圳 --max-apply 20 --once
```

### 4. 命令行参数

```bash
# main.py（B*** API 模式）
python main.py --once              # 只扫描一次
python main.py --interval 300      # 自定义间隔5分钟
python main.py --no-auto-apply     # 只回复消息，不投递
python main.py --no-auto-reply     # 只投递，不回复
python main.py --dry-run           # 试运行
python main.py --status            # 查看统计

# multi_hunter.py（全平台浏览器模式）
python multi_hunter.py --once --city 深圳 --max-apply 20
python multi_hunter.py --chat-only --city 深圳      # 只检查消息
python multi_hunter.py --apply-only --city 深圳      # 只投递
python multi_hunter.py --direction 2 --city 东莞     # 只跑第2个求职方向
```

## ⚙️ 配置说明

`config.json` 关键配置项：

```json
{
  "scan_interval_seconds": 600,
  "max_daily_applications": 30,
  "auto_apply": false,
  "auto_reply": false,
  "job_preferences": {
    "titles": ["品牌策划", "内容策略"],
    "min_salary": 8000,
    "cities": ["深圳", "东莞"]
  }
}
```

> ⚠️ **建议**：初次使用先设 `auto_apply: false` 和 `auto_reply: false`，观察几轮评估结果，确认过滤逻辑符合预期后再开启自动模式。

## 🧠 智能过滤怎么工作

工具会对每个岗位打分（满分100）：

| 维度 | 权重 | 示例 |
|------|:---:|------|
| 🔴 红旗检测 | 一票否决 | 保险代理、培训收费、无底薪、薪资面议不标范围 |
| 💰 薪资评估 | ±15 | 低于最低期望扣分、面议扣分 |
| 📝 JD质量 | ±15 | JD太短（<100字）扣分、结构完整加分 |
| 🏢 公司信息 | ±30 | 规模/融资阶段/行业是否匹配 |
| 👤 HR活跃度 | ±5 | 今日活跃加分、回复率>80%加分 |
| 🎯 关键词匹配 | +10~20 | 岗位名、城市是否匹配 |

**评分 ≥75 → 强匹配（自动投递），60-74 → 好匹配（自动投递），45-59 → 备选，<45 → 跳过。**

## 📁 项目结构

```
boss-jobhunter/
├── main.py              # B*** API 主循环
├── multi_hunter.py      # 全平台浏览器模式（猎*+前***+B***）
├── zhipin.py            # B*** API 适配器
├── filter.py            # 岗位/公司评估引擎
├── responder.py         # HR消息场景分类+智能应答
├── resume_engine.py     # JD-简历匹配+打招呼话术生成
├── requirements.txt     # Python依赖
├── config.example.json  # 配置模板
├── user_profile.example.json  # 个人资料模板
└── data/                # 运行数据（.gitignore已排除）
```

## ⚠️ 免责声明

**本工具仅供学习研究 Python 自动化、API 逆向和浏览器自动化技术。**

- 请遵守各招聘平台的用户协议
- 自动化操作可能触发平台风控机制
- 使用本工具产生的任何后果（包括但不限于账号受限）由使用者自行承担
- 作者不提供任何担保

## 👤 关于作者

**金山齐达内（冯桂金）**

- 🌐 个人作品站：[https://luxury-torrone-364f29.netlify.app/](https://luxury-torrone-364f29.netlify.app/)
- 📖 知乎「金山齐达内」— 60万+阅读，3800+赞同
- 🛠️ 文案AI工坊主理人 — AI内容生产系统搭建
- 🎬 代表作：品牌病毒短片（百万播放）、整合营销全案、AI内容工厂搭建
- 📧 联系：知乎私信 或 作品站留言

**我用这个工具找到了工作，希望你也能。**

---

⭐ 如果这个项目对你有帮助，点个 Star 让更多人看到！

> 📸 效果截图和实战记录正在整理中，后续更新。关注知乎「金山齐达内」获取最新动态。
