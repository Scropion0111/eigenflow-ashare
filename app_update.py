"""
================================================================================
EigenFlow | 量化研究订阅平台
Quantitative Research Platform

【订阅型研究产品化重构 v2.2】
├── 纯横向导航栏（点击有效）
├── 行情视图需Key验证
├── 反共享风控与水印
└── 合规克制设计

================================================================================
"""

import streamlit as st
import pandas as pd
import os
import uuid
import json
import hashlib
import streamlit.components.v1 as components
from datetime import datetime, timedelta
from pathlib import Path

# ==================== 配置 | Configuration ====================

st.set_page_config(
    page_title="EigenFlow | 量化研究",
    page_icon="📊",
    layout="centered",
    initial_sidebar_state="collapsed"
)

APP_DIR = os.path.dirname(__file__)

# ==================== 文件路径配置 ====================

KEY_STATE_FILE = os.path.join(APP_DIR, 'key_state.json')
USAGE_LOG_FILE = os.path.join(APP_DIR, 'usage_log.jsonl')
KEYS_FILE = os.path.join(APP_DIR, 'keys.json')

# ==================== 风控配置 ====================

# 【异常阈值配置位置】
# - max_devices_per_key: 每个Key最多允许的设备数
# - time_window_hours: 时间窗口（小时）
# - device_threshold: 设备阈值，超过此值则标记异常
SHARE_CONFIG = {
    'max_devices_per_key': 2,      # 每个Key最多2个设备
    'time_window_hours': 24,       # 24小时时间窗口
    'device_threshold': 2,        # 超过2个不同设备标记异常
}

KEY_VALIDITY_DAYS = 30  # Key有效期（天）

# ==================== Key 存储与验证 ====================

def load_valid_keys():
    """
    加载有效 Key 列表
    优先级：st.secrets > keys.json > 默认测试Key
    
    【生产环境建议】
    - 使用 Streamlit Cloud secrets 存储真实Key
    - 不要将真实Key写入代码或GitHub
    """
    # 优先从 secrets 加载
    try:
        if hasattr(st.secrets, 'access_keys'):
            return st.secrets.access_keys.get('keys', [])
    except:
        pass
    
    # 其次从本地 keys.json 加载
    if os.path.exists(KEYS_FILE):
        try:
            with open(KEYS_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data.get('keys', [])
        except:
            pass
    
    # 默认测试Key（仅供开发测试）
    return [
        "EF-26Q1-A9F4KZ2M",
        "EF-26Q1-B3H8LP5N",
        "EF-26Q1-C7J2MR9R",
    ]


def validate_access_key(key: str) -> dict:
    """
    验证 Access Key 并返回详细状态
    
    【Key有效期逻辑】
    - first_seen = 用户第一次成功输入该key的当日日期
    - 到期日 = first_seen + 30天
    - 超过30天则Key无效
    """
    key = key.strip().upper()
    valid_keys = load_valid_keys()
    
    if key not in valid_keys:
        return {'valid': False, 'key': mask_key(key)}
    
    now = datetime.now()
    today = now.strftime('%Y-%m-%d')
    
    # 尝试加载状态
    try:
        key_state = load_key_state()
    except:
        key_state = {}
    
    # 首次使用：记录 first_seen
    if key not in key_state:
        # 尝试保存状态（云端可能失败）
        try:
            key_state[key] = {
                'first_seen': today,
                'activated_at': now.isoformat(),
            }
            save_key_state(key_state)
        except:
            pass  # 云端只读文件系统，保存可能失败
        
        # 云端模式：如果无法保存状态，每次都视为首次使用
        return {
            'valid': True,
            'key': mask_key(key),
            'first_seen': today,
            'days_remaining': KEY_VALIDITY_DAYS,
            'expired': False,
            'is_first_use': True
        }
    
    # 已存在状态，检查是否过期
    first_seen = key_state[key].get('first_seen', today)
    
    try:
        first_seen_date = datetime.strptime(first_seen, '%Y-%m-%d')
        days_used = (now - first_seen_date).days
    except:
        days_used = 0
    
    if days_used >= KEY_VALIDITY_DAYS:
        return {
            'valid': False,
            'key': mask_key(key),
            'first_seen': first_seen,
            'days_remaining': 0,
            'expired': True
        }
    
    return {
        'valid': True,
        'key': mask_key(key),
        'first_seen': first_seen,
        'days_remaining': KEY_VALIDITY_DAYS - days_used,
        'expired': False,
        'is_first_use': False
    }


def mask_key(key: str) -> str:
    """掩码Key显示（防止完整泄露）"""
    if len(key) >= 12:
        return f"{key[:8]}{'****'}{key[-4:]}"
    return key[:6] + '****'


# ==================== Key 状态持久化 ====================

def load_key_state() -> dict:
    """加载Key状态（包含first_seen）"""
    if os.path.exists(KEY_STATE_FILE):
        try:
            with open(KEY_STATE_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            pass
    return {}


def save_key_state(state: dict):
    """保存Key状态"""
    try:
        with open(KEY_STATE_FILE, 'w', encoding='utf-8') as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    except Exception as e:
        # 云端只读文件系统可能失败，忽略错误
        pass


# ==================== 设备指纹与日志 ====================

def get_device_id():
    """获取设备ID（session持久化）"""
    if 'device_id' not in st.session_state:
        st.session_state.device_id = str(uuid.uuid4())
    return st.session_state.device_id


def get_client_info():
    """
    获取客户端信息（用于风控）
    
    【日志记录字段】
    - ip: IP地址（hash）
    - ua_hash: User-Agent（hash）
    - device_id: 设备标识（uuid）
    """
    ip = 'unknown'
    try:
        ip = st.context.headers.get('X-Forwarded-For', 'unknown').split(',')[0].strip()
    except:
        pass
    
    ua = 'unknown'
    try:
        ua = st.context.headers.get('User-Agent', 'unknown')
    except:
        pass
    
    return {
        'ip': hashlib.md5(ip.encode()).hexdigest()[:16] if ip != 'unknown' else 'unknown',
        'ua_hash': hashlib.md5(ua.encode()).hexdigest()[:16] if ua != 'unknown' else 'unknown',
        'device_id': get_device_id()
    }


def log_usage(key: str, status: str = 'access'):
    """
    记录使用日志
    
    【日志格式】
    {
        "timestamp": "2026-02-06T10:30:00",
        "key_mask": "EF-26Q1-****KZ2M",
        "status": "access|warning|blocked",
        "ip_hash": "abc123...",
        "ua_hash": "def456...",
        "device_id": "uuid-string",
        "page": "signals|chart|support"
    }
    """
    now = datetime.now()
    client = get_client_info()
    
    log_entry = {
        'timestamp': now.isoformat(),
        'key_mask': mask_key(key),
        'status': status,
        'ip_hash': client['ip'],
        'ua_hash': client['ua_hash'],
        'device_id': client['device_id'],
        'page': st.session_state.get('current_tab', 'unknown')
    }
    
    try:
        with open(USAGE_LOG_FILE, 'a', encoding='utf-8') as f:
            f.write(json.dumps(log_entry, ensure_ascii=False) + '\n')
    except Exception as e:
        # 云端只读文件系统可能失败，忽略错误
        pass


def check_share_anomaly(key: str) -> dict:
    """
    检查共享异常
    
    【异常规则】
    - 同一key在24小时内出现 >2 个不同device_id → 标记异常
    - 检测到异常时返回警告信息，但不强制锁定
    """
    key_state = load_key_state()
    
    if key not in key_state:
        return {'is_anomaly': False, 'warning_message': None, 'should_block': False}
    
    state = key_state[key]
    now = datetime.now()
    window_start = now - timedelta(hours=SHARE_CONFIG['time_window_hours'])
    
    if not os.path.exists(USAGE_LOG_FILE):
        return {'is_anomaly': False, 'warning_message': None, 'should_block': False}
    
    try:
        with open(USAGE_LOG_FILE, 'r', encoding='utf-8') as f:
            recent_devices = set()
            recent_entries = []
            
            for line in f:
                try:
                    entry = json.loads(line.strip())
                    # 匹配同一key的日志（通过mask匹配）
                    if entry.get('key_mask', '').replace('*', '') in key:
                        log_time = datetime.fromisoformat(entry['timestamp'])
                        if log_time >= window_start:
                            recent_entries.append(entry)
                            if entry.get('device_id'):
                                recent_devices.add(entry['device_id'])
                except:
                    pass
    except:
        return {'is_anomaly': False, 'warning_message': None, 'should_block': False}
    
    device_count = len(recent_devices)
    
    if device_count > SHARE_CONFIG['device_threshold']:
        return {
            'is_anomaly': True,
            'warning_message': f"⚠️ 检测到异常使用行为：同一账号在 {SHARE_CONFIG['time_window_hours']} 小时内被 {device_count} 个设备使用。如需多设备使用，请联系作者。",
            'should_block': False
        }
    
    return {'is_anomaly': False, 'warning_message': None, 'should_block': False}


# ==================== 工具函数 ====================

def format_stock_code(code):
    """格式化股票代码"""
    return str(code).strip().zfill(6)


def get_tradingview_symbol(stock_code):
    """获取TradingView股票代码"""
    code = format_stock_code(stock_code)
    if code.startswith(('600', '601', '603', '605', '688')):
        return f"SSE:{code}"
    elif code.startswith(('000', '001', '002', '003', '300', '301')):
        return f"SZSE:{code}"
    else:
        return f"SSE:{code}"


def load_signal_data():
    """加载信号数据"""
    csv_path = os.path.join(APP_DIR, 'trade_list_top10.csv')
    if os.path.exists(csv_path):
        return pd.read_csv(csv_path)
    return pd.DataFrame()


# ==================== CSS 样式 | 顶级设计 ====================

st.markdown("""
<style>
/* 基础设置 */
.block-container {
    max-width: 680px !important;
    padding-top: 0.5rem !important;
    padding-bottom: 4rem !important;
}

/* 品牌头部 */
.brand-header {
    text-align: center;
    padding: 16px 0 12px;
    margin-bottom: 8px;
}

.brand-logo {
    font-size: 1.8em;
    font-weight: 700;
    color: #1a1a1a;
    letter-spacing: -0.5px;
}

.brand-tagline {
    font-size: 0.85em;
    color: #888;
    margin-top: 4px;
    letter-spacing: 1px;
}

/* 合规横幅 */
.compliance-banner {
    background: #f5f5f5;
    color: #666;
    font-size: 12px;
    text-align: center;
    padding: 10px 16px;
    border-radius: 8px;
    margin: 0 0 16px 0;
    line-height: 1.6;
}

/* ========== 纯横向导航栏 ========== */
.nav-wrapper {
    display: flex;
    justify-content: center;
    margin: 20px 0 24px;
}

.nav-container {
    display: inline-flex;
    gap: 4px;
    padding: 4px;
    background: #e5e7eb;
    border-radius: 10px;
}

/* 导航按钮 */
.nav-btn {
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 14px 28px;
    border-radius: 8px;
    font-size: 0.95em;
    font-weight: 600;
    color: #374151;
    cursor: pointer;
    transition: all 0.2s ease;
    border: none;
    background: transparent;
    outline: none;
    user-select: none;
}

.nav-btn:hover {
    color: #111827;
    background: rgba(255,255,255,0.8);
    box-shadow: 0 2px 4px rgba(0,0,0,0.1);
}

.nav-btn.active {
    color: #fff;
    background: #4f46e5;
    box-shadow: 0 2px 6px rgba(79, 70, 229, 0.3);
}

.nav-icon {
    font-size: 1.2em;
}

/* 免责声明条 */
.disclaimer-bar {
    background: #f8fafc;
    border-radius: 6px;
    padding: 10px 14px;
    margin-top: 8px;
    font-size: 12px;
    color: #6b7280;
    text-align: center;
    line-height: 1.6;

    white-space: normal;
    word-break: break-word;
}


/* 锁定屏幕 */
.lock-screen {
    background: linear-gradient(135deg, #fff 0%, #f9fafb 100%);
    border: 2px solid #fbbf24;
    border-radius: 16px;
    padding: 32px 24px;
    margin: 24px 0;
    text-align: center;
}

.lock-icon {
    font-size: 2.5em;
    margin-bottom: 16px;
}

.lock-title {
    font-size: 1.25em;
    font-weight: 700;
    color: #1a1a1a;
    margin-bottom: 12px;
}

.lock-desc {
    font-size: 0.88em;
    color: #6b7280;
    line-height: 1.7;
    margin-bottom: 20px;
}

/* 信号卡片 */
.signal-card {
    padding: 18px;
    border-radius: 12px;
    margin: 10px 0;
    text-align: center;
}

/* Rank #1 - 金色 */
.signal-featured {
    background: linear-gradient(135deg, #fffbeb, #fef3c7);
    border: 2px solid #C9A227;
}

.signal-featured .label {
    color: #92400e;
    font-size: 0.7em;
    font-weight: 600;
    letter-spacing: 1px;
    margin-bottom: 8px;
}

/* Silver */
.signal-silver {
    background: linear-gradient(135deg, #f9fafb, #f3f4f6);
    border: 1px solid #d1d5db;
}

.signal-silver .label {
    color: #6b7280;
    font-size: 0.65em;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 1px;
    margin-bottom: 6px;
}

/* Other */
.signal-other {
    background: #fff;
    border: 1px solid #e5e7eb;
}

.signal-other .label {
    color: #9ca3af;
    font-size: 0.6em;
    font-weight: 500;
    margin-bottom: 4px;
}

.stock-code {
    font-size: 1.1em;
    font-weight: 600;
    color: #1a1a1a;
}

.stock-name {
    color: #4b5563;
    margin-left: 8px;
}

.signal-score {
    font-size: 0.9em;
    color: #6b7280;
}

/* 分区标题 */
.section-title {
    font-size: 0.75em;
    font-weight: 600;
    color: #666;
    margin: 24px 0 12px;
    padding-left: 12px;
    border-left: 3px solid #C9A227;
}

/* 日期标签 */
.date-label {
    text-align: center;
    margin: 12px 0 20px;
    color: #6b7280;
    font-size: 0.78em;
}

/* 水印 */
.watermark {
    position: fixed;
    bottom: 6px;
    left: 0;
    right: 0;
    text-align: center;
    font-size: 0.58em;
    color: #d1d5db;
    padding: 8px;
    background: linear-gradient(to top, rgba(255,255,255,0.95), transparent);
    z-index: 100;
}

/* 底部法律声明 */
.footer-legal {
    background: #f8f9fa;
    border-radius: 8px;
    padding: 16px;
    margin: 24px 0 16px 0;
    text-align: left;
    border: 1px solid #e5e7eb;
}

.footer-title {
    font-size: 0.75em;
    font-weight: 600;
    color: #666;
    margin-bottom: 8px;
}

.footer-content {
    font-size: 0.65em;
    color: #888;
    line-height: 1.8;
}

/* TradingView */
.tv-container {
    width: 100%;
    min-height: 420px;
    margin-bottom: 8px;
}


.tv-disclaimer {
    font-size: 8px;
    color: #64748B;
    line-height: 1.6;
    margin-top: 10px;
    padding: 8px 10px;

    /* 关键：避免被裁剪 */
    white-space: normal;
    word-break: break-word;

    /* 如果被父容器裁掉 */
    overflow: visible;
}


/* 卡片样式 */
.info-card {
    background: #fff;
    border: 1px solid #e5e7eb;
    border-radius: 12px;
    padding: 18px;
    margin: 14px 0;
}

.info-card-title {
    font-size: 0.95em;
    font-weight: 600;
    color: #1a1a1a;
    margin-bottom: 10px;
}

.info-card-text {
    font-size: 0.8em;
    color: #6b7280;
    line-height: 1.7;
}

/* 二维码区域 */
.qr-area {
    background: #f8f9fa;
    border-radius: 12px;
    padding: 14px;
    text-align: center;
    margin: 12px 0;
}

.qr-label {
    font-size: 0.78em;
    color: #6b7280;
    margin-top: 8px;
}

/* 价格样式 */
.price-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 12px 0;
    border-bottom: 1px solid #f0f0f0;
}

.price-row:last-child {
    border-bottom: none;
}

.price-label {
    font-size: 0.9em;
    color: #666;
}

.price-value {
    font-size: 1.1em;
    font-weight: 600;
    color: #333;
}

.price-value.highlight {
    color: #C9A227;
    font-size: 1.2em;
}

.price-tag {
    font-size: 0.6em;
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    color: white;
    padding: 2px 8px;
    border-radius: 10px;
    margin-left: 6px;
}

/* Access Key 显示 */
.access-key-display {
    background: linear-gradient(135deg, #fffbeb 0%, #fef3c7 100%);
    border: 2px solid #C9A227;
    border-radius: 12px;
    padding: 20px;
    margin: 16px 0;
    text-align: center;
}

.ak-label {
    font-size: 0.7em;
    color: #92400e;
    margin-bottom: 8px;
    letter-spacing: 1px;
}

.ak-value {
    font-size: 1.3em;
    font-weight: 700;
    color: #C9A227;
    margin-bottom: 12px;
    font-family: 'SF Mono', Monaco, monospace;
    letter-spacing: 1px;
}

.ak-warning {
    font-size: 0.65em;
    color: #888;
    line-height: 1.6;
}

/* 输入框组 */
.input-group {
    background: linear-gradient(135deg, #fafafa, #f0f0f0);
    border: 1px solid #e5e7eb;
    border-radius: 12px;
    padding: 18px;
    margin: 16px 0;
}

.input-label {
    font-size: 0.9em;
    font-weight: 600;
    color: #374151;
    margin-bottom: 12px;
    text-align: center;
}

/* 隐藏元素 */
#MainMenu {visibility: hidden;}
footer {visibility: hidden;}
header {visibility: hidden;}

/* 隐藏触发按钮 */
button[id^="trigger_"] {
    visibility: hidden !important;
    position: absolute !important;
    width: 1px !important;
    height:  auto;
    padding: 0 !important;
    margin: -1px !important;
    overflow: hidden !important;
    clip: rect(0, 0, 0, 0) !important;
    border: 0 !important;
}

/* 权限提示 */
.locked-prompt {
    background: linear-gradient(135deg, #fef3c7, #fffbeb);
    border: 1px solid #fcd34d;
    border-radius: 12px;
    padding: 20px;
    margin: 20px 0;
    text-align: center;
}

.locked-prompt-icon {
    font-size: 2em;
    margin-bottom: 12px;
}

.locked-prompt-title {
    font-size: 1.1em;
    font-weight: 600;
    color: #92400e;
    margin-bottom: 8px;
}

.locked-prompt-text {
    font-size: 0.85em;
    color: #78350f;
    line-height: 1.6;
}
</style>
""", unsafe_allow_html=True)


# ==================== 页面组件 | 品牌与导航 ====================

def render_brand_header():
    """渲染 EigenFlow 品牌头部 - 机构级专业设计"""
    st.markdown("""
    <div class="brand-header">
        <div class="brand-logo">📊 EigenFlow</div>
        <div class="brand-tagline">Quantitative Research Platform</div>
    </div>
    """, unsafe_allow_html=True)
    
    # ===== 合规横幅 =====
    ##         EigenFlow 为量化研究展示平台，内容仅用于市场行为研究与数据观察，
    ##    不构成证券投资建议或任何交易指令。
    st.markdown('''
    <div class="compliance-banner">
        EigenFlow 是一个基于量化模型的市场研究与数据分析平台，致力于提供系统化的风险状态和市场信号参考，帮助用户理解市场结构与风险变化。
        本平台内容仅用于研究与信息参考，不构成任何投资建议或个股推荐。
    </div>
    ''', unsafe_allow_html=True)


def render_disclaimer():
    """渲染精简免责声明"""          # 本平台仅供学术研究，不构成投资建议，不诱导交易行为
    st.markdown("""
    <div class="disclaimer-bar">
        EigenFlow 平台内容仅用于量化研究与市场信息参考，不构成任何投资建议或买卖依据。</br>
        金融市场存在风险，历史表现不代表未来结果，用户据此决策风险自担。
    </div>
    """, unsafe_allow_html=True)


def render_nav_tabs():
    """
    横向导航栏 - 使用 st.radio 控制状态
    最可靠的方法，兼容所有环境
    """
    tabs = [
        (0, "📊", "信号清单"),
        (1, "📈", "行情视图"),
        (2, "☕", "支持订阅")
    ]
    
    # 获取当前 tab
    current_tab = st.session_state.get('target_tab', 0)
    url_tab = st.query_params.get("tab", None)
    if url_tab is not None:
        current_tab = int(url_tab)
        st.session_state.target_tab = current_tab
    
    # tab 标签
    tab_labels = [f"{icon} {name}" for _, icon, name in tabs]
    
    # ===== 先放最彻底的隐藏 CSS =====
    st.markdown('''
    <style>
    /* ===== 彻底隐藏所有 radio 按钮 ===== */
    /* 隐藏整个 radio 区域 */
    .stRadio {
        display: none !important;
    }
    /* 隐藏我们手动添加的 radio input */
    .nav-radio-inputs,
    .nav-radio-inputs input {
        display: none !important;
        visibility: hidden !important;
        opacity: 0 !important;
        position: absolute !important;
        width: 0 !important;
        height: 0 !important;
        overflow: hidden !important;
    }
    /*标签的 for 隐藏 属性关联 */
    label[for^="nav_radio_"] {
        cursor: pointer;
    }
    </style>
    
    <div class="nav-radio-inputs" style="display:none;">
    ''', unsafe_allow_html=True)
    
    # 渲染大按钮导航（放在隐藏容器前面）
    st.markdown('''
    <div class="nav-wrapper">
        <div class="nav-container">
    ''', unsafe_allow_html=True)
    
    for idx, icon, name in tabs:
        active_class = 'active' if current_tab == idx else ''
        st.markdown(
            f'''<label class="nav-btn {active_class}" for="nav_radio_{idx}">
                <span class="nav-icon">{icon}</span>{name}
            </label>''',
            unsafe_allow_html=True
        )
    
    st.markdown('</div></div>', unsafe_allow_html=True)
    
    # 渲染隐藏的 radio 按钮
    radio_html = '<div class="nav-radio-inputs">'
    for idx, _, _ in tabs:
        checked = 'checked' if current_tab == idx else ''
        radio_html += f'<input type="radio" name="nav_radio" id="nav_radio_{idx}" value="{idx}" {checked}>'
    radio_html += '</div>'
    st.markdown(radio_html, unsafe_allow_html=True)
    
    # ===== 大按钮样式 =====
    st.markdown('''
    <style>
    /* ===== 大按钮样式 ===== */
    .nav-wrapper {
        display: flex;
        justify-content: center;
        margin: 24px 0;
    }
    
    .nav-container {
        display: inline-flex;
        gap: 8px;
        padding: 6px;
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        border-radius: 16px;
        box-shadow: 0 4px 15px rgba(102, 126, 234, 0.3);
    }
    
    /* 大按钮 */
    .nav-btn {
        display: inline-flex;
        align-items: center;
        gap: 8px;
        padding: 16px 32px;
        border-radius: 12px;
        font-size: 1.05em;
        font-weight: 600;
        color: rgba(255, 255, 255, 0.85);
        cursor: pointer;
        transition: all 0.3s ease;
        border: none;
        background: transparent;
        user-select: none;
        margin: 2px;
    }
    
    .nav-btn:hover {
        background: rgba(255, 255, 255, 0.2);
        color: white;
        transform: translateY(-2px);
        box-shadow: 0 4px 12px rgba(0,0,0,0.2);
    }
    
    /* 选中状态 - 白底紫字 */
    .nav-btn.active {
        background: white;
        color: #667eea;
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
    }
    
    .nav-icon {
        font-size: 1.2em;
    }
    
    /* 响应式：小屏幕 */
    @media (max-width: 600px) {
        .nav-btn {
            padding: 12px 16px;
            font-size: 0.9em;
        }
    }
    </style>
    ''', unsafe_allow_html=True)
    
    # 关闭隐藏容器
    st.markdown('</div>', unsafe_allow_html=True)
    
    # 关键：使用 st.radio 同步状态
    selected = st.radio(
        "导航",
        options=tab_labels,
        index=current_tab,
        key="nav_radio_sync",
        label_visibility="collapsed"
    )
    
    # 根据选择更新 tab
    selected_idx = tab_labels.index(selected) if selected in tab_labels else 0
    if selected_idx != current_tab:
        st.session_state.target_tab = selected_idx
        st.query_params["tab"] = str(selected_idx)
        st.rerun()
    
    # 根据选择更新 tab
    selected_idx = tab_labels.index(selected) if selected in tab_labels else 0
    if selected_idx != current_tab:
        st.session_state.target_tab = selected_idx
        st.query_params["tab"] = str(selected_idx)
        st.rerun()


def handle_tab_switch():
    """处理 tab 切换 - 从 session_state 或 URL 读取"""
    # 优先从 session_state 读取
    if 'target_tab' in st.session_state:
        return st.session_state.target_tab
    
    # 其次从 URL query_params 读取
    tab = st.query_params.get("tab", "0")
    st.session_state.target_tab = int(tab)
    return st.session_state.target_tab


def switch_tab(tab_idx):
    """切换 tab"""
    st.session_state.target_tab = tab_idx
    st.query_params["tab"] = str(tab_idx)
    st.rerun()


# ==================== 信号页面组件 ====================

def render_access_input():
    """渲染 Access Key 输入框，返回 (key, masked_key) 或 (None, None)"""
    st.markdown("""
    <div class="input-group">
        <div class="input-label">🔐 输入访问密钥</div>
    """, unsafe_allow_html=True)

    col1, col2 = st.columns([3, 1])
    with col1:
        access_key = st.text_input(
            "Access Key",
            type="password",
            placeholder="EF-26Q1-XXXXXXXX",
            label_visibility="collapsed",
            key="access_key_input"
        )
    with col2:
        confirm_btn = st.button("确认", use_container_width=True, type="primary")

    st.markdown("</div>", unsafe_allow_html=True)

    if confirm_btn and access_key:
        result = validate_access_key(access_key)

        if not result['valid']:
            if result.get('expired'):
                st.error(f"❌ Key 已到期（首次使用：{result['first_seen']}，有效期30天）")
            else:
                st.error("❌ 无效的 Access Key")
            log_usage(access_key, 'blocked')
            return None, None

        if result.get('is_first_use'):
            # 兼容云端模式（first_seen 可能不存在）
            first_seen = result.get('first_seen', datetime.now().strftime('%Y-%m-%d'))
            st.success(f"✅ Key 已激活！有效期至 {(datetime.strptime(first_seen) + timedelta(days=30)).strftime('%Y-%m-%d')}")
        else:
            st.info(f"剩余有效期：{result['days_remaining']} 天")

        # 检查共享异常
        anomaly = check_share_anomaly(access_key)
        if anomaly['is_anomaly']:
            st.warning(anomaly['warning_message'])
            log_usage(access_key, 'warning')

        log_usage(access_key, 'access')

        # 保存验证状态
        st.session_state.verified_key = access_key
        st.session_state.verified_key_mask = result['key']

        return access_key, result['key']

    return None, None


def render_lock_screen():
    """渲染锁定屏幕"""
    st.markdown("""
    <div class="lock-screen">
        <div class="lock-icon">🔐</div>
        <div class="lock-title">核心信号已锁定</div>
        <div class="lock-desc">
            本页面展示 EigenFlow 量化研究核心信号<br>
            包括 Rank 1-10 精选股票与评分<br><br>
            <strong style="color:#f59e0b;">请切换至「支持订阅」页面获取 Access Key</strong>
        </div>
    </div>
    """, unsafe_allow_html=True)


def render_signal_featured(row, name: str, rank: int = 1):
    """渲染模型输出结果 (#1)"""
    code = format_stock_code(str(row.get('symbol', '')))
    score = row.get('score', 0)

    st.markdown(f"""
    <div class="signal-card signal-featured">
        <div class="label">🏆 模型输出结果 #{rank}</div>
        <div class="stock-code">{code} <span class="stock-name">{name}</span></div>
        <div class="signal-score" style="margin-top:8px;">因子得分：{score:.2f}</div>
    </div>
    """, unsafe_allow_html=True)


def render_signal_silver(rank: int, row, name: str):
    """渲染模型输出结果 (#2-3)"""
    code = format_stock_code(str(row.get('symbol', '')))
    score = row.get('score', 0)

    st.markdown(f"""
    <div class="signal-card signal-silver">
        <div class="label">🥈 模型输出结果 #{rank}</div>
        <div class="stock-code">{code} <span class="stock-name">{name}</span></div>
        <div class="signal-score" style="margin-top:6px;">因子得分：{score:.2f}</div>
    </div>
    """, unsafe_allow_html=True)


def render_signal_other(rank: int, row, name: str):
    """渲染模型输出结果 (#4-10)"""
    code = format_stock_code(str(row.get('symbol', '')))
    score = row.get('score', 0)

    st.markdown(f"""
    <div class="signal-card signal-other">
        <div class="label">🥉 模型输出结果 #{rank}</div>
        <div class="stock-code">{code} <span class="stock-name">{name}</span></div>
        <div class="signal-score" style="margin-top:4px;">因子得分：{score:.2f}</div>
    </div>
    """, unsafe_allow_html=True)


# ==================== TradingView 组件 ====================

def render_tradingview_chart(symbol: str, height: int = 400):
    """渲染 TradingView 图表（合规嵌入）"""
    tv_html = f"""
    <div class="tv-container">
        <div id="tradingview_widget" style="height:{height}px;"></div>
    </div>
    <script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script>
    <script type="text/javascript">
    new TradingView.widget({{
        "width": "100%",
        "height": {height},
        "symbol": "{symbol}",
        "interval": "D",
        "timezone": "Asia/Shanghai",
        "theme": "light",
        "style": "1",
        "locale": "zh_CN",
        "toolbar_bg": "#f1f3f6",
        "enable_publishing": false,
        "allow_symbol_change": true,
        "container_id": "tradingview_widget"
    }});
    </script>

    
    <div class="tv-disclaimer">
        本页面行情图表由第三方数据服务提供，仅用于市场数据展示与可视化分析参考。<br>
        图表内容不构成任何买卖建议、价格预测或投资判断。<br>
        部分图表服务可能受网络环境或地区访问影响，如加载异常，请更换网络环境后重试。<br>
        TradingView 为 TradingView, Inc. 的注册商标。本平台与 TradingView, Inc. 不存在合作、授权或隶属关系。<br>
    </div>

    """
    components.html(tv_html, height=height + 130)


# 行情图表由第三方提供，仅作为市场数据可视化参考。<br>
#  EigenFlow 不提供任何买卖建议或价格判断。<br>
#  TradingView® 为 TradingView, Inc. 的注册商标。<br>
#  本平台与 TradingView, Inc. 无合作、授权或隶属关系。<br>

def render_trial_chart():
    """渲染试用版图表"""
    st.markdown("""
    <div class="info-card">
        <div class="info-card-title">🔓 TradingView 试用</div>
        <div class="info-card-text">
            输入任意股票代码，查看实时行情图表。
        </div>
    </div>
    """, unsafe_allow_html=True)

    trial_symbol = st.text_input(
        "输入股票代码",
        placeholder="600519, 000001, 300624",
        max_chars=6,
        label_visibility="visible",
        key="trial_symbol"
    )

    if trial_symbol:
        trial_symbol = trial_symbol.strip().zfill(6)
        if len(trial_symbol) == 6 and trial_symbol.isdigit():
            tv_symbol = get_tradingview_symbol(trial_symbol)
            render_tradingview_chart(tv_symbol)


# ==================== 订阅与支持页面 ====================

def render_support_page():
    """渲染支持订阅页面 - 合规+转化设计"""
    st.markdown("""
    <div class="info-card">
        <div class="info-card-title">📊 研究访问授权说明</div>
        <div class="info-card-text">
            <p>EigenFlow 提供量化研究内容访问授权服务。</p>
            <p style="margin-top:10px;"><strong>订阅用户可获得：</strong></p>
            <ul style="margin:8px 0; padding-left:16px;">
                <li>每日量化模型输出结果</li>
                <li>市场行为观察样本</li>
                <li>行情辅助分析视图</li>
            </ul>
            <p style="margin-top:10px; color:#9ca3af; font-size:0.85em;">
                订阅内容为研究资料访问授权，不构成证券投资建议或交易指令。
            </p>
        </div>
    </div>
    
    <div class="info-card">
        <div class="info-card-title">💰 研究访问授权费用</div>
        <div class="info-card-text">
            <div class="price-row">
                <span class="price-label">月度授权</span>
                <span class="price-value">299 元</span>
            </div>
            <div class="price-row">
                <span class="price-label">季度授权</span>
                <span class="price-value highlight">799 元 <span class="price-tag">推荐</span></span>
            </div>
            <p style="margin-top:12px; font-size:0.75em; color:#888;">仅限个人研究使用</p>
        </div>
    </div>
    
    <div class="info-card">
        <div class="info-card-title">📧 获取 Access Key</div>
        <div class="info-card-text">
            <ul style="margin:8px 0; padding-left:16px;">
                <li>微信：扫描下方二维码联系</li>
                <li>Email：research.eigenflow@gmail.com</li>
            </ul>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # 二维码
    col_qr1, col_qr2 = st.columns(2)

    with col_qr1:

        st.markdown("### 💬 微信咨询")
        st.image("wechat_qr.png", width=180)
        st.caption("扫码咨询详情")

    with col_qr2:
        st.markdown("### 💳 支付宝付款")
        st.image("alipay_qr.png", width=180)
        st.caption("付款备注：邮箱或微信号")
        st.caption("付款后联系开通，获取Access Key解锁模型输出")
    st.markdown("---")
    
    # ========== 法务与语言威慑 ==========
    st.markdown("""
    <div class="info-card">
        <div class="info-card-title">⚖️ 使用声明</div>
        <div class="info-card-text">
            <ul style="margin:8px 0; padding-left:16px;">
                <li><strong>使用范围：</strong>本内容仅供个人研究与学习使用，禁止转售、二次分发或任何形式的公开传播。</li>
                <li><strong>二次收费禁止：</strong>严禁任何形式的二次收费、转售或商业化使用。</li>
                <li><strong>违约后果：</strong>如发现违规行为，访问授权可能被立即终止，恕不另行通知。</li>
            </ul>
        </div>
    </div>
    """, unsafe_allow_html=True)


# ==================== 水印组件 ====================

def render_watermark(key_mask: str = None, mode: str = "licensed"):
    """
    渲染水印（截图威慑）
    
    【水印格式】
    - 授权模式：授权码：EF-26Q1-****KZ2M｜仅限个人研究使用
    - 试用模式：试用模式 | 仅供演示
    """
    if mode == "trial":
        text = "试用模式 | 仅供演示"
    elif key_mask:
        text = f"授权码：{key_mask}｜仅限个人研究使用"
    else:
        text = "EigenFlow Research"

    st.markdown(f'<div class="watermark">{text}</div>', unsafe_allow_html=True)


def render_access_key_display(key_mask: str):
    """渲染Access Key显示（金色+防转售警告）"""
    st.markdown(f'''
    <div class="access-key-display">
        <div class="ak-label">Access Key</div>
        <div class="ak-value">{key_mask}</div>
        <div class="ak-warning">
            仅限个人研究使用。禁止共享、传播或用于商业用途。<br>
            如检测到异常访问行为，平台有权终止授权。
        </div>
    </div>
    ''', unsafe_allow_html=True)


# ==================== 页面内容 | 完整页面定义 ====================

def page_signal_list(key_mask: str):
    """
    【信号清单页】
    - 严格展示 Rank 1~10
    - 分区：精选(#1)、银牌(#2-3)、其他(#4-10)
    - 底部添加时效性提示
    """
    csv_path = os.path.join(APP_DIR, 'trade_list_top10.csv')
    if not os.path.exists(csv_path):
        st.error("❌ 数据文件不存在，请上传 trade_list_top10.csv")
        return

    df = load_signal_data()
    if df.empty:
        st.error("❌ 无法加载信号数据")
        return

    if 'symbol' not in df.columns:
        st.error("❌ 数据格式错误：缺少 symbol 列")
        return

    df_top10 = df.head(10).copy()
    df_top10['symbol'] = df_top10['symbol'].apply(format_stock_code)
    stock_names = df_top10.get('name', df_top10['name']).tolist()

    # 日期标签
    now = datetime.now()
    current_hour = now.hour
    date_label = "下一个交易日" if current_hour >= 16 else "今日信号"

    st.markdown(f"""
    <div class="date-label">📅 {date_label} · {now.strftime('%Y-%m-%d')}</div>
    """, unsafe_allow_html=True)

    # Featured - Rank #1
    if len(df_top10) >= 1:
        render_signal_featured(df_top10.iloc[0], stock_names[0], rank=1)

    # Silver - Rank #2-3
    if len(df_top10) >= 3:
        st.markdown('<div class="section-title">🥈 模型输出结果 #2-3</div>', unsafe_allow_html=True)
        for i in range(1, 3):
            render_signal_silver(i + 1, df_top10.iloc[i], stock_names[i])

    # Other - Rank #4-10
    if len(df_top10) >= 4:
        st.markdown('<div class="section-title">🥉 模型输出结果 #4-10</div>', unsafe_allow_html=True)
        for i in range(3, min(10, len(df_top10))):
            render_signal_other(i + 1, df_top10.iloc[i], stock_names[i])

    st.markdown("---")
    
    # ========== 时效性提示 ==========
    st.markdown("""
    <div class="disclaimer-bar">
        信号具有时效性，仅在研究窗口期内具有参考意义。
    </div>
    """, unsafe_allow_html=True)

    # ========== 底部法律声明 ==========
    st.markdown("""
    <div class="footer-legal">
        <div class="footer-title">使用声明</div>
        <div class="footer-content">
            本本平台展示的市场状态或模型结果来源于历史数据与统计方法，不代表未来市场走势，仅供研究参考，不作为任何投资决策依据。<br>
            模型结果可能存在失效风险、参数偏差或市场环境变化带来的不确定性，用户应基于自身风险承受能力独立决策并自行承担投资风险。<br>
            本平台内容仅供个人研究与学习使用，禁止二次传播、转售或公开发布。<br>
            严禁任何形式的商业化使用或二次收费。<br>
            如发现违规行为，平台有权终止访问授权并保留追责权利。
    </div>
    """, unsafe_allow_html=True)

    render_watermark(key_mask)


def page_chart(key_verified: bool = False):
    """
    【行情视图页】
    - TradingView 合规嵌入
    - 图表下方标注免责声明
    - 需要 Key 验证
    """
    st.markdown("""
    <div class="date-label" style="font-size:1em; font-weight:600; color:#374151;">
        📈 行情视图
    </div>
    """, unsafe_allow_html=True)

    # 未验证 Key 时显示锁定状态
    if not key_verified:
        st.markdown("""
        <div class="locked-prompt">
            <div class="locked-prompt-icon">🔒</div>
            <div class="locked-prompt-title">行情视图需订阅后解锁</div>
            <div class="locked-prompt-text">
                请输入 Access Key 验证身份
            </div>
        </div>
        """, unsafe_allow_html=True)

        # Key 验证入口
        st.markdown("""
        <div class="input-group">
            <div class="input-label">🔐 输入 Access Key 解锁</div>
        """, unsafe_allow_html=True)

        col1, col2 = st.columns([3, 1])
        with col1:
            chart_key = st.text_input(
                "Access Key",
                type="password",
                placeholder="EF-26Q1-XXXXXXXX",
                label_visibility="collapsed",
                key="chart_key_input"
            )
        with col2:
            chart_confirm = st.button("解锁", use_container_width=True, type="primary")

        st.markdown("</div>", unsafe_allow_html=True)

        # 验证逻辑
        if chart_confirm and chart_key:
            result = validate_access_key(chart_key)
            if result['valid']:
                st.session_state.verified_key = chart_key
                st.session_state.verified_key_mask = result['key']
                st.success("✅ 验证成功！")
                st.rerun()
            else:
                if result.get('expired'):
                    st.error(f"❌ Key 已到期")
                else:
                    st.error("❌ 无效的 Access Key")

        # 快捷入口
        if st.button("→ 获取 Access Key", type="secondary", use_container_width=True):
            st.session_state.target_tab = 2
            st.rerun()

        render_watermark(mode="trial")
        return

    # 已验证 Key，加载图表
    df = load_signal_data()

    if df.empty:
        st.warning("暂无信号数据，请上传 trade_list_top10.csv")
        return

    if 'symbol' not in df.columns:
        st.error("数据格式错误：缺少 symbol 列")
        return

    df_top10 = df.head(10).copy()
    df_top10['symbol'] = df_top10['symbol'].apply(format_stock_code)

    # 股票选择器
    stock_options = [f"{row['symbol']} · {row.get('name', row['symbol'])}" for _, row in df_top10.iterrows()]

    if not stock_options:
        st.warning("无法生成股票选项")
        return

    selected = st.selectbox("选择股票", options=stock_options, index=0, label_visibility="visible", key="chart_select")

    if selected:
        selected_code = selected.split(" · ")[0]
        symbol = get_tradingview_symbol(selected_code)
        render_tradingview_chart(symbol)

    # 水印
    key_mask = st.session_state.get('verified_key_mask', None)
    render_watermark(key_mask)


# ==================== 主程序 | 页面调度 ====================

def main():
    """
    【主入口】
    
    工程架构：
    - HTML 负责"点"：<a href="?tab=xxx">
    - Streamlit 只负责"读 URL"：st.query_params.get("tab")
    - 绝对不渲染任何导航组件（st.radio/st.tabs/st.button）
    """
    render_brand_header()
    render_disclaimer()

    # ===== 只读 URL，不做任何导航组件 =====
    tab = st.query_params.get("tab", "support")

    # ===== HTML 横向导航（纯 a 标签）=====
    st.markdown('''
    <style>
    .nav-container {
        display: flex;
        gap: 0;
        background: white;
        border-radius: 12px;
        padding: 8px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.08);
        margin: 16px 0;
    }
    
    .nav-link {
        flex: 1;
        text-align: center;
        padding: 16px 12px;
        border-radius: 10px;
        text-decoration: none !important;
        color: #6b7280;
        font-weight: 500;
        font-size: 14px;
        transition: all 0.3s;
        border: 2px solid transparent;
    }
    
    .nav-link:hover {
        background: #f3f4f6;
        color: #374151;
    }
    
    .nav-link.active {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white !important;
    }
    
    .nav-icon {
        font-size: 20px;
        display: block;
        margin-bottom: 4px;
    }
    </style>
    
    <div class="nav-container">
        <a href="?tab=signal" class="nav-link ''' + ('active' if tab == 'signal' else '') + '''">
            <span class="nav-icon">📊</span>
            信号清单
        </a>
        <a href="?tab=chart" class="nav-link ''' + ('active' if tab == 'chart' else '') + '''">
            <span class="nav-icon">📈</span>
            行情视图
        </a>
        <a href="?tab=support" class="nav-link ''' + ('active' if tab == 'support' else '') + '''">
            <span class="nav-icon">☕</span>
            支持订阅
        </a>
    </div>
    ''', unsafe_allow_html=True)

    # ===== 根据 URL 参数渲染页面（只渲染内容，不渲染导航）=====
    
    if tab == "signal":
        # ===== 信号清单 =====
        access_key = st.session_state.get('verified_key', None)
        key_mask = st.session_state.get('verified_key_mask', None)
        
        if access_key:
            page_signal_list(key_mask)
        else:
            # 无 Key，必须显示 Access Key 输入框
            st.markdown('''
            <div style="
                background: linear-gradient(135deg, #fef3c7 0%, #fde68a 100%);
                border-radius: 16px;
                padding: 32px;
                text-align: center;
                border: 2px solid #f59e0b;
                margin-bottom: 24px;
            ">
                <div style="font-size: 48px; margin-bottom: 12px;">🔒</div>
                <h3 style="color: #92400e; margin-bottom: 8px;">请输入 Access Key 解锁信号清单</h3>
                <p style="color: #b45309;">在下方输入框中输入您的订阅密钥</p>
            </div>
            ''', unsafe_allow_html=True)
            
            # 显示 Key 输入框
            access_key, key_mask = render_access_input()
            
            if access_key:
                st.session_state.verified_key = access_key
                st.session_state.verified_key_mask = key_mask
                st.success("✅ 验证成功！")
                st.rerun()
            
            # 提示引导
            st.info("💡 没有 Key？请切换到「☕ 支持订阅」页面获取")
            
            render_trial_chart()
            render_watermark(mode="trial")

    elif tab == "chart":
        # ===== 行情视图 =====
        access_key = st.session_state.get('verified_key', None)
        
        if access_key:
            page_chart(key_verified=True)
        else:
            st.markdown('''
            <div style="
                background: linear-gradient(135deg, #fee2e2 0%, #fecaca 100%);
                border-radius: 16px;
                padding: 32px;
                text-align: center;
                border: 2px solid #ef4444;
                margin-bottom: 24px;
            ">
                <div style="font-size: 48px; margin-bottom: 12px;">🔒</div>
                <h3 style="color: #b91c1c; margin-bottom: 8px;">行情视图需解锁后查看</h3>
                <h3 style="color: #b91c1c; margin-bottom: 8px;">详情请点击“支持订阅”界面</h3>
                <h4 style="color: #F59E0B;">请先获取 Access Key</h4>
            </div>
            ''', unsafe_allow_html=True)
            
            # 显示 Key 输入框
            col1, col2 = st.columns([3, 1])
            with col1:
                chart_key = st.text_input(
                    "Access Key", type="password", placeholder="EF-26Q1-XXXXXXXX",
                    label_visibility="collapsed", key="chart_key_input"
                )
            with col2:
                if st.button("解锁", use_container_width=True, type="primary"):
                    result = validate_access_key(chart_key)
                    if result['valid']:
                        st.session_state.verified_key = chart_key
                        st.session_state.verified_key_mask = result['key']
                        st.success("✅ 验证成功！")
                        st.rerun()
                    else:
                        st.error("❌ 无效的 Access Key")
            
            # 引导
            st.info("💡 没有 Key？请切换到「☕ 支持订阅」页面获取")
            
            render_watermark(mode="trial")

    else:  # tab == "support"
        # ===== 支持订阅（始终开放）=====
        render_support_page()


if __name__ == "__main__":
    main()
