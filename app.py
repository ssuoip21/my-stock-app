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

# 1. 앱 설정 및 보안 키 로드
st.set_page_config(page_title="프리미엄 주식 분석 리포트", layout="wide")
st.title("🚀 KIS 실시간 종합 분석 리포트")

try:
    APP_KEY = st.secrets["kis"]["app_key"]
    APP_SECRET = st.secrets["kis"]["app_secret"]
    ACC_NO = st.secrets["kis"]["acc_no"]
    ACC_NO_PS = st.secrets["kis"]["acc_no_ps"]
except Exception:
    st.error("Secrets 설정(app_key, app_secret 등)을 확인해 주세요.")
    st.stop()

# 2. [지능형 엔진] 종목 사전 및 API 연결
@st.cache_resource
def get_broker():
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

# 3. 사이드바 컨트롤 패널
st.sidebar.write("### ⚙️ 설정 및 검색")

# [종목 검색]
user_input = st.sidebar.text_input("종목명 또는 코드 입력", value="삼성전자")

# [차트 주기 선택]
timeframe = st.sidebar.radio("차트 주기 선택", ("일봉", "주봉", "월봉"), index=0)
tf_map = {"일봉": "D", "주봉": "W", "월봉": "M"}

# [차트 색상 선택]
up_color = st.sidebar.color_picker("상승봉 색상", "#FF4136")
down_color = st.sidebar.color_picker("하락봉 색상", "#0074D9")

target_code = None
target_name = None

if user_input:
    if user_input.isdigit() and len(user_input) == 6:
        target_code = user_input
        target_name = next((n for n, c in STOCK_DICT.items() if c == target_code), user_input)
    elif user_input in STOCK_DICT:
        target_code = STOCK_DICT[user_input]
        target_name = user_input
    else:
        all_names = list(STOCK_DICT.keys())
        matches = difflib.get_close_matches(user_input, all_names, n=3, cutoff=0.2)
        if matches:
            st.sidebar.info(f"💡 혹시 이 종목인가요? : **{matches[0]}**")
            if st.sidebar.button(f"{matches[0]} 분석하기"):
                target_code = STOCK_DICT[matches[0]]
                target_name = matches[0]
        else:
            st.sidebar.error("일치하는 종목이 없습니다.")

# 4. 메인 분석 리포트
if target_code:
    with st.spinner(f"{target_name} 데이터를 정밀 분석 중..."):
        try:
            # [A] 실시간 시세 정보
            price_data = broker.fetch_price(target_code)['output']
            curr_p = int(price_data['stck_prpr'])
            diff = int(price_data['prdy_vrss'])
            rate = float(price_data['prdy_ctrt'])
            
            # [B] 차트 데이터 (드래그를 위해 약 2년치 넉넉히 수집)
            end_d = datetime.now().strftime("%Y%m%d")
            start_d = (datetime.now() - timedelta(days=730)).strftime("%Y%m%d")
            chart_res = broker.fetch_ohlcv(target_code, tf_map[timeframe], start_d, end_d)['output2']
            
            df = pd.DataFrame(chart_res)
            df['date'] = pd.to_datetime(df['stck_bsop_date'])
            for col in ['stck_clpr', 'stck_oprc', 'stck_hgpr', 'stck_lwpr']:
                df[col] = pd.to_numeric(df[col])
            
            # 지표 계산
            df['MA5'] = df['stck_clpr'].rolling(window=5).mean()
            df['MA20'] = df['stck_clpr'].rolling(window=20).mean()
            
            # [C] 화면 상단 요약
            col1, col2, col3 = st.columns([2, 1, 1])
            with col1:
                st.subheader(f"📊 {target_name}({target_code}) {timeframe}")
            with col2:
                st.metric("현재가", f"{curr_p:,}원", f"{diff:,}원 ({rate:+.2f}%)")
            with col3:
                st.write(f"**거래량:** {int(price_data['acml_vol']):,}주")

            # --- [인터랙티브 차트 섹션] ---
            # 하단에 범위를 조절할 수 있는 Range Slider 추가 (드래그 가능)
            fig = go.Figure(data=[go.Candlestick(
                x=df['date'], open=df['stck_oprc'],
                high=df['stck_hgpr'], low=df['stck_lwpr'],
                close=df['stck_clpr'],
                increasing_line_color=up_color, 
                decreasing_line_color=down_color,
                name='주가'
            )])
            fig.add_trace(go.Scatter(x=df['date'], y=df['MA5'], name='5일선', line=dict(color='orange', width=1.2)))
            fig.add_trace(go.Scatter(x=df['date'], y=df['MA20'], name='20일선', line=dict(color='purple', width=1.2)))
            
            fig.update_layout(
                xaxis_rangeslider_visible=True, # 하단 드래그 바 활성화
                height=600,
                xaxis_type='date',
                template='plotly_white',
                margin=dict(l=10, r=10, t=30, b=10)
            )
            st.plotly_chart(fig, use_container_width=True)

            # --- [탭 하단 상세 분석] ---
            tab1, tab2, tab3 = st.tabs(["📊 수급 및 전략", "📰 최신 뉴스", "🎯 AI 시나리오"])
            
            with tab1:
                # 수급 동향
                st.write("#### 📈 투자자별 순매수 동향 (최근 10일)")
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
                # 구글 뉴스 RSS 활용 (안정적)
                st.write(f"#### 📰 {target_name} 관련 최신 뉴스")
                try:
                    enc_name = urllib.parse.quote(target_name)
                    rss_url = f"https://news.google.com/rss/search?q={enc_name}&hl=ko&gl=KR&ceid=KR:ko"
                    res = requests.get(rss_url)
                    root = ET.fromstring(res.content)
                    
                    for item in root.findall('.//item')[:8]: # 뉴스 8개 출력
                        title = item.find('title').text
                        link = item.find('link').text
                        pub_date = item.find('pubDate').text[:16]
                        st.markdown(f"🔹 **[{title}]({link})**")
                        st.caption(f"게시일: {pub_date}")
                        st.write("")
                except:
                    st.error("뉴스를 불러오는 데 실패했습니다.")

            with tab3:
                volatility = df['stck_clpr'].pct_change().std()
                v_f = volatility * 100
                strat = {
                    "초단기 (3일)": [int(curr_p*0.99), int(curr_p*(1+0.02*v_f)), int(curr_p*0.97)],
                    "단기 (1개월)": [int(curr_p*0.97), int(curr_p*(1+0.05*v_f)), int(curr_p*0.93)],
                    "장기 (1년+)": [int(curr_p*0.90), int(curr_p*(1+0.30*v_f)), int(curr_p*0.75)]
                }
                s_df = pd.DataFrame(strat, index=["추천 매수가", "목표가", "손절가"])
                st.table(s_df.style.format("{:,}원"))

        except Exception as e:
            st.error(f"분석 중 오류가 발생했습니다: {e}")
