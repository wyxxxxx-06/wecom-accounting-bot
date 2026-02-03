# 微信公众号记账机器人

一个简单的记账机器人，支持多人共同记账、共同统计。

## 功能

- ✅ 快速记账：`午餐 35` 或 `打车 50 交通`
- ✅ 自动识别分类：餐饮、交通、购物、娱乐等
- ✅ 统计查询：今日/本周/本月
- ✅ 统计面板：月/周/年趋势、分类占比
- ✅ 多人共同记账，共同统计

## 重要说明

### 公众号类型选择

1. **订阅号（个人）**：
   - ✅ 可以注册（免费）
   - ❌ 不支持自定义菜单
   - ❌ 消息回复功能有限
   - ⚠️ **不推荐用于机器人**

2. **服务号（企业）**：
   - ✅ 支持完整功能
   - ✅ 支持自定义菜单
   - ✅ 支持消息自动回复
   - ❌ 需要企业认证（300元/年）

3. **测试号（推荐开始使用）**：
   - ✅ 完全免费
   - ✅ 支持所有功能
   - ✅ 适合开发和测试
   - ⚠️ 只能添加最多100个关注者

## 推荐方案

### 方案 1：使用测试号（推荐，免费）

1. **注册测试号**：
   - 打开：https://mp.weixin.qq.com/debug/cgi-bin/sandbox?t=jsapisandbox
   - 或者搜索"微信公众平台测试号"
   - 用微信扫码登录
2. **获取信息**：
   - 记录 `AppID`
   - 记录 `AppSecret`
   - 保存测试号二维码（用于关注）
3. **配置服务器 URL**（见下方部署步骤）
4. **开始使用**

### 方案 2：注册服务号（需要认证）

1. 注册微信公众平台：https://mp.weixin.qq.com
2. 选择"服务号"
3. 完成企业认证（需要营业执照，300元/年）
4. 配置服务器

## 部署步骤

### 第一步：注册测试号（推荐）

1. 打开微信公众平台测试号：https://mp.weixin.qq.com/debug/cgi-bin/sandbox?t=jsapisandbox
   或者搜索"微信公众平台测试号"
2. 用微信扫码登录
3. 记录下：
   - **AppID**
   - **AppSecret**
   - **测试号二维码**（用微信扫码关注）

### 第二步：创建 Supabase 数据库

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

4. 记录 `Project URL` 和 `anon key`

### 第三步：部署代码

1. 将代码部署到 Render/Vercel
2. 配置环境变量：
   - `WECHAT_APPID` = 你的 AppID
   - `WECHAT_APPSECRET` = 你的 AppSecret
   - `WECHAT_TOKEN` = 自定义 Token（随机字符串）
   - `SUPABASE_URL` = 你的 Supabase URL
   - `SUPABASE_KEY` = 你的 Supabase Key

### 第四步：配置微信公众号

1. 在测试号管理页面，找到"接口配置信息"
2. 填写：
   - **URL**：`https://你的域名/api/wechat`
   - **Token**：你设置的环境变量 `WECHAT_TOKEN`
   - **EncodingAESKey**：点击"随机获取"（可选，如果启用加密）
3. 点击"提交"验证

### 第五步：关注测试号

1. 用微信扫描测试号二维码
2. 关注后发送消息测试

## 使用说明

### 记账
```
午餐 35
打车 50 交通
35 买水果
咖啡15
```

### 查询统计
```
今日
本周
本月
统计 1月
统计 2025年1月
统计面板
```

### 查看明细
```
明细
明细 1月
```

### 按分类查询
```
餐饮
交通
生活用品
```

### 纠错学习
```
纠错 午饭 餐饮
```

## 分类说明

| 分类 | 自动识别关键词 |
|------|---------------|
| 餐饮 | 早餐、午餐、晚餐、外卖、奶茶、咖啡... |
| 交通 | 打车、滴滴、地铁、公交、油费... |
| 购物 | 淘宝、京东、买、衣服、超市... |
| 娱乐 | 电影、游戏、KTV、旅游... |
| 居住 | 房租、水费、电费、物业... |
| 医疗 | 医院、药、看病... |
| 教育 | 书、课程、培训... |
| 生活用品 | 洗发水、纸巾、洗衣液、清洁... |
| 其他 | 无法识别时归入此类 |
