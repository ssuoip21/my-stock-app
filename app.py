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

st.markdown("""
    <style>
    .main .block-container { padding-top: 1rem; padding-bottom: 1rem; padding-left: 0.5rem; padding-right: 0.5rem; }
    /* 다크모드/라이트모드 자동 대응 박스 스타일 */
    div[data-testid="stMetric"] { 
        padding: 10px; border-radius: 12px; 
        border: 1px solid rgba(128, 128, 128, 0.2);
        background-color: rgba(128, 128, 128, 0.05);
    }
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

# 3. 분석 엔진 (이동평균선 5, 20, 60, 120일 추가)
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
    
    # [핵심] 이동평균선 추가 (5, 20, 60, 120)
    df['MA5'] = df['stck_clpr'].rolling(window=5).mean()
    df['MA20'] = df['stck_clpr'].rolling(window=20).mean()
    df['MA60'] = df['stck_clpr'].rolling(window=60).mean()
    df['MA120'] = df['stck_clpr'].rolling(window=120).mean()
    
    # 보조지표 계산
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

# 4. 상단 검색창 (관심종목 삭제됨)
with st.expander("🔍 종목 검색 및 설정", expanded=True):
    col1, col2 = st.columns([2, 1])
    with col1:
        search_input = st.text_input("종목명 입력", value="삼성전자")
        timeframe = st.radio("주기", ("일봉", "주봉", "월봉"), horizontal=True)
    with col2:
        up_color = st.color_picker("상승 색상", "#FF4136")
        down_color = st.color_picker("하락 색상", "#0074D9")

# 검색 로직
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

            # 통합 지표 영역
            with st.container(border=True):
                c1, c2, c3, c4 = st.columns([1.5, 1, 1, 1])
                c1.metric(f"{target_name} 현재가", f"{curr_p:,}원", f"{int(price_resp['prdy_vrss']):,}원 ({float(price_resp['prdy_ctrt']):+.2f}%)")
                c2.metric("거래량", f"{int(price_resp['acml_vol']):,}주")
                c3.metric("시가총액", fund['시총'])
                c4.metric("PER / PBR", f"{fund['PER']} / {fund['PBR']}")

            # 차트 영역
            view = df.tail(30)
            y_range = [view[['stck_lwpr', 'Lower_BB']].min().min()*0.98, view[['stck_hgpr', 'Upper_BB']].max().max()*1.02]
            fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.03, row_heights=[0.7, 0.3])
            
            # 주가 및 이평선 (5, 20, 60, 120)
            fig.add_trace(go.Candlestick(x=df['date_str'], open=df['stck_oprc'], high=df['stck_hgpr'], low=df['stck_lwpr'], close=df['stck_clpr'], increasing_line_color=up_color, decreasing_line_color=down_color, name='주가'), row=1, col=1)
            fig.add_trace(go.Scatter(x=df['date_str'], y=df['MA5'], name='5일선', line=dict(color='orange', width=1)), row=1, col=1)
            fig.add_trace(go.Scatter(x=df['date_str'], y=df['MA20'], name='20일선', line=dict(color='purple', width=1)), row=1, col=1)
            fig.add_trace(go.Scatter(x=df['date_str'], y=df['MA60'], name='60일선', line=dict(color='green', width=1)), row=1, col=1)
            fig.add_trace(go.Scatter(x=df['date_str'], y=df['MA120'], name='120일선', line=dict(color='blue', width=1.5)), row=1, col=1)
            
            # 볼린저 밴드 영역
            fig.add_trace(go.Scatter(x=df['date_str'], y=df['Upper_BB'], line=dict(color='rgba(173,216,230,0.2)'), showlegend=False), row=1, col=1)
            fig.add_trace(go.Scatter(x=df['date_str'], y=df['Lower_BB'], line=dict(color='rgba(173,216,230,0.2)'), fill='tonexty', fillcolor='rgba(173,216,230,0.05)', showlegend=False), row=1, col=1)
            
            # 거래량
            vol_colors = np.where(df['stck_clpr'] >= df['stck_oprc'], up_color, down_color)
            fig.add_trace(go.Bar(x=df['date_str'], y=df['acml_vol'], marker_color=vol_colors, name='거래량'), row=2, col=1)
            
            fig.update_layout(height=500, template='plotly_white', margin=dict(l=0, r=0, t=10, b=0), dragmode='pan', yaxis=dict(range=y_range, side='right'), paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
            fig.update_xaxes(type='category', range=[len(df)-30, len(df)], rangeslider_visible=False)
            st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})

            # 하단 탭
            t1, t2, t3 = st.tabs(["📊 분석 & 전략", "📖 용어 사전", "📰 뉴스"])
            
            with t1:
                col_s1, col_s2 = st.columns(2)
                with col_s1:
                    st.write("**[투자 전략 표]**")
                    volatility = df['stck_clpr'].pct_change().std() * 100
                    strat = {
                        "초단기(3일)": [int(curr_p*(1+0.05))],
                        "단기(1개월)": [int(curr_p*(1+0.12))],
                        "중기(6개월)": [int(curr_p*(1+0.25))],
                        "장기(1년)": [int(curr_p*(1+0.45))]
                    }
                    st.table(pd.DataFrame(strat, index=["목표가"]).style.format("{:,}원"))
                
                with col_s2:
                    st.write("**[AI 종합 분석]**")
                    rsi = df['RSI'].iloc[-1]
                    ma60, ma120 = df['MA60'].iloc[-1], df['MA120'].iloc[-1]
                    
                    analysis = f"현재 **{target_name}**의 주가는 "
                    if curr_p > ma60 and ma60 > ma120:
                        analysis += "단기, 중기, 장기 이평선이 나란히 위를 향하는 **정배열** 상태로 아주 강한 상승 추세입니다. "
                    elif curr_p < ma60:
                        analysis += "중기 수급선(60일선) 아래에 위치하여 조정 국면에 있습니다. "
                    
                    if rsi > 70: analysis += "RSI가 과열권이므로 추격 매수보다는 분할 매도를 고려할 타이밍입니다."
                    elif rsi < 35: analysis += "RSI가 바닥권에 근접하여 기술적 반등을 기대해볼 수 있습니다."
                    else: analysis += "현재 심리 지표는 안정적인 중립 상태입니다."
                    st.info(analysis)

            with t2:
                st.write("#### 💡 이평선의 의미")
                st.write("- **5일선:** 일주일간의 평균 가격. 단기적인 주가 방향을 결정합니다.")
                st.write("- **60일선 (수급선):** 3개월간의 평균 가격. 기관과 외국인의 자금이 들어오는지 판단하는 기준입니다.")
                st.write("- **120일선 (경기선):** 6개월간의 평균 가격. 전체적인 경기가 살아나는지 보여주는 대세 선입니다.")
                st.write("- **RSI / 볼린저 밴드:** 주가가 과하게 올랐는지, 아니면 통로 끝에 닿아 반등할지 알려주는 보조 지표입니다.")

            with t3:
                try:
                    enc = urllib.parse.quote(target_name)
                    rss = ET.fromstring(requests.get(f"https://news.google.com/rss/search?q={enc}&hl=ko&gl=KR&ceid=KR:ko").content)
                    for item in rss.findall('.//item')[:5]:
                        st.markdown(f"🔹 **[{item.find('title').text}]({item.find('link').text})**")
                        st.caption(f"📅 {item.find('pubDate').text[:16]}")
                except: st.write("뉴스 로딩 실패")

        except Exception as e: st.error(f"데이터 분석 중 오류 발생: {e}")
