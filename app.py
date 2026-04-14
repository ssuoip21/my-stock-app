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

# [궁극의 해결책] 네이버 금융 통합 검색 엔진 직접 활용 (차단 X, 소형주 100% 검색)
@st.cache_data(ttl=3600)
def resolve_stock(query):
    query = query.strip()
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    
    # 1. 6자리 숫자를 입력한 경우 (바로 해당 종목 페이지로 직행)
    if query.isdigit() and len(query) == 6:
        try:
            url = f"https://finance.naver.com/item/main.naver?code={query}"
            res = requests.get(url, headers=headers, timeout=5)
            soup = BeautifulSoup(res.text, 'html.parser')
            name_tag = soup.select_one('.wrap_company h2 a')
            if name_tag:
                return query, name_tag.text.strip(), []
        except:
            pass
        return query, query, [] # 이름 추출 실패 시 코드만 반환
        
    # 2. 한글/영문 이름을 입력한 경우 (네이버 금융 검색창 결과 파싱)
    try:
        # 네이버 금융 검색은 euc-kr 인코딩을 사용합니다.
        encoded_query = urllib.parse.quote(query.encode('euc-kr', errors='ignore'))
        url = f"https://finance.naver.com/search/searchList.naver?query={encoded_query}"
        res = requests.get(url, headers=headers, timeout=5)
        
        # [핵심] 정확한 종목명을 입력하면 네이버가 검색 목록 대신 '종목 상세 페이지'로 즉시 자동 이동(Redirect)시킵니다.
        if '/item/main.naver?code=' in res.url:
            code = res.url.split('code=')[-1].split('&')[0]
            soup = BeautifulSoup(res.text, 'html.parser')
            name_tag = soup.select_one('.wrap_company h2 a')
            name = name_tag.text.strip() if name_tag else query
            return code, name, []
            
        # 정확한 일치가 없어 '검색 결과 목록'이 나타난 경우 (오타, 부분 일치 등)
        soup = BeautifulSoup(res.text, 'html.parser')
        a_tags = soup.select('td.tit a')
        if a_tags:
            # 가장 정확도 높은 첫 번째 결과를 선택
            best_code = a_tags[0].get('href', '').split('code=')[-1]
            best_name = a_tags[0].text.strip()
            
            # 나머지 결과들은 사용자에게 제안하기 위해 수집
            suggestions = []
            for a in a_tags:
                n = a.text.strip()
                if n != best_name and n not in suggestions:
                    suggestions.append(n)
                    
            return best_code, best_name, suggestions[:7] # 최대 7개만 제안
    except Exception:
        pass
        
    return None, None, []

# 2. 사이드바: 네이버 기반 지능형 검색창
st.sidebar.write("### 🔍 지능형 종목 검색")
st.sidebar.caption("소형주 완벽 지원! 오타가 있어도 네이버 엔진이 찾아줍니다.")
user_input = st.sidebar.text_input("종목명 또는 코드 입력", value="삼성전자")

if user_input:
    with st.spinner(f"'{user_input}' 종목을 찾고 있습니다..."):
        try:
            # 종목 찾기
            target_code, target_name, suggestions = resolve_stock(user_input)

            if target_code:
                # 검색된 종목이 사용자가 입력한 이름과 다르고 제안 목록이 있다면 오타 보정 알림
                if target_name != user_input and suggestions:
                    st.sidebar.success(f"✔️ 자동 교정됨: **{target_name}**")
                    st.sidebar.info("💡 **혹시 다른 종목을 찾으셨나요?**\n\n" + "\n".join([f"- {s}" for s in suggestions]))
            else:
                st.sidebar.error("❌ 일치하는 종목을 찾을 수 없습니다. (상장 폐지되었거나 검색어 오류)")

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
