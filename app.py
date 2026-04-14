import streamlit as st
import FinanceDataReader as fdr
import requests
from bs4 import BeautifulSoup
import plotly.graph_objects as go
from datetime import datetime, timedelta
import numpy as np
import pandas as pd
import difflib

# 1. 앱 기본 설정
st.set_page_config(page_title="주식 검색기", layout="wide")
st.title("📑 통합 보고서")

# 2,500개 상장사 목록을 안전하게 가져오는 함수
@st.cache_data(ttl=86400)
def load_all_stocks():
    stock_dict = {}
    # 우회 경로: 한국거래소 KIND 공시 포털 엑셀 데이터 파싱
    try:
        url = 'http://kind.krx.co.kr/corpgeneral/corpList.do?method=download&searchType=13'
        df = pd.read_html(url, header=0)[0]
        for _, row in df.iterrows():
            stock_dict[row['회사명']] = str(row['종목코드']).zfill(6)
        return stock_dict
    except:
        pass
    
    # 예비 경로: FinanceDataReader
    try:
        df = fdr.StockListing('KRX')
        for _, row in df.iterrows():
            stock_dict[row['Name']] = str(row['Code']).zfill(6)
        return stock_dict
    except:
        return {"삼성전자": "005930", "SK하이닉스": "000660", "화신정공": "126640"}

STOCK_DICT = load_all_stocks()
# 2. 사이드바 검색 엔진
st.sidebar.write("### 🔍 지능형 종목 검색")
user_input = st.sidebar.text_input("종목명 또는 코드 입력", value="화신정공")

target_code = None
target_name = None

if user_input:
    # 6자리 코드 입력 시
    if user_input.isdigit() and len(user_input) == 6:
        target_code = user_input
        target_name = next((name for name, code in STOCK_DICT.items() if code == target_code), user_input)
    # 종목명 입력 시
    else:
        if user_input in STOCK_DICT:
            target_code = STOCK_DICT[user_input]
            target_name = user_input
        else:
            # 오타 교정 및 부분 일치 검색
            all_names = list(STOCK_DICT.keys())
            close_matches = difflib.get_close_matches(user_input, all_names, n=5, cutoff=0.3)
            partial_matches = [name for name in all_names if user_input in name]
            suggestions = list(dict.fromkeys(close_matches + partial_matches))
            
            if suggestions:
                st.sidebar.warning(f"⚠️ '{user_input}'을(를) 찾을 수 없습니다.")
                st.sidebar.info("💡 **혹시 아래 종목을 찾으시나요?**\n\n" + "\n".join([f"- {s}" for s in suggestions[:7]]))
            else:
                st.sidebar.error("❌ 일치하는 종목을 찾을 수 없습니다.")
                # 3. 메인 화면 출력
if target_code:
    with st.spinner(f"'{target_name}' 분석 중..."):
        try:
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

                opinion = "관망"
                if current_p > ma20_curr and future_p > current_p:
                    opinion = "매수"
                elif current_p < ma20_curr and future_p < current_p:
                    opinion = "매도"

                col1, col2 = st.columns([3, 1])
                with col1:
                    st.subheader(f"📊 {target_name}({target_code}) 차트")
                    x_dates = df_recent.index.strftime('%Y-%m-%d')
                    fig = go.Figure(data=[go.Candlestick(x=x_dates, open=df_recent['Open'], high=df_recent['High'], low=df_recent['Low'], close=df_recent['Close'], increasing_line_color='#FF4136', decreasing_line_color='#0074D9')])
                    fig.add_trace(go.Scatter(x=x_dates, y=df_recent['MA5'], name='5일선', line=dict(color='orange', width=1.5)))
                    fig.add_trace(go.Scatter(x=x_dates, y=df_recent['MA20'], name='20일선', line=dict(color='purple', width=1.5)))
                    fig.update_layout(xaxis_rangeslider_visible=False, height=450, xaxis_type='category')
                    st.plotly_chart(fig, use_container_width=True)
                with col2:
                    st.subheader("💰 현재 정보")
                    st.metric(label="현재가", value=f"{current_p:,}원", delta=f"{current_p - prev_p:,}원")
                    st.info(f"💡 AI 의견: **{opinion}**")

                table_style = "<style>.custom-table { width: 100%; border-collapse: collapse; margin-bottom: 20px; border: 1px solid #ddd; } .custom-table th, .custom-table td { border: 1px solid #ddd; padding: 12px; font-size: 14px; text-align: center; } .custom-table td.right-num { text-align: right; } .custom-table th { background-color: #f0f2f6; font-weight: bold; }</style>"
                
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
                    a_html += f"<tr><td><b>{label}</b></td>"
                    for key in strat: a_html += f"<td class='right-num'>{strat[key][i]:,}원</td>"
                    a_html += "</tr>"
                st.markdown(a_html + "</tbody></table>", unsafe_allow_html=True)
            else:
                st.error("데이터를 불러올 수 없습니다.")
        except Exception as e:
            st.error(f"오류 발생: {e}")
