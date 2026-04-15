import streamlit as st
import mojito
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
import requests
from bs4 import BeautifulSoup
import urllib.parse
import xml.etree.ElementTree as ET
import numpy as np
import FinanceDataReader as fdr

# 1. 앱 설정 (모바일 최적화 레이아웃)
st.set_page_config(page_title="스마트 주식 비서", layout="wide")

st.markdown("""
    <style>
    .main .block-container { padding-top: 1rem; padding-bottom: 1rem; padding-left: 0.5rem; padding-right: 0.5rem; }
    div[data-testid="stMetric"] { background-color: #ffffff; border: 1px solid #f0f2f6; padding: 10px; border-radius: 10px; }
    @media (max-width: 640px) { .stTabs [data-baseweb="tab-list"] { gap: 10px; } .stTabs [data-baseweb="tab"] { padding-left: 10px; padding-right: 10px; } }
    </style>
    """, unsafe_allow_html=True)

# 2. 보안 키 로드 및 API 연결
try:
    APP_KEY = st.secrets["kis"]["app_key"]
    APP_SECRET = st.secrets["kis"]["app_secret"]
    ACC_NO = st.secrets["kis"]["acc_no"]
    ACC_NO_PS = st.secrets["kis"]["acc_no_ps"]
except Exception:
    st.error("⚠️ Streamlit Secrets 설정을 확인해주세요.")
    st.stop()

@st.cache_resource
def get_broker():
    return mojito.KoreaInvestment(
        api_key=APP_KEY, api_secret=APP_SECRET, 
        acc_no=f"{ACC_NO}-{ACC_NO_PS}", mock=False
    )

@st.cache_data(ttl=86400) 
def get_stock_dict():
    try:
        krx_df = fdr.StockListing('KRX')
        return dict(zip(krx_df['Name'], krx_df['Code']))
    except:
        return {"삼성전자": "005930", "SK하이닉스": "000660"}

broker = get_broker()
STOCK_DICT = get_stock_dict()

# 3. 상단 검색 및 설정
with st.expander("⚙️ 종목 검색 및 설정", expanded=True):
    col1, col2 = st.columns([2, 1])
    with col1:
        user_input = st.text_input("종목명 또는 코드 입력 (예: 삼성전기, 009150)", value="삼성전자")
        timeframe = st.radio("차트 주기", ("일봉", "주봉", "월봉"), horizontal=True)
    with col2:
        up_color = st.color_picker("상승 색상 (양봉)", "#FF4136")
        down_color = st.color_picker("하락 색상 (음봉)", "#0074D9")

tf_map = {"일봉": "D", "주봉": "W", "월봉": "M"}
target_code = None
target_name = None

# 종목 검색 로직 
if user_input:
    if user_input.isdigit() and len(user_input) == 6:
        target_code = user_input
        target_name = next((n for n, c in STOCK_DICT.items() if c == target_code), user_input)
    elif user_input in STOCK_DICT:
        target_code = STOCK_DICT[user_input]
        target_name = user_input
    else:
        clean_input = user_input.replace(" ", "")
        matches = [name for name in STOCK_DICT.keys() if clean_input in name.replace(" ", "")]
        
        if matches:
            st.info(f"💡 '{user_input}'(이)가 포함된 종목을 찾았습니다. 아래에서 선택해주세요.")
            selected_match = st.selectbox("정확한 종목 선택", ["여기를 눌러 선택하세요..."] + matches)
            if selected_match != "여기를 눌러 선택하세요...":
                target_code = STOCK_DICT[selected_match]
                target_name = selected_match
        else:
            st.error("❌ 일치하는 상장 종목이 없습니다. 정확한 이름이나 6자리 코드를 입력해주세요.")

# 4. 메인 리포트 시작
if target_code:
    with st.spinner(f"{target_name} 데이터 분석 중..."):
        try:
            price_resp = broker.fetch_price(target_code)['output']
            curr_p = int(price_resp['stck_prpr'])
            diff = int(price_resp['prdy_vrss'])
            rate = float(price_resp['prdy_ctrt'])
            
            end_d = datetime.now().strftime("%Y%m%d")
            start_d = (datetime.now() - timedelta(days=500)).strftime("%Y%m%d")
            chart_res = broker.fetch_ohlcv(target_code, tf_map[timeframe], start_d, end_d)['output2']
            
            df = pd.DataFrame(chart_res)
            df['date'] = pd.to_datetime(df['stck_bsop_date'])
            for col in ['stck_clpr', 'stck_oprc', 'stck_hgpr', 'stck_lwpr', 'acml_vol']:
                df[col] = pd.to_numeric(df[col])
            
            df = df.sort_values(by='date').reset_index(drop=True)
            df['date_str'] = df['date'].dt.strftime('%Y-%m-%d')
            
            df['MA5'] = df['stck_clpr'].rolling(window=5).mean()
            df['MA20'] = df['stck_clpr'].rolling(window=20).mean()

            view_limit = df.tail(30)
            min_y = view_limit['stck_lwpr'].min()
            max_y = view_limit['stck_hgpr'].max()
            y_margin = (max_y - min_y) * 0.05
            y_range = [min_y - y_margin, max_y + y_margin]

            st.write(f"### 📈 {target_name} ({target_code})")
            
            m1, m2 = st.columns(2)
            m1.metric("현재가", f"{curr_p:,}원", f"{diff:,}원 ({rate:+.2f}%)")
            # [수정된 부분] 거래량도 metric 박스 형태로 출력하여 UI 밸런스를 맞춤
            m2.metric("거래량", f"{int(price_resp['acml_vol']):,}주")

            fig = make_subplots(
                rows=2, cols=1, shared_xaxes=True, 
                vertical_spacing=0.03, row_heights=[0.7, 0.3]
            )

            fig.add_trace(go.Candlestick(
                x=df['date_str'], open=df['stck_oprc'], high=df['stck_hgpr'],
                low=df['stck_lwpr'], close=df['stck_clpr'],
                increasing_line_color=up_color, decreasing_line_color=down_color,
                name='주가'
            ), row=1, col=1)
            
            fig.add_trace(go.Scatter(x=df['date_str'], y=df['MA5'], name='5일선', line=dict(color='orange', width=1)), row=1, col=1)
            fig.add_trace(go.Scatter(x=df['date_str'], y=df['MA20'], name='20일선', line=dict(color='purple', width=1)), row=1, col=1)

            vol_colors = np.where(
