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

# 1. 앱 설정 (다크모드 완벽 대응 스타일)
st.set_page_config(page_title="스마트 주식 비서 Pro", layout="wide")

# [수정] 다크모드 표(Table) 글씨 색상 가시성 확보를 위한 CSS 추가
st.markdown("""
    <style>
    .main .block-container { padding-top: 1rem; padding-bottom: 1rem; padding-left: 0.5rem; padding-right: 0.5rem; }
    div[data-testid="stMetric"] { 
        padding: 10px; border-radius: 12px; 
        border: 1px solid rgba(128, 128, 128, 0.2);
        background-color: rgba(128, 128, 128, 0.05);
    }
    table { color: inherit !important; }
    thead tr th { color: inherit !important; background-color: rgba(128, 128, 128, 0.1) !important; font-weight: bold !important; }
    tbody tr th { color: inherit !important; }
    td { color: inherit !important; }
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
    return mojito.KoreaInvestment(api_key=APP_KEY, api_secret=APP_SECRET, acc_no=f"{ACC_NO}-{ACC_NO_PS}", mock=False)

@st.cache_data(ttl=86400) 
def get_stock_dict():
    try:
        krx_df = fdr.StockListing('KRX')
        return dict(zip(krx_df['Name'], krx_df['Code']))
    except:
        return {"삼성전자": "005930"}

broker = get_broker()
STOCK_DICT = get_stock_dict()

# 3. 분석 엔진
@st.cache_data(ttl=300)
def fetch_and_calc(code, timeframe):
    tf_map = {"일봉": "D", "주봉": "W", "월봉": "M"}
    end_d = datetime.now().strftime("%Y%m%d")
    start_d = (datetime.now() - timedelta(days=500)).strftime("%Y%m%d")
    res = broker.fetch_ohlcv(code, tf_map[timeframe], start_d, end_d)['output2']
    df = pd.DataFrame(res)
    df['date'] = pd.to_datetime(df['stck_bsop_date'])
    for col in ['stck_clpr', 'stck_oprc', 'stck_hgpr', 'stck_lwpr', 'acml_vol']:
        df[col] = pd.to_numeric(df[col])
    df = df.sort_values(by='date').reset_index(drop=True)
    df['date_str'] = df['date'].dt.strftime('%Y-%m-%d')
    
    df['MA5'] = df['stck_clpr'].rolling(window=5).mean()
    df['MA20'] = df['stck_clpr'].rolling(window=20).mean()
    df['MA60'] = df['stck_clpr'].rolling(window=60).mean()
    df['MA120'] = df['stck_clpr'].rolling(window=120).mean()
    
    df['std'] = df['stck_clpr'].rolling(window=20).std()
    df['Upper_BB'] = df['MA20'] + (df['std'] * 2)
    df['Lower_BB'] = df['MA20'] - (df['std'] * 2)
    
    delta = df['stck_clpr'].diff()
    up, down = delta.clip(lower=0), -1 * delta.clip(upper=0)
    ema_up = up.ewm(com=13, adjust=False).mean()
    ema_down = down.ewm(com=13, adjust=False).mean()
    df['RSI'] = 100 - (100 / (1 + (ema_up / ema_down)))
    return df

@st.cache_data(ttl=3600)
def get_fundamental(code):
    try:
        url = f"https://finance.naver.com/item/main.naver?code={code}"
        res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'})
        soup = BeautifulSoup(res.text, 'html.parser')
        m_cap = soup.select_one('#_market_sum').text.strip().replace('\t', '').replace('\n', '')
        per = soup.select_one('#_per').text.strip() if soup.select_one('#_per') else "N/A"
        pbr = soup.select_one('#_pbr').text.strip() if soup.select_one('#_pbr') else "N/A"
        return {"시총": m_cap, "PER": per, "PBR": pbr}
    except: return {"시총": "-", "PER": "-", "PBR": "-"}

# 4. 상단 검색창
with st.expander("🔍 종목 검색 및 설정", expanded=True):
    col1, col2 = st.columns([2, 1])
    with col1:
        search_input = st.text_input("종목명 입력", value="삼성전자")
        timeframe = st.radio("주기", ("일봉", "주봉", "월봉"), horizontal=True)
    with col2:
        up_color = st.color_picker("상승 색상", "#FF4136")
        down_color = st.color_picker("하락 색상", "#0074D9")

target_code, target_name = None, None
if search_input in STOCK_DICT:
    target_code, target_name = STOCK_DICT[search_input], search_input
else:
    matches = [n for n in STOCK_DICT.keys() if search_input in n]
    if matches:
        sel = st.selectbox("종목 선택", ["선택하세요..."] + matches)
        if sel != "선택하세요...":
            target_code, target_name = STOCK_DICT[sel], sel

# 5. 메인 분석창
if target_code:
    with st.spinner("데이터 분석 리포트 생성 중..."):
        try:
            price_resp = broker.fetch_price(target_code)['output']
            curr_p = int(price_resp['stck_prpr'])
            df = fetch_and_calc(target_code, timeframe)
            fund = get_fundamental(target_code)

            with st.container(border=True):
                c1, c2, c3, c4 = st.columns([1.5, 1, 1, 1])
                c1.metric(f"{target_name} 현재가", f"{curr_p:,}원", f"{int(price_resp['prdy_vrss']):,}원 ({float(price_resp['prdy_ctrt']):+.2f}%)")
                c2.metric("거래량", f"{int(price_resp['acml_vol']):,}주")
                c3.metric("시가총액", fund['시총'])
                c4.metric("PER / PBR", f"{fund['PER']} / {fund['PBR']}")

            # [수정] 차트 범위 최적화 (마이너스 값 제거)
            view = df.tail(30)
            # Y축의 최소값이 무조건 0보다 크거나 같도록 max(0, ...) 적용
            min_y = max(0, view[['stck_lwpr', 'Lower_BB']].min().min() * 0.98)
            max_y = view[['stck_hgpr', 'Upper_BB']].max().max() * 1.02
            y_range = [min_y, max_y]
            
            # 거래량 차트도 현재 보이는 30일치 데이터 기준의 최대값으로 최적화
            vol_max = view['acml_vol'].max()

            fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.03, row_heights=[0.7, 0.3])
            
            fig.add_trace(go.Candlestick(x=df['date_str'], open=df['stck_oprc'], high=df['stck_hgpr'], low=df['stck_lwpr'], close=df['stck_clpr'], increasing_line_color=up_color, decreasing_line_color=down_color, name='주가'), row=1, col=1)
            fig.add_trace(go.Scatter(x=df['date_str'], y=df['MA5'], name='5일선', line=dict(color='orange', width=1)), row=1, col=1)
            fig.add_trace(go.Scatter(x=df['date_str'], y=df['MA20'], name='20일선', line=dict(color='purple', width=1)), row=1, col=1)
            fig.add_trace(go.Scatter(x=df['date_str'], y=df['MA60'], name='60일선', line=dict(color='green', width=1)), row=1, col=1)
            fig.add_trace(go.Scatter(x=df['date_str'], y=df['MA120'], name='120일선', line=dict(color='blue', width=1.5)), row=1, col=1)
            
            fig.add_trace(go.Scatter(x=df['date_str'], y=df['Upper_BB'], line=dict(color='rgba(173,216,230,0.2)'), showlegend=False), row=1, col=1)
            fig.add_trace(go.Scatter(x=df['date_str'], y=df['Lower_BB'], line=dict(color='rgba(173,216,230,0.2)'), fill='tonexty', fillcolor='rgba(173,216,230,0.05)', showlegend=False), row=1, col=1)
            
            vol_colors = np.where(df['stck_clpr'] >= df['stck_oprc'], up_color, down_color)
            fig.add_trace(go.Bar(x=df['date_str'], y=df['acml_vol'], marker_color=vol_colors, name='거래량'), row=2, col=1)
            
            fig.update_layout(
                height=500, template='plotly_white', margin=dict(l=0, r=0, t=10, b=0), dragmode='pan',
                # [수정] 범례(Legend)를 차트 영역 상단 내부로 겹치게(Overlay) 이동
                legend=dict(orientation="h", yanchor="top", y=0.99, xanchor="left", x=0.01, bgcolor="rgba(128,128,128,0.1)"),
                yaxis=dict(range=y_range, side='right', showgrid=True, gridcolor='rgba(128,128,128,0.1)'),
                # [수정] 거래량 Y축 범위를 0 이상으로 고정
                yaxis2=dict(side='right', showgrid=False, range=[0, vol_max * 1.1]),
                paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)'
            )
            fig.update_xaxes(type='category', range=[len(df)-30, len(df)], rangeslider_visible=False)
            st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})

            # 하단 탭
            t1, t2, t3 = st.tabs(["🎯 투자 전략 & AI 분석", "📊 수급(매매) 동향", "📰 뉴스피드"])
            
            with t1:
                st.subheader("🎯 단계별 투자 전략")
                volatility = df['stck_clpr'].pct_change().std()
                v_f = volatility * 100
                st.write(f"현재 주가 변동성: **{v_f:.2f}%**")
                
                strat = {
                    "초단기 (3일)": [int(curr_p*0.99), int(curr_p*(1+0.02*v_f)), int(curr_p*0.97)],
                    "단기 (1개월)": [int(curr_p*0.97), int(curr_p*(1+0.05*v_f)), int(curr_p*0.93)],
                    "중기 (6개월)": [int(curr_p*0.93), int(curr_p*(1+0.15*v_f)), int(curr_p*0.85)],
                    "장기 (1년+)": [int(curr_p*0.90), int(curr_p*(1+0.30*v_f)), int(curr_p*0.75)]
                }
                s_df = pd.DataFrame(strat, index=["추천 매수가", "목표가", "손절가"])
                st.table(s_df.style.format("{:,}원"))
                
                st.divider()

                st.subheader("🤖 AI 종합 판단 결과")
                rsi = df['RSI'].iloc[-1]
                ma60, ma120 = df['MA60'].iloc[-1], df['MA120'].iloc[-1]
                per_val = float(fund['PER'].replace(',','')) if fund['PER'] not in ['N/A', '-'] else 20
                bb_width = (df['Upper_BB'].iloc[-1] - df['Lower_BB'].iloc[-1]) / df['MA20'].iloc[-1]
                
                analysis = f"현재 **{target_name}**의 주가는 "
                if curr_p > ma60 and ma60 > ma120:
                    analysis += "단기, 중기, 장기 이평선이 나란히 위를 향하는 **정배열** 상태로 아주 강한 상승 추세입니다. "
                elif curr_p < ma60:
                    analysis += "중기 수급선(60일선) 아래에 위치하여 **조정 국면**에 있습니다. "
                
                if rsi > 70: analysis += f"현재 RSI가 {rsi:.1f}로 과열권(70 초과)이므로 추격 매수보다는 분할 매도를 고려할 타이밍입니다. "
                elif rsi < 35: analysis += f"현재 RSI가 {rsi:.1f}로 바닥권에 근접하여 기술적 반등을 기대해볼 수 있습니다. "
                else: analysis += f"수급 강도(RSI {rsi:.1f})는 안정적인 중립 상태입니다. "
                
                if per_val < 10: analysis += "또한 밸류에이션(PER) 측면에서 저평가되어 있어 장기 투자 매력이 높습니다. "
                if bb_width < 0.05: analysis += "볼린저 밴드 폭이 매우 좁아져 있어, 조만간 위나 아래로 큰 변동성이 발생할 수 있으니 주의 깊게 관찰하세요."
                
                st.info(analysis)

                st.write("---")
                st.write("#### 📖 참고: 기술적 지표 및 용어 설명")
                st.write("- **PER/PBR:** 기업 가치 대비 주가 수준 (낮을수록 회사가치에 비해 주가가 저렴함을 뜻함)")
                st.write("- **RSI (상대강도지수):** 최근 주가의 상승/하락 강도를 수치화한 것 (70 이상 과매수, 30 이하 과매도)")
                st.write("- **볼린저 밴드:** 주가가 움직이는 통로. 통로가 좁아지면(수축) 조만간 위나 아래로 큰 변동이 일어날 징조입니다.")
                st.write("- **60일선 (수급선):** 3개월 평균 가격으로, 주로 기관/외국인 등 큰 자금 유입의 기준선이 됩니다.")
                st.write("- **120일선 (경기선):** 6개월 평균 가격으로, 장기적인 대세 상승/하락을 가르는 가장 중요한 기준선입니다.")

            with t2:
                try:
                    h = {'User-Agent': 'Mozilla/5.0'}
                    n_url = f"https://finance.naver.com/item/frgn.naver?code={target_code}"
                    n_res = requests.get(n_url, headers=h, timeout=5)
                    n_res.encoding = 'euc-kr'
                    rows = BeautifulSoup(n_res.text, 'html.parser').select('table.type2 tr')
                    t_html = '<div style="overflow-x:auto;"><table style="width:100%; border-collapse:collapse; font-size:12px; text-align:center;">'
                    t_html += '<tr style="border-bottom: 1px solid gray;"><th>날짜</th><th>개인</th><th>외국인</th><th>기관</th></tr>'
                    count = 0
                    for r in rows:
                        tds = r.select('td')
                        if len(tds) == 9 and tds[0].text.
