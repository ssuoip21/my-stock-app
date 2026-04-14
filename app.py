import streamlit as st
import FinanceDataReader as fdr
import requests
from bs4 import BeautifulSoup
import plotly.graph_objects as go
from datetime import datetime, timedelta
import urllib.parse
import xml.etree.ElementTree as ET
import numpy as np
import pandas as pd
import difflib

# 1. 앱 기본 설정
st.set_page_config(page_title="주식 검색기", layout="wide")
st.title("📑 통합 보고서")

# [핵심] 상장사 전체 목록을 앱 내부에 구축하는 로직 (3중 우회)
@st.cache_data(ttl=86400) # 하루 단위로 캐시 업데이트
def load_all_stocks():
    stock_dict = {}
    
    # Plan A: FinanceDataReader 기본 로드 시도
    try:
        df = fdr.StockListing('KRX')
        if not df.empty and 'Name' in df.columns:
            for _, row in df.iterrows():
                stock_dict[row['Name']] = str(row['Code']).zfill(6)
            return stock_dict
    except:
        pass

    # Plan B: KIND 공시 포털 HTML 직접 파싱 (API가 아닌 엑셀 다운로드용 웹페이지 우회 접근)
    try:
        url = 'http://kind.krx.co.kr/corpgeneral/corpList.do?method=download&searchType=13'
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        res = requests.get(url, headers=headers, timeout=10)
        res.encoding = 'euc-kr' # KIND 서버 기본 인코딩
        soup = BeautifulSoup(res.text, 'html.parser')
        
        for tr in soup.find_all('tr'):
            tds = tr.find_all('td')
            if len(tds) >= 2:
                name = tds[0].text.strip()
                code = tds[1].text.strip()
                if code.isdigit():
                    stock_dict[name] = code.zfill(6)
        if stock_dict:
            return stock_dict
    except:
        pass

    # Plan C: 모든 연결이 차단되었을 때의 최소한의 작동 보장
    return {
        "삼성전자": "005930", "SK하이닉스": "000660", "현대차": "005380",
        "기아": "000270", "NAVER": "035420", "카카오": "035720", 
        "코텍": "052330", "아비코전자": "036010"
    }

# 전체 종목 딕셔너리 로드
stock_dict = load_all_stocks()

# 2. 사이드바: 지능형 검색창
st.sidebar.write("### 🔍 지능형 종목 검색")
st.sidebar.caption("종목명의 일부만 입력하거나 오타가 있어도 찾아줍니다.")
user_input = st.sidebar.text_input("종목명 또는 코드 입력", value="삼성전자")

if user_input:
    with st.spinner(f"'{user_input}' 종목을 찾고 있습니다..."):
        try:
            target_code = None
            target_name = None
            suggestions = []

            # 입력값이 6자리 숫자(코드)인 경우
            if user_input.isdigit() and len(user_input) == 6:
                target_code = user_input
                # 코드로 이름 역추적
                target_name = next((name for name, code in stock_dict.items() if code == target_code), user_input)
            
            # 입력값이 문자(이름)인 경우
            else:
                if user_input in stock_dict:
                    # 정확한 이름 매칭
                    target_code = stock_dict[user_input]
                    target_name = user_input
                else:
                    # 정확한 이름이 없을 때 유사 검색 (오타 교정 및 부분 일치)
                    all_names = list(stock_dict.keys())
                    partial_matches = [name for name in all_names if user_input in name]
                    close_matches = difflib.get_close_matches(user_input, all_names, n=5, cutoff=0.4)
                    
                    # 두 리스트를 합치고 중복 제거
                    suggestions = list(dict.fromkeys(partial_matches + close_matches))
                    
                    if suggestions:
                        st.sidebar.warning(f"⚠️ '{user_input}'과(와) 정확히 일치하는 종목이 없습니다.")
                        st.sidebar.info("💡 **아래 종목 중 하나를 찾으시나요?**\n\n" + "\n".join([f"- **{s}**" for s in suggestions[:7]]))
                    else:
                        st.sidebar.error("❌ 일치하거나 비슷한 종목명을 찾을 수 없습니다. (데이터 소스 오류일 수 있습니다)")

            # 정확한 종목 코드를 찾았을 때만 분석 시작
            if target_code:
                headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
                now = datetime.now()
                df_price = fdr.DataReader(target_code, now - timedelta(days=60), now)
                
                if not df_price.empty:
                    df_price['MA5'] = df_price['Close'].rolling(window=5).mean()
                    df_price['MA20'] = df_price['Close'].rolling(window=20).mean()
                    df_recent = df_price.tail(10)
                    volatility = df_price['Close'].pct_change().std()

                    current_p = int(df_recent['Close'].iloc[-1])
                    prev_p = int(df_recent['Close'].iloc[-2])
                    ma20_curr = df_recent['MA20'].iloc[-1]
                    
                    X = np.arange(len(df_recent))
                    y = df_recent['Close'].values
                    coef = np.polyfit(X, y, 1)
                    future_p = int(coef[0] * (len(df_recent) + 3) + coef[1])

                    if current_p > ma20_curr and future_p > current_p:
                        opinion = "AI 의견: **매수** - 추세 상단 안착 및 상승 에너지 관측"
                    elif current_p < ma20_curr and future_p < current_p:
                        opinion = "AI 의견: **매도** - 하방 압력 지속 및 지지선 이탈 주의"
                    else:
                        opinion = "AI 의견: **관망** - 방향성 결정 전 중립 흐름 유지"

                    # --- 화면 구성 ---
                    col1, col2 = st.columns([3, 1])
                    with col1:
                        st.subheader(f"📊 {target_name}({target_code}) 분석 차트")
                        x_dates = df_recent.index.strftime('%Y-%m-%d')
                        fig = go.Figure(data=[go.Candlestick(x=x_dates, open=df_recent['Open'], high=df_recent['High'], low=df_recent['Low'], close=df_recent['Close'], increasing_line_color='#FF4136', decreasing_line_color='#0074D9')])
                        fig.add_trace(go.Scatter(x=x_dates, y=df_recent['MA5'], name='5일선', line=dict(color='orange', width=1.5)))
                        fig.add_trace(go.Scatter(x=x_dates, y=df_recent['MA20'], name='20일선', line=dict(color='purple', width=1.5)))
                        fig.update_layout(xaxis_rangeslider_visible=False, height=450, xaxis_type='category')
                        st.plotly_chart(fig, use_container_width=True)
                    with col2:
                        st.subheader("💰 현재 정보")
                        delta_val = current_p - prev_p
                        st.metric(label="현재가", value=f"{current_p:,}원", delta=f"{delta_val:,}원")
                        st.divider()
                        st.info(f"💡 {opinion}")

                    # --- 표 스타일 지정 (가운데/우측 정렬 유지) ---
                    table_style = """
                    <style>
                        .custom-table { width: 100%; border-collapse: collapse; margin-bottom: 20px; border: 1px solid #ddd; }
                        .custom-table th, .custom-table td { border: 1px solid #ddd; padding: 12px; font-size: 14px; }
                        .custom-table th { background-color: #f0f2f6; font-weight: bold; text-align: center; }
                        .custom-table td.center-txt { text-align: center; }
                        .custom-table td.right-num { text-align: right; }
                        .custom-table tr:nth-child(even) { background-color: #fcfcfc; }
                    </style>
                    """
                    
                    st.divider()
                    st.subheader("📈 10거래일 투자자별 순매수 동향")
                    f_url = f"https://finance.naver.com/item/frgn.naver?code={target_code}"
                    f_res = requests.get(f_url, headers=headers); f_res.encoding = 'euc-kr'
                    rows = BeautifulSoup(f_res.text, 'html.parser').select('table.type2 tr')
                    s_html = table_style + '<table class="custom-table"><thead><tr><th>날짜</th><th>개인</th><th>외국인</th><th>기관</th></tr></thead><tbody>'
                    c = 0
                    for r in rows:
                        tds = r.select('td')
                        if len(tds) == 9 and tds[0].text.strip():
                            fv = int(tds[6].text.strip().replace(',',''))
                            iv = int(tds[5].text.strip().replace(',',''))
                            pv = -(fv + iv)
                            def stl(v): return f'color: {"#FF4136" if v>0 else "#0074D9" if v<0 else "black"}; font-weight: bold;'
                            s_html += f'<tr><td class="center-txt">{tds[0].text}</td><td class="right-num" style="{stl(pv)}">{pv:+,}</td><td class="right-num" style="{stl(fv)}">{fv:+,}</td><td class="right-num" style="{stl(iv)}">{iv:+,}</td></tr>'
                            c += 1
                            if c >= 10: break
                    st.markdown(s_html + "</tbody></table>", unsafe_allow_html=True)

                    st.divider()
                    st.subheader("📰 최신 주요 뉴스")
                    rss_url = f"https://news.google.com/rss/search?q={urllib.parse.quote(target_name)}&hl=ko&gl=KR&ceid=KR:ko"
                    root = ET.fromstring(requests.get(rss_url).content)
                    for i, item in enumerate(root.findall('.//item')[:5]):
                        st.markdown(f"{i+1}. [{item.find('title').text}]({item.find('link').text})")

                    st.divider()
                    st.subheader("🎯 AI 투자 전략 시나리오")
                    v_f = volatility * 100
                    strat = {
                        "3일 (초단기)": [int(current_p * 0.99), int(current_p * (1 + 0.02 * v_f)), int(current_p * 0.97)],
                        "1개월 (단기)": [int(current_p * 0.97), int(current_p * (1 + 0.05 * v_f)), int(current_p * 0.93)],
                        "1년+ (장기)": [int(current_p * 0.90), int(current_p * (1 + 0.30 * v_f)), int(current_p * 0.75)]
                    }
                    labels = ["매수가", "목표가", "손절가"]
                    a_html = table_style + '<table class="custom-table"><thead><tr><th>구분</th><th>3일 (초단기)</th><th>1개월 (단기)</th><th>1년+ (장기)</th></tr></thead><tbody>'
                    for i, label in enumerate(labels):
                        a_html += f"<tr><td class='center-txt'><b>{label}</b></td>"
                        for key in strat: a_html += f"<td class='right-num'>{strat[key][i]:,}원</td>"
                        a_html += "</tr>"
                    st.markdown(a_html + "</tbody></table>", unsafe_allow_html=True)
                else:
                    st.error("해당 종목의 가격 데이터를 불러올 수 없습니다. 일시적인 서버 통신 장애일 수 있습니다.")
        except Exception as e:
            st.error(f"⚠️ 데이터 처리 중 오류가 발생했습니다. (사유: {e})")
