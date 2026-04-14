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

# 2. 사이드바: 종목 입력
item_name = st.sidebar.text_input("조회할 종목명을 입력하세요", value="삼성전자")

if item_name:
    with st.spinner(f"'{item_name}'의 데이터를 분석 중입니다..."):
        try:
            # [데이터 수집] 종목 정보 및 가격 데이터
            df_list = fdr.StockListing('KRX')
            target = df_list[df_list['Name'] == item_name]
            
            if not target.empty:
                code = target['Code'].values[0]
                headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}

                now = datetime.now()
                df_price = fdr.DataReader(code, now - timedelta(days=60), now)
                
                # 지표 계산
                df_price['MA5'] = df_price['Close'].rolling(window=5).mean()
                df_price['MA20'] = df_price['Close'].rolling(window=20).mean()
                df_recent = df_price.tail(10)
                volatility = df_price['Close'].pct_change().std()

                current_p = int(df_recent['Close'].iloc[-1])
                prev_p = int(df_recent['Close'].iloc[-2])
                ma20_curr = df_recent['MA20'].iloc[-1]
                
                # AI 단기 예측값 계산
                X = np.arange(len(df_recent))
                y = df_recent['Close'].values
                coef = np.polyfit(X, y, 1)
                future_p = int(coef[0] * (len(df_recent) + 3) + coef[1])

                # AI 투자 의견 로직
                if current_p > ma20_curr and future_p > current_p:
                    opinion_text = "AI 의견: **매수** - 주요 이동평균선 상단에 위치하며 단기 상승 추세가 유효해 보입니다."
                elif current_p < ma20_curr and future_p < current_p:
                    opinion_text = "AI 의견: **매도** - 하락 추세가 지속되고 있으며 단기 반등 시그널이 부족한 상태입니다."
                else:
                    opinion_text = "AI 의견: **관망** - 수급 흐름과 추세 지표가 혼조세를 보이고 있어 방향성 확인 후 진입을 권장합니다."

                # --- 화면 레이아웃 (상단) ---
                col1, col2 = st.columns([3, 1])

                with col1:
                    st.subheader(f"📊 {item_name}({code}) 분석 차트")
                    x_dates = df_recent.index.strftime('%Y-%m-%d')
                    fig = go.Figure()
                    fig.add_trace(go.Candlestick(
                        x=x_dates, open=df_recent['Open'], high=df_recent['High'],
                        low=df_recent['Low'], close=df_recent['Close'], name='주가',
                        increasing_line_color='#FF4136', decreasing_line_color='#0074D9'
                    ))
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

                # --- 공통 스타일 (텍스트 중앙, 숫자 우측 정렬) ---
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

                # --- 섹션 2: 투자자별 순매수 동향 ---
                st.divider()
                st.subheader("📈 10거래일 투자자별 순매수 동향")
                
                frgn_url = f"https://finance.naver.com/item/frgn.naver?code={code}"
                frgn_res = requests.get(frgn_url, headers=headers); frgn_res.encoding = 'euc-kr'
                frgn_soup = BeautifulSoup(frgn_res.text, 'html.parser')
                rows = frgn_soup.select('table.type2 tr')
                
                s_html = table_style + '<table class="custom-table"><thead><tr><th>날짜</th><th>개인</th><th>외국인</th><th>기관</th></tr></thead><tbody>'
                count = 0
                for row in rows:
                    cols = row.select('td')
                    if len(cols) == 9 and cols[0].text.strip():
                        date = cols[0].text.strip()
                        f_v = int(cols[6].text.strip().replace(',',''))
                        i_v = int(cols[5].text.strip().replace(',',''))
                        p_v = -(f_v + i_v)

                        def get_color(v):
                            if v > 0: return "color: #FF4136; font-weight: bold;"
                            elif v < 0: return "color: #0074D9; font-weight: bold;"
                            return "color: black;"

                        s_html += f'<tr><td class="center-txt">{date}</td>'
                        s_html += f'<td class="right-num" style="{get_color(p_v)}">{p_v:+,}</td>'
                        s_html += f'<td class="right-num" style="{get_color(f_v)}">{f_v:+,}</td>'
                        s_html += f'<td class="right-num" style="{get_color(i_v)}">{i_v:+,}</td></tr>'
                        count += 1
                        if count >= 10: break
                s_html += "</tbody></table>"
                st.markdown(s_html, unsafe_allow_html=True)

                # --- 섹션 3: 최신 주요 뉴스 ---
                st.divider()
                st.subheader("📰 최신 주요 뉴스")
                rss_url = f"https://news.google.com/rss/search?q={urllib.parse.quote(item_name)}&hl=ko&gl=KR&ceid=KR:ko"
                rss_res = requests.get(rss_url)
                root = ET.fromstring(rss_res.content)
                for i, item in enumerate(root.findall('.//item')[:5]):
                    st.markdown(f"{i+1}. [{item.find('title').text}]({item.find('link').text})")

                # --- 섹션 4: AI 투자 전략 시나리오 (최하단) ---
                st.divider()
                st.subheader("🎯 AI 투자 전략 시나리오")
                
                v_f = volatility * 100
                strat = {
                    "3일 (초단기)": [int(current_p * 0.99), int(current_p * (1 + 0.02 * v_f)), int(current_p * (1 + 0.04 * v_f)), int(current_p * 0.97)],
                    "1개월 (단기)": [int(current_p * 0.97), int(current_p * (1 + 0.05 * v_f)), int(current_p * (1 + 0.10 * v_f)), int(current_p * 0.93)],
                    "3개월 (중기)": [int(current_p * 0.95), int(current_p * (1 + 0.12 * v_f)), int(current_p * (1 + 0.20 * v_f)), int(current_p * 0.88)],
                    "1년+ (장기)": [int(current_p * 0.90), int(current_p * (1 + 0.30 * v_f)), int(current_p * (1 + 0.60 * v_f)), int(current_p * 0.75)]
                }
                
                labels = ["매수가", "1차 목표가", "2차 목표가", "손절가"]
                a_html = table_style + '<table class="custom-table"><thead><tr><th>구분</th><th>3일 (초단기)</th><th>1개월 (단기)</th><th>3개월 (중기)</th><th>1년+ (장기)</th></tr></thead><tbody>'
                
                for i, label in enumerate(labels):
                    a_html += f"<tr><td class='center-txt'><b>{label}</b></td>"
                    for key in strat:
                        a_html += f"<td class='right-num'>{strat[key][i]:,}원</td>"
                    a_html += "</tr>"
                
                a_html += "</tbody></table>"
                st.markdown(a_html, unsafe_allow_html=True)

            else:
                st.error("종목명을 다시 확인해주세요.")
        except Exception as e:
            st.error(f"오류 발생: {e}")