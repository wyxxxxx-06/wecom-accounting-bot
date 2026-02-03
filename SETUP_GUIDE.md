# 微信公众号记账机器人 - 完整设置指南

## 第一步：获取 AppID 和 AppSecret

### 如果你注册的是测试号：

1. 打开测试号管理页面：https://mp.weixin.qq.com/debug/cgi-bin/sandbox?t=jsapisandbox
2. 用微信扫码登录
3. 在页面中可以看到：
   - **appID**：复制这个值
   - **appsecret**：点击"查看"或"重置"获取，复制这个值
   - **测试号二维码**：保存这个二维码，用于关注

### 如果你注册的是订阅号/服务号：

1. 登录微信公众平台：https://mp.weixin.qq.com
2. 左侧菜单找到 **"开发"** → **"基本配置"**
3. 在"基本配置"页面可以看到：
   - **AppID(应用ID)**：复制这个值
   - **AppSecret(应用密钥)**：点击"生成"或"查看"，复制这个值
   - **服务器配置**：这里需要配置 Token（见下一步）

## 第二步：创建 Supabase 数据库

1. 打开 https://supabase.com 注册账号（可用 GitHub 登录）
2. 点击 "New Project" 创建新项目
3. 设置项目名称（如 `wechat-accounting`），设置数据库密码，选择区域（推荐新加坡）
4. 等待项目创建完成（约1-2分钟）
5. 进入项目后，点击左侧 "SQL Editor"
6. 复制下面的 SQL 并执行：

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

-- 创建索引提高查询速度
CREATE INDEX idx_records_openid ON records(openid);
CREATE INDEX idx_records_created_at ON records(created_at);
CREATE INDEX idx_records_category ON records(category);

CREATE TABLE message_dedup (
    msg_id VARCHAR(64) PRIMARY KEY,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE category_aliases (
    id SERIAL PRIMARY KEY,
    keyword VARCHAR(100) UNIQUE NOT NULL,
    category VARCHAR(50) NOT NULL,
    enabled BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
CREATE INDEX idx_category_aliases_category ON category_aliases(category);
```

7. 点击 "Run" 执行
8. 记录下 Supabase 的配置信息：
   - 点击左侧 "Project Settings" → "API"
   - 记录 `Project URL`（即 SUPABASE_URL）
   - 记录 `anon public` 密钥（即 SUPABASE_KEY）

## 第三步：部署代码到 Render/Vercel

### 选项 A：使用 Render（推荐）

1. 登录 Render：https://dashboard.render.com
2. 点击 "New" → "Web Service"
3. 连接你的 GitHub 仓库（如果没有，先创建 GitHub 仓库并推送代码）
4. 配置：
   - **Name**: `wechat-accounting-bot`
   - **Environment**: `Python 3`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `uvicorn api.wechat:app --host 0.0.0.0 --port $PORT`
5. 在 "Environment Variables" 添加：

| Name | Value |
|------|-------|
| `WECHAT_APPID` | 你的 AppID |
| `WECHAT_APPSECRET` | 你的 AppSecret |
| `WECHAT_TOKEN` | 自定义 Token（随机字符串，如：`MyToken123456`） |
| `SUPABASE_URL` | 你的 Supabase Project URL |
| `SUPABASE_KEY` | 你的 Supabase anon key |
| `RETENTION_DAYS` | 明细保留天数（0 表示不归档） |

6. 点击 "Create Web Service"
7. 等待部署完成，记录下域名（如：`https://wechat-accounting-bot.onrender.com`）

### 选项 B：使用 Vercel

1. 登录 Vercel：https://vercel.com
2. 点击 "Add New..." → "Project"
3. 导入 GitHub 仓库
4. 在 "Environment Variables" 添加相同的环境变量
5. 点击 "Deploy"
6. 等待部署完成，记录下域名

## 第四步：配置微信公众号服务器

### 测试号配置：

1. 打开测试号管理页面：https://mp.weixin.qq.com/debug/cgi-bin/sandbox?t=jsapisandbox
2. 找到 **"接口配置信息"** 部分
3. 填写：
   - **URL**：`https://你的域名/api/wechat`（例如：`https://wechat-accounting-bot.onrender.com/api/wechat`）
   - **Token**：你设置的环境变量 `WECHAT_TOKEN`（例如：`MyToken123456`）
   - **EncodingAESKey**：选择"明文模式"（或点击"随机获取"）
4. 点击 **"提交"** 进行验证
5. 如果显示"配置成功"，恭喜！

### 订阅号/服务号配置：

1. 登录微信公众平台：https://mp.weixin.qq.com
2. 左侧菜单找到 **"开发"** → **"基本配置"**
3. 在"服务器配置"部分：
   - 点击 **"修改配置"**
   - **URL**：`https://你的域名/api/wechat`
   - **Token**：你设置的环境变量 `WECHAT_TOKEN`
   - **EncodingAESKey**：选择"明文模式"（或点击"随机获取"）
   - **消息加解密方式**：选择"明文模式"
4. 点击 **"提交"** 进行验证
5. 验证成功后，点击 **"启用"** 开启服务器配置

## 第五步：关注并测试

### 测试号：

1. 用微信扫描测试号二维码关注
2. 发送消息测试：
   - `帮助` - 查看使用说明
   - `午餐 35` - 记账
   - `今日` - 查看今日统计

### 订阅号/服务号：

1. 在微信中搜索你的公众号名称
2. 关注公众号
3. 发送消息测试

## 两个人共同使用

1. 让第二个人也关注公众号（测试号用二维码，订阅号搜索名称）
2. 两个人可以：
   - 各自记账
   - 查看共同统计（`今日`、`本周`、`本月`）
   - 查看共同明细（`明细`）

## 常见问题

**Q: 验证失败怎么办？**
A: 检查：
- URL 是否正确（必须是 `https://` 开头）
- Token 是否与环境变量一致
- 服务器是否已部署成功
- 在浏览器访问 URL，应该返回验证响应

**Q: 消息没有回复？**
A: 检查：
- Render/Vercel 的日志看是否有错误
- 环境变量是否都配置正确
- 数据库是否已创建表

**Q: 如何添加更多用户？**
A: 让其他人关注公众号即可，所有关注者都可以使用。
