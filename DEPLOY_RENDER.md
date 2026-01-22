# Render 部署完整指南

## 你的配置信息

- **AppID**: `wxc105157e5f9dcff7`
- **AppSecret**: `fd00fc3bbc390648b7a66fc7165fb9ca`

## 第一步：创建 GitHub 仓库并推送代码

### 1. 创建 GitHub 仓库

1. 打开 https://github.com 登录
2. 点击右上角 "+" → "New repository"
3. 仓库名填 `wechat-accounting-bot`
4. 选择 "Public"
5. 点击 "Create repository"

### 2. 推送代码到 GitHub

在终端执行：

```bash
cd /Users/Zhuanz/Desktop/未命名文件夹/wechat-accounting-bot
git remote add origin https://github.com/你的用户名/wechat-accounting-bot.git
git branch -M main
git push -u origin main
```

**注意**：如果提示需要认证，使用之前配置的 token 作为密码。

## 第二步：在 Render 上创建服务

### 1. 登录 Render

1. 打开 https://dashboard.render.com
2. 用 GitHub 账号登录

### 2. 创建 Web Service

1. 点击 "New" → "Web Service"
2. 找到并选择 `wechat-accounting-bot` 仓库
3. 点击 "Connect"

### 3. 配置服务

- **Name**: `wechat-accounting-bot`（或自定义）
- **Environment**: `Python 3`
- **Region**: 选择离你最近的（推荐 Singapore）
- **Branch**: `main`
- **Root Directory**: 留空
- **Build Command**: `pip install -r requirements.txt`
- **Start Command**: `uvicorn api.wechat:app --host 0.0.0.0 --port $PORT`

### 4. 配置环境变量

在 "Environment Variables" 部分添加：

| Key | Value |
|-----|-------|
| `WECHAT_APPID` | `wxc105157e5f9dcff7` |
| `WECHAT_APPSECRET` | `fd00fc3bbc390648b7a66fc7165fb9ca` |
| `WECHAT_TOKEN` | `MyToken123456`（自定义，稍后配置公众号时要用） |
| `SUPABASE_URL` | （第二步获取） |
| `SUPABASE_KEY` | （第二步获取） |

**重要**：`WECHAT_TOKEN` 可以自定义，比如：`MyToken123456`，记住这个值，稍后配置公众号时需要。

### 5. 创建服务

1. 点击 "Create Web Service"
2. 等待部署完成（约 2-3 分钟）
3. 记录下你的域名，类似：`https://wechat-accounting-bot.onrender.com`

## 第三步：创建 Supabase 数据库

1. 打开 https://supabase.com 注册账号
2. 创建新项目
3. 在 SQL Editor 执行：

```sql
CREATE TABLE records (
    id SERIAL PRIMARY KEY,
    openid VARCHAR(100) NOT NULL,
    nickname VARCHAR(100),
    amount DECIMAL(10, 2) NOT NULL,
    category VARCHAR(50) NOT NULL,
    description VARCHAR(200) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_records_openid ON records(openid);
CREATE INDEX idx_records_created_at ON records(created_at);
CREATE INDEX idx_records_category ON records(category);
```

4. 获取配置：
   - Project Settings → API
   - 复制 `Project URL` → 设置为 `SUPABASE_URL`
   - 复制 `anon public` key → 设置为 `SUPABASE_KEY`

5. 回到 Render，更新环境变量：
   - 进入服务 → Environment
   - 更新 `SUPABASE_URL` 和 `SUPABASE_KEY`
   - 保存后会自动重新部署

## 第四步：配置微信公众号服务器

### 在公众号后台配置：

1. 登录微信公众平台：https://mp.weixin.qq.com
2. 左侧菜单找到 **"开发"** → **"基本配置"**
3. 在"服务器配置"部分：
   - 点击 **"修改配置"**
   - **URL**：`https://你的render域名/api/wechat`（例如：`https://wechat-accounting-bot.onrender.com/api/wechat`）
   - **Token**：你设置的环境变量 `WECHAT_TOKEN`（例如：`MyToken123456`）
   - **EncodingAESKey**：选择"明文模式"（或点击"随机获取"）
   - **消息加解密方式**：选择 **"明文模式"**
4. 点击 **"提交"** 进行验证
5. 如果显示"配置成功"，点击 **"启用"** 开启服务器配置

## 第五步：测试使用

1. 在微信中搜索你的公众号名称
2. 关注公众号
3. 发送消息测试：
   - `帮助` - 查看使用说明
   - `午餐 35` - 记账
   - `今日` - 查看今日统计

## 两个人共同使用

1. 让第二个人也关注公众号
2. 两个人可以：
   - 各自记账
   - 查看共同统计（`今日`、`本周`、`本月`）
   - 查看共同明细（`明细`）
