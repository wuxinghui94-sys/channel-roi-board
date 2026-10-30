import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
import requests
import json
import os
import sys
import io
import re

# 1. 页面基本配置
st.set_page_config(
    page_title="渠道ROI与转化分析看板",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 2. 现代轻奢风格 CSS
st.markdown("""
<style>
    /* 全局间距 */
    .block-container {
        padding-top: 1.2rem;
        padding-bottom: 2rem;
    }
    
    /* 核心转化率超级卡片 */
    .metric-hero-card {
        background: linear-gradient(135deg, #1e3a8a 0%, #2563eb 50%, #3b82f6 100%);
        border-radius: 12px;
        padding: 20px 24px;
        color: #ffffff;
        box-shadow: 0 4px 14px 0 rgba(37, 99, 235, 0.25);
        margin-bottom: 14px;
    }
    .metric-hero-title {
        font-size: 13px;
        font-weight: 500;
        opacity: 0.9;
        margin-bottom: 4px;
    }
    .metric-hero-value {
        font-size: 34px;
        font-weight: 800;
        letter-spacing: -0.5px;
    }
    .metric-hero-sub {
        font-size: 12.5px;
        opacity: 0.85;
        margin-top: 4px;
    }
    
    /* 次级通用指标卡片 */
    .metric-sub-card {
        background-color: #ffffff;
        border: 1px solid #e2e8f0;
        border-radius: 10px;
        padding: 14px 16px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.05);
        margin-bottom: 14px;
    }
    .metric-sub-title {
        font-size: 12.5px;
        color: #64748b;
        font-weight: 500;
        margin-bottom: 2px;
    }
    .metric-sub-value {
        font-size: 22px;
        font-weight: 700;
        color: #0f172a;
    }
    .metric-sub-badge {
        font-size: 11.5px;
        display: inline-block;
        padding: 2px 7px;
        border-radius: 4px;
        margin-top: 3px;
        font-weight: 500;
    }
    
    /* 区分项目标识 */
    .project-pill {
        display: inline-block;
        padding: 4px 14px;
        border-radius: 20px;
        background-color: #e0f2fe;
        color: #0369a1;
        font-weight: 600;
        font-size: 13.5px;
        margin-bottom: 8px;
    }
    
    /* 隐藏 DataFrame 原生未排版下载按钮 */
    [data-testid="stElementToolbar"] button[title*="CSV"],
    [data-testid="stElementToolbar"] button[title*="csv"] {
        display: none !important;
    }
</style>
""", unsafe_allow_html=True)

# 3. 飞书数据源配置
# 3. 飞书数据源配置 (安全机制：从 Streamlit Secrets 加密保险箱动态读取)
def get_secret(key, default=""):
    try:
        if key in st.secrets:
            return str(st.secrets[key]).strip()
    except Exception:
        pass
    return default

APP_ID = get_secret("FEISHU_APP_ID", "")
APP_SECRET = get_secret("FEISHU_APP_SECRET", "")
SPREADSHEET_TOKEN = get_secret("FEISHU_SPREADSHEET_TOKEN", "")

PROJECT_CONFIG = {
    "晓辉项目": {
        "period_sheet": "9a3aed",
        "monthly_sheet": "2lVk5y",
        "team_monthly_sheet": "uTFJkV",
        "has_team": True
    },
    "静弘项目": {
        "period_sheet": "ii6DLq",
        "monthly_sheet": "XUsKw6",
        "has_team": False
    },
    "钧岚项目": {
        "period_sheet": "yQMpU7",
        "monthly_sheet": "Qriu5n",
        "has_team": False
    }
}

# 核心重点关注渠道定义（自动置顶）
CORE_CHANNELS_MAP = {
    "晓辉项目": [
        "19.9视频号短带",
        "19.9视频号腾讯广告",
        "19.9视频号小店投放",
        "29.9小红书短带自投",
        "29.9百度短带"
    ],
    "静弘项目": [
        "19.9视频号短带",
        "19.9视频号小店投放",
        "19.9视频号素人直播",
        "9.9视频号短带"
    ],
    "钧岚项目": [
        "19.9视频号短带",
        "19.9视频号直播",
        "59.9视频号短带"
    ]
}

def sort_channels_core_first(channels, proj_name):
    core_list = CORE_CHANNELS_MAP.get(proj_name, [])
    in_core = [c for c in core_list if c in channels]
    others = sorted([c for c in channels if c not in core_list])
    return in_core + others

def safe_num(v, default=0.0):
    if v is None: return default
    if isinstance(v, (int, float)):
        return float(v) if not np.isnan(v) else default
    s = str(v).strip()
    if s == '' or s in ['#DIV/0!', '#VALUE!', '#N/A', 'None', 'nan']:
        return default
    if s.endswith('%'):
        try: return float(s[:-1]) / 100.0
        except: return default
    try: return float(s)
    except: return default

def get_tenant_access_token():
    url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
    res = requests.post(url, json={"app_id": APP_ID, "app_secret": APP_SECRET}, timeout=15)
    return res.json().get("tenant_access_token")

def fetch_feishu_sheet_data(token, sheet_id, max_rows=300):
    url = f"https://open.feishu.cn/open-apis/sheets/v2/spreadsheets/{SPREADSHEET_TOKEN}/values/{sheet_id}!A1:AZ{max_rows}?valueRenderOption=UnformattedValue"
    headers = {"Authorization": f"Bearer {token}"}
    res = requests.get(url, headers=headers, timeout=25)
    if res.status_code != 200:
        return pd.DataFrame()
    data = res.json().get("data", {}).get("valueRange", {}).get("values", [])
    if not data: return pd.DataFrame()
    
    header = [str(c).strip() if c is not None else '' for c in data[0]]
    while header and header[-1] == '':
        header.pop()
        
    rows = []
    for r in data[1:]:
        rows.append(r[:len(header)] + [None] * max(0, len(header) - len(r)))
    return pd.DataFrame(rows, columns=header)

# 解析期次数据
def parse_period_sheet(proj_name, raw_df):
    if raw_df.empty: return pd.DataFrame()
    df = raw_df.copy()
    
    p_col = next((c for c in df.columns if c in ['期次', '期数']), None)
    d_col = next((c for c in df.columns if '时间' in c or '日期' in c), None)
    ch_col = next((c for c in df.columns if c == '渠道'), None)
    
    if proj_name == "晓辉项目":
        if p_col:
            df['当前期次'] = df[p_col].replace('', np.nan).replace('None', np.nan).ffill()
        if d_col:
            df['开课时间'] = df[d_col].replace('', np.nan).replace('None', np.nan).ffill()
        df['渠道名称'] = df[ch_col] if ch_col else ''
        
    elif proj_name in ["静弘项目", "钧岚项目"]:
        curr_p = None
        curr_d = None
        period_list = []
        date_list = []
        for _, row in df.iterrows():
            pval = str(row.get(p_col, '')).strip() if row.get(p_col) is not None else ''
            dval = str(row.get(d_col, '')).strip() if row.get(d_col) is not None else ''
            if pval and pval not in ['None', 'nan', ''] and not ('合计' in pval or '总计' in pval):
                curr_p = pval
            if dval and dval not in ['None', 'nan', '']:
                curr_d = dval
            period_list.append(curr_p)
            date_list.append(curr_d)
        df['当前期次'] = period_list
        df['开课时间'] = date_list
        df['渠道名称'] = df[ch_col] if ch_col else ''
        
    df = df.dropna(subset=['当前期次'])
    df = df[df['当前期次'].astype(str).str.strip().isin(['None', 'nan', '']) == False]
    
    ch_str = df['渠道名称'].astype(str).str.strip()
    p_str = df['当前期次'].astype(str).str.strip()
    df['is_summary'] = ch_str.str.contains('总计|合计') | p_str.str.contains('总计|合计') | ch_str.isin(['None', 'nan', ''])
    
    num_cols_map = {
        '线索量': next((c for c in df.columns if '线索量' in c or '粉量' in c), None),
        '总转化率': next((c for c in df.columns if c == '总转化率'), None),
        '总转化量': next((c for c in df.columns if c == '总转化量'), None),
        '直播转化': next((c for c in df.columns if '直播转化' in str(c) and '率' not in str(c)), None),
        '私聊转化': next((c for c in df.columns if ('社群转化' in str(c) or '私聊转化' in str(c)) and '率' not in str(c)), None),
        '单粉成本': next((c for c in df.columns if '单粉成本' in c or '粉成本' in c), None),
        '总成本': next((c for c in df.columns if '总成本' in c), None),
        '总销售额': next((c for c in df.columns if '总销售额' in c), None),
        'roi': next((c for c in df.columns if c.lower() == 'roi'), None),
        '总盈亏': next((c for c in df.columns if '盈亏' in c), None),
        '正式课退单': next((c for c in df.columns if c == '正式课退单'), None),
    }
    
    for target_col, src_col in num_cols_map.items():
        if src_col and src_col in df.columns:
            df[target_col] = df[src_col].apply(safe_num)
        else:
            df[target_col] = 0.0
            
    # 【成交场景归因】：直播与私聊转化占比（针对总单数）
    df['直播占比'] = np.where(df['总转化量'] > 0, df['直播转化'] / df['总转化量'], 0.0)
    df['私聊占比'] = np.where(df['总转化量'] > 0, df['私聊转化'] / df['总转化量'], 0.0)

    # 【核心修正】：正式课退单率严格按照业务公式计算 = 正式课退单 / (正式课退单 + 总单数)
    refund_denom = df['正式课退单'] + df['总转化量']
    df['正式课总退单率'] = np.where(refund_denom > 0, df['正式课退单'] / refund_denom, 0.0)
            
    df['项目'] = proj_name
    return df

# 解析月度数据
def parse_monthly_sheet(proj_name, raw_df, is_team=False):
    if raw_df.empty: return pd.DataFrame()
    df = raw_df.copy()
    
    m_col = next((c for c in df.columns if c in ['月份', '期数']), df.columns[0])
    ch_col = next((c for c in df.columns if c == '渠道'), None)
    
    df['月份标签'] = (
        df[m_col]
        .replace('', np.nan)
        .replace('None', np.nan)
        .replace('nan', np.nan)
        .ffill()
    )
    df['渠道名称'] = df[ch_col].astype(str).str.strip() if ch_col else ''
    
    df = df[df['渠道名称'].isin(['None', 'nan', '']) == False]
    df['is_summary'] = df['渠道名称'].str.contains('总计|合计') | df['月份标签'].str.contains('总计|合计')
    
    num_cols_map = {
        '线索量': next((c for c in df.columns if '线索量' in c or '粉量' in c), None),
        '总转化率': next((c for c in df.columns if c == '总转化率'), None),
        '总转化量': next((c for c in df.columns if c == '总转化量'), None),
        '直播转化': next((c for c in df.columns if '直播转化' in str(c) and '率' not in str(c)), None),
        '私聊转化': next((c for c in df.columns if ('社群转化' in str(c) or '私聊转化' in str(c)) and '率' not in str(c)), None),
        '单粉成本': next((c for c in df.columns if '单粉成本' in c or '粉成本' in c), None),
        '总成本': next((c for c in df.columns if '总成本' in c), None),
        '总销售额': next((c for c in df.columns if '总销售额' in c), None),
        'roi': next((c for c in df.columns if c.lower() == 'roi'), None),
        '总盈亏': next((c for c in df.columns if '盈亏' in c), None),
        '正式课退单': next((c for c in df.columns if c == '正式课退单'), None),
    }
    
    for target_col, src_col in num_cols_map.items():
        if src_col and src_col in df.columns:
            df[target_col] = df[src_col].apply(safe_num)
        else:
            df[target_col] = 0.0
            
    # 【成交场景归因】：直播与私聊转化占比（针对总单数）
    df['直播占比'] = np.where(df['总转化量'] > 0, df['直播转化'] / df['总转化量'], 0.0)
    df['私聊占比'] = np.where(df['总转化量'] > 0, df['私聊转化'] / df['总转化量'], 0.0)

    # 【核心修正】：正式课退单率严格按照业务公式计算 = 正式课退单 / (正式课退单 + 总单数)
    refund_denom = df['正式课退单'] + df['总转化量']
    df['正式课总退单率'] = np.where(refund_denom > 0, df['正式课退单'] / refund_denom, 0.0)
            
    df['项目'] = proj_name
    return df

# 同一期次内相同渠道的智能加权聚合函数（解决 127B 新老课分段导致的单期双点怪异曲线）
def aggregate_channel_by_period(df_part):
    if df_part.empty: return pd.DataFrame()
    
    period_order = []
    for p in df_part['当前期次']:
        if p not in period_order:
            period_order.append(p)
            
    records = []
    for (p, ch), group in df_part.groupby(['当前期次', '渠道名称'], sort=False, as_index=False):
        leads = group['线索量'].sum()
        total_conv = group['总转化量'].sum()
        conv_rate = (total_conv / leads) if leads > 0 else 0.0
        
        live_conv = group['直播转化'].sum()
        chat_conv = group['私聊转化'].sum()
        live_share = (live_conv / total_conv) if total_conv > 0 else 0.0
        chat_share = (chat_conv / total_conv) if total_conv > 0 else 0.0

        cost = group['总成本'].sum()
        cac = (cost / leads) if leads > 0 else 0.0
        
        revenue = group['总销售额'].sum()
        roi = (revenue / cost) if cost > 0 else 0.0
        profit = group['总盈亏'].sum()
        
        refund = group['正式课退单'].sum()
        # 【核心修正】：正式课退单率严格按照业务公式计算 = 正式课退单 / (正式课退单 + 总单数)
        refund_denom = refund + total_conv
        refund_rate = (refund / refund_denom) if refund_denom > 0 else 0.0
        
        d_val = group['开课时间'].iloc[0] if '开课时间' in group.columns else ''
        
        records.append({
            '当前期次': p,
            '开课时间': d_val,
            '渠道名称': ch,
            '线索量': leads,
            '总转化率': conv_rate,
            '总转化量': total_conv,
            '直播转化': live_conv,
            '直播占比': live_share,
            '私聊转化': chat_conv,
            '私聊占比': chat_share,
            '单粉成本': cac,
            '总成本': cost,
            '总销售额': revenue,
            'roi': roi,
            '总盈亏': profit,
            '正式课退单': refund,
            '正式课总退单率': refund_rate
        })
        
    res = pd.DataFrame(records)
    res['sort_key'] = res['当前期次'].apply(lambda x: period_order.index(x) if x in period_order else 999)
    res.sort_values(by=['sort_key'], inplace=True)
    res.drop(columns=['sort_key'], inplace=True)
    return res

# 格式化期次 X 轴标签（去除（）及内部日期，只保留纯净期次名称，彻底保持清爽易读）
def format_period_axis_label(p_str):
    if not p_str or pd.isna(p_str):
        return ""
    s = str(p_str).strip()
    # 彻底去除中英文括号及其中间所有开课日期/数字内容
    clean = re.sub(r'[\(（].*?[\)）]', '', s).strip()
    return clean if clean else s

# 全期次大盘汇总（当用户全选所有渠道或选择全期大盘视角时，每个期次全量加权汇总为 1 条记录）
def aggregate_by_period_overall(df_part):
    if df_part.empty: return pd.DataFrame()
    
    period_order = []
    for p in df_part['当前期次']:
        if p not in period_order:
            period_order.append(p)
            
    records = []
    for p, group in df_part.groupby('当前期次', sort=False):
        leads = group['线索量'].sum()
        total_conv = group['总转化量'].sum()
        conv_rate = (total_conv / leads) if leads > 0 else 0.0
        
        live_conv = group['直播转化'].sum()
        chat_conv = group['私聊转化'].sum()
        live_share = (live_conv / total_conv) if total_conv > 0 else 0.0
        chat_share = (chat_conv / total_conv) if total_conv > 0 else 0.0

        cost = group['总成本'].sum()
        cac = (cost / leads) if leads > 0 else 0.0
        revenue = group['总销售额'].sum()
        roi = (revenue / cost) if cost > 0 else 0.0
        profit = group['总盈亏'].sum()
        
        refund = group['正式课退单'].sum()
        refund_denom = refund + total_conv
        refund_rate = (refund / refund_denom) if refund_denom > 0 else 0.0
        
        d_val = group['开课时间'].iloc[0] if '开课时间' in group.columns else ''
        
        records.append({
            '当前期次': p,
            '开课时间': d_val,
            '渠道名称': '全渠道大盘汇总',
            '线索量': leads,
            '总转化率': conv_rate,
            '总转化量': total_conv,
            '直播转化': live_conv,
            '直播占比': live_share,
            '私聊转化': chat_conv,
            '私聊占比': chat_share,
            '单粉成本': cac,
            '总成本': cost,
            '总销售额': revenue,
            'roi': roi,
            '总盈亏': profit,
            '正式课退单': refund,
            '正式课总退单率': refund_rate
        })
        
    res = pd.DataFrame(records)
    res['sort_key'] = res['当前期次'].apply(lambda x: period_order.index(x) if x in period_order else 999)
    res.sort_values(by=['sort_key'], inplace=True)
    res.drop(columns=['sort_key'], inplace=True)
    return res

# 表格列配置：ROI等关键商业指标前置，直播/私聊后置作为次级辅助列
def build_clean_column_config(has_period_col=False):
    cfg = {}
    if has_period_col:
        cfg["当前期次"] = st.column_config.TextColumn("期次", width="medium")
        
    cfg.update({
        "渠道名称": st.column_config.TextColumn("渠道", width="medium"),
        "线索量": st.column_config.NumberColumn("线索量 (人)", format="%d"),
        "总转化率": st.column_config.NumberColumn("🔥 总转化率", format="%.2f%%", help="总单数 / 线索量"),
        "总转化量": st.column_config.NumberColumn("总单数", format="%.1f"),
        "roi": st.column_config.NumberColumn("ROI", format="%.2f"),
        "总销售额": st.column_config.NumberColumn("总销售额", format="¥%.2f"),
        "总成本": st.column_config.NumberColumn("总成本", format="¥%.2f"),
        "总盈亏": st.column_config.NumberColumn("总盈亏", format="¥%.2f"),
        "单粉成本": st.column_config.NumberColumn("单粉成本", format="¥%.2f"),
        "正式课退单": st.column_config.NumberColumn("正式课退单", format="%d"),
        "正式课总退单率": st.column_config.NumberColumn("正式课退单率", format="%.2f%%", help="公式：正式课退单 / (正式课退单 + 总单数)"),
        "直播转化": st.column_config.NumberColumn("🎙️ 直播转化", format="%.1f", help="直播间现场成交单数"),
        "直播占比": st.column_config.NumberColumn("直播占比", format="%.1f%%", help="直播转化单数 / 总成交单数"),
        "私聊转化": st.column_config.NumberColumn("💬 私聊转化", format="%.1f", help="私域1v1私聊/社群跟进成交单数"),
        "私聊占比": st.column_config.NumberColumn("私聊占比", format="%.1f%%", help="私聊转化单数 / 总成交单数"),
    })
    return cfg

# 准备展示的 DataFrame：关键ROI前置，直播与私聊后置
def prepare_display_dataframe(df_input, is_cross_period=False):
    df_out = df_input.copy()
    rate_cols = ['总转化率', '正式课总退单率', '直播占比', '私聊占比']
    for c in rate_cols:
        if c in df_out.columns:
            df_out[c] = df_out[c] * 100.0
            
    cols_order = []
    if is_cross_period and '当前期次' in df_out.columns:
        cols_order.append('当前期次')
    cols_order.extend([
        '渠道名称', '线索量', '总转化率', '总转化量',
        'roi', '总销售额', '总成本', '总盈亏', '单粉成本',
        '正式课退单', '正式课总退单率',
        '直播转化', '直播占比', '私聊转化', '私聊占比'
    ])
    valid_cols = [c for c in cols_order if c in df_out.columns]
    return df_out[valid_cols]

@st.cache_data(ttl=600)
def load_all_dashboard_data():
    token = get_tenant_access_token()
    all_data = {}
    
    for proj_name, cfg in PROJECT_CONFIG.items():
        all_data[proj_name] = {}
        raw_p = fetch_feishu_sheet_data(token, cfg["period_sheet"])
        all_data[proj_name]["period_df"] = parse_period_sheet(proj_name, raw_p)
        
        raw_m = fetch_feishu_sheet_data(token, cfg["monthly_sheet"])
        all_data[proj_name]["monthly_df"] = parse_monthly_sheet(proj_name, raw_m, is_team=False)
        
        if cfg.get("has_team") and cfg.get("team_monthly_sheet"):
            raw_tm = fetch_feishu_sheet_data(token, cfg["team_monthly_sheet"])
            all_data[proj_name]["team_monthly_df"] = parse_monthly_sheet(proj_name, raw_tm, is_team=True)
            
    return all_data

# =============================================================================
# 登录权限验证机制 (安全锁)
# =============================================================================
AUTH_CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "auth_config.json")
DEFAULT_PASSWORD = ""

def get_auth_password():
    pwd = get_secret("DASHBOARD_PASSWORD", "")
    if pwd:
        return pwd
    if os.path.exists(AUTH_CONFIG_FILE):
        try:
            with open(AUTH_CONFIG_FILE, "r", encoding="utf-8") as f:
                cfg = json.load(f)
                return str(cfg.get("password", DEFAULT_PASSWORD)).strip()
        except Exception:
            return DEFAULT_PASSWORD
    else:
        try:
            with open(AUTH_CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump({"password": DEFAULT_PASSWORD}, f, ensure_ascii=False, indent=2)
        except Exception:
            pass
        return DEFAULT_PASSWORD

def set_auth_password(new_pwd):
    try:
        with open(AUTH_CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump({"password": str(new_pwd).strip()}, f, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False

def check_auth():
    if st.session_state.get("authenticated", False):
        return True

    current_pwd = get_auth_password()
    
    # 未登录时隐藏侧边栏
    st.markdown("""
    <style>
        [data-testid="stSidebar"] {
            display: none !important;
        }
        [data-testid="stSidebarCollapsedControl"] {
            display: none !important;
        }
    </style>
    """, unsafe_allow_html=True)
    
    # 居中卡片式登录表单
    _, login_col, _ = st.columns([1, 1.4, 1])
    with login_col:
        st.markdown("<br><br>", unsafe_allow_html=True)
        st.markdown("""
        <div style='background: #ffffff; border: 1px solid #e2e8f0; border-radius: 16px; padding: 28px 32px; box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.07); text-align: center; margin-bottom: 20px;'>
            <div style='font-size: 40px; margin-bottom: 6px;'>🔒</div>
            <h2 style='color: #0f172a; margin-bottom: 6px; font-weight: 700; font-size: 20px;'>渠道投放 ROI 与转化分析看板</h2>
            <div style='color: #64748b; font-size: 13px;'>内部经营敏感数据，请先输入访问密码验证身份</div>
        </div>
        """, unsafe_allow_html=True)
        
        with st.form("login_form", clear_on_submit=False):
            entered_password = st.text_input("🔑 请输入访问密码", type="password", placeholder="请输入访问密码...")
            submit_btn = st.form_submit_button("🚀 验证并进入看板", use_container_width=True)
            
            if submit_btn:
                if entered_password == current_pwd:
                    st.session_state["authenticated"] = True
                    st.success("✅ 验证成功，正在进入看板...")
                    st.rerun()
                else:
                    st.error("❌ 密码错误，请核对后重试！")
                    
        st.markdown("""
        <div style='text-align: center; margin-top: 15px; color: #94a3b8; font-size: 12px;'>
            💡 内部经营数据系统，如需重置密码请联系管理员在后台配置文件处理。
        </div>
        """, unsafe_allow_html=True)
        
    return False

if not check_auth():
    st.stop()

# 侧边栏：项目选择与控制
with st.sidebar:
    st.markdown("## 📊 渠道 ROI 看板")
    st.caption("数据源: 飞书《渠道表更新》")
    
    # 安全验证与权限控制
    st.markdown("""
    <div style='background: #f0fdf4; border: 1px solid #bbf7d0; border-radius: 8px; padding: 6px 12px; margin-bottom: 8px; display: flex; align-items: center; justify-content: space-between;'>
        <span style='color: #166534; font-size: 12px; font-weight: 600;'>🛡️ 已登录 (管理员权限)</span>
    </div>
    """, unsafe_allow_html=True)
    
    col_auth1, col_auth2 = st.columns([1, 1])
    with col_auth1:
        if st.button("🔒 退出登录", use_container_width=True):
            st.session_state["authenticated"] = False
            st.rerun()
    with col_auth2:
        if st.button("🔄 刷新数据", use_container_width=True):
            st.cache_data.clear()
            st.rerun()
            

                    
    st.markdown("---")
    st.markdown("### 🏢 选择项目")
    selected_project = st.radio(
        "切换分析业务线",
        options=["晓辉项目", "静弘项目", "钧岚项目"],
        index=0,
        label_visibility="collapsed"
    )

# 加载数据
try:
    with st.spinner(f"正在读取【{selected_project}】数据..."):
        data_bundle = load_all_dashboard_data()
        current_proj_data = data_bundle.get(selected_project, {})
        period_df = current_proj_data.get("period_df", pd.DataFrame())
        monthly_df = current_proj_data.get("monthly_df", pd.DataFrame())
        team_monthly_df = current_proj_data.get("team_monthly_df", pd.DataFrame())
except Exception as e:
    st.error(f"❌ 数据加载异常: {e}")
    st.stop()

# 页面头部
st.markdown(f"<div class='project-pill'>当前项目：{selected_project}</div>", unsafe_allow_html=True)
st.title(f"📈 {selected_project} - 渠道投放与转化分析中心")

# 三个一级导航标签
tab_period, tab_cross_period, tab_month = st.tabs(["🎯 期次明细复盘", "📈 渠道跨期对比", "🗓️ 月度数据看板"])

# =========================================================================
# 标签 1：期次明细复盘 (单期横切面)
# =========================================================================
with tab_period:
    if period_df.empty:
        st.warning("暂无期次数据")
    else:
        all_periods = [p for p in period_df['当前期次'].dropna().unique() if not any(x in str(p) for x in ['合计', '总计', 'nan', 'None'])]
        
        filter_col1, filter_col2, filter_col3 = st.columns([1.8, 2.5, 1.7])
        with filter_col1:
            selected_period = st.selectbox("📌 选择复盘期次", options=all_periods, index=0 if all_periods else None)
        
        p_filtered = period_df[(period_df['当前期次'] == selected_period) & (~period_df['is_summary'])].copy()
        
        # 期次内同名渠道合并
        p_filtered = aggregate_channel_by_period(p_filtered)
        
        # 渠道排序：核心主要渠道排在最前
        raw_channels = list(p_filtered['渠道名称'].dropna().unique())
        sorted_channels = sort_channels_core_first(raw_channels, selected_project)
        core_channels = CORE_CHANNELS_MAP.get(selected_project, [])
        in_core_selected = [c for c in core_channels if c in sorted_channels]
        
        with filter_col2:
            scope_mode = st.radio("渠道聚焦模式", options=["⭐ 仅看核心主要渠道", "全部渠道"], horizontal=True, label_visibility="collapsed", key="p_scope_radio")
            default_channels = in_core_selected if (scope_mode.startswith("⭐") and in_core_selected) else sorted_channels
            selected_channels = st.multiselect("🔍 筛选具体渠道", options=sorted_channels, default=default_channels, key=f"p_channels_select_{scope_mode}")
            
        with filter_col3:
            sort_by = st.selectbox("🔃 排序依据", options=["总转化率（从高到低）", "线索量（从多到少）", "ROI（从高到低）", "总单数（从多到少）"])

        if selected_channels:
            p_display = p_filtered[p_filtered['渠道名称'].isin(selected_channels)].copy()
        else:
            p_display = p_filtered.copy()

        if sort_by == "总转化率（从高到低）":
            p_display.sort_values(by="总转化率", ascending=False, inplace=True)
        elif sort_by == "线索量（从多到少）":
            p_display.sort_values(by="线索量", ascending=False, inplace=True)
        elif sort_by == "ROI（从高到低）":
            p_display.sort_values(by="roi", ascending=False, inplace=True)
        elif sort_by == "总单数（从多到少）":
            p_display.sort_values(by="总转化量", ascending=False, inplace=True)

        total_leads = p_display['线索量'].sum()
        total_conv = p_display['总转化量'].sum()
        overall_conv_rate = (total_conv / total_leads) if total_leads > 0 else 0.0
        
        total_live = p_display['直播转化'].sum()
        total_chat = p_display['私聊转化'].sum()
        live_ratio = (total_live / total_conv) if total_conv > 0 else 0.0
        chat_ratio = (total_chat / total_conv) if total_conv > 0 else 0.0

        total_cost = p_display['总成本'].sum()
        total_revenue = p_display['总销售额'].sum()
        period_roi = (total_revenue / total_cost) if total_cost > 0 else 0.0
        total_profit = p_display['总盈亏'].sum()
        avg_cac = (total_cost / total_leads) if total_leads > 0 else 0.0
        
        total_refund_orders = p_display['正式课退单'].sum()
        # 【核心修正】：退单率严格按照 = 退单 / (退单 + 总单数)
        total_refund_denom = total_refund_orders + total_conv
        total_refund_rate = (total_refund_orders / total_refund_denom) if total_refund_denom > 0 else 0.0

        # --- 核心指标大卡片 ---
        st.markdown("### 🎯 核心经营指标（本期大盘）")
        kpi_col1, kpi_col2, kpi_col3, kpi_col4 = st.columns([1.3, 1, 1.1, 1])
        
        with kpi_col1:
            st.markdown(f"""
            <div class='metric-hero-card'>
                <div class='metric-hero-title'>总转化率</div>
                <div class='metric-hero-value'>{overall_conv_rate:.2%}</div>
                <div class='metric-hero-sub'>总成交: <b>{total_conv:g} 单</b> / 消耗线索: <b>{int(total_leads):,} 人</b></div>
            </div>
            """, unsafe_allow_html=True)
            
        with kpi_col2:
            st.markdown(f"""
            <div class='metric-sub-card'>
                <div class='metric-sub-title'>总单数</div>
                <div class='metric-sub-value' style='color:#1d4ed8;'>{total_conv:g} <span style='font-size:14px;font-weight:normal;'>单</span></div>
                <div class='metric-sub-badge' style='background:#eff6ff;color:#1e40af;'>单粉成本 (CAC): ¥{avg_cac:.2f}</div>
            </div>
            """, unsafe_allow_html=True)

        with kpi_col3:
            roi_color = "#16a34a" if period_roi >= 1 else "#dc2626"
            roi_badge_bg = "#f0fdf4" if period_roi >= 1 else "#fef2f2"
            roi_badge_color = "#166534" if period_roi >= 1 else "#991b1b"
            st.markdown(f"""
            <div class='metric-sub-card'>
                <div class='metric-sub-title'>ROI</div>
                <div class='metric-sub-value' style='color:{roi_color};'>{period_roi:.2f}</div>
                <div class='metric-sub-badge' style='background:{roi_badge_bg};color:{roi_badge_color};'>销售额 ¥{total_revenue:,.0f} | 成本 ¥{total_cost:,.0f}</div>
            </div>
            """, unsafe_allow_html=True)

        with kpi_col4:
            refund_badge_bg = "#fef2f2" if total_refund_rate > 0.05 else "#f0fdf4"
            refund_badge_color = "#991b1b" if total_refund_rate > 0.05 else "#166534"
            st.markdown(f"""
            <div class='metric-sub-card'>
                <div class='metric-sub-title'>正式课退单</div>
                <div class='metric-sub-value' style='color:#dc2626;'>{int(total_refund_orders)} <span style='font-size:14px;font-weight:normal;'>单</span></div>
                <div class='metric-sub-badge' style='background:{refund_badge_bg};color:{refund_badge_color};'>正式课退单率: {total_refund_rate:.2%}</div>
            </div>
            """, unsafe_allow_html=True)

        fin_col1, fin_col2, fin_col3, fin_col4 = st.columns(4)
        with fin_col1:
            st.metric("总销售额", f"¥{total_revenue:,.2f}")
        with fin_col2:
            st.metric("投放总成本", f"¥{total_cost:,.2f}")
        with fin_col3:
            st.metric("本期总盈亏", f"¥{total_profit:,.2f}", delta="盈利" if total_profit >= 0 else "亏损", delta_color="normal" if total_profit >= 0 else "inverse")
        with fin_col4:
            st.metric("单粉平均成本 (CAC)", f"¥{avg_cac:.2f}")

        st.markdown("---")
        
        # 图表展示（总转化率与 ROI 并列呈现，剔除多余子模块）
        st.markdown("### 📊 渠道转化率与 ROI 表现")
        chart_col1, chart_col2 = st.columns([1, 1])
        with chart_col1:
            top_conv_df = p_display.sort_values(by="总转化率", ascending=False)
            fig_bar = go.Figure()
            fig_bar.add_trace(go.Bar(
                x=top_conv_df["渠道名称"],
                y=top_conv_df["总转化率"],
                text=top_conv_df["总转化率"].apply(lambda x: f"{x:.2%}"),
                textposition='outside',
                marker_color='#2563eb',
                cliponaxis=False,
                customdata=np.stack((
                    top_conv_df['线索量'].astype(int),
                    top_conv_df['总转化量']
                ), axis=-1),
                hovertemplate=(
                    "<b>%{x}</b><br>"
                    + "🔥 总转化率: <b>%{text}</b><br>"
                    + "👥 消耗线索: <b>%{customdata[0]:,} 人</b><br>"
                    + "🎯 成交单数: <b>%{customdata[1]:g} 单</b>"
                    + "<extra></extra>"
                )
            ))
            max_c = top_conv_df["总转化率"].max() if not top_conv_df.empty else 0.05
            fig_bar.update_layout(
                title="总转化率",
                xaxis_title="",
                yaxis_title="总转化率",
                yaxis_tickformat='.1%',
                yaxis_range=[0, max(max_c * 1.25, 0.05)],
                xaxis=dict(
                    tickangle=-15 if len(top_conv_df) > 3 else 0,
                    tickfont=dict(size=12, color="#334155"),
                    showgrid=True,
                    gridcolor="#f1f5f9"
                ),
                yaxis=dict(showgrid=True, gridcolor="#f1f5f9"),
                height=380,
                margin=dict(l=10, r=20, t=50, b=50)
            )
            st.plotly_chart(fig_bar, use_container_width=True)

        with chart_col2:
            top_roi_df = p_display.sort_values(by="roi", ascending=False)
            bar_colors = ['#10b981' if r >= 1.0 else '#3b82f6' for r in top_roi_df['roi']]
            fig_roi = go.Figure()
            fig_roi.add_trace(go.Bar(
                x=top_roi_df["渠道名称"],
                y=top_roi_df["roi"],
                text=top_roi_df["roi"].apply(lambda x: f"{x:.2f}"),
                textposition='outside',
                marker_color=bar_colors,
                cliponaxis=False,
                customdata=np.stack((
                    top_roi_df['总销售额'],
                    top_roi_df['总成本'],
                    top_roi_df['总盈亏']
                ), axis=-1),
                hovertemplate=(
                    "<b>%{x}</b><br>"
                    + "💹 ROI: <b>%{text}</b><br>"
                    + "💰 销售额: <b>¥%{customdata[0]:,.2f}</b><br>"
                    + "💸 成本: <b>¥%{customdata[1]:,.2f}</b><br>"
                    + "⚖️ 盈亏: <b>¥%{customdata[2]:,.2f}</b>"
                    + "<extra></extra>"
                )
            ))
            fig_roi.add_hline(
                y=1.0,
                line_dash="dash",
                line_color="#ef4444",
                line_width=1.5,
                annotation_text="保本 1.0",
                annotation_position="top left",
                annotation_font_color="#ef4444"
            )
            max_r = top_roi_df["roi"].max() if not top_roi_df.empty else 1.2
            fig_roi.update_layout(
                title="ROI",
                xaxis_title="",
                yaxis_title="ROI",
                yaxis_range=[0, max(max_r * 1.25, 1.2)],
                xaxis=dict(
                    tickangle=-15 if len(top_roi_df) > 3 else 0,
                    tickfont=dict(size=12, color="#334155"),
                    showgrid=True,
                    gridcolor="#f1f5f9"
                ),
                yaxis=dict(showgrid=True, gridcolor="#f1f5f9"),
                height=380,
                margin=dict(l=10, r=20, t=50, b=50)
            )
            st.plotly_chart(fig_roi, use_container_width=True)

        st.markdown("---")
        
        # 详细数据表格（纯数值呈现，无进度条，已移除3980与1980共4列）
        st.markdown(f"### 📋 【{selected_period}】渠道详细数据透视 (共 {len(p_display)} 个渠道)")
        
        p_table_df = prepare_display_dataframe(p_display, is_cross_period=False)
        p_col_cfg = build_clean_column_config(has_period_col=False)
        
        st.dataframe(
            p_table_df,
            column_config=p_col_cfg,
            use_container_width=True,
            hide_index=True
        )
        
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
            export_cols = [
                '渠道名称', '线索量', '总转化率', '总转化量',
                'roi', '总销售额', '总成本', '总盈亏', '单粉成本',
                '正式课退单', '正式课总退单率',
                '直播转化', '直播占比', '私聊转化', '私聊占比'
            ]
            valid_export_cols = [c for c in export_cols if c in p_display.columns]
            p_display[valid_export_cols].to_excel(writer, index=False, sheet_name=selected_period[:30])
        st.download_button(
            label=f"📥 导出【{selected_period}】渠道数据 Excel",
            data=buffer.getvalue(),
            file_name=f"{selected_project}_{selected_period}_渠道数据.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

# =========================================================================
# 标签 2：渠道跨期对比 (解决核心痛点：多期纵向无歧义对比)
# =========================================================================
with tab_cross_period:
    st.markdown("### 📈 同一渠道跨期走势与多期纵向对比")
    st.caption("💡 针对同一期次内存在的多段同名渠道（如新课与老课），系统已自动完成真实加权合并，确保各期次折线点唯一、数据精准。")
    
    if period_df.empty:
        st.warning("暂无期次数据")
    else:
        all_detail_df = period_df[~period_df['is_summary']].copy()
        
        avail_channels = list(all_detail_df['渠道名称'].dropna().unique())
        sorted_cross_channels = sort_channels_core_first(avail_channels, selected_project)
        core_channels = CORE_CHANNELS_MAP.get(selected_project, [])
        default_target_ch = [c for c in core_channels if c in sorted_cross_channels]
        if not default_target_ch and sorted_cross_channels:
            default_target_ch = [sorted_cross_channels[0]]
            
        # 跨期分析视角选择
        cp_view_mode = st.radio(
            "📊 跨期分析视角",
            options=["🌐 全期次大盘汇总（按期汇总·看整期表现）", "🔍 细分渠道跨期对比（选具体渠道）"],
            horizontal=True,
            help="全期次大盘汇总模式下，系统自动将所有渠道合并为整期宏观表现；细分渠道对比模式下可对比特定渠道。"
        )
        
        c_filter1, c_filter2 = st.columns([3, 3])
        
        if cp_view_mode.startswith("🌐"):
            with c_filter1:
                st.info("💡 **当前为【全期次大盘汇总】模式**：已自动将所有渠道合并为整期宏观表现，无多渠道线条干扰。")
            selected_comp_channels = sorted_cross_channels
            is_period_overall = True
        else:
            with c_filter1:
                selected_comp_channels = st.multiselect(
                    "📌 选择需要追踪对比的渠道（支持多选并在下方同图对比）",
                    options=sorted_cross_channels,
                    default=default_target_ch[:1]
                )
            # 用户在细分模式下如果 select all，也自动智能切换为大盘汇总，满足“全选时就不看渠道搞得乱七八糟”的需求
            is_period_overall = (len(selected_comp_channels) == len(sorted_cross_channels))
            if is_period_overall and selected_comp_channels:
                st.caption("✨ 已全选所有渠道，系统自动为您折叠为【全期次大盘汇总】单条曲线，防止多线条杂乱。")
            
        if not selected_comp_channels:
            st.info("👈 请在上方选择至少一个渠道以查看跨期对比数据。")
        else:
            raw_comp_df = all_detail_df[all_detail_df['渠道名称'].isin(selected_comp_channels)].copy()
            
            # 根据是否汇总为期次总计，选择不同的聚合函数
            if is_period_overall:
                comp_df = aggregate_by_period_overall(raw_comp_df)
            else:
                comp_df = aggregate_channel_by_period(raw_comp_df)
            
            all_comp_periods = list(comp_df['当前期次'].unique())
            with c_filter2:
                selected_comp_periods = st.multiselect(
                    "📅 选择对比的业务期次（默认全选）",
                    options=all_comp_periods,
                    default=all_comp_periods,
                    format_func=format_period_axis_label
                )
                
            comp_df = comp_df[comp_df['当前期次'].isin(selected_comp_periods)].copy()
            
            if comp_df.empty:
                st.warning("选定范围无数据")
            else:
                # 生成双行优化的期次展示标签（消除重叠倾斜拥挤，横向清晰易读）
                comp_df['当前期次_展示'] = comp_df['当前期次'].apply(format_period_axis_label)

                cp_leads = comp_df['线索量'].sum()
                cp_conv = comp_df['总转化量'].sum()
                cp_conv_rate = (cp_conv / cp_leads) if cp_leads > 0 else 0.0
                
                cp_live = comp_df['直播转化'].sum()
                cp_chat = comp_df['私聊转化'].sum()
                cp_live_ratio = (cp_live / cp_conv) if cp_conv > 0 else 0.0
                cp_chat_ratio = (cp_chat / cp_conv) if cp_conv > 0 else 0.0

                cp_cost = comp_df['总成本'].sum()
                cp_rev = comp_df['总销售额'].sum()
                cp_roi = (cp_rev / cp_cost) if cp_cost > 0 else 0.0
                cp_profit = comp_df['总盈亏'].sum()
                
                cp_refund = comp_df['正式课退单'].sum()
                # 【核心修正】：正式课退单率 = 退单 / (退单 + 总单数)
                cp_refund_denom = cp_refund + cp_conv
                cp_refund_rate = (cp_refund / cp_refund_denom) if cp_refund_denom > 0 else 0.0
                
                # 顶部加权跨期汇总卡片
                st.markdown(f"#### 📊 所选渠道在所选 {len(selected_comp_periods)} 个期次中的【累计加权大盘】")
                cp_kpi1, cp_kpi2, cp_kpi3, cp_kpi4 = st.columns([1.3, 1, 1.1, 1])
                with cp_kpi1:
                    st.markdown(f"""
                    <div class='metric-hero-card' style='background: linear-gradient(135deg, #1e3a8a 0%, #312e81 100%);'>
                        <div class='metric-hero-title'>总转化率</div>
                        <div class='metric-hero-value'>{cp_conv_rate:.2%}</div>
                        <div class='metric-hero-sub'>跨期累计成交: <b>{cp_conv:g} 单</b> / 累计线索: <b>{int(cp_leads):,} 人</b></div>
                    </div>
                    """, unsafe_allow_html=True)
                with cp_kpi2:
                    st.markdown(f"""
                    <div class='metric-sub-card'>
                        <div class='metric-sub-title'>总单数</div>
                        <div class='metric-sub-value' style='color:#1d4ed8;'>{cp_conv:g} <span style='font-size:14px;font-weight:normal;'>单</span></div>
                        <div class='metric-sub-badge' style='background:#eff6ff;color:#1e40af;'>累计线索: {int(cp_leads):,} 人</div>
                    </div>
                    """, unsafe_allow_html=True)
                with cp_kpi3:
                    cp_roi_color = "#16a34a" if cp_roi >= 1 else "#dc2626"
                    cp_roi_badge_bg = "#f0fdf4" if cp_roi >= 1 else "#fef2f2"
                    cp_roi_badge_color = "#166534" if cp_roi >= 1 else "#991b1b"
                    st.markdown(f"""
                    <div class='metric-sub-card'>
                        <div class='metric-sub-title'>ROI</div>
                        <div class='metric-sub-value' style='color:{cp_roi_color};'>{cp_roi:.2f}</div>
                        <div class='metric-sub-badge' style='background:{cp_roi_badge_bg};color:{cp_roi_badge_color};'>销售额 ¥{cp_rev:,.0f} | 成本 ¥{cp_cost:,.0f}</div>
                    </div>
                    """, unsafe_allow_html=True)
                with cp_kpi4:
                    cp_ref_bg = "#fef2f2" if cp_refund_rate > 0.05 else "#f0fdf4"
                    cp_ref_color = "#991b1b" if cp_refund_rate > 0.05 else "#166534"
                    st.markdown(f"""
                    <div class='metric-sub-card'>
                        <div class='metric-sub-title'>正式课退单</div>
                        <div class='metric-sub-value' style='color:#dc2626;'>{int(cp_refund)} <span style='font-size:14px;font-weight:normal;'>单</span></div>
                        <div class='metric-sub-badge' style='background:{cp_ref_bg};color:{cp_ref_color};'>正式课退单率: {cp_refund_rate:.2%}</div>
                    </div>
                    """, unsafe_allow_html=True)
                    
                cp_fin1, cp_fin2, cp_fin3, cp_fin4 = st.columns(4)
                with cp_fin1:
                    st.metric("跨期总销售额", f"¥{cp_rev:,.2f}")
                with cp_fin2:
                    st.metric("跨期总成本", f"¥{cp_cost:,.2f}")
                with cp_fin3:
                    st.metric("跨期总盈亏", f"¥{cp_profit:,.2f}", delta="盈利" if cp_profit >= 0 else "亏损", delta_color="normal" if cp_profit >= 0 else "inverse")
                with cp_fin4:
                    cp_cac = (cp_cost / cp_leads) if cp_leads > 0 else 0.0
                    st.metric("跨期单粉成本", f"¥{cp_cac:.2f}")

                st.markdown("---")
                
                # --- 图表区：纯单点无歧义折线图 与 ROI对比图（直接并列，去除多余子标签） ---
                st.markdown("#### 📉 跨期走势与 ROI 对比")
                cp_chart1, cp_chart2 = st.columns([1.3, 1])
                with cp_chart1:
                    # 转化率条形柱状图（根据要求改为条形柱状图，与ROI图保持一致清晰直观）
                    if is_period_overall:
                        customdata_trend = np.stack((
                            comp_df['当前期次_展示'],
                            comp_df['总转化率'].apply(lambda x: f"{x:.2%}"),
                            comp_df['线索量'].astype(int)
                        ), axis=-1)
                        
                        fig_trend = go.Figure()
                        fig_trend.add_trace(go.Bar(
                            x=comp_df['当前期次_展示'],
                            y=comp_df['总转化率'],
                            text=comp_df['总转化率'].apply(lambda x: f"{x:.2%}"),
                            textposition='outside',
                            marker_color='#2563eb',
                            cliponaxis=False,
                            customdata=customdata_trend,
                            hovertemplate=(
                                "<b>%{customdata[0]}</b><br>"
                                + "🔥 总转化率: <b>%{customdata[1]}</b><br>"
                                + "👥 消耗线索: <b>%{customdata[2]:,} 人</b>"
                                + "<extra></extra>"
                            )
                        ))
                        max_c = comp_df['总转化率'].max() if not comp_df.empty else 0.05
                        fig_trend.update_layout(
                            title="总转化率",
                            xaxis=dict(
                                tickangle=0,
                                tickfont=dict(size=11, color="#334155"),
                                showgrid=True,
                                gridcolor="#f1f5f9",
                                gridwidth=1
                            ),
                            yaxis=dict(
                                title="总转化率",
                                tickformat='.1%',
                                range=[0, max(max_c * 1.25, 0.05)],
                                showgrid=True,
                                gridcolor="#f1f5f9"
                            ),
                            height=400,
                            margin=dict(l=10, r=20, t=50, b=50)
                        )
                    else:
                        fig_trend = px.bar(
                            comp_df,
                            x="当前期次_展示",
                            y="总转化率",
                            color="渠道名称",
                            barmode="group",
                            text=comp_df["总转化率"].apply(lambda x: f"{x:.2%}"),
                            title="总转化率"
                        )
                        for trace in fig_trend.data:
                            ch_name = trace.name
                            sub_df = comp_df[comp_df['渠道名称'] == ch_name]
                            c_data = np.stack((
                                sub_df['当前期次_展示'],
                                sub_df['总转化率'].apply(lambda x: f"{x:.2%}"),
                                sub_df['线索量'].astype(int),
                                sub_df['渠道名称']
                            ), axis=-1)
                            trace.customdata = c_data
                            trace.hovertemplate = (
                                "<b>%{customdata[0]}</b><br>"
                                + "渠道: %{customdata[3]}<br>"
                                + "🔥 总转化率: <b>%{customdata[1]}</b><br>"
                                + "👥 消耗线索: <b>%{customdata[2]:,} 人</b>"
                                + "<extra></extra>"
                            )
                            trace.textposition = "outside"
                            trace.cliponaxis = False
                        max_c = comp_df['总转化率'].max() if not comp_df.empty else 0.05
                        fig_trend.update_layout(
                            yaxis_tickformat='.1%',
                            yaxis_range=[0, max(max_c * 1.25, 0.05)],
                            xaxis=dict(
                                tickangle=0,
                                tickfont=dict(size=11, color="#334155"),
                                showgrid=True,
                                gridcolor="#f1f5f9",
                                gridwidth=1
                            ),
                            yaxis_title="总转化率",
                            height=400,
                            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                            margin=dict(l=10, r=20, t=50, b=50)
                        )
                    st.plotly_chart(fig_trend, use_container_width=True)
                    
                with cp_chart2:
                    # ROI 投入产出对比图
                    if is_period_overall:
                        bar_colors = ['#10b981' if r >= 1.0 else '#3b82f6' for r in comp_df['roi']]
                        customdata_roi = np.stack((
                            comp_df['当前期次_展示'],
                            comp_df['roi'],
                            comp_df['总销售额'],
                            comp_df['总成本'],
                            comp_df['总盈亏']
                        ), axis=-1)

                        fig_roi = go.Figure()
                        fig_roi.add_trace(go.Bar(
                            x=comp_df['当前期次_展示'],
                            y=comp_df['roi'],
                            text=comp_df['roi'].apply(lambda x: f"{x:.2f}"),
                            textposition='outside',
                            marker_color=bar_colors,
                            cliponaxis=False,
                            customdata=customdata_roi,
                            hovertemplate=(
                                "<b>%{customdata[0]}</b><br>"
                                + "💹 ROI: <b>%{customdata[1]:.2f}</b><br>"
                                + "💰 总销售额: <b>¥%{customdata[2]:,.2f}</b><br>"
                                + "💸 投放成本: <b>¥%{customdata[3]:,.2f}</b><br>"
                                + "⚖️ 本期盈亏: <b>¥%{customdata[4]:,.2f}</b>"
                                + "<extra></extra>"
                            )
                        ))
                        fig_roi.add_hline(
                            y=1.0,
                            line_dash="dash",
                            line_color="#ef4444",
                            line_width=1.5,
                            annotation_text="保本 1.0",
                            annotation_position="top left",
                            annotation_font_color="#ef4444"
                        )
                        max_roi_p = comp_df['roi'].max() if not comp_df.empty else 1.2
                        fig_roi.update_layout(
                            title="ROI",
                            xaxis=dict(
                                tickangle=0,
                                tickfont=dict(size=11, color="#334155"),
                                showgrid=True,
                                gridcolor="#f1f5f9",
                                gridwidth=1
                            ),
                            yaxis=dict(
                                title="ROI",
                                rangemode='tozero',
                                range=[0, max(max_roi_p * 1.25, 1.2)],
                                showgrid=True,
                                gridcolor="#f1f5f9"
                            ),
                            height=400,
                            margin=dict(l=10, r=20, t=50, b=50)
                        )
                    else:
                        fig_roi = px.bar(
                            comp_df,
                            x="当前期次_展示",
                            y="roi",
                            color="渠道名称",
                            barmode="group",
                            text=comp_df["roi"].apply(lambda x: f"{x:.2f}"),
                            title="ROI"
                        )
                        for trace in fig_roi.data:
                            ch_name = trace.name
                            sub_df = comp_df[comp_df['渠道名称'] == ch_name]
                            c_data = np.stack((
                                sub_df['当前期次_展示'],
                                sub_df['roi'],
                                sub_df['总销售额'],
                                sub_df['总成本'],
                                sub_df['总盈亏'],
                                sub_df['渠道名称']
                            ), axis=-1)
                            trace.customdata = c_data
                            trace.hovertemplate = (
                                "<b>%{customdata[0]}</b><br>"
                                + "渠道: %{customdata[5]}<br>"
                                + "💹 ROI: <b>%{customdata[1]:.2f}</b><br>"
                                + "💰 销售额: <b>¥%{customdata[2]:,.2f}</b><br>"
                                + "💸 成本: <b>¥%{customdata[3]:,.2f}</b>"
                                + "<extra></extra>"
                            )
                            trace.textposition = "outside"
                            trace.cliponaxis = False
                        fig_roi.add_hline(
                            y=1.0,
                            line_dash="dash",
                            line_color="#ef4444",
                            line_width=1.5,
                            annotation_text="保本 1.0",
                            annotation_position="top left",
                            annotation_font_color="#ef4444"
                        )
                        max_roi_p = comp_df['roi'].max() if not comp_df.empty else 1.2
                        fig_roi.update_layout(
                            xaxis=dict(
                                tickangle=0,
                                tickfont=dict(size=11, color="#334155"),
                                showgrid=True,
                                gridcolor="#f1f5f9",
                                gridwidth=1
                            ),
                            yaxis_title="ROI",
                            yaxis_range=[0, max(max_roi_p * 1.25, 1.2)],
                            height=400,
                            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                            margin=dict(l=10, r=20, t=50, b=50)
                        )
                    st.plotly_chart(fig_roi, use_container_width=True)

                st.markdown("---")
                
                # --- 跨期详细数据表格（纯数值呈现，无进度条，已剔除3980与1980共4列） ---
                table_title = f"#### 📋 全期次大盘汇总对照明细表 (共 {len(comp_df)} 期)" if is_period_overall else f"#### 📋 渠道跨期详细对照明细表 (共 {len(comp_df)} 条期次记录)"
                st.markdown(table_title)
                
                cp_table_df = prepare_display_dataframe(comp_df, is_cross_period=True)
                cp_col_cfg = build_clean_column_config(has_period_col=True)
                
                st.dataframe(
                    cp_table_df,
                    column_config=cp_col_cfg,
                    use_container_width=True,
                    hide_index=True
                )
                
                cp_buffer = io.BytesIO()
                with pd.ExcelWriter(cp_buffer, engine='openpyxl') as writer:
                    export_cols = [
                        '当前期次', '渠道名称', '线索量', '总转化率', '总转化量',
                        '直播转化', '直播占比', '私聊转化', '私聊占比',
                        '单粉成本', '总成本', '总销售额', 'roi', '总盈亏',
                        '正式课退单', '正式课总退单率'
                    ]
                    valid_export_cols = [c for c in export_cols if c in comp_df.columns]
                    comp_df[valid_export_cols].to_excel(writer, index=False, sheet_name="跨期对比")
                st.download_button(
                    label="📥 导出渠道跨期对比 Excel",
                    data=cp_buffer.getvalue(),
                    file_name=f"{selected_project}_渠道跨期对比.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )

# =========================================================================
# 标签 3：月度数据看板 (全量渠道正常展现，已剔除4列)
# =========================================================================
with tab_month:
    if monthly_df.empty:
        st.warning("暂无月度数据")
    else:
        m_view_type = "全项目月度汇总"
        if selected_project == "晓辉项目" and not team_monthly_df.empty:
            m_view_type = st.radio("视角切换", options=["全项目月度汇总", "分团队月度数据 (A轨/B轨/同心向阳)"], horizontal=True)

        is_team_comparison = m_view_type.startswith("分团队")
        
        if not is_team_comparison:
            # -------------------------------------------------------------
            # 模式 A：全项目月度汇总
            # -------------------------------------------------------------
            target_monthly_df = monthly_df
            avail_months = target_monthly_df['月份标签'].dropna().unique().tolist()
            avail_months = [m for m in avail_months if not any(x in str(m) for x in ['合计', '总计', 'nan', 'None'])]
            
            m_filter_col1, m_filter_col2 = st.columns([2, 4])
            with m_filter_col1:
                selected_month_period = st.selectbox("📅 选择月份", options=avail_months, index=0 if avail_months else None)
                
            m_filtered = target_monthly_df[(target_monthly_df['月份标签'] == selected_month_period) & (~target_monthly_df['is_summary'])].copy()
            
            raw_m_channels = list(m_filtered['渠道名称'].dropna().unique())
            sorted_m_channels = sort_channels_core_first(raw_m_channels, selected_project)
            core_channels = CORE_CHANNELS_MAP.get(selected_project, [])
            in_core_m = [c for c in core_channels if c in sorted_m_channels]
            
            with m_filter_col2:
                m_scope = st.radio("月度渠道聚焦", options=["⭐ 仅看核心主要渠道", "全部渠道"], horizontal=True, label_visibility="collapsed", key="m_scope_radio")
                default_m = in_core_m if (m_scope.startswith("⭐") and in_core_m) else sorted_m_channels
                selected_m_channels = st.multiselect("🔍 筛选渠道", options=sorted_m_channels, default=default_m, key=f"m_channels_select_{m_scope}")
                
            if selected_m_channels:
                m_display = m_filtered[m_filtered['渠道名称'].isin(selected_m_channels)].copy()
            else:
                m_display = m_filtered.copy()

            m_leads = m_display['线索量'].sum()
            m_conv = m_display['总转化量'].sum()
            m_conv_rate = (m_conv / m_leads) if m_leads > 0 else 0.0
            
            m_cost = m_display['总成本'].sum()
            m_rev = m_display['总销售额'].sum()
            m_roi = (m_rev / m_cost) if m_cost > 0 else 0.0
            m_profit = m_display['总盈亏'].sum()
            m_cac = (m_cost / m_leads) if m_leads > 0 else 0.0
            
            m_refund = m_display['正式课退单'].sum()
            m_refund_denom = m_refund + m_conv
            m_refund_rate = (m_refund / m_refund_denom) if m_refund_denom > 0 else 0.0

            st.markdown(f"### 🗓️ 【{selected_month_period}】大盘经营成果")
            mkpi_col1, mkpi_col2, mkpi_col3, mkpi_col4 = st.columns([1.3, 1, 1.1, 1])
            with mkpi_col1:
                st.markdown(f"""
                <div class='metric-hero-card' style='background: linear-gradient(135deg, #0f766e 0%, #0d9488 50%, #14b8a6 100%);'>
                    <div class='metric-hero-title'>总转化率</div>
                    <div class='metric-hero-value'>{m_conv_rate:.2%}</div>
                    <div class='metric-hero-sub'>总成交: <b>{m_conv:g} 单</b> / 消耗线索: <b>{int(m_leads):,} 人</b></div>
                </div>
                """, unsafe_allow_html=True)
            with mkpi_col2:
                st.markdown(f"""
                <div class='metric-sub-card'>
                    <div class='metric-sub-title'>总单数</div>
                    <div class='metric-sub-value' style='color:#1d4ed8;'>{m_conv:g} <span style='font-size:14px;font-weight:normal;'>单</span></div>
                    <div class='metric-sub-badge' style='background:#eff6ff;color:#1e40af;'>单粉成本: ¥{m_cac:.2f}</div>
                </div>
                """, unsafe_allow_html=True)
            with mkpi_col3:
                m_roi_color = "#16a34a" if m_roi >= 1 else "#dc2626"
                m_roi_badge_bg = "#f0fdf4" if m_roi >= 1 else "#fef2f2"
                m_roi_badge_color = "#166534" if m_roi >= 1 else "#991b1b"
                st.markdown(f"""
                <div class='metric-sub-card'>
                    <div class='metric-sub-title'>ROI</div>
                    <div class='metric-sub-value' style='color:{m_roi_color};'>{m_roi:.2f}</div>
                    <div class='metric-sub-badge' style='background:{m_roi_badge_bg};color:{m_roi_badge_color};'>销售额 ¥{m_rev:,.0f} | 成本 ¥{m_cost:,.0f}</div>
                </div>
                """, unsafe_allow_html=True)
            with mkpi_col4:
                m_refund_bg = "#fef2f2" if m_refund_rate > 0.05 else "#f0fdf4"
                m_refund_color = "#991b1b" if m_refund_rate > 0.05 else "#166534"
                st.markdown(f"""
                <div class='metric-sub-card'>
                    <div class='metric-sub-title'>正式课退单</div>
                    <div class='metric-sub-value' style='color:#dc2626;'>{int(m_refund)} <span style='font-size:14px;font-weight:normal;'>单</span></div>
                    <div class='metric-sub-badge' style='background:{m_refund_bg};color:{m_refund_color};'>正式课退单率: {m_refund_rate:.2%}</div>
                </div>
                """, unsafe_allow_html=True)

            mfin_col1, mfin_col2, mfin_col3, mfin_col4 = st.columns(4)
            with mfin_col1:
                st.metric("月度总销售额", f"¥{m_rev:,.2f}")
            with mfin_col2:
                st.metric("月度总成本", f"¥{m_cost:,.2f}")
            with mfin_col3:
                st.metric("月度总盈亏", f"¥{m_profit:,.2f}", delta="盈利" if m_profit >= 0 else "亏损", delta_color="normal" if m_profit >= 0 else "inverse")
            with mfin_col4:
                st.metric("单粉综合成本 (CAC)", f"¥{m_cac:.2f}")

            st.markdown("---")
            
            # 单月各渠道图表
            st.markdown(f"### 📊 【{selected_month_period}】各渠道表现")
            m_col1, m_col2 = st.columns([1, 1])
            with m_col1:
                top_m_conv = m_display.sort_values(by="总转化率", ascending=False)
                fig_m_bar = go.Figure()
                fig_m_bar.add_trace(go.Bar(
                    x=top_m_conv["渠道名称"],
                    y=top_m_conv["总转化率"],
                    text=top_m_conv["总转化率"].apply(lambda x: f"{x:.2%}"),
                    textposition='outside',
                    marker_color='#2563eb',
                    cliponaxis=False,
                    customdata=np.stack((
                        top_m_conv['线索量'].astype(int),
                        top_m_conv['总转化量']
                    ), axis=-1),
                    hovertemplate=(
                        "<b>%{x}</b><br>"
                        + "🔥 总转化率: <b>%{text}</b><br>"
                        + "👥 消耗线索: <b>%{customdata[0]:,} 人</b><br>"
                        + "🎯 成交单数: <b>%{customdata[1]:g} 单</b>"
                        + "<extra></extra>"
                    )
                ))
                max_mc = top_m_conv["总转化率"].max() if not top_m_conv.empty else 0.05
                fig_m_bar.update_layout(
                    title="总转化率",
                    xaxis_title="",
                    yaxis_title="总转化率",
                    yaxis_tickformat='.1%',
                    yaxis_range=[0, max(max_mc * 1.25, 0.05)],
                    xaxis=dict(
                        tickangle=-15 if len(top_m_conv) > 3 else 0,
                        tickfont=dict(size=12, color="#334155"),
                        showgrid=True,
                        gridcolor="#f1f5f9"
                    ),
                    yaxis=dict(showgrid=True, gridcolor="#f1f5f9"),
                    height=380,
                    margin=dict(l=10, r=20, t=50, b=50)
                )
                st.plotly_chart(fig_m_bar, use_container_width=True)

            with m_col2:
                top_m_roi = m_display.sort_values(by="roi", ascending=False)
                m_bar_colors = ['#10b981' if r >= 1.0 else '#3b82f6' for r in top_m_roi['roi']]
                fig_m_roi = go.Figure()
                fig_m_roi.add_trace(go.Bar(
                    x=top_m_roi["渠道名称"],
                    y=top_m_roi["roi"],
                    text=top_m_roi["roi"].apply(lambda x: f"{x:.2f}"),
                    textposition='outside',
                    marker_color=m_bar_colors,
                    cliponaxis=False,
                    customdata=np.stack((
                        top_m_roi['总销售额'],
                        top_m_roi['总成本'],
                        top_m_roi['总盈亏']
                    ), axis=-1),
                    hovertemplate=(
                        "<b>%{x}</b><br>"
                        + "💹 ROI: <b>%{text}</b><br>"
                        + "💰 销售额: <b>¥%{customdata[0]:,.2f}</b><br>"
                        + "💸 成本: <b>¥%{customdata[1]:,.2f}</b><br>"
                        + "⚖️ 盈亏: <b>¥%{customdata[2]:,.2f}</b>"
                        + "<extra></extra>"
                    )
                ))
                fig_m_roi.add_hline(
                    y=1.0,
                    line_dash="dash",
                    line_color="#ef4444",
                    line_width=1.5,
                    annotation_text="保本 1.0",
                    annotation_position="top left",
                    annotation_font_color="#ef4444"
                )
                max_mr = top_m_roi["roi"].max() if not top_m_roi.empty else 1.2
                fig_m_roi.update_layout(
                    title="ROI",
                    xaxis_title="",
                    yaxis_title="ROI",
                    yaxis_range=[0, max(max_mr * 1.25, 1.2)],
                    xaxis=dict(
                        tickangle=-15 if len(top_m_roi) > 3 else 0,
                        tickfont=dict(size=12, color="#334155"),
                        showgrid=True,
                        gridcolor="#f1f5f9"
                    ),
                    yaxis=dict(showgrid=True, gridcolor="#f1f5f9"),
                    height=380,
                    margin=dict(l=10, r=20, t=50, b=50)
                )
                st.plotly_chart(fig_m_roi, use_container_width=True)

            st.markdown("---")
            
            # 月度表格（ROI等核心商业数据前置，直播/私聊后置）
            st.markdown(f"### 📋 【{selected_month_period}】月度详细数据透视 (共 {len(m_display)} 个渠道)")
            m_sorted = m_display.sort_values(by='总转化率', ascending=False)
            m_table_df = prepare_display_dataframe(m_sorted, is_cross_period=False)
            m_col_cfg = build_clean_column_config(has_period_col=False)
            
            st.dataframe(m_table_df, column_config=m_col_cfg, use_container_width=True, hide_index=True)
            
            m_buffer = io.BytesIO()
            with pd.ExcelWriter(m_buffer, engine='openpyxl') as writer:
                export_cols = [
                    '渠道名称', '线索量', '总转化率', '总转化量',
                    'roi', '总销售额', '总成本', '总盈亏', '单粉成本',
                    '正式课退单', '正式课总退单率',
                    '直播转化', '直播占比', '私聊转化', '私聊占比'
                ]
                valid_export_cols = [c for c in export_cols if c in m_sorted.columns]
                m_sorted[valid_export_cols].to_excel(writer, index=False, sheet_name=selected_month_period[:30])
            st.download_button(
                label=f"📥 导出【{selected_month_period}】月度数据 Excel",
                data=m_buffer.getvalue(),
                file_name=f"{selected_project}_{selected_month_period}_月度数据.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

        else:
            # -------------------------------------------------------------
            # 模式 B：分团队月度数据对比（各个团队主要渠道横向 PK）
            # -------------------------------------------------------------
            pref_teams = ['10月A轨', '10月B轨', '10月同心向阳', 'A轨', 'B轨', '同心向阳']
            avail_teams = [m for m in team_monthly_df['月份标签'].dropna().unique().tolist() if not any(x in str(m) for x in ['合计', '总计', 'nan', 'None'])]
            avail_teams = sorted(avail_teams, key=lambda x: pref_teams.index(x) if x in pref_teams else 99)
            
            m_filter_col1, m_filter_col2 = st.columns([2.5, 3.5])
            with m_filter_col1:
                selected_teams = st.multiselect("👥 选择对比团队（支持多团队同图PK）", options=avail_teams, default=avail_teams, key="m_team_select_top")
                
            raw_team_channels = list(team_monthly_df[team_monthly_df['月份标签'].isin(selected_teams)]['渠道名称'].dropna().unique())
            sorted_team_channels = sort_channels_core_first(raw_team_channels, selected_project)
            core_channels = CORE_CHANNELS_MAP.get(selected_project, [])
            in_core_team = [c for c in core_channels if c in sorted_team_channels]
            
            with m_filter_col2:
                m_team_scope = st.radio("对比渠道范围", options=["⭐ 仅看核心主要渠道", "全部渠道"], horizontal=True, label_visibility="collapsed", key="m_team_scope_radio_top")
                default_team_ch = in_core_team if (m_team_scope.startswith("⭐") and in_core_team) else sorted_team_channels
                selected_team_channels = st.multiselect("🔍 筛选对比渠道（控制上方汇总战报与对比图表）", options=sorted_team_channels, default=default_team_ch, key=f"m_team_channels_select_{m_team_scope}")

            if not selected_teams:
                st.info("👈 请在上方选择至少一个团队以进行对比")
            elif not selected_team_channels:
                st.info("👈 请在上方选择至少一个对比渠道")
            else:
                team_display = team_monthly_df[
                    (team_monthly_df['月份标签'].isin(selected_teams))
                    & (team_monthly_df['渠道名称'].isin(selected_team_channels))
                    & (~team_monthly_df['is_summary'])
                ].copy()

                # 按核心渠道及团队顺序排序
                team_display['ch_sort'] = team_display['渠道名称'].apply(lambda x: selected_team_channels.index(x) if x in selected_team_channels else 99)
                team_display['team_sort'] = team_display['月份标签'].apply(lambda x: selected_teams.index(x) if x in selected_teams else 99)
                team_display.sort_values(by=['ch_sort', 'team_sort'], inplace=True)

                # 顶部所选团队在已选渠道的总体汇总战报卡片
                tm_leads = team_display['线索量'].sum()
                tm_conv = team_display['总转化量'].sum()
                tm_conv_rate = (tm_conv / tm_leads) if tm_leads > 0 else 0.0
                tm_cost = team_display['总成本'].sum()
                tm_rev = team_display['总销售额'].sum()
                tm_roi = (tm_rev / tm_cost) if tm_cost > 0 else 0.0
                tm_profit = team_display['总盈亏'].sum()
                tm_refund = team_display['正式课退单'].sum()
                tm_refund_denom = tm_refund + tm_conv
                tm_refund_rate = (tm_refund / tm_refund_denom) if tm_refund_denom > 0 else 0.0
                tm_cac = (tm_cost / tm_leads) if tm_leads > 0 else 0.0

                st.markdown(f"### 👥 所选 {len(selected_teams)} 个团队在主要渠道的【汇总战报】")
                tkpi1, tkpi2, tkpi3, tkpi4 = st.columns([1.3, 1, 1.1, 1])
                with tkpi1:
                    st.markdown(f"""
                    <div class='metric-hero-card' style='background: linear-gradient(135deg, #0f766e 0%, #0d9488 50%, #14b8a6 100%);'>
                        <div class='metric-hero-title'>总转化率</div>
                        <div class='metric-hero-value'>{tm_conv_rate:.2%}</div>
                        <div class='metric-hero-sub'>总成交: <b>{tm_conv:g} 单</b> / 消耗线索: <b>{int(tm_leads):,} 人</b></div>
                    </div>
                    """, unsafe_allow_html=True)
                with tkpi2:
                    st.markdown(f"""
                    <div class='metric-sub-card'>
                        <div class='metric-sub-title'>总单数</div>
                        <div class='metric-sub-value' style='color:#1d4ed8;'>{tm_conv:g} <span style='font-size:14px;font-weight:normal;'>单</span></div>
                        <div class='metric-sub-badge' style='background:#eff6ff;color:#1e40af;'>平均单粉成本: ¥{tm_cac:.2f}</div>
                    </div>
                    """, unsafe_allow_html=True)
                with tkpi3:
                    tm_roi_color = "#16a34a" if tm_roi >= 1 else "#dc2626"
                    tm_roi_badge_bg = "#f0fdf4" if tm_roi >= 1 else "#fef2f2"
                    tm_roi_badge_color = "#166534" if tm_roi >= 1 else "#991b1b"
                    st.markdown(f"""
                    <div class='metric-sub-card'>
                        <div class='metric-sub-title'>ROI</div>
                        <div class='metric-sub-value' style='color:{tm_roi_color};'>{tm_roi:.2f}</div>
                        <div class='metric-sub-badge' style='background:{tm_roi_badge_bg};color:{tm_roi_badge_color};'>销售额 ¥{tm_rev:,.0f} | 成本 ¥{tm_cost:,.0f}</div>
                    </div>
                    """, unsafe_allow_html=True)
                with tkpi4:
                    tm_ref_bg = "#fef2f2" if tm_refund_rate > 0.05 else "#f0fdf4"
                    tm_ref_color = "#991b1b" if tm_refund_rate > 0.05 else "#166534"
                    st.markdown(f"""
                    <div class='metric-sub-card'>
                        <div class='metric-sub-title'>正式课退单</div>
                        <div class='metric-sub-value' style='color:#dc2626;'>{int(tm_refund)} <span style='font-size:14px;font-weight:normal;'>单</span></div>
                        <div class='metric-sub-badge' style='background:{tm_ref_bg};color:{tm_ref_color};'>正式课退单率: {tm_refund_rate:.2%}</div>
                    </div>
                    """, unsafe_allow_html=True)

                # 各团队总体经营指标对比小卡
                st.markdown("##### 🏢 各团队大盘数据快速对齐")
                t_cols = st.columns(len(selected_teams))
                for i, t_name in enumerate(selected_teams):
                    t_sub = team_display[team_display['月份标签'] == t_name]
                    tl = t_sub['线索量'].sum()
                    tc = t_sub['总转化量'].sum()
                    tr = (tc / tl) if tl > 0 else 0.0
                    t_rev = t_sub['总销售额'].sum()
                    t_cost = t_sub['总成本'].sum()
                    t_r = (t_rev / t_cost) if t_cost > 0 else 0.0
                    with t_cols[i]:
                        st.markdown(f"""
                        <div style='background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 10px 12px; margin-bottom: 12px;'>
                            <div style='font-weight: 700; color: #1e293b; font-size: 14px;'>📌 {t_name}</div>
                            <div style='margin-top: 4px; font-size: 13px; color: #334155;'>
                                转化率: <b style='color:#2563eb;'>{tr:.2%}</b> ｜ ROI: <b style='color:{"#16a34a" if t_r>=1 else "#dc2626"};'>{t_r:.2f}</b>
                            </div>
                            <div style='font-size: 12px; color: #64748b; margin-top: 2px;'>
                                成交: <b>{tc:g}</b> 单 / 线索: <b>{int(tl):,}</b> 人 / 销售: <b>¥{t_rev:,.0f}</b>
                            </div>
                        </div>
                        """, unsafe_allow_html=True)

                st.markdown("---")

                # =========================================================
                # 核心对比图表（各团队主要渠道横向对比图）
                # =========================================================
                st.markdown("### 📊 各团队主要渠道横向对比图")
                team_col1, team_col2 = st.columns([1, 1])

                team_colors = ['#2563eb', '#0ea5e9', '#f59e0b', '#8b5cf6', '#10b981']

                with team_col1:
                    # 分团队主要渠道【总转化率】分组柱状图
                    fig_team_conv = px.bar(
                        team_display,
                        x="渠道名称",
                        y="总转化率",
                        color="月份标签",
                        barmode="group",
                        text=team_display["总转化率"].apply(lambda x: f"{x:.2%}"),
                        title="总转化率",
                        color_discrete_sequence=team_colors
                    )
                    for trace in fig_team_conv.data:
                        t_name = trace.name
                        sub_t = team_display[team_display['月份标签'] == t_name]
                        c_data = np.stack((
                            sub_t['渠道名称'],
                            sub_t['总转化率'].apply(lambda x: f"{x:.2%}"),
                            sub_t['线索量'].astype(int),
                            sub_t['总转化量'],
                            sub_t['月份标签']
                        ), axis=-1)
                        trace.customdata = c_data
                        trace.hovertemplate = (
                            "<b>%{customdata[0]}</b><br>"
                            + "团队: <b>%{customdata[4]}</b><br>"
                            + "🔥 总转化率: <b>%{customdata[1]}</b><br>"
                            + "👥 消耗线索: <b>%{customdata[2]:,} 人</b><br>"
                            + "🎯 成交单数: <b>%{customdata[3]:g} 单</b>"
                            + "<extra></extra>"
                        )
                        trace.textposition = "outside"
                        trace.cliponaxis = False
                    max_tc = team_display['总转化率'].max() if not team_display.empty else 0.05
                    fig_team_conv.update_layout(
                        yaxis_tickformat='.1%',
                        yaxis_range=[0, max(max_tc * 1.25, 0.05)],
                        xaxis=dict(
                            tickangle=-15 if len(selected_team_channels) > 3 else 0,
                            tickfont=dict(size=12, color="#334155"),
                            showgrid=True,
                            gridcolor="#f1f5f9"
                        ),
                        yaxis=dict(showgrid=True, gridcolor="#f1f5f9"),
                        yaxis_title="总转化率",
                        height=400,
                        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1, title=""),
                        margin=dict(l=10, r=20, t=50, b=50)
                    )
                    st.plotly_chart(fig_team_conv, use_container_width=True)

                with team_col2:
                    # 分团队主要渠道【ROI】分组柱状图
                    fig_team_roi = px.bar(
                        team_display,
                        x="渠道名称",
                        y="roi",
                        color="月份标签",
                        barmode="group",
                        text=team_display["roi"].apply(lambda x: f"{x:.2f}"),
                        title="ROI",
                        color_discrete_sequence=team_colors
                    )
                    for trace in fig_team_roi.data:
                        t_name = trace.name
                        sub_t = team_display[team_display['月份标签'] == t_name]
                        c_data = np.stack((
                            sub_t['渠道名称'],
                            sub_t['roi'].apply(lambda x: f"{x:.2f}"),
                            sub_t['总销售额'],
                            sub_t['总成本'],
                            sub_t['总盈亏'],
                            sub_t['月份标签']
                        ), axis=-1)
                        trace.customdata = c_data
                        trace.hovertemplate = (
                            "<b>%{customdata[0]}</b><br>"
                            + "团队: <b>%{customdata[5]}</b><br>"
                            + "💹 ROI: <b>%{customdata[1]}</b><br>"
                            + "💰 销售额: <b>¥%{customdata[2]:,.2f}</b><br>"
                            + "💸 成本: <b>¥%{customdata[3]:,.2f}</b><br>"
                            + "⚖️ 盈亏: <b>¥%{customdata[4]:,.2f}</b>"
                            + "<extra></extra>"
                        )
                        trace.textposition = "outside"
                        trace.cliponaxis = False
                    fig_team_roi.add_hline(
                        y=1.0,
                        line_dash="dash",
                        line_color="#ef4444",
                        line_width=1.5,
                        annotation_text="保本 1.0",
                        annotation_position="top left",
                        annotation_font_color="#ef4444"
                    )
                    max_tr = team_display['roi'].max() if not team_display.empty else 1.2
                    fig_team_roi.update_layout(
                        xaxis=dict(
                            tickangle=-15 if len(selected_team_channels) > 3 else 0,
                            tickfont=dict(size=12, color="#334155"),
                            showgrid=True,
                            gridcolor="#f1f5f9"
                        ),
                        yaxis=dict(
                            title="ROI",
                            range=[0, max(max_tr * 1.25, 1.2)],
                            showgrid=True,
                            gridcolor="#f1f5f9"
                        ),
                        yaxis_title="ROI",
                        height=400,
                        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1, title=""),
                        margin=dict(l=10, r=20, t=50, b=50)
                    )
                    st.plotly_chart(fig_team_roi, use_container_width=True)

                st.markdown("---")

                # =========================================================
                # 表格独立区域：在表格正上方直接筛选渠道（无需页面上下滚动）
                # =========================================================
                st.markdown("### 📋 分团队渠道详细数据对比表")
                st.caption("💡 此处自带就近专属渠道筛选：无需反复上滑页面，可直接在此处单选切换某个渠道深入透视三大团队PK，或多选渠道拉通对比。")

                tbl_filter_col1, tbl_filter_col2 = st.columns([2.2, 4.8])
                with tbl_filter_col1:
                    tbl_view_type = st.radio(
                        "表格对比视角",
                        options=["🎯 单渠道横向透视（行：团队 ｜ 列：指标）", "📊 多渠道拉通对比大表"],
                        horizontal=True,
                        key="tbl_view_type_radio"
                    )

                if tbl_view_type.startswith("🎯"):
                    with tbl_filter_col2:
                        tbl_single_channel = st.selectbox(
                            "🎯 选择单渠道进行团队横向透视（一键切换任一渠道，查看三大团队对比）",
                            options=sorted_team_channels,
                            index=0 if sorted_team_channels else None,
                            key="tbl_single_ch_select"
                        )

                    if not tbl_single_channel:
                        st.info("👈 请选择一个渠道以查看团队对比")
                    else:
                        # 获取该渠道在各团队的数据
                        ch_team_df = team_monthly_df[
                            (team_monthly_df['渠道名称'] == tbl_single_channel)
                            & (team_monthly_df['月份标签'].isin(selected_teams))
                            & (~team_monthly_df['is_summary'])
                        ].copy()

                        # 构建每个团队的完整对比记录（行：团队）
                        table_rows = []
                        for t in selected_teams:
                            t_match = ch_team_df[ch_team_df['月份标签'] == t]
                            if not t_match.empty:
                                row = t_match.iloc[0].to_dict()
                                table_rows.append(row)
                            else:
                                table_rows.append({
                                    '月份标签': t,
                                    '渠道名称': tbl_single_channel,
                                    '线索量': 0,
                                    '总转化率': 0.0,
                                    '总转化量': 0.0,
                                    'roi': 0.0,
                                    '总销售额': 0.0,
                                    '总成本': 0.0,
                                    '总盈亏': 0.0,
                                    '单粉成本': 0.0,
                                    '正式课退单': 0,
                                    '正式课总退单率': 0.0,
                                    '直播转化': 0.0,
                                    '直播占比': 0.0,
                                    '私聊转化': 0.0,
                                    '私聊占比': 0.0
                                })
                        team_comp_df = pd.DataFrame(table_rows)

                        # 计算全团队合计指标
                        tot_leads = team_comp_df['线索量'].sum()
                        tot_conv = team_comp_df['总转化量'].sum()
                        tot_conv_rate = (tot_conv / tot_leads) if tot_leads > 0 else 0.0
                        tot_cost = team_comp_df['总成本'].sum()
                        tot_rev = team_comp_df['总销售额'].sum()
                        tot_roi = (tot_rev / tot_cost) if tot_cost > 0 else 0.0
                        tot_profit = team_comp_df['总盈亏'].sum()
                        tot_cac = (tot_cost / tot_leads) if tot_leads > 0 else 0.0
                        tot_refund = team_comp_df['正式课退单'].sum()
                        tot_refund_denom = tot_refund + tot_conv
                        tot_refund_rate = (tot_refund / tot_refund_denom) if tot_refund_denom > 0 else 0.0
                        tot_live = team_comp_df['直播转化'].sum()
                        tot_chat = team_comp_df['私聊转化'].sum()
                        tot_live_ratio = (tot_live / tot_conv) if tot_conv > 0 else 0.0
                        tot_chat_ratio = (tot_chat / tot_conv) if tot_conv > 0 else 0.0

                        total_row = {
                            '月份标签': '全团队合计',
                            '渠道名称': tbl_single_channel,
                            '线索量': tot_leads,
                            '总转化率': tot_conv_rate,
                            '总转化量': tot_conv,
                            'roi': tot_roi,
                            '总销售额': tot_rev,
                            '总成本': tot_cost,
                            '总盈亏': tot_profit,
                            '单粉成本': tot_cac,
                            '正式课退单': tot_refund,
                            '正式课总退单率': tot_refund_rate,
                            '直播转化': tot_live,
                            '直播占比': tot_live_ratio,
                            '私聊转化': tot_chat,
                            '私聊占比': tot_chat_ratio
                        }
                        team_comp_with_total = pd.concat([team_comp_df, pd.DataFrame([total_row])], ignore_index=True)

                        st.markdown(f"#### 📋 【{tbl_single_channel}】各团队详细数据对比（行：团队 ｜ 列：具体指标）")
                        
                        display_table = team_comp_with_total.copy()
                        rate_cols = ['总转化率', '正式课总退单率', '直播占比', '私聊占比']
                        for c in rate_cols:
                            if c in display_table.columns:
                                display_table[c] = display_table[c] * 100.0

                        cols_order = [
                            '月份标签', '线索量', '总转化率', '总转化量',
                            'roi', '总销售额', '总成本', '总盈亏', '单粉成本',
                            '正式课退单', '正式课总退单率',
                            '直播转化', '直播占比', '私聊转化', '私聊占比'
                        ]
                        display_table = display_table[[c for c in cols_order if c in display_table]]
                        
                        team_col_cfg = {
                            "月份标签": st.column_config.TextColumn("团队", width="medium"),
                            "线索量": st.column_config.NumberColumn("线索量 (人)", format="%d"),
                            "总转化率": st.column_config.NumberColumn("🔥 总转化率", format="%.2f%%"),
                            "总转化量": st.column_config.NumberColumn("总单数", format="%.1f"),
                            "roi": st.column_config.NumberColumn("ROI", format="%.2f"),
                            "总销售额": st.column_config.NumberColumn("总销售额", format="¥%.2f"),
                            "总成本": st.column_config.NumberColumn("总成本", format="¥%.2f"),
                            "总盈亏": st.column_config.NumberColumn("总盈亏", format="¥%.2f"),
                            "单粉成本": st.column_config.NumberColumn("单粉成本", format="¥%.2f"),
                            "正式课退单": st.column_config.NumberColumn("正式课退单", format="%d"),
                            "正式课总退单率": st.column_config.NumberColumn("正式课退单率", format="%.2f%%"),
                            "直播转化": st.column_config.NumberColumn("🎙️ 直播转化", format="%.1f"),
                            "直播占比": st.column_config.NumberColumn("直播占比", format="%.1f%%"),
                            "私聊转化": st.column_config.NumberColumn("💬 私聊转化", format="%.1f"),
                            "私聊占比": st.column_config.NumberColumn("私聊占比", format="%.1f%%"),
                        }
                        
                        st.dataframe(display_table, column_config=team_col_cfg, use_container_width=True, hide_index=True)

                        # 导出 Excel
                        t_buffer = io.BytesIO()
                        with pd.ExcelWriter(t_buffer, engine='openpyxl') as writer:
                            export_cols = [
                                '月份标签', '渠道名称', '线索量', '总转化率', '总转化量',
                                'roi', '总销售额', '总成本', '总盈亏', '单粉成本',
                                '正式课退单', '正式课总退单率',
                                '直播转化', '直播占比', '私聊转化', '私聊占比'
                            ]
                            valid_export_cols = [c for c in export_cols if c in team_comp_with_total.columns]
                            team_comp_with_total[valid_export_cols].to_excel(writer, index=False, sheet_name=tbl_single_channel[:30])
                        st.download_button(
                            label=f"📥 导出【{tbl_single_channel}】各团队对比 Excel",
                            data=t_buffer.getvalue(),
                            file_name=f"{selected_project}_{tbl_single_channel}_各团队对比.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            key=f"dl_single_{tbl_single_channel}"
                        )

                else:
                    # ---------------------------------------------------------
                    # 多渠道拉通大表模式（支持就地多选渠道，看全量数据）
                    # ---------------------------------------------------------
                    with tbl_filter_col2:
                        tbl_multi_channels = st.multiselect(
                            "🔍 筛选表格渠道（支持多选，就近直接筛选无需上滑）",
                            options=sorted_team_channels,
                            default=in_core_team if in_core_team else sorted_team_channels[:5],
                            key="tbl_multi_ch_select"
                        )

                    if not tbl_multi_channels:
                        st.info("👈 请在上方选择至少一个渠道以展示对比明细表")
                    else:
                        all_tbl_rows = []
                        for ch in tbl_multi_channels:
                            ch_sub = team_monthly_df[
                                (team_monthly_df['渠道名称'] == ch)
                                & (team_monthly_df['月份标签'].isin(selected_teams))
                                & (~team_monthly_df['is_summary'])
                            ].copy()
                            
                            ch_leads = 0
                            ch_conv = 0.0
                            ch_cost = 0.0
                            ch_rev = 0.0
                            ch_profit = 0.0
                            ch_refund = 0
                            ch_live = 0.0
                            ch_chat = 0.0

                            for t in selected_teams:
                                t_match = ch_sub[ch_sub['月份标签'] == t]
                                if not t_match.empty:
                                    r = t_match.iloc[0].to_dict()
                                else:
                                    r = {
                                        '渠道名称': ch,
                                        '月份标签': t,
                                        '线索量': 0,
                                        '总转化率': 0.0,
                                        '总转化量': 0.0,
                                        'roi': 0.0,
                                        '总销售额': 0.0,
                                        '总成本': 0.0,
                                        '总盈亏': 0.0,
                                        '单粉成本': 0.0,
                                        '正式课退单': 0,
                                        '正式课总退单率': 0.0,
                                        '直播转化': 0.0,
                                        '直播占比': 0.0,
                                        '私聊转化': 0.0,
                                        '私聊占比': 0.0
                                    }
                                all_tbl_rows.append(r)
                                ch_leads += r['线索量']
                                ch_conv += r['总转化量']
                                ch_cost += r['总成本']
                                ch_rev += r['总销售额']
                                ch_profit += r['总盈亏']
                                ch_refund += r['正式课退单']
                                ch_live += r['直播转化']
                                ch_chat += r['私聊转化']

                            # 渠道小计行
                            sub_rate = (ch_conv / ch_leads) if ch_leads > 0 else 0.0
                            sub_roi = (ch_rev / ch_cost) if ch_cost > 0 else 0.0
                            sub_cac = (ch_cost / ch_leads) if ch_leads > 0 else 0.0
                            sub_ref_rate = (ch_refund / (ch_refund + ch_conv)) if (ch_refund + ch_conv) > 0 else 0.0
                            sub_live_ratio = (ch_live / ch_conv) if ch_conv > 0 else 0.0
                            sub_chat_ratio = (ch_chat / ch_conv) if ch_conv > 0 else 0.0
                            all_tbl_rows.append({
                                '渠道名称': ch,
                                '月份标签': f'【{ch} 合计】',
                                '线索量': ch_leads,
                                '总转化率': sub_rate,
                                '总转化量': ch_conv,
                                'roi': sub_roi,
                                '总销售额': ch_rev,
                                '总成本': ch_cost,
                                '总盈亏': ch_profit,
                                '单粉成本': sub_cac,
                                '正式课退单': ch_refund,
                                '正式课总退单率': sub_ref_rate,
                                '直播转化': ch_live,
                                '直播占比': sub_live_ratio,
                                '私聊转化': ch_chat,
                                '私聊占比': sub_chat_ratio
                            })

                        multi_comp_df = pd.DataFrame(all_tbl_rows)

                        # 追加全渠道大盘总计行
                        g_leads = multi_comp_df[~multi_comp_df['月份标签'].str.contains('合计')]['线索量'].sum()
                        g_conv = multi_comp_df[~multi_comp_df['月份标签'].str.contains('合计')]['总转化量'].sum()
                        g_rate = (g_conv / g_leads) if g_leads > 0 else 0.0
                        g_cost = multi_comp_df[~multi_comp_df['月份标签'].str.contains('合计')]['总成本'].sum()
                        g_rev = multi_comp_df[~multi_comp_df['月份标签'].str.contains('合计')]['总销售额'].sum()
                        g_roi = (g_rev / g_cost) if g_cost > 0 else 0.0
                        g_profit = multi_comp_df[~multi_comp_df['月份标签'].str.contains('合计')]['总盈亏'].sum()
                        g_cac = (g_cost / g_leads) if g_leads > 0 else 0.0
                        g_refund = multi_comp_df[~multi_comp_df['月份标签'].str.contains('合计')]['正式课退单'].sum()
                        g_ref_rate = (g_refund / (g_refund + g_conv)) if (g_refund + g_conv) > 0 else 0.0
                        g_live = multi_comp_df[~multi_comp_df['月份标签'].str.contains('合计')]['直播转化'].sum()
                        g_chat = multi_comp_df[~multi_comp_df['月份标签'].str.contains('合计')]['私聊转化'].sum()
                        g_live_ratio = (g_live / g_conv) if g_conv > 0 else 0.0
                        g_chat_ratio = (g_chat / g_conv) if g_conv > 0 else 0.0

                        grand_total_row = {
                            '渠道名称': '⭐ 全部已选渠道',
                            '月份标签': '【全渠道总计】',
                            '线索量': g_leads,
                            '总转化率': g_rate,
                            '总转化量': g_conv,
                            'roi': g_roi,
                            '总销售额': g_rev,
                            '总成本': g_cost,
                            '总盈亏': g_profit,
                            '单粉成本': g_cac,
                            '正式课退单': g_refund,
                            '正式课总退单率': g_ref_rate,
                            '直播转化': g_live,
                            '直播占比': g_live_ratio,
                            '私聊转化': g_chat,
                            '私聊占比': g_chat_ratio
                        }
                        multi_comp_with_total = pd.concat([multi_comp_df, pd.DataFrame([grand_total_row])], ignore_index=True)

                        st.markdown(f"#### 📋 所选 {len(tbl_multi_channels)} 个渠道各团队对比明细大表")

                        display_multi_table = multi_comp_with_total.copy()
                        rate_cols = ['总转化率', '正式课总退单率', '直播占比', '私聊占比']
                        for c in rate_cols:
                            if c in display_multi_table.columns:
                                display_multi_table[c] = display_multi_table[c] * 100.0

                        multi_cols_order = [
                            '渠道名称', '月份标签', '线索量', '总转化率', '总转化量',
                            'roi', '总销售额', '总成本', '总盈亏', '单粉成本',
                            '正式课退单', '正式课总退单率',
                            '直播转化', '直播占比', '私聊转化', '私聊占比'
                        ]
                        display_multi_table = display_multi_table[[c for c in multi_cols_order if c in display_multi_table]]

                        multi_col_cfg = {
                            "渠道名称": st.column_config.TextColumn("渠道名称", width="medium"),
                            "月份标签": st.column_config.TextColumn("团队", width="medium"),
                            "线索量": st.column_config.NumberColumn("线索量 (人)", format="%d"),
                            "总转化率": st.column_config.NumberColumn("🔥 总转化率", format="%.2f%%"),
                            "总转化量": st.column_config.NumberColumn("总单数", format="%.1f"),
                            "roi": st.column_config.NumberColumn("ROI", format="%.2f"),
                            "总销售额": st.column_config.NumberColumn("总销售额", format="¥%.2f"),
                            "总成本": st.column_config.NumberColumn("总成本", format="¥%.2f"),
                            "总盈亏": st.column_config.NumberColumn("总盈亏", format="¥%.2f"),
                            "单粉成本": st.column_config.NumberColumn("单粉成本", format="¥%.2f"),
                            "正式课退单": st.column_config.NumberColumn("正式课退单", format="%d"),
                            "正式课总退单率": st.column_config.NumberColumn("正式课退单率", format="%.2f%%"),
                            "直播转化": st.column_config.NumberColumn("🎙️ 直播转化", format="%.1f"),
                            "直播占比": st.column_config.NumberColumn("直播占比", format="%.1f%%"),
                            "私聊转化": st.column_config.NumberColumn("💬 私聊转化", format="%.1f"),
                            "私聊占比": st.column_config.NumberColumn("私聊占比", format="%.1f%%"),
                        }

                        st.dataframe(display_multi_table, column_config=multi_col_cfg, use_container_width=True, hide_index=True)

                        # 导出 Excel
                        m_buffer = io.BytesIO()
                        with pd.ExcelWriter(m_buffer, engine='openpyxl') as writer:
                            valid_export_cols = [c for c in multi_cols_order if c in multi_comp_with_total.columns]
                            multi_comp_with_total[valid_export_cols].to_excel(writer, index=False, sheet_name="多渠道团队对比")
                        st.download_button(
                            label="📥 导出多渠道团队对比 Excel",
                            data=m_buffer.getvalue(),
                            file_name=f"{selected_project}_多渠道各团队对比.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            key="dl_multi_teams"
                        )
