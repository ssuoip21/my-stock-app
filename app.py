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

# ==========================================
# [블록 1] 앱 기본 설정 및 종목 사전 구축
# ==========================================
st.set_page_config(page_title="주식 검색기", layout="wide")
st.title("📑 통합 보고서")

@st.cache_data(ttl=86400)
def get_stock_dictionary():
    # 외부 서버 차단 시에도 작동하는 무적의 사전
    stocks = {
        "삼성전자": "005930", "SK하이닉스": "000660", "LG에너지솔루션": "373220",
        "삼성바이오로직스": "207940", "현대차": "005380", "기아": "000270",
        "셀트리온": "068270", "POSCO홀딩스": "005490", "NAVER": "035420",
        "LG화학": "051910", "삼성SDI": "006400", "삼성물산": "028260",
        "카카오": "035720", "KB금융": "105560", "신한지주": "055550",
        "에코프로비엠": "247540", "에코프로": "086520", 
        "화신정공": "126640", "코텍": "052330", "아비코전자": "036010",
        "한미반도체": "042700", "HLB": "028300", "알테오젠": "196170"
    }
    try:
        df = fdr.StockListing('KRX')
        for _, row in df.iterrows():
            stocks[row['Name']] = str(row['Code']).zfill(6)
    except:
        pass
    return stocks

STOCK_DICT = get_stock_dictionary()

# ==========================================
# [블록 2] 사이드바 검색 엔진 및 오타 교정
# ==========================================
st.sidebar.write("### 🔍 지능형 종목 검색")
st.sidebar.caption("오타가 있어도, 소형주라도 똑똑하게 찾아줍니다.")
user_input = st.sidebar.text_input("종목명을 입력하세요", value="삼성전자")

target_code = None
target_name = None

if user_input:
    if user_input.isdigit() and len(user_input) == 6:
        target_code = user_input
        target_name = next((name for name, code in STOCK_DICT.items() if code == target_code), user_input)
    else:
        if user_input in STOCK_DICT:
            target_code = STOCK_DICT[user_input]
            target_name = user_input
        else:
            all_names = list(STOCK_DICT.keys())
            close_matches = difflib.get_close_matches(user_input, all_names, n=5, cutoff=0.3)
            partial_matches = [name for name in all_names if user_input in name]
            suggestions = list(dict.fromkeys(close_matches + partial_matches))
            
            if suggestions:
                st.sidebar.warning(f"⚠️ '{user_input}'을(를) 찾을 수 없습니다.")
                st.sidebar.info("💡 **혹시 아래 종목을 찾으시나요?**\n\n" + "\n".join([f"- **{s}**" for s in suggestions[:7]]))
            else:
                st.sidebar.error("❌ 일치하는 종목을 찾을 수 없습니다.")

# ==========================================
# [블록 3] 데이터 시각화 및 분석 리포트 출력
# ==========================================
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
                    st.info(f"💡 AI 의견: **{opinion}**")

                table_style = """
                <style>
                    .custom-table { width: 100%; border-collapse: collapse; margin-bottom: 20px; border: 1px solid #ddd; }
                    .custom-table th, .custom-table td { border: 1px solid #ddd; padding: 12px; font-size: 14px; text-align: center; }
                    .custom-table td.right-num { text-align: right; }
                    .custom-table th { background-color: #f0f2f6; font-weight: bold; }
                </style>
                """
                
                # 수급 동향 (차단 대비 방어 코드)
                st.divider()
                st.subheader("📈 10거래일 투자자별 순매수 동향")
                try:
                    headers = {'User-Agent': 'Mozilla/5.0'}
                    f_url = f"https://finance.naver.com/item/frgn.naver?code={target_code}"
                    f_res = requests.get(f_url, headers=headers, timeout=5)
                    f_res.encoding = 'euc-kr'
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
                            s_html += f'<tr><td>{tds[0].text}</td><td class="right-num" style="{stl(pv)}">{pv:+,}</td><td class="right-num" style="{stl(fv)}">{fv:+,}</td><td class="right-num" style="{stl(iv)}">{iv:+,}</td></tr>'
                            c += 1
                            if c >= 10: break
                    st.markdown(s_html + "</tbody></table>", unsafe_allow_html=True)
                except:
                    st.warning("⚠️ 현재 외부 서버 정책으로 인해 수급 데이터를 불러올 수 없습니다.")

                # 뉴스
                st.divider()
                st.subheader("📰 최신 주요 뉴스")
                try:
                    rss_url = f"https://news.google.com/rss/search?q={urllib.parse.quote(target_name)}&hl=ko&gl=KR&ceid=KR:ko"
                    root = ET.fromstring(requests.get(rss_url, timeout=5).content)
                    items = root.findall('.//item')[:5]
                    for i, item in enumerate(items):
                        st.markdown(f"{i+1}. [{item.find('title').text}]({item.find('link').text})")
                except:
                    st.warning("⚠️ 뉴스 피드를 불러올 수 없습니다.")

                # 전략 시나리오
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
