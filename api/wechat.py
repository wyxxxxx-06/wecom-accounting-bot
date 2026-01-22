"""
微信公众号记账机器人 - Webhook 入口
"""
import os
import io
import hmac
import hashlib
import time
import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from urllib.parse import unquote

from fastapi import FastAPI, Request, Response
from fastapi.responses import StreamingResponse
from openpyxl import Workbook
import httpx

app = FastAPI()

# ============ 配置（从环境变量读取）============
APPID = os.environ.get("WECHAT_APPID", "")
APPSECRET = os.environ.get("WECHAT_APPSECRET", "")
TOKEN = os.environ.get("WECHAT_TOKEN", "")
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")
PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", "").rstrip("/")
RETENTION_DAYS = 38
ARCHIVE_BATCH = 200
EXPORT_TTL_SECONDS = 600
LOCAL_TZ = ZoneInfo("Asia/Shanghai")

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

        def update(self, data):
            return UpdateBuilder(self.url, self.headers, data)

        def delete(self):
            return DeleteBuilder(self.url, self.headers)
    
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
        
        def lt(self, column, value):
            self.filters.append((column, "lt", value))
            return self

        def ilike(self, column, value):
            self.filters.append((column, "ilike", value))
            return self

        def lte(self, column, value):
            self.filters.append((column, "lte", value))
            return self
        
        def order(self, column, desc=False):
            self.params["order"] = f"{column}.{'desc' if desc else 'asc'}"
            return self

        def limit(self, count: int):
            self.params["limit"] = str(count)
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

    class UpdateBuilder:
        def __init__(self, url, headers, data):
            self.url = url
            self.headers = headers
            self.data = data
            self.params = {}
            self.filters = []

        def eq(self, column, value):
            self.filters.append((column, "eq", value))
            return self

        def execute(self):
            for column, op, value in self.filters:
                self.params[column] = f"{op}.{value}"

            response = httpx.patch(self.url, params=self.params, json=self.data, headers=self.headers, timeout=10.0)
            response.raise_for_status()
            class Result:
                def __init__(self, data):
                    self.data = data
            return Result(response.json() if response.content else [])

    class DeleteBuilder:
        def __init__(self, url, headers):
            self.url = url
            self.headers = headers
            self.params = {}
            self.filters = []

        def eq(self, column, value):
            self.filters.append((column, "eq", value))
            return self

        def execute(self):
            for column, op, value in self.filters:
                self.params[column] = f"{op}.{value}"

            response = httpx.delete(self.url, params=self.params, headers=self.headers, timeout=10.0)
            response.raise_for_status()
            class Result:
                def __init__(self, data):
                    self.data = data
            return Result(response.json() if response.content else [])
    
    return SupabaseClient(SUPABASE_URL, SUPABASE_KEY)


def add_record(openid: str, nickname: str, amount: float, category: str, description: str):
    """添加记账记录"""
    try:
        archive_old_records()
        supabase = get_supabase_client()
        data = {
            "openid": openid,
            "nickname": nickname,
            "amount": amount,
            "category": category,
            "description": description,
            "created_at": datetime.now(LOCAL_TZ).isoformat()
        }
        result = supabase.table("records").insert(data).execute()
        return result
    except Exception as e:
        print(f"数据库错误: {str(e)[:100]}")
        raise


def get_records(start_date: datetime = None, end_date: datetime = None, category: str = None, limit: int = None):
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
        if limit:
            query = query.limit(limit)
        result = query.execute()
        return result.data
    except Exception as e:
        print(f"查询错误: {str(e)[:100]}")
        return []


def get_records_by_keyword(start_date: datetime = None, end_date: datetime = None, keyword: str = "", limit: int = None):
    """按描述关键词查询记录"""
    try:
        supabase = get_supabase_client()
        query = supabase.table("records").select("*")

        if start_date:
            query = query.gte("created_at", start_date.isoformat())
        if end_date:
            query = query.lte("created_at", end_date.isoformat())
        if keyword:
            query = query.ilike("description", f"*{keyword}*")

        query = query.order("created_at", desc=True)
        if limit:
            query = query.limit(limit)
        result = query.execute()
        return result.data
    except Exception as e:
        print(f"关键词查询错误: {str(e)[:100]}")
        return []


def get_statistics(start_date: datetime = None, end_date: datetime = None):
    """获取统计数据（所有人共同）"""
    records = get_records(start_date, end_date)
    
    total = sum(r["amount"] for r in records)
    by_category = {}
    by_user = {}
    max_record = None
    
    for r in records:
        cat = r["category"]
        by_category[cat] = by_category.get(cat, 0) + r["amount"]
        nickname = r.get("nickname", "")
        openid = r.get("openid", "")
        if nickname and nickname != openid[:8]:
            by_user[nickname] = by_user.get(nickname, 0) + r["amount"]
        if not max_record or r["amount"] > max_record["amount"]:
            max_record = r
    
    return {
        "total": total,
        "by_category": by_category,
        "by_user": by_user,
        "count": len(records),
        "max_record": max_record,
        "latest_record": records[0] if records else None
    }


def to_local_datetime(value: str) -> datetime:
    """解析并转为北京时间"""
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        return dt.replace(tzinfo=LOCAL_TZ)
    return dt.astimezone(LOCAL_TZ)


def update_record(record_id: int, amount: float, category: str, description: str):
    """更新记账记录"""
    supabase = get_supabase_client()
    data = {
        "amount": amount,
        "category": category,
        "description": description
    }
    supabase.table("records").update(data).eq("id", record_id).execute()


def delete_record(record_id: int):
    """删除记账记录"""
    supabase = get_supabase_client()
    supabase.table("records").delete().eq("id", record_id).execute()


def get_daily_total(record_date: str):
    """获取按天汇总数据"""
    try:
        supabase = get_supabase_client()
        result = supabase.table("daily_totals").select("*").eq("record_date", record_date).execute()
        return result.data[0] if result.data else None
    except Exception as e:
        print(f"汇总查询错误: {str(e)[:100]}")
        return None


def add_daily_total(record_date: str, amount: float):
    """新增或累加日汇总"""
    supabase = get_supabase_client()
    now = datetime.now(LOCAL_TZ).isoformat()
    existing = get_daily_total(record_date)
    if existing:
        new_total = float(existing.get("total_amount", 0)) + amount
        supabase.table("daily_totals").update({
            "total_amount": new_total,
            "updated_at": now
        }).eq("record_date", record_date).execute()
        return new_total

    supabase.table("daily_totals").insert({
        "record_date": record_date,
        "total_amount": amount,
        "updated_at": now
    }).execute()
    return amount


def archive_old_records():
    """归档超过保留天数的明细，只保留金额汇总"""
    try:
        supabase = get_supabase_client()
        cutoff = datetime.now(LOCAL_TZ) - timedelta(days=RETENTION_DAYS)
        records = (
            supabase.table("records")
            .select("*")
            .lte("created_at", cutoff.isoformat())
            .order("created_at", desc=False)
            .limit(ARCHIVE_BATCH)
            .execute()
            .data
        )
        if not records:
            return 0

        totals_by_date = {}
        for r in records:
            dt = to_local_datetime(r["created_at"])
            date_key = dt.strftime("%Y-%m-%d")
            totals_by_date[date_key] = totals_by_date.get(date_key, 0) + float(r["amount"])

        for date_key, amount in totals_by_date.items():
            add_daily_total(date_key, amount)

        for r in records:
            delete_record(r["id"])

        return len(records)
    except Exception as e:
        print(f"归档错误: {str(e)[:100]}")
        return 0


def get_debt(name: str):
    """获取指定人的欠款记录（别人欠我）"""
    try:
        supabase = get_supabase_client()
        result = supabase.table("debts").select("*").eq("name", name).execute()
        return result.data[0] if result.data else None
    except Exception as e:
        print(f"外债查询错误: {str(e)[:100]}")
        return None


def add_debt(name: str, amount: float, note: str = ""):
    """新增或累加欠款（别人欠我）"""
    supabase = get_supabase_client()
    now = datetime.now(LOCAL_TZ).isoformat()
    existing = get_debt(name)
    if existing:
        new_amount = float(existing.get("amount", 0)) + amount
        data = {
            "amount": new_amount,
            "status": "active",
            "updated_at": now
        }
        if note:
            data["note"] = note
        supabase.table("debts").update(data).eq("name", name).execute()
        return new_amount

    data = {
        "name": name,
        "amount": amount,
        "status": "active",
        "note": note,
        "created_at": now,
        "updated_at": now
    }
    supabase.table("debts").insert(data).execute()
    return amount


def repay_debt(name: str, amount: float):
    """还钱扣减欠款（别人欠我）"""
    supabase = get_supabase_client()
    now = datetime.now(LOCAL_TZ).isoformat()
    existing = get_debt(name)
    if not existing:
        return {"error": "not_found"}

    balance = float(existing.get("amount", 0))
    if amount > balance:
        return {"error": "overpay", "balance": balance}

    new_balance = balance - amount
    status = "paid" if new_balance == 0 else "active"
    data = {
        "amount": new_balance,
        "status": status,
        "updated_at": now
    }
    supabase.table("debts").update(data).eq("name", name).execute()
    return {"balance": new_balance, "status": status}


def list_debts():
    """列出所有未清欠款（别人欠我）"""
    try:
        supabase = get_supabase_client()
        result = supabase.table("debts").select("*").eq("status", "active").order("amount", desc=True).execute()
        return result.data
    except Exception as e:
        print(f"外债列表错误: {str(e)[:100]}")
        return []


# ============ 消息解析 ============
def parse_category(text: str) -> str:
    """从文本中识别分类"""
    text_lower = text.lower()
    for category, keywords in CATEGORY_KEYWORDS.items():
        for keyword in keywords:
            if keyword in text_lower:
                return category
    return "其他"


def parse_record_text(text: str) -> dict:
    """解析记账文本，返回 dict 或 unknown"""
    import re
    text = text.strip()

    # 分类 描述 金额（手动分类优先）
    explicit_match = re.match(r'^(\S+)\s+(.+?)\s+(\d+(?:\.\d+)?)$', text)
    if explicit_match:
        category, desc, amount = explicit_match.groups()
        return {
            "type": "record",
            "amount": float(amount),
            "description": desc.strip(),
            "category": category.strip()
        }

    # 记账：尝试解析金额
    patterns = [
        r'^(.+?)\s+(\d+(?:\.\d+)?)\s*(.*)$',  # 描述 金额 [分类]
        r'^(\d+(?:\.\d+)?)\s+(.+?)$',          # 金额 描述
        r'^(.+?)(\d+(?:\.\d+)?)$',             # 描述金额（无空格）
        r'^(\d+(?:\.\d+)?)(.+?)$',             # 金额描述（无空格）
    ]

    for i, pattern in enumerate(patterns):
        match = re.match(pattern, text)
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


def parse_message(content: str) -> dict:
    """解析用户消息"""
    import re
    content = content.strip()
    
    # 查询命令
    if content in ["今日", "今天"]:
        return {"type": "query", "period": "today"}
    if content in ["昨日", "昨天"]:
        return {"type": "query", "period": "yesterday"}
    if content in ["七天", "近七天"]:
        return {"type": "query", "period": "7days"}
    if content in ["半个月", "十五天", "近半个月"]:
        return {"type": "query", "period": "15days"}
    if content in ["一个月", "近一个月", "30天"]:
        return {"type": "query", "period": "30days"}
    if content in ["本周", "这周"]:
        return {"type": "query", "period": "week"}
    if content in ["本月", "这个月"]:
        return {"type": "query", "period": "month"}
    if content in ["明细", "详情", "记录"]:
        return {"type": "detail"}
    if content in ["帮助", "help", "?"]:
        return {"type": "help"}

    # 导出
    export_excel_match = re.match(r'^(导出excel|导出Excel|导出表格)\s*(.*)$', content)
    if export_excel_match:
        target = export_excel_match.group(2)
        return {"type": "export", "target": target.strip() if target else ""}

    export_match = re.match(r'^导出(?:\s+(.+))?$', content)
    if export_match:
        target = export_match.group(1)
        return {"type": "export", "target": target.strip() if target else ""}

    # 记录修改/删除
    edit_match = re.match(r'^(改|修改)\s+(\d+)\s+(.+)$', content)
    if edit_match:
        index = int(edit_match.group(2))
        rest = edit_match.group(3).strip()
        parsed = parse_record_text(rest)
        if parsed["type"] == "record":
            return {
                "type": "record_edit",
                "index": index,
                "amount": parsed["amount"],
                "description": parsed["description"],
                "category": parsed["category"]
            }
        return {"type": "unknown"}

    delete_match = re.match(r'^(删|删除)\s+(\d+)$', content)
    if delete_match:
        return {"type": "record_delete", "index": int(delete_match.group(2))}

    # 外债相关
    debt_add_match = re.match(r'^欠款\s+(\S+)\s+(\d+(?:\.\d+)?)\s*(.*)$', content)
    if debt_add_match:
        name, amount, note = debt_add_match.groups()
        return {"type": "debt_add", "name": name, "amount": float(amount), "note": note.strip()}

    debt_repay_match = re.match(r'^还钱\s+(\S+)\s+(\d+(?:\.\d+)?)$', content)
    if debt_repay_match:
        name, amount = debt_repay_match.groups()
        return {"type": "debt_repay", "name": name, "amount": float(amount)}

    debt_query_match = re.match(r'^外债(?:\s+(\S+))?$', content)
    if debt_query_match:
        name = debt_query_match.group(1)
        if name:
            return {"type": "debt_query_person", "name": name}
        return {"type": "debt_query_all"}

    # 自定义分类查询
    if content.startswith("分类 "):
        return {"type": "query_category", "category": content.split(maxsplit=1)[1].strip()}
    if content.startswith("统计 "):
        return {"type": "query_category", "category": content.split(maxsplit=1)[1].strip()}
    
    # 分类查询
    for category in CATEGORY_KEYWORDS.keys():
        if content == category:
            return {"type": "query_category", "category": category}
    
    return parse_record_text(content)


def get_date_range(period: str):
    """获取日期范围"""
    now = datetime.now(LOCAL_TZ)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    
    if period == "today":
        return today_start, now
    elif period == "yesterday":
        yesterday_start = today_start - timedelta(days=1)
        yesterday_end = today_start - timedelta(seconds=1)
        return yesterday_start, yesterday_end
    elif period == "7days":
        return now - timedelta(days=7), now
    elif period == "15days":
        return now - timedelta(days=15), now
    elif period == "30days":
        return now - timedelta(days=30), now
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
    
    avg = stats["total"] / stats["count"] if stats["count"] else 0
    lines = [
        f"📊 {period_name}统计（共同）",
        f"💰 总支出：{stats['total']:.2f} 元",
        f"🧾 记录数：{stats['count']} 条",
        f"📉 平均单笔：{avg:.2f} 元",
        ""
    ]
    
    # 按分类
    if stats["by_category"]:
        lines.append("📂 分类明细：")
        top_categories = sorted(stats["by_category"].items(), key=lambda x: -x[1])
        for cat, amount in top_categories:
            lines.append(f"  • {cat}：{amount:.2f} 元")
    
    # 按用户
    if len(stats["by_user"]) > 1:
        lines.append("")
        lines.append("👥 个人支出：")
        for user, amount in sorted(stats["by_user"].items(), key=lambda x: -x[1]):
            lines.append(f"  • {user}：{amount:.2f} 元")

    if stats.get("max_record"):
        lines.append("")
        lines.append(f"🔥 最高单笔：{stats['max_record']['description']} {stats['max_record']['amount']:.2f} 元 [{stats['max_record']['category']}]")

    if stats.get("latest_record"):
        latest = stats["latest_record"]
        lines.append(f"🕒 最近一笔：{latest['description']} {latest['amount']:.2f} 元 [{latest['category']}]")
    
    return "\n".join(lines)


def format_records(records: list, limit: int = 20) -> str:
    """格式化记录列表"""
    if not records:
        return "📝 暂无记录"
    
    lines = ["📝 最近记录（共同）："]
    for i, r in enumerate(records[:limit], start=1):
        dt = to_local_datetime(r["created_at"])
        date_str = dt.strftime("%m-%d %H:%M")
        lines.append(f"{i}. {date_str} {r['description']} {r['amount']:.2f}元 [{r['category']}]")
    
    if len(records) > limit:
        lines.append(f"  ... 共 {len(records)} 条记录")
    
    return "\n".join(lines)


def build_export_signature(openid: str, period: str, ts: int) -> str:
    """生成导出链接签名"""
    payload = f"{openid}|{period}|{ts}"
    return hmac.new(TOKEN.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()


def build_export_link(openid: str, period: str) -> str:
    """生成导出 Excel 的临时链接"""
    if not PUBLIC_BASE_URL:
        return ""
    ts = int(time.time())
    sig = build_export_signature(openid, period, ts)
    return f"{PUBLIC_BASE_URL}/api/export?openid={openid}&period={period}&ts={ts}&sig={sig}"


def verify_export_signature(openid: str, period: str, ts: str, sig: str) -> bool:
    """校验导出链接签名与有效期"""
    if not openid or not period or not ts or not sig:
        return False
    try:
        ts_int = int(ts)
    except ValueError:
        return False
    if abs(int(time.time()) - ts_int) > EXPORT_TTL_SECONDS:
        return False
    expected = build_export_signature(openid, period, ts_int)
    return hmac.compare_digest(expected, sig)


def build_export_excel_bytes(records: list, limit: int = 1000) -> bytes:
    """导出 Excel（二进制）"""
    wb = Workbook()
    ws = wb.active
    ws.title = "records"
    ws.append(["日期", "描述", "金额", "分类"])

    for r in records[:limit]:
        dt = to_local_datetime(r["created_at"])
        date_str = dt.strftime("%Y-%m-%d %H:%M")
        ws.append([date_str, r["description"], float(r["amount"]), r["category"]])

    bio = io.BytesIO()
    wb.save(bio)
    bio.seek(0)
    return bio.read()


def format_debts(debts: list) -> str:
    """格式化外债列表"""
    if not debts:
        return "📌 外债总览：暂无欠款"

    total = sum(float(d.get("amount", 0)) for d in debts)
    lines = ["📌 外债总览（别人欠我）"]
    for d in debts:
        lines.append(f"  • {d['name']}：{float(d['amount']):.2f} 元")
    lines.append(f"合计：{total:.2f} 元")
    return "\n".join(lines)


def get_help_text() -> str:
    """返回帮助信息"""
    return """📖 记账机器人使用指南

【记账】
发送：分类 描述 金额
例如：夜宵 鸡锁骨 18
      夜宵 泡面 18
      买菜 西红柿 25
也支持：描述 金额 / 金额 描述（自动分类）

【查询统计】
发送：今日 / 昨日 / 七天 / 半个月 / 一个月 / 本周 / 本月

【查看明细】
发送：明细

【修改/删除记录】
发送：改 1 夜宵 鸡锁骨 16
发送：删 2

【按分类查询】
发送：分类 夜宵 / 统计 夜宵
或发送分类名：餐饮 / 交通 / 购物 / 娱乐 / 居住 / 医疗 / 教育

【外债（别人欠我）】
欠款 张三 5000
还钱 张三 500
外债
外债 张三

【导出Excel】
发送：导出 今日 / 昨日 / 七天 / 半个月 / 一个月
发送：导出表格 今日 / 昨日 / 七天 / 半个月 / 一个月

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

    elif parsed["type"] == "record_edit":
        try:
            records = get_records(limit=20)
            index = parsed["index"]
            if index < 1 or index > len(records):
                return "❌ 编号无效，请先发送「明细」查看编号"
            record = records[index - 1]
            update_record(record["id"], parsed["amount"], parsed["category"], parsed["description"])
            return f"✅ 已修改第 {index} 条\n{parsed['description']}：{parsed['amount']:.2f} 元\n分类：{parsed['category']}"
        except Exception as e:
            print(f"修改记录失败: {str(e)[:100]}")
            return "❌ 修改失败，请稍后重试"

    elif parsed["type"] == "record_delete":
        try:
            records = get_records(limit=20)
            index = parsed["index"]
            if index < 1 or index > len(records):
                return "❌ 编号无效，请先发送「明细」查看编号"
            record = records[index - 1]
            delete_record(record["id"])
            return f"✅ 已删除第 {index} 条：{record['description']} {record['amount']:.2f} 元"
        except Exception as e:
            print(f"删除记录失败: {str(e)[:100]}")
            return "❌ 删除失败，请稍后重试"
    
    elif parsed["type"] == "query":
        try:
            start_date, end_date = get_date_range(parsed["period"])
            period_names = {
                "today": "今日",
                "yesterday": "昨日",
                "7days": "近七天",
                "15days": "近半个月",
                "30days": "近一个月",
                "week": "本周",
                "month": "本月"
            }
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
            count = len(records)
            avg = total / count if count else 0
            if count > 0:
                result = (
                    f"📂 本月【{parsed['category']}】支出：{total:.2f} 元\n"
                    f"🧾 记录数：{count} 条\n"
                    f"📉 平均单笔：{avg:.2f} 元\n\n"
                )
                result += format_records(records, limit=5)
                return result

            keyword_records = get_records_by_keyword(start_date=month_start, keyword=parsed["category"])
            keyword_total = sum(r["amount"] for r in keyword_records)
            keyword_count = len(keyword_records)
            keyword_avg = keyword_total / keyword_count if keyword_count else 0
            if keyword_count == 0:
                return "📝 暂无记录"

            result = (
                f"🔎 本月包含「{parsed['category']}」的支出：{keyword_total:.2f} 元\n"
                f"🧾 记录数：{keyword_count} 条\n"
                f"📉 平均单笔：{keyword_avg:.2f} 元\n\n"
            )
            result += format_records(keyword_records, limit=5)
            return result
        except Exception as e:
            print(f"分类查询失败: {str(e)[:100]}")
            return "❌ 查询失败，请稍后重试"
    
    elif parsed["type"] == "debt_add":
        try:
            new_amount = add_debt(parsed["name"], parsed["amount"], parsed.get("note", ""))
            note_text = f"\n备注：{parsed['note']}" if parsed.get("note") else ""
            return f"✅ 已记录：{parsed['name']} 欠你 {parsed['amount']:.2f} 元{note_text}\n当前欠款：{new_amount:.2f} 元"
        except Exception as e:
            print(f"外债记录失败: {str(e)[:100]}")
            return "❌ 外债记录失败，请稍后重试"

    elif parsed["type"] == "debt_repay":
        try:
            result = repay_debt(parsed["name"], parsed["amount"])
            if result.get("error") == "not_found":
                return f"❌ 未找到 {parsed['name']} 的欠款记录"
            if result.get("error") == "overpay":
                return f"❌ {parsed['name']} 当前欠款 {result['balance']:.2f} 元，本次还款超出，请修改金额"
            if result["status"] == "paid":
                return f"✅ 还钱 {parsed['name']} {parsed['amount']:.2f} 元\n{parsed['name']} 已还清"
            return f"✅ 还钱 {parsed['name']} {parsed['amount']:.2f} 元\n剩余欠款 {result['balance']:.2f} 元"
        except Exception as e:
            print(f"外债还款失败: {str(e)[:100]}")
            return "❌ 还款失败，请稍后重试"

    elif parsed["type"] == "debt_query_all":
        try:
            debts = list_debts()
            return format_debts(debts)
        except Exception as e:
            print(f"外债查询失败: {str(e)[:100]}")
            return "❌ 外债查询失败，请稍后重试"

    elif parsed["type"] == "debt_query_person":
        try:
            debt = get_debt(parsed["name"])
            if not debt or float(debt.get("amount", 0)) <= 0:
                return f"📌 {parsed['name']} 当前无欠款"
            return f"📌 {parsed['name']} 当前欠款：{float(debt['amount']):.2f} 元"
        except Exception as e:
            print(f"外债单人查询失败: {str(e)[:100]}")
            return "❌ 外债查询失败，请稍后重试"

    elif parsed["type"] == "detail":
        try:
            cutoff = datetime.now() - timedelta(days=RETENTION_DAYS)
            records = get_records(start_date=cutoff)
            return format_records(records, limit=20) + f"\n\n仅展示近 {RETENTION_DAYS} 天明细"
        except Exception as e:
            print(f"明细查询失败: {str(e)[:100]}")
            return "❌ 查询失败，请稍后重试"

    elif parsed["type"] == "export":
        try:
            target = parsed.get("target", "")
            mapping = {
                "今日": "today",
                "昨天": "yesterday",
                "昨日": "yesterday",
                "七天": "7days",
                "近七天": "7days",
                "半个月": "15days",
                "十五天": "15days",
                "近半个月": "15days",
                "一个月": "30days",
                "近一个月": "30days",
                "本周": "week",
                "本月": "month"
            }
            period_key = mapping.get(target, "month")
            export_link = build_export_link(openid, period_key)
            if not export_link:
                return "❌ 未配置导出地址，请先设置 PUBLIC_BASE_URL"
            return f"📥 Excel 导出链接（10分钟内有效）：\n{export_link}"
        except Exception as e:
            print(f"导出失败: {str(e)[:100]}")
            return "❌ 导出失败，请稍后重试"
    
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


@app.get("/api/export")
async def export_excel(request: Request):
    """导出 Excel"""
    try:
        params = dict(request.query_params)
        openid = params.get("openid", "")
        period = params.get("period", "")
        ts = params.get("ts", "")
        sig = params.get("sig", "")

        if not verify_export_signature(openid, period, ts, sig):
            return Response(content="invalid", status_code=403)

        start_date, end_date = get_date_range(period)
        records = get_records(start_date=start_date, end_date=end_date)
        data = build_export_excel_bytes(records)
        filename = f"records-{period}.xlsx"
        headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
        return StreamingResponse(io.BytesIO(data),
                                 media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                 headers=headers)
    except Exception as e:
        print(f"导出错误: {str(e)[:100]}")
        return Response(content="error", status_code=500)
