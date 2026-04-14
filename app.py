import streamlit as st
import mojito
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta

# 1. 앱 설정 및 보안 키 불러오기
st.set_page_config(page_title="KIS 전용 주식 분석기", layout="wide")
st.title("📈 KIS 실시간 통합 리포트")

# Secrets에서 키 가져오기
APP_KEY = st.secrets["kis"]["app_key"]
APP_SECRET = st.secrets["kis"]["app_secret"]
ACC_NO = st.secrets["kis"]["acc_no"]
ACC_NO_PS = st.secrets["kis"]["acc_no_ps"]

# 2. 한국투자증권 API 연결 (모든 종목 가능)
@st.cache_resource
def get_broker():
    return mojito.KoreaInvestment( ... )
        api_key=APP_KEY,
        api_secret=APP_SECRET,
        acc_no=f"{ACC_NO}-{ACC_NO_PS}",
        mock=False # 실전투자 모드
    )

broker = get_broker()

# 3. 사이드바 검색
st.sidebar.write("### 🔍 종목 검색")
symbol = st.sidebar.text_input("6자리 종목코드를 입력하세요", value="005930")

if symbol:
    with st.spinner("증권사 서버에서 실시간 데이터를 가져오는 중..."):
        # 실시간 현재가 정보
        resp = broker.fetch_price(symbol)
        
        if 'output' in resp:
            data = resp['output']
            name = data['hts_kor_isnm']
            curr_price = int(data['stck_prpr'])
            diff = int(data['prdy_vrss'])
            rate = float(data['prdy_ctrt'])
            
            # 차트용 과거 데이터 (일봉 30일)
            end_date = datetime.now().strftime("%Y%m%d")
            start_date = (datetime.now() - timedelta(days=60)).strftime("%Y%m%d")
            
            chart_resp = broker.fetch_ohlcv(
                symbol=symbol,
                timeframe='D',
                start_day=start_date,
                end_day=end_date
            )
            
            if 'output2' in chart_resp:
                df = pd.DataFrame(chart_resp['output2'])
                # 데이터 정제
                df['stck_bsop_date'] = pd.to_datetime(df['stck_bsop_date'])
                cols = ['stck_oprc', 'stck_hgpr', 'stck_lwpr', 'stck_clpr']
                df[cols] = df[cols].apply(pd.to_numeric)
                
                # --- 화면 출력 ---
                col1, col2 = st.columns([3, 1])
                with col1:
                    st.subheader(f"📊 {name}({symbol}) 실시간 차트")
                    fig = go.Figure(data=[go.Candlestick(
                        x=df['stck_bsop_date'],
                        open=df['stck_oprc'], high=df['stck_hgpr'],
                        low=df['lwpr'], close=df['stck_clpr'],
                        increasing_line_color='#FF4136', decreasing_line_color='#0074D9'
                    )])
                    fig.update_layout(xaxis_rangeslider_visible=False, height=500)
                    st.plotly_chart(fig, use_container_width=True)
                
                with col2:
                    st.subheader("💰 실시간 시세")
                    st.metric(label="현재가", value=f"{curr_price:,}원", delta=f"{diff:,}원 ({rate:+.2f}%)")
                    st.write(f"최고가: {int(data['stck_mxpr']):,}원")
                    st.write(f"최저가: {int(data['stck_llam']):,}원")
                    st.write(f"거래량: {int(data['acml_vol']):,}주")
                    
                # 여기에 추가적인 AI 분석이나 지표를 더할 수 있습니다.
        else:
            st.error("종목 정보를 가져오지 못했습니다. 코드를 확인해 주세요.")
