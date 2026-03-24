# 哈工程本科生学分统计系统

自动登录教务系统，查询成绩、统计学分、检查毕业要求的跨平台桌面工具。

## 功能

- **CAS SSO 自动登录** — 自动识别验证码，无需手动操作
- **学分统计** — 必修 / 专选 / 公选（按类别细分）
- **毕业要求检查** — 实时判断各项要求是否达标
- **毕业预测** — 模拟本学期课程全部通过后能否满足毕业要求
- **要求配置** — GUI 中可自定义毕业学分要求，实时生效
- **本学期课表** — 查看当前学期课程安排

## 下载

前往 [Releases](../../releases) 页面下载对应系统的可执行文件：

| 系统 | 文件 |
|------|------|
| Windows (x64) | `CreditStatistics-Windows.exe` |
| macOS (Intel) | `CreditStatistics-macOS-x64` |
| macOS (Apple Silicon) | `CreditStatistics-macOS-arm64` |
| Linux (x64) | `CreditStatistics-Linux` |

> macOS / Linux 用户下载后需要添加执行权限：`chmod +x CreditStatistics-*`

## 从源码运行

```bash
# 克隆仓库
git clone <repo-url> && cd CreditStatistics

# 创建虚拟环境并安装依赖
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

pip install -r requirements.txt

# 运行
python credit_statistics.py
```

## 本地构建二进制

```bash
pip install pyinstaller
pyinstaller credit_statistics.spec
# 产物在 dist/CreditStatistics.exe (Windows) 或 dist/CreditStatistics (Unix)
```

## CI/CD

推送 `v*` 标签即可触发 GitHub Actions 自动构建四平台二进制并创建 Release：

```bash
git tag v1.0.0
git push origin v1.0.0
```

## 技术栈

- Python 3.13 + tkinter（GUI）
- ddddocr（验证码 OCR）
- requests（HTTP 会话）
- PyInstaller（打包）
- GitHub Actions（CI 构建）
