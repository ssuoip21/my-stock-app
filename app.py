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

# 1. 앱 기본 설정 및 테마
st.set_page_config(page_title="고급 주식 분석 리포트", layout="wide")
st.title("🚀 KIS 프로페셔널 주식 탐색기")

# 2. 보안 키 로드
try:
    APP_KEY = st.secrets["kis"]["app_key"]
    APP_SECRET = st.secrets["kis"]["app_secret"]
    ACC_NO = st.secrets["kis"]["acc_no"]
    ACC_NO_PS = st.secrets["kis"]["acc_no_ps"]
except Exception:
    st.error("Secrets 설정(app_key, app_secret 등)을 먼저 완료해 주세요.")
    st.stop()

# 3. 브로커 및 종목 사전 설정
@st.cache_resource
def get_broker():
    return mojito.KoreaInvestment(
        api_key=APP_KEY, api_secret=APP_SECRET,
        acc_no=f"{ACC_NO}-{ACC_NO_PS}", mock=False
    )

@st.cache_data(ttl=86400)
def get_stock_dict():
    # 주요 종목 사전 (필요시 더 추가 가능)
    return {
        "삼성전자": "005930", "SK하이닉스": "000660", "현대차": "005380",
        "화신정공": "126640", "코텍": "052330", "아비코전자": "036010",
        "에코프로": "086520", "셀트리온": "068270", "카카오": "035720"
    }

broker = get_broker()
STOCK_DICT = get_stock_dict()

# 4. 사이드바 컨트롤 패널
st.sidebar.header("⚙️ 분석 설정")

# [검색창]
user_input = st.sidebar.text_input("종목명 또는 코드", value="삼성전자")

# [차트 주기 선택]
timeframe = st.sidebar.radio("차트 주기", ("일봉", "주봉", "월봉"), index=0)
tf_code = {"일봉": "D", "주봉": "W", "월봉": "M"}[timeframe]

# [차트 색상 커스텀]
up_color = st.sidebar.color_picker("상승봉 색상", "#FF4136")
down_color = st.sidebar.color_picker("하락봉 색상", "#0074D9")

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
        all_names = list(STOCK_DICT.keys())
        matches = difflib.get_close_matches(user_input, all_names, n=1, cutoff=0.2)
        if matches:
            st.sidebar.info(f"💡 혹시 이 종목인가요?: **{matches[0]}**")
            if st.sidebar.button(f"{matches[0]} 분석 시작"):
                target_code = STOCK_DICT[matches[0]]
                target_name = matches[0]
        else:
            st.sidebar.error("종목을 찾을 수 없습니다.")

# 5. 메인 리포트 엔진
if target_code:
    with st.spinner(f"{target_name} 리포트를 생성 중입니다..."):
        try:
            # [데이터 수신]
            price_resp = broker.fetch_price(target_code)['output']
            curr_p = int(price_resp['stck_prpr'])
            
            # 과거 데이터 (드래그 기능을 위해 충분히 많은 120개 캔들을 가져옵니다)
            end_d = datetime.now().strftime("%Y%m%d")
            start_d = (datetime.now() - timedelta(days=500)).strftime("%Y%m%d")
            chart_res = broker.fetch_ohlcv(target_code, tf_code, start_d, end_d)['output2']
            
            df = pd.DataFrame(chart_res)
            df['date'] = pd.to_datetime(df['stck_bsop_date'])
            for col in ['stck_clpr', 'stck_oprc', 'stck_hgpr', 'stck_lwpr']:
                df[col] = pd.to_numeric(df[col])
            
            # 이동평균선 계산
            df['MA5'] = df['stck_clpr'].rolling(window=5).mean()
            df['MA20'] = df['stck_clpr'].rolling(window=20).mean()

            # --- 상단 현재가 정보 ---
            c1, c2, c3 = st.columns([2, 1, 1])
            with c1:
                st.subheader(f"🏷️ {target_name} ({target_code})")
            with c2:
                diff = int(price_resp['prdy_vrss'])
                rate = float(price_resp['prdy_ctrt'])
                st.metric("현재가", f"{curr_p:,}원", f"{diff:,}원 ({rate:+.2f}%)")
            with c3:
                st.write(f"**전일종가:** {int(price_resp['stck_sdpr']):,}원")
                st.write(f"**거래량:** {int(price_resp['acml_vol']):,}주")

            # --- 메인 인터랙티브 차트 ---
            st.markdown("---")
            st.write(f"### 📈 {timeframe} 기술적 분석")
            
            fig = go.Figure(data=[go.Candlestick(
                x=df['date'], open=df['stck_oprc'],
                high=df['stck_hgpr'], low=df['stck_lwpr'],
                close=df['stck_clpr'],
                increasing_line_color=up_color, decreasing_line_color=down_color,
                name='주가'
            )])
            
            # 지표 추가
            fig.add_trace(go.Scatter(x=df['date'], y=df['MA5'], name='5일선', line=dict(color='orange', width=1)))
            fig.add_trace(go.Scatter(x=df['date'], y=df['MA20'], name='20일선', line=dict(color='purple', width=1)))

            # 레이아웃 설정 (드래그 및 줌 가능)
            fig.update_layout(
                height=600,
                xaxis_rangeslider_visible=True, # 하단 슬라이더로 범위 조절
                xaxis_type='date',
                margin=dict(l=10, r=10, t=30, b=10),
                template='plotly_white'
            )
            st.plotly_chart(fig, use_container_width=True)

            # --- 수급 및 시나리오 (기존 기능 통합) ---
            tab1, tab2, tab3 = st.tabs(["📊 수급 동향", "🎯 AI 전략", "📰 최신 뉴스"])
            
            with tab1:
                try:
                    h = {'User-Agent': 'Mozilla/5.0'}
                    n_url = f"https://finance.naver.com/item/frgn.naver?code={target_code}"
                    n_res = requests.get(n_url, headers=h, timeout=5)
                    n_res.encoding = 'euc-kr'
                    rows = BeautifulSoup(n_res.text, 'html.parser').select('table.type2 tr')
                    t_html = '<table style="width:100%; border-collapse:collapse; text-align:center;">'
                    t_html += '<tr style="background:#f0f2f6;"><th>날짜</th><th>개인</th><th>외국인</th><th>기관</th></tr>'
                    count = 0
                    for r in rows:
                        tds = r.select('td')
                        if len(tds) == 9 and tds[0].text.strip():
                            fv = int(tds[6].text.strip().replace(',',''))
                            iv = int(tds[5].text.strip().replace(',',''))
                            pv = -(fv + iv)
                            def stl(v): return f'color:{"#FF4136" if v>0 else "#0074D9" if v<0 else "black"}'
                            t_html += f'<tr><td>{tds[0].text}</td><td style="{stl(pv)}">{pv:+,}</td><td style="{stl(fv)}">{fv:+,}</td><td style="{stl(iv)}">{iv:+,}</td></tr>'
                            count += 1
                            if count >= 10: break
                    st.markdown(t_html + '</table>', unsafe_allow_html=True)
                except:
                    st.warning("수급 데이터를 가져올 수 없습니다.")

            with tab2:
                volatility = df['stck_clpr'].pct_change().std()
                v_f = volatility * 100
                strat = {
                    "초단기 (3일)": [int(curr_p*0.99), int(curr_p*(1+0.02*v_f)), int(curr_p*0.97)],
                    "단기 (1개월)": [int(curr_p*0.97), int(curr_p*(1+0.05*v_f)), int(curr_p*0.93)],
                    "장기 (1년+)": [int(curr_p*0.90), int(curr_p*(1+0.30*v_f)), int(curr_p*0.75)]
                }
                st.table(pd.DataFrame(strat, index=["추천 매수가", "목표가", "손절가"]).style.format("{:,}원"))

            with tab3:
                # 구글 뉴스 RSS 연동
                try:
                    encoded_name = urllib.parse.quote(target_name)
                    rss_url = f"https://news.google.com/rss/search?q={encoded_name}&hl=ko&gl=KR&ceid=KR:ko"
                    root = ET.fromstring(requests.get(rss_url, timeout=5).content)
                    items = root.findall('.//item')[:8]
                    for item in items:
                        title = item.find('title').text
                        link = item.find('link').text
                        pub_date = item.find('pubDate').text[:16]
                        st.markdown(f"🔹 [{title}]({link}) <br> <small>{pub_date}</small>", unsafe_allow_html=True)
                except:
                    st.error("뉴스를 불러오지 못했습니다.")

        except Exception as e:
            st.error(f"분석 중 오류가 발생했습니다: {e}")
