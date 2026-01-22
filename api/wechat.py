"""
微信公众号记账机器人 - Webhook 入口
"""
import os
import hashlib
import time
import json
from datetime import datetime, timedelta
from urllib.parse import unquote

from fastapi import FastAPI, Request, Response
import httpx

app = FastAPI()

# ============ 配置（从环境变量读取）============
APPID = os.environ.get("WECHAT_APPID", "")
APPSECRET = os.environ.get("WECHAT_APPSECRET", "")
TOKEN = os.environ.get("WECHAT_TOKEN", "")
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")

# ============ 分类关键词映射 ============
CATEGORY_KEYWORDS = {
    "餐饮": ["早餐", "午餐", "晚餐", "早饭", "午饭", "晚饭", "吃饭", "外卖", "饭", "餐", "奶茶", "咖啡", "饮料", "零食", "水果", "菜", "肉", "面", "粉", "火锅", "烧烤", "小吃"],
    "交通": ["打车", "滴滴", "出租车", "地铁", "公交", "公车", "油费", "加油", "停车", "高速", "过路费", "单车", "共享", "车费", "交通"],
    "购物": ["淘宝", "京东", "拼多多", "购物", "买", "衣服", "鞋", "包", "日用品", "超市", "商场"],
    "娱乐": ["电影", "游戏", "ktv", "唱歌", "旅游", "门票", "娱乐", "玩"],
    "居住": ["房租", "水费", "电费", "燃气", "物业", "网费", "宽带"],
    "医疗": ["医院", "药", "看病", "体检", "医疗"],
    "教育": ["书", "课程", "培训", "学习", "教育"],
}

# ============ 数据库操作（使用 REST API）============
def get_supabase_client():
    """创建简单的 Supabase REST 客户端"""
    class SupabaseClient:
        def __init__(self, url, key):
            self.url = url.rstrip('/')
            self.key = key
            self.headers = {
                "apikey": key,
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
                "Prefer": "return=representation"
            }
        
        def table(self, name):
            return SupabaseTable(self.url, name, self.headers)
    
    class SupabaseTable:
        def __init__(self, base_url, name, headers):
            self.url = f"{base_url}/rest/v1/{name}"
            self.headers = headers
        
        def insert(self, data):
            class Result:
                def __init__(self, data):
                    self.data = data
                def execute(self):
                    return self
            
            response = httpx.post(self.url, json=data, headers=self.headers, timeout=10.0)
            response.raise_for_status()
            return Result(response.json() if response.content else [data])
        
        def select(self, columns="*"):
            return QueryBuilder(self.url, self.headers, columns)
    
    class QueryBuilder:
        def __init__(self, url, headers, columns):
            self.url = url
            self.headers = headers
            self.params = {"select": columns}
            self.filters = []
        
        def eq(self, column, value):
            self.filters.append((column, "eq", value))
            return self
        
        def gte(self, column, value):
            self.filters.append((column, "gte", value))
            return self
        
        def lte(self, column, value):
            self.filters.append((column, "lte", value))
            return self
        
        def order(self, column, desc=False):
            self.params["order"] = f"{column}.{'desc' if desc else 'asc'}"
            return self
        
        def execute(self):
            for column, op, value in self.filters:
                self.params[column] = f"{op}.{value}"
            
            response = httpx.get(self.url, params=self.params, headers=self.headers, timeout=10.0)
            response.raise_for_status()
            class Result:
                def __init__(self, data):
                    self.data = data
            return Result(response.json())
    
    return SupabaseClient(SUPABASE_URL, SUPABASE_KEY)


def add_record(openid: str, nickname: str, amount: float, category: str, description: str):
    """添加记账记录"""
    try:
        supabase = get_supabase_client()
        data = {
            "openid": openid,
            "nickname": nickname,
            "amount": amount,
            "category": category,
            "description": description,
            "created_at": datetime.now().isoformat()
        }
        result = supabase.table("records").insert(data).execute()
        return result
    except Exception as e:
        print(f"数据库错误: {str(e)[:100]}")
        raise


def get_records(start_date: datetime = None, end_date: datetime = None, category: str = None):
    """查询记录（所有人共同）"""
    try:
        supabase = get_supabase_client()
        query = supabase.table("records").select("*")
        
        if start_date:
            query = query.gte("created_at", start_date.isoformat())
        if end_date:
            query = query.lte("created_at", end_date.isoformat())
        if category:
            query = query.eq("category", category)
        
        query = query.order("created_at", desc=True)
        result = query.execute()
        return result.data
    except Exception as e:
        print(f"查询错误: {str(e)[:100]}")
        return []


def get_statistics(start_date: datetime = None, end_date: datetime = None):
    """获取统计数据（所有人共同）"""
    records = get_records(start_date, end_date)
    
    total = sum(r["amount"] for r in records)
    by_category = {}
    by_user = {}
    
    for r in records:
        cat = r["category"]
        user = r.get("nickname", r.get("openid", "未知"))
        by_category[cat] = by_category.get(cat, 0) + r["amount"]
        by_user[user] = by_user.get(user, 0) + r["amount"]
    
    return {
        "total": total,
        "by_category": by_category,
        "by_user": by_user,
        "count": len(records)
    }


# ============ 消息解析 ============
def parse_category(text: str) -> str:
    """从文本中识别分类"""
    text_lower = text.lower()
    for category, keywords in CATEGORY_KEYWORDS.items():
        for keyword in keywords:
            if keyword in text_lower:
                return category
    return "其他"


def parse_message(content: str) -> dict:
    """解析用户消息"""
    import re
    content = content.strip()
    
    # 查询命令
    if content in ["今日", "今天"]:
        return {"type": "query", "period": "today"}
    if content in ["本周", "这周"]:
        return {"type": "query", "period": "week"}
    if content in ["本月", "这个月"]:
        return {"type": "query", "period": "month"}
    if content in ["明细", "详情", "记录"]:
        return {"type": "detail"}
    if content in ["帮助", "help", "?"]:
        return {"type": "help"}
    
    # 分类查询
    for category in CATEGORY_KEYWORDS.keys():
        if content == category:
            return {"type": "query_category", "category": category}
    
    # 记账：尝试解析金额
    patterns = [
        r'^(.+?)\s+(\d+(?:\.\d+)?)\s*(.*)$',  # 描述 金额 [分类]
        r'^(\d+(?:\.\d+)?)\s+(.+?)$',          # 金额 描述
        r'^(.+?)(\d+(?:\.\d+)?)$',             # 描述金额（无空格）
        r'^(\d+(?:\.\d+)?)(.+?)$',             # 金额描述（无空格）
    ]
    
    for i, pattern in enumerate(patterns):
        match = re.match(pattern, content)
        if match:
            groups = match.groups()
            if i == 0:  # 描述 金额 [分类]
                desc, amount, extra = groups
                amount = float(amount)
                category = extra.strip() if extra.strip() in CATEGORY_KEYWORDS else parse_category(desc)
            elif i == 1:  # 金额 描述
                amount, desc = groups
                amount = float(amount)
                category = parse_category(desc)
            elif i == 2:  # 描述金额
                desc, amount = groups
                amount = float(amount)
                category = parse_category(desc)
            else:  # 金额描述
                amount, desc = groups
                amount = float(amount)
                category = parse_category(desc)
            
            return {
                "type": "record",
                "amount": amount,
                "description": desc.strip(),
                "category": category
            }
    
    return {"type": "unknown"}


def get_date_range(period: str):
    """获取日期范围"""
    now = datetime.now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    
    if period == "today":
        return today_start, now
    elif period == "week":
        week_start = today_start - timedelta(days=today_start.weekday())
        return week_start, now
    elif period == "month":
        month_start = today_start.replace(day=1)
        return month_start, now
    return None, None


def format_statistics(stats: dict, period_name: str) -> str:
    """格式化统计信息"""
    if stats["count"] == 0:
        return f"📊 {period_name}暂无记录"
    
    lines = [f"📊 {period_name}统计（共同）", f"💰 总支出：{stats['total']:.2f} 元", ""]
    
    # 按分类
    if stats["by_category"]:
        lines.append("📂 分类明细：")
        for cat, amount in sorted(stats["by_category"].items(), key=lambda x: -x[1]):
            lines.append(f"  • {cat}：{amount:.2f} 元")
    
    # 按用户
    if len(stats["by_user"]) > 1:
        lines.append("")
        lines.append("👥 个人支出：")
        for user, amount in sorted(stats["by_user"].items(), key=lambda x: -x[1]):
            lines.append(f"  • {user}：{amount:.2f} 元")
    
    return "\n".join(lines)


def format_records(records: list, limit: int = 10) -> str:
    """格式化记录列表"""
    if not records:
        return "📝 暂无记录"
    
    lines = ["📝 最近记录（共同）："]
    for r in records[:limit]:
        dt = datetime.fromisoformat(r["created_at"].replace("Z", "+00:00"))
        date_str = dt.strftime("%m-%d %H:%M")
        user = r.get("nickname", r.get("openid", "未知")[:4])
        lines.append(f"  • {date_str} {user} {r['description']} {r['amount']:.2f}元 [{r['category']}]")
    
    if len(records) > limit:
        lines.append(f"  ... 共 {len(records)} 条记录")
    
    return "\n".join(lines)


def get_help_text() -> str:
    """返回帮助信息"""
    return """📖 记账机器人使用指南

【记账】
发送：描述 金额
例如：午餐 35
      打车 50 交通
      35 买水果

【查询统计】
发送：今日 / 本周 / 本月

【查看明细】
发送：明细

【按分类查询】
发送分类名：餐饮 / 交通 / 购物 / 娱乐 / 居住 / 医疗 / 教育

💡 所有记录共同统计，支持多人使用"""


# ============ 处理消息 ============
def handle_message(openid: str, nickname: str, content: str) -> str:
    """处理用户消息，返回回复内容"""
    parsed = parse_message(content)
    
    if parsed["type"] == "help":
        return get_help_text()
    
    elif parsed["type"] == "record":
        try:
            add_record(
                openid=openid,
                nickname=nickname,
                amount=parsed["amount"],
                category=parsed["category"],
                description=parsed["description"]
            )
            return f"✅ 记账成功！\n{parsed['description']}：{parsed['amount']:.2f} 元\n分类：{parsed['category']}"
        except Exception as e:
            print(f"记账失败: {str(e)[:100]}")
            return "❌ 记账失败，请稍后重试"
    
    elif parsed["type"] == "query":
        try:
            start_date, end_date = get_date_range(parsed["period"])
            period_names = {"today": "今日", "week": "本周", "month": "本月"}
            stats = get_statistics(start_date=start_date, end_date=end_date)
            return format_statistics(stats, period_names[parsed["period"]])
        except Exception as e:
            print(f"查询失败: {str(e)[:100]}")
            return "❌ 查询失败，请稍后重试"
    
    elif parsed["type"] == "query_category":
        try:
            now = datetime.now()
            month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            records = get_records(start_date=month_start, category=parsed["category"])
            total = sum(r["amount"] for r in records)
            result = f"📂 本月【{parsed['category']}】支出：{total:.2f} 元\n\n"
            result += format_records(records, limit=5)
            return result
        except Exception as e:
            print(f"分类查询失败: {str(e)[:100]}")
            return "❌ 查询失败，请稍后重试"
    
    elif parsed["type"] == "detail":
        try:
            records = get_records()
            return format_records(records, limit=15)
        except Exception as e:
            print(f"明细查询失败: {str(e)[:100]}")
            return "❌ 查询失败，请稍后重试"
    
    else:
        return "🤔 没理解你的意思\n\n发送「帮助」查看使用说明"


# ============ 微信公众号验证 ============
def check_signature(signature, timestamp, nonce):
    """验证微信服务器签名"""
    tmp_arr = [TOKEN, timestamp, nonce]
    tmp_arr.sort()
    tmp_str = ''.join(tmp_arr)
    tmp_str = hashlib.sha1(tmp_str.encode('utf-8')).hexdigest()
    return tmp_str == signature


# ============ API 路由 ============
@app.get("/api/wechat")
async def verify(request: Request):
    """微信公众号 URL 验证"""
    try:
        params = dict(request.query_params)
        signature = params.get("signature", "")
        timestamp = params.get("timestamp", "")
        nonce = params.get("nonce", "")
        echostr = params.get("echostr", "")
        
        if check_signature(signature, timestamp, nonce):
            return Response(content=echostr, media_type="text/plain")
        else:
            return Response(content="verify failed", status_code=403)
    except Exception as e:
        print(f"验证错误: {str(e)[:100]}")
        return Response(content="error", status_code=500)


@app.post("/api/wechat")
async def webhook(request: Request):
    """接收微信公众号消息"""
    try:
        body = await request.body()
        body_str = body.decode("utf-8")
        
        # 解析 XML
        from xml.etree import ElementTree as ET
        xml_tree = ET.fromstring(body_str)
        
        msg_type = xml_tree.find("MsgType").text
        from_user = xml_tree.find("FromUserName").text
        
        # 只处理文本消息
        if msg_type != "text":
            return Response(content="success", media_type="text/plain")
        
        content = xml_tree.find("Content").text
        
        # 获取用户信息（可选，需要 access_token）
        nickname = from_user[:8]  # 暂时用 openid 前8位作为标识
        
        # 处理消息
        reply_content = handle_message(from_user, nickname, content)
        
        # 构造回复 XML
        to_user = xml_tree.find("FromUserName").text
        from_user_name = xml_tree.find("ToUserName").text
        create_time = int(time.time())
        
        reply_xml = f"""<xml>
<ToUserName><![CDATA[{to_user}]]></ToUserName>
<FromUserName><![CDATA[{from_user_name}]]></FromUserName>
<CreateTime>{create_time}</CreateTime>
<MsgType><![CDATA[text]]></MsgType>
<Content><![CDATA[{reply_content}]]></Content>
</xml>"""
        
        return Response(content=reply_xml, media_type="application/xml")
    except Exception as e:
        print(f"处理消息错误: {str(e)[:100]}")
        return Response(content="success", media_type="text/plain")
