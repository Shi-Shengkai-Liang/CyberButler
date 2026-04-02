# CyberButler 🦾

自动扫描 Moodle 和 Gradescope 的智能作业追踪系统，支持 AI 遗忘风险分析和手机推送通知。

> 由 Rose-Hulman Institute of Technology 学生开发，适用于所有使用 Moodle 的学校。

## 功能

- 自动扫描 Moodle 结构化作业和 quiz
- AI 读取课程页面文字、PDF/Word 日历文件，提取隐藏的 DDL
- 自动扫描 Gradescope 未提交作业
- AI 分析遗忘风险，智能提醒
- 网页任务列表，支持标记完成、按课程筛选
- 手机推送通知（ntfy.sh，免费）
- 每天自动扫描，也可手动刷新

## 所需资源（全部免费）

| 资源 | 说明 | 费用 |
|------|------|------|
| Oracle Cloud 免费 VPS | 运行服务器 | $0 |
| Google Gemini API | AI 分析 | $0 |
| ntfy.sh | 手机推送通知 | $0 |
| Moodle Web Service Token | 从学校获取 | $0 |
| Gradescope 账号 | 学校账号 | $0 |

> 也支持 Anthropic Claude（约$1/月）和 Groq（免费）

## 部署步骤

### 1. 申请 Oracle Cloud 免费 VPS

1. 注册 [Oracle Cloud](https://cloud.oracle.com)
2. 创建 Ubuntu 22.04 ARM 实例（选 Always Free，4 CPU / 24GB RAM）
3. 在 Security List 里开放 TCP 5000 端口
4. SSH 连接到服务器

### 2. 安装依赖
```bash
curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash -
sudo apt-get install -y python3 python3-pip
pip3 install requests beautifulsoup4 pdfplumber python-docx flask

# 根据你选择的 AI 提供商安装对应库
pip3 install anthropic          # Anthropic
pip3 install google-generativeai  # Google Gemini（推荐，免费）
pip3 install groq               # Groq（免费）
```

### 3. 上传文件
```bash
mkdir ~/cyberbutler
# 把所有文件上传到 ~/cyberbutler/
```

### 4. 获取 Moodle Token

1. 登录学校 Moodle
2. 头像 → Preferences → Security keys
3. 找到 **Moodle mobile web service**，点 Reset 获取 Token
4. 用户 ID：登录后点头像，URL 里的 `?id=XXXXX` 就是你的 ID

### 5. 配置环境变量
```bash
cp config.example.env .env
nano .env  # 填入你的配置
```

把 .env 加载到环境：
```bash
cat >> ~/.bashrc << 'EOF'
export $(grep -v '^#' ~/cyberbutler/.env | xargs)
EOF
source ~/.bashrc
```

### 6. 配置课程

编辑 `scan_to_json.py`，填入你的课程信息：
```python
# 名字里没有学期标识的课程，手动添加
MANUAL_COURSES = {
    122597: "MA223 Statistics",  # 课程ID从Moodle URL获取
}

# Gradescope 课程，ID从 gradescope.com/courses/XXXXX 的URL获取
GRADESCOPE_COURSES = {
    "1273436": "ME328 Material Engineering",
}
```

### 7. 首次运行
```bash
cd ~/cyberbutler
python3 scan_to_json.py
```

### 8. 启动网页服务
```bash
# 设置开机自启
mkdir -p ~/.config/systemd/user
cat > ~/.config/systemd/user/cyberbutler-web.service << 'EOF'
[Unit]
Description=CyberButler Web Server
After=network.target

[Service]
ExecStart=/usr/bin/python3 /home/ubuntu/cyberbutler/web.py
Restart=always
WorkingDirectory=/home/ubuntu/cyberbutler

[Install]
WantedBy=default.target
EOF

systemctl --user enable cyberbutler-web
systemctl --user start cyberbutler-web
```

### 9. 设置定时扫描
```bash
crontab -e
# 添加（每天早8点晚8点）：
# 0 8 * * * python3 /home/ubuntu/cyberbutler/scan_to_json.py
# 0 20 * * * python3 /home/ubuntu/cyberbutler/scan_to_json.py
```

### 10. 手机推送

1. 下载 [ntfy](https://ntfy.sh) app
2. 订阅你在 `.env` 里设置的 `NTFY_TOPIC` 频道名

## 使用

- 网页：`http://你的服务器IP:5000`
- 密码：`.env` 里的 `WEB_PASSWORD`
- 手动刷新：网页右上角 Refresh 按钮

## 添加其他平台支持

欢迎 PR！目前支持：
- Moodle（API + 页面扫描 + 文件扫描）
- Gradescope

待添加：
- Canvas
- Blackboard
- Brightspace

## License

MIT License
