import streamlit as st
import mojito
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta
import requests
from bs4 import BeautifulSoup
import urllib.parse
import xml.etree.ElementTree as ET
import numpy as np
import difflib

# 1. 앱 설정 (모바일 최적화 레이아웃)
st.set_page_config(page_title="스마트 주식 비서", layout="wide")

# 모바일 가독성을 위한 커스텀 스타일
st.markdown("""
    <style>
    .main .block-container { padding-top: 1.5rem; padding-bottom: 1rem; padding-left: 0.5rem; padding-right: 0.5rem; }
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
    # 실전투자계좌(mock=False) 연결
    return mojito.KoreaInvestment(
        api_key=APP_KEY, api_secret=APP_SECRET, 
        acc_no=f"{ACC_NO}-{ACC_NO_PS}", mock=False
    )

@st.cache_data(ttl=86400)
def get_stock_dict():
    return {
        "삼성전자": "005930", "SK하이닉스": "000660", "현대차": "005380",
        "기아": "000270", "NAVER": "035420", "카카오": "035720",
        "화신정공": "126640", "코텍": "052330", "아비코전자": "036010",
        "한미반도체": "042700", "에코프로": "086520", "셀트리온": "068270"
    }

broker = get_broker()
STOCK_DICT = get_stock_dict()

# 3. 사이드바 (설정)
st.sidebar.header("⚙️ 검색 및 설정")
user_input = st.sidebar.text_input("종목명 또는 코드", value="삼성전자")
timeframe = st.sidebar.radio("차트 주기", ("일봉", "주봉", "월봉"), horizontal=True)
tf_map = {"일봉": "D", "주봉": "W", "월봉": "M"}

up_color = st.sidebar.color_picker("상승 색상", "#FF4136")
down_color = st.sidebar.color_picker("하락 색상", "#0074D9")

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
        matches = difflib.get_close_matches(user_input, list(STOCK_DICT.keys()), n=1, cutoff=0.2)
        if matches:
            if st.sidebar.button(f"'{matches[0]}' 분석하기"):
                target_code = STOCK_DICT[matches[0]]
                target_name = matches[0]

# 4. 메인 리포트 시작
if target_code:
    with st.spinner(f"{target_name} 데이터 분석 중..."):
        try:
            # [A] 실시간 데이터
            price_resp = broker.fetch_price(target_code)['output']
            curr_p = int(price_resp['stck_prpr'])
            diff = int(price_resp['prdy_vrss'])
            rate = float(price_resp['prdy_ctrt'])
            
            # [B] 차트 데이터 수신 (과거 탐색을 위해 500일치 수집)
            end_d = datetime.now().strftime("%Y%m%d")
            start_d = (datetime.now() - timedelta(days=500)).strftime("%Y%m%d")
            chart_res = broker.fetch_ohlcv(target_code, tf_map[timeframe], start_d, end_d)['output2']
            
            df = pd.DataFrame(chart_res)
            df['date'] = pd.to_datetime(df['stck_bsop_date'])
            for col in ['stck_clpr', 'stck_oprc', 'stck_hgpr', 'stck_lwpr']:
                df[col] = pd.to_numeric(df[col])
            
            # 지표 계산
            df['MA5'] = df['stck_clpr'].rolling(window=5).mean()
            df['MA20'] = df['stck_clpr'].rolling(window=20).mean()

            # [C] Y축 가변 범위 및 초기 10일 줌 설정
            view_limit = df.tail(30) # 최근 30일 데이터 기준 스케일링
            min_y = view_limit['stck_lwpr'].min()
            max_y = view_limit['stck_hgpr'].max()
            y_margin = (max_y - min_y) * 0.05
            y_range = [min_y - y_margin, max_y + y_margin]

            last_date = df['date'].iloc[-1]
            zoom_start_date = df['date'].iloc[-10] if len(df) >= 10 else df['date'].iloc[0]

            # --- 화면 레이아웃 ---
            st.write(f"### 📈 {target_name} ({target_code})")
            
            m1, m2 = st.columns(2)
            m1.metric("현재가", f"{curr_p:,}원", f"{diff:,}원 ({rate:+.2f}%)")
            m2.write(f"**거래량:** {int(price_resp['acml_vol']):,}주")

            # --- 인터랙티브 차트 ---
            fig = go.Figure(data=[go.Candlestick(
                x=df['date'], open=df['stck_oprc'], high=df['stck_hgpr'],
                low=df['stck_lwpr'], close=df['stck_clpr'],
                increasing_line_color=up_color, decreasing_line_color=down_color,
                name='주가'
            )])
            fig.add_trace(go.Scatter(x=df['date'], y=df['MA5'], name='5일선', line=dict(color='orange', width=1)))
            fig.add_trace(go.Scatter(x=df['date'], y=df['MA20'], name='20일선', line=dict(color='purple', width=1)))
            
            fig.update_layout(
                height=480,
                template='plotly_white',
                margin=dict(l=0, r=0, t=10, b=0),
                yaxis=dict(
                    range=y_range, fixedrange=False, side='right', 
                    showgrid=True, gridcolor='#f0f0f0'
                ),
                xaxis=dict(
                    range=[zoom_start_date, last_date + timedelta(days=1)],
                    rangeslider_visible=False, type='date'
                ),
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
            )
            st.plotly_chart(fig, use_container_width=True, config={'scrollZoom': True, 'displayModeBar': False})

            # --- 하단 상세 정보 (탭) ---
            st.divider()
            tab1, tab2, tab3 = st.tabs(["📊 수급동향", "📰 뉴스피드", "🎯 투자전략"])
            
            with tab1:
                try:
                    h = {'User-Agent': 'Mozilla/5.0'}
                    n_url = f"https://finance.naver.com/item/frgn.naver?code={target_code}"
                    n_res = requests.get(n_url, headers=h, timeout=5)
                    n_res.encoding = 'euc-kr'
                    rows = BeautifulSoup(n_res.text, 'html.parser').select('table.type2 tr')
                    t_html = '<div style="overflow-x:auto;"><table style="width:100%; border-collapse:collapse; font-size:12px; text-align:center;">'
                    t_html += '<tr style="background:#f8f9fa;"><th>날짜</th><th>개인</th><th>외인</th><th>기관</th></tr>'
                    count = 0
                    for r in rows:
                        tds = r.select('td')
                        if len(tds) == 9 and tds[0].text.strip():
                            fv, iv = int(tds[6].text.strip().replace(',','')), int(tds[5].text.strip().replace(',',''))
                            pv = -(fv + iv)
                            def s(v): return f'color:{"#FF4136" if v>0 else "#0074D9" if v<0 else "black"}'
                            t_html += f'<tr><td>{tds[0].text[5:]}</td><td style="{s(pv)}">{pv:+,}</td><td style="{s(fv)}">{fv:+,}</td><td style="{s(iv)}">{iv:+,}</td></tr>'
                            count += 1
                            if count >= 7: break
                    st.markdown(t_html + '</table></div>', unsafe_allow_html=True)
                except: st.write("수급 데이터 일시 오류")

            with tab2:
                try:
                    enc_name = urllib.parse.quote(target_name)
                    rss_url = f"https://news.google.com/rss/search?q={enc_name}&hl=ko&gl=KR&ceid=KR:ko"
                    root = ET.fromstring(requests.get(rss_url).content)
                    for item in root.findall('.//item')[:6]:
                        st.markdown(f"🔹 [{item.find('title').text}]({item.find('link').text})")
                except: st.write("뉴스를 불러올 수 없습니다.")

            with tab3:
                volatility = df['stck_clpr'].pct_change().std()
                v_f = volatility * 100
                st.write(f"**현재 변동성:** {v_f:.2f}%")
                strat = {
                    "단기전략": [int(curr_p*(1+0.05*v_f)), int(curr_p*0.96)],
                    "중장기": [int(curr_p*(1+0.20*v_f)), int(curr_p*0.85)]
                }
                for k, v in strat.items():
                    st.info(f"📍 **{k}** | 목표가: {v[0]:,}원 / 손절가: {v[1]:,}원")

        except Exception as e:
            st.error(f"데이터 수신 중 오류 발생: {e}")
