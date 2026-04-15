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
st.set_page_config(page_title="가족 주식 비서 Pro", layout="wide")

st.markdown("""
    <style>
    .main .block-container { padding-top: 1rem; padding-bottom: 1rem; padding-left: 0.5rem; padding-right: 0.5rem; }
    /* 다크모드/라이트모드 자동 대응 박스 스타일 */
    div[data-testid="stMetric"] { 
        padding: 10px; border-radius: 12px; 
        border: 1px solid rgba(128, 128, 128, 0.2);
        background-color: rgba(128, 128, 128, 0.05);
    }
    /* 별표 버튼 스타일 */
    .stButton>button { border-radius: 20px; }
    </style>
    """, unsafe_allow_html=True)

# 2. 세션 상태 초기화 (관심종목 저장용)
if 'favorites' not in st.session_state:
    st.session_state.favorites = set(["삼성전자", "SK하이닉스"])

# 3. 보안 키 로드 및 API 연결
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

# 4. 분석 엔진 (데이터 수집 및 보조지표 계산)
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
    
    # 지표 계산
    df['MA5'] = df['stck_clpr'].rolling(window=5).mean()
    df['MA20'] = df['stck_clpr'].rolling(window=20).mean()
    df['std'] = df['stck_clpr'].rolling(window=20).std()
    df['Upper_BB'] = df['MA20'] + (df['std'] * 2)
    df['Lower_BB'] = df['MA20'] - (df['std'] * 2)
    
    # RSI
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

# 5. 화면 레이아웃
st.write("### ⭐ 나만의 관심 종목")
fav_cols = st.columns(5)
selected_stock = None
for i, fav in enumerate(list(st.session_state.favorites)[:5]):
    with fav_cols[i]:
        if st.button(f"📌 {fav}", use_container_width=True):
            selected_stock = fav

with st.expander("🔍 종목 검색 및 설정", expanded=(selected_stock is None)):
    col1, col2 = st.columns([2, 1])
    with col1:
        search_input = st.text_input("종목명 입력", value=selected_stock if selected_stock else "삼성전자")
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

# 6. 메인 분석창
if target_code:
    # 별표 토글 버튼
    is_fav = target_name in st.session_state.favorites
    if st.button("⭐ 관심종목 추가/해제", type="primary" if is_fav else "secondary"):
        if is_fav: st.session_state.favorites.remove(target_name)
        else: st.session_state.favorites.add(target_name)
        st.rerun()

    with st.spinner("AI 분석 리포트 생성 중..."):
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
        y_range = [view['Lower_BB'].min()*0.98, view['Upper_BB'].max()*1.02]
        fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.03, row_heights=[0.7, 0.3])
        fig.add_trace(go.Candlestick(x=df['date_str'], open=df['stck_oprc'], high=df['stck_hgpr'], low=df['stck_lwpr'], close=df['stck_clpr'], increasing_line_color=up_color, decreasing_line_color=down_color, name='주가'), row=1, col=1)
        fig.add_trace(go.Scatter(x=df['date_str'], y=df['MA20'], name='20일선', line=dict(color='purple', width=1)), row=1, col=1)
        fig.add_trace(go.Scatter(x=df['date_str'], y=df['Upper_BB'], line=dict(color='rgba(173,216,230,0.2)'), showlegend=False), row=1, col=1)
        fig.add_trace(go.Scatter(x=df['date_str'], y=df['Lower_BB'], line=dict(color='rgba(173,216,230,0.2)'), fill='tonexty', fillcolor='rgba(173,216,230,0.05)', showlegend=False), row=1, col=1)
        vol_colors = np.where(df['stck_clpr'] >= df['stck_oprc'], up_color, down_color)
        fig.add_trace(go.Bar(x=df['date_str'], y=df['acml_vol'], marker_color=vol_colors, name='거래량'), row=2, col=1)
        fig.update_layout(height=500, template='plotly_white', margin=dict(l=0, r=0, t=10, b=0), dragmode='pan', yaxis=dict(range=y_range, side='right'), paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
        fig.update_xaxes(type='category', range=[len(df)-30, len(df)], rangeslider_visible=False)
        st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})

        # 하단 분석 탭
        t1, t2, t3 = st.tabs(["🎯 투자 전략 & AI 진단", "🔬 기술 지표 설명", "📰 뉴스"])
        
        with t1:
            volatility = df['stck_clpr'].pct_change().std() * 100
            strat = {
                "목표가 (1차)": [int(curr_p*(1+0.05))],
                "목표가 (2차)": [int(curr_p*(1+0.12))],
                "손절가": [int(curr_p*0.94)]
            }
            st.table(pd.DataFrame(strat, index=["추천 가격"]).style.format("{:,}원"))
            
            # AI 종합 판단 로직
            rsi = df['RSI'].iloc[-1]
            per_val = float(fund['PER'].replace(',','')) if fund['PER'] != 'N/A' else 20
            
            st.subheader("🤖 AI 종합 분석 결과")
            analysis_text = f"**{target_name}**에 대한 종합 진단입니다. "
            if rsi > 70: analysis_text += "현재 RSI가 70을 초과하여 단기적 과열 구간에 진입했습니다. 신규 매수는 신중해야 합니다. "
            elif rsi < 30: analysis_text += "RSI가 30 미만으로 과매도 상태입니다. 기술적 반등 가능성이 높습니다. "
            else: analysis_text += "수급 강도는 정상 범위 내에 있습니다. "
            
            if per_val < 10: analysis_text += "밸류에이션(PER) 측면에서 매우 저평가되어 있어 장기 투자 매력이 높습니다. "
            
            bb_width = (df['Upper_BB'].iloc[-1] - df['Lower_BB'].iloc[-1]) / df['MA20'].iloc[-1]
            if bb_width < 0.05: analysis_text += "볼린저 밴드 폭이 매우 좁아졌습니다. 곧 큰 변동성이 예상되니 주의 깊게 관찰하세요."
            
            st.info(analysis_text)

        with t2:
            st.write("#### 📖 초보자를 위한 용어 사전")
            st.write("**PER/PBR:** 기업 가치 대비 주가 수준 (낮을수록 저평가)")
            st.write("**RSI:** 현재 매수세가 강한지(70↑) 매도세가 강한지(30↓) 측정")
            st.write("**볼린저 밴드:** 주가가 이동하는 통로 (좁아지면 폭발적 움직임의 전조)")

        with t3:
            try:
                enc = urllib.parse.quote(target_name)
                rss = ET.fromstring(requests.get(f"https://news.google.com/rss/search?q={enc}&hl=ko&gl=KR&ceid=KR:ko").content)
                for item in rss.findall('.//item')[:5]:
                    st.markdown(f"🔹 **[{item.find('title').text}]({item.find('link').text})**")
                    st.caption(f"📅 {item.find('pubDate').text[:16]}")
            except: st.write("뉴스 로딩 실패")

except Exception as e: st.error(f"오류 발생: {e}")
