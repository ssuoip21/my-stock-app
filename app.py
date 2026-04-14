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

# 1. 앱 기본 설정
st.set_page_config(page_title="주식 검색기", layout="wide")
st.title("📑 통합 보고서")

# [개선] 거래소 종목 리스트를 미리 불러와서 캐싱합니다 (속도 향상)
@st.cache_data(ttl=86400) # 하루 동안 저장
def load_stock_list():
    try:
        # KRX, KOSPI, KOSDAQ 종목 전체 리스트
        return fdr.StockListing('KRX')[['Code', 'Name']]
    except:
        return pd.DataFrame()

df_stock_list = load_stock_list()

# 2. 사이드바: 종목명 또는 코드 입력
st.sidebar.write("### 🔍 종목 검색")
user_input = st.sidebar.text_input("종목명(예: 삼성전자) 또는 코드(005930)를 입력하세요", value="삼성전자")

if user_input:
    with st.spinner(f"'{user_input}'의 데이터를 분석 중입니다..."):
        try:
            target_code = None
            target_name = None

            # [핵심 로직] 입력값이 코드인지 이름인지 판단
            if user_input.isdigit() and len(user_input) == 6:
                # 6자리 숫자라면 코드로 간주
                target_code = user_input
                # 이름 찾기 시도
                match = df_stock_list[df_stock_list['Code'] == target_code]
                target_name = match['Name'].values[0] if not match.empty else target_code
            else:
                # 이름으로 간주하고 코드 찾기 시도
                match = df_stock_list[df_stock_list['Name'] == user_input]
                if not match.empty:
                    target_code = match['Code'].values[0]
                    target_name = user_input
                else:
                    st.sidebar.warning("⚠️ 정확한 종목명을 찾을 수 없습니다.")

            if target_code:
                headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
                now = datetime.now()
                
                # 데이터 수집
                df_price = fdr.DataReader(target_code, now - timedelta(days=60), now)
                
                if not df_price.empty:
                    # 지표 계산
                    df_price['MA5'] = df_price['Close'].rolling(window=5).mean()
                    df_price['MA20'] = df_price['Close'].rolling(window=20).mean()
                    df_recent = df_price.tail(10)
                    volatility = df_price['Close'].pct_change().std()

                    current_p = int(df_recent['Close'].iloc[-1])
                    prev_p = int(df_recent['Close'].iloc[-2])
                    ma20_curr = df_recent['MA20'].iloc[-1]
                    
                    # AI 예측 (단기)
                    X = np.arange(len(df_recent))
                    y = df_recent['Close'].values
                    coef = np.polyfit(X, y, 1)
                    future_p = int(coef[0] * (len(df_recent) + 3) + coef[1])

                    # AI 투자 의견
                    if current_p > ma20_curr and future_p > current_p:
                        opinion_text = "AI 의견: **매수** - 추세 상단 안착 및 상승 에너지 관측"
                    elif current_p < ma20_curr and future_p < current_p:
                        opinion_text = "AI 의견: **매도** - 하방 압력 지속 및 지지선 이탈 주의"
                    else:
                        opinion_text = "AI 의견: **관망** - 방향성 결정 전 중립 흐름 유지"

                    # --- 화면 레이아웃 ---
                    col1, col2 = st.columns([3, 1])
                    with col1:
                        st.subheader(f"📊 {target_name}({target_code}) 분석 차트")
                        x_dates = df_recent.index.strftime('%Y-%m-%d')
                        fig = go.Figure()
                        fig.add_trace(go.Candlestick(x=x_dates, open=df_recent['Open'], high=df_recent['High'], low=df_recent['Low'], close=df_recent['Close'], name='주가', increasing_line_color='#FF4136', decreasing_line_color='#0074D9'))
                        fig.add_trace(go.Scatter(x=x_dates, y=df_recent['MA5'], name='5일선', line=dict(color='orange', width=1.5)))
                        fig.add_trace(go.Scatter(x=x_dates, y=df_recent['MA20'], name='20일선', line=dict(color='purple', width=1.5)))
                        fig.update_layout(xaxis_rangeslider_visible=False, height=450, xaxis_type='category', margin=dict(l=10, r=10, t=10, b=10))
                        st.plotly_chart(fig, use_container_width=True)

                    with col2:
                        st.subheader("💰 현재 정보")
                        change = current_p - prev_p
                        change_percent = (change / prev_p) * 100
                        st.metric(label="현재가", value=f"{current_p:,}원", delta=f"{change:,}원 ({change_percent:+.2f}%)")
                        st.write(f"최종 업데이트: {now.strftime('%Y-%m-%d %H:%M:%S')}")
                        st.divider()
                        st.info(f"💡 {opinion_text}")

                    # --- 하단 표 디자인 (중앙/우측 정렬) ---
                    table_style = """
                    <style>
                        .custom-table { width: 100%; border-collapse: collapse; margin-bottom: 20px; border: 1px solid #ddd; }
                        .custom-table th, .custom-table td { border: 1px solid #ddd; padding: 12px; text-align: left; font-size: 14px; }
                        .custom-table th { background-color: #f0f2f6; font-weight: bold; text-align: center; }
                        .custom-table td.center-txt { text-align: center; }
                        .custom-table td.right-num { text-align: right; }
                        .custom-table tr:nth-child(even) { background-color: #fcfcfc; }
                    </style>
                    """

                    st.divider()
                    st.subheader("📈 10거래일 투자자별 순매수 동향")
                    frgn_url = f"https://finance.naver.com/item/frgn.naver?code={target_code}"
                    frgn_res = requests.get(frgn_url, headers=headers); frgn_res.encoding = 'euc-kr'
                    rows = BeautifulSoup(frgn_res.text, 'html.parser').select('table.type2 tr')
                    s_html = table_style + '<table class="custom-table"><thead><tr><th>날짜</th><th>개인</th><th>외국인</th><th>기관</th></tr></thead><tbody>'
                    count = 0
                    for row in rows:
                        cols = row.select('td')
                        if len(cols) == 9 and cols[0].text.strip():
                            fv = int(cols[6].text.strip().replace(',',''))
                            iv = int(cols[5].text.strip().replace(',',''))
                            pv = -(fv + iv)
                            def style(v): return f'color: {"#FF4136" if v>0 else "#0074D9" if v<0 else "black"}; font-weight: bold;'
                            s_html += f'<tr><td class="center-txt">{cols[0].text.strip()}</td><td class="right-num" style="{style(pv)}">{pv:+,}</td><td class="right-num" style="{style(fv)}">{fv:+,}</td><td class="right-num" style="{style(iv)}">{iv:+,}</td></tr>'
                            if count >= 9: break
                            count += 1
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
                    st.warning("데이터를 가져올 수 없는 종목입니다.")
        except Exception as e:
            st.error(f"데이터를 불러오는 중 문제가 발생했습니다. (오류: {e})")
