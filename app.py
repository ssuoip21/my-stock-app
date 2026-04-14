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

# 1. 앱 설정 (모바일에서 여백을 최소화하기 위해 레이아웃 조정)
st.set_page_config(page_title="모바일 주식 비서", layout="wide")

# 모바일용 스타일 시트 (글자 크기 및 여백 조정)
st.markdown("""
    <style>
    .main .block-container { padding-top: 2rem; padding-bottom: 2rem; padding-left: 1rem; padding-right: 1rem; }
    div[data-testid="stMetric"] { background-color: #f8f9fa; padding: 10px; border-radius: 10px; }
    </style>
    """, unsafe_allow_html=True)

st.title("📱 실시간 주식 분석")

# 2. 보안 키 로드
try:
    APP_KEY = st.secrets["kis"]["app_key"]
    APP_SECRET = st.secrets["kis"]["app_secret"]
    ACC_NO = st.secrets["kis"]["acc_no"]
    ACC_NO_PS = st.secrets["kis"]["acc_no_ps"]
except Exception:
    st.error("Secrets 설정을 확인해 주세요.")
    st.stop()

# 3. KIS 연결 및 종목 사전
@st.cache_resource
def get_broker():
    return mojito.KoreaInvestment(api_key=APP_KEY, api_secret=APP_SECRET, acc_no=f"{ACC_NO}-{ACC_NO_PS}", mock=False)

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

# 4. 사이드바 (모바일에서는 자동으로 접힙니다)
st.sidebar.header("⚙️ 옵션")
user_input = st.sidebar.text_input("종목명/코드", value="삼성전자")
timeframe = st.sidebar.radio("주기", ("일봉", "주봉", "월봉"), horizontal=True)
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
        matches = difflib.get_close_matches(user_input, list(STOCK_DICT.keys()), n=1, cutoff=0.2)
        if matches:
            if st.sidebar.button(f"'{matches[0]}' 분석"):
                target_code = STOCK_DICT[matches[0]]
                target_name = matches[0]

# 5. 메인 리포트
if target_code:
    with st.spinner("분석 중..."):
        try:
            # 실시간 데이터
            price_resp = broker.fetch_price(target_code)['output']
            curr_p = int(price_resp['stck_prpr'])
            diff = int(price_resp['prdy_vrss'])
            rate = float(price_resp['prdy_ctrt'])
            
            # 차트 데이터 수신 (넉넉히 가져오되 보여주는 건 10일치)
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

            # --- 모바일 최적화 레이아웃 (세로 배치) ---
            st.write(f"### {target_name} ({target_code})")
            
            # 지표를 가로로 배치 (모바일에서는 자동으로 위아래로 쌓임)
            m1, m2 = st.columns(2)
            m1.metric("현재가", f"{curr_p:,}원", f"{diff:,}원 ({rate:+.2f}%)")
            m2.write(f"**거래량:** {int(price_resp['acml_vol']):,}주")

            # --- 인터랙티브 차트 (최근 10일 초기 줌 설정) ---
            # 최근 10거래일 날짜 범위 계산
            last_date = df['date'].iloc[-1]
            # 인덱스를 사용하여 최근 10번째 데이터의 날짜 찾기
            zoom_start_date = df['date'].iloc[-10] if len(df) >= 10 else df['date'].iloc[0]

            fig = go.Figure(data=[go.Candlestick(
                x=df['date'], open=df['stck_oprc'], high=df['stck_hgpr'],
                low=df['stck_lwpr'], close=df['stck_clpr'],
                increasing_line_color='#FF4136', decreasing_line_color='#0074D9',
                name='주가'
            )])
            fig.add_trace(go.Scatter(x=df['date'], y=df['MA5'], name='5일선', line=dict(color='orange', width=1)))
            fig.add_trace(go.Scatter(x=df['date'], y=df['MA20'], name='20일선', line=dict(color='purple', width=1)))
            
            fig.update_layout(
                height=450, # 모바일에서 한 화면에 차트가 다 보이도록 높이 조절
                xaxis_rangeslider_visible=False, # 모바일 공간 확보를 위해 하단 슬라이더 제거 (드래그는 가능)
                # [핵심] 최근 10일치만 보이도록 범위 설정
                xaxis=dict(range=[zoom_start_date, last_date + timedelta(days=1)]),
                margin=dict(l=0, r=0, t=10, b=0),
                template='plotly_white'
            )
            # 모바일에서 두 손가락 줌 대신 한 손가락 드래그가 잘 되도록 설정
            st.plotly_chart(fig, use_container_width=True, config={'scrollZoom': True})

            # --- 상세 정보 탭 ---
            st.divider()
            tab1, tab2, tab3 = st.tabs(["📊 수급", "📰 뉴스", "🎯 전략"])
            
            with tab1:
                # 수급 데이터 (표 형태로 간소화)
                try:
                    h = {'User-Agent': 'Mozilla/5.0'}
                    n_url = f"https://finance.naver.com/item/frgn.naver?code={target_code}"
                    n_res = requests.get(n_url, headers=h, timeout=5)
                    n_res.encoding = 'euc-kr'
                    rows = BeautifulSoup(n_res.text, 'html.parser').select('table.type2 tr')
                    t_html = '<div style="overflow-x:auto;"><table style="width:100%; border-collapse:collapse; font-size:12px; text-align:center;">'
                    t_html += '<tr style="background:#f0f2f6;"><th>날짜</th><th>개인</th><th>외인</th><th>기관</th></tr>'
                    count = 0
                    for r in rows:
                        tds = r.select('td')
                        if len(tds) == 9 and tds[0].text.strip():
                            fv, iv = int(tds[6].text.strip().replace(',','')), int(tds[5].text.strip().replace(',',''))
                            pv = -(fv + iv)
                            def s(v): return f'color:{"red" if v>0 else "blue" if v<0 else "black"}'
                            t_html += f'<tr><td>{tds[0].text[5:]}</td><td style="{s(pv)}">{pv:+,}</td><td style="{s(fv)}">{fv:+,}</td><td style="{s(iv)}">{iv:+,}</td></tr>'
                            count += 1
                            if count >= 7: break
                    st.markdown(t_html + '</table></div>', unsafe_allow_html=True)
                except: st.write("수급 로드 실패")

            with tab2:
                # 뉴스 (모바일 가독성을 위해 간결하게)
                try:
                    enc_name = urllib.parse.quote(target_name)
                    rss_url = f"https://news.google.com/rss/search?q={enc_name}&hl=ko&gl=KR&ceid=KR:ko"
                    root = ET.fromstring(requests.get(rss_url).content)
                    for item in root.findall('.//item')[:5]:
                        st.markdown(f"📍 [{item.find('title').text}]({item.find('link').text})")
                except: st.write("뉴스 로드 실패")

            with tab3:
                # AI 시나리오
                volatility = df['stck_clpr'].pct_change().std()
                v_f = volatility * 100
                strat = {
                    "단기": [int(curr_p*(1+0.05*v_f)), int(curr_p*0.95)],
                    "장기": [int(curr_p*(1+0.25*v_f)), int(curr_p*0.80)]
                }
                for k, v in strat.items():
                    st.write(f"**{k} 목표:** {v[0]:,}원 / **손절:** {v[1]:,}원")

        except Exception as e:
            st.error(f"오류: {e}")
