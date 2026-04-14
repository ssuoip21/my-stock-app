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

# [개선] 종목 리스트 로드 및 에러 방지 로직
@st.cache_data(ttl=3600)
def load_stock_list():
    try:
        df = fdr.StockListing('KRX')
        if df is not None and not df.empty and 'Name' in df.columns:
            return df[['Code', 'Name']]
        return pd.DataFrame(columns=['Code', 'Name'])
    except:
        return pd.DataFrame(columns=['Code', 'Name'])

df_stock_list = load_stock_list()

# 2. 사이드바 검색
st.sidebar.write("### 🔍 종목 검색")
user_input = st.sidebar.text_input("종목명(예: 삼성전자) 또는 코드(005930)를 입력하세요", value="삼성전자")

if user_input:
    with st.spinner(f"'{user_input}'의 데이터를 분석 중입니다..."):
        try:
            target_code = None
            target_name = None

            # 입력값이 6자리 숫자(코드)인 경우
            if user_input.isdigit() and len(user_input) == 6:
                target_code = user_input
                if not df_stock_list.empty:
                    match = df_stock_list[df_stock_list['Code'] == target_code]
                    target_name = match['Name'].values[0] if not match.empty else target_code
                else:
                    target_name = target_code
            
            # 입력값이 이름인 경우
            else:
                if not df_stock_list.empty:
                    match = df_stock_list[df_stock_list['Name'] == user_input]
                    if not match.empty:
                        target_code = match['Code'].values[0]
                        target_name = user_input
                    else:
                        st.sidebar.warning(f"⚠️ '{user_input}'을(를) 찾을 수 없습니다. 정확한 명칭인지 확인해 주세요.")
                else:
                    st.sidebar.error("❌ 현재 거래소 서버 연결이 원활하지 않아 이름 검색이 어렵습니다. '005930'과 같은 숫자로 된 코드를 입력해 주세요.")

            # 분석 시작
            if target_code:
                headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
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
                    
                    # AI 투자 의견 계산
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

                    # --- 표 스타일 및 하단 데이터 ---
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

        except Exception as e:
            st.error(f"⚠️ 데이터를 불러오는 중 일시적인 문제가 발생했습니다. (사유: {e})")
