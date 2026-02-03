# 微信公众号记账机器人

一个简单的记账机器人，支持多人共同记账、共同统计。

## 功能

- ✅ 快速记账：`午餐 35` 或 `打车 50 交通`
- ✅ 自动识别分类：餐饮、交通、购物、娱乐等
- ✅ 统计查询：今日/本周/本月
- ✅ 统计面板：月/周/年趋势、分类占比
- ✅ 分类选择与纠错学习：首次选择后自动记住
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

### 批量修改历史记录（包括修改分类）
1. 发送：`导出 本月` 或 `导出 1月` 获取 Excel 文件
2. 在 Excel 的"明细"表中修改：
   - **分类**：可以改成已有分类，也可以输入新分类名
   - **描述**：修改错别字或内容
   - **金额**：修正金额
3. 打开 `https://你的域名/api/import` 上传修改后的文件
4. 系统会按 ID 批量更新记录

**示例：批量修改分类**
- 把多条记录的"餐饮"改成"吃饭"
- 把"其他"改成"七七八八"
- 输入新分类"早点"、"宵夜"等

> 注意：不要删除或修改 ID 列，不能新增或删除记录行

### 纠错学习
```
纠错 午饭 餐饮
```

### 管理分类名称

**方法1：导出明细表批量改（推荐，最灵活）**
- 导出 Excel → 在"分类"列直接改 → 导入
- 支持改成新分类名，系统会自动接受

**方法2：微信指令（快速单个改）**
```
分类列表              # 查看所有分类
重命名分类 餐饮 吃饭   # 批量重命名所有历史记录
```

### 分类选择
首次记账时如未学习分类会提示选择：
```
1
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
