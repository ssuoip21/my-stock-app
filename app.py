import streamlit as st
import mojito
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta

# 1. 앱 기본 설정
st.set_page_config(page_title="KIS 실시간 주식 리포트", layout="wide")
st.title("📈 KIS 실시간 통합 리포트")

# 2. 보안 키 불러오기
try:
    # Secrets에서 정보 로드
    APP_KEY = st.secrets["kis"]["app_key"]
    APP_SECRET = st.secrets["kis"]["app_secret"]
    ACC_NO = st.secrets["kis"]["acc_no"]
    ACC_NO_PS = st.secrets["kis"]["acc_no_ps"]
except Exception as e:
    st.error("Secrets 설정 오류: [kis] 섹션과 키 이름들을 다시 확인해 주세요.")
    st.stop()

# 3. KIS API 연결 함수
@st.cache_resource
def get_broker():
    # 최신 버전의 mojito 클래스명을 사용합니다.
    return mojito.KoreaInvestment(
        api_key=APP_KEY,
        api_secret=APP_SECRET,
        acc_no=f"{ACC_NO}-{ACC_NO_PS}",
        mock=False
    )

broker = get_broker()

# 4. 사이드바 검색창
st.sidebar.write("### 🔍 종목 검색")
symbol = st.sidebar.text_input("종목코드 6자리 입력", value="005930")

# 5. 메인 데이터 처리 로직
if symbol:
    with st.spinner("실시간 데이터를 수신 중입니다..."):
        try:
            # 현재가 수신
            resp = broker.fetch_price(symbol)
            
            if resp and 'output' in resp:
                data = resp['output']
                name = data.get('hts_kor_isnm', symbol)
                curr_price = int(data.get('stck_prpr', 0))
                diff = int(data.get('prdy_vrss', 0))
                rate = float(data.get('prdy_ctrt', 0.0))
                
                # 차트용 데이터 (최근 30일)
                end_day = datetime.now().strftime("%Y%m%d")
                start_day = (datetime.now() - timedelta(days=60)).strftime("%Y%m%d")
                
                chart_resp = broker.fetch_ohlcv(
                    symbol=symbol,
                    timeframe='D',
                    start_day=start_day,
                    end_day=end_day
                )
                
                if chart_resp and 'output2' in chart_resp:
                    df = pd.DataFrame(chart_resp['output2'])
                    df['stck_bsop_date'] = pd.to_datetime(df['stck_bsop_date'])
                    cols = ['stck_oprc', 'stck_hgpr', 'stck_lwpr', 'stck_clpr']
                    df[cols] = df[cols].apply(pd.to_numeric)
                    
                    # 화면 배치
                    col1, col2 = st.columns([3, 1])
                    
                    with col1:
                        st.subheader(f"📊 {name}({symbol}) 분석 차트")
                        fig = go.Figure(data=[go.Candlestick(
                            x=df['stck_bsop_date'],
                            open=df['stck_oprc'], high=df['stck_hgpr'],
                            low=df['stck_lwpr'], close=df['stck_clpr'],
                            increasing_line_color='#FF4136',
                            decreasing_line_color='#0074D9',
                            name='주가'
                        )])
                        fig.update_layout(xaxis_rangeslider_visible=False, height=500)
                        st.plotly_chart(fig, use_container_width=True)
                        
                    with col2:
                        st.subheader("💰 실시간 정보")
                        st.metric(label="현재가", value=f"{curr_price:,}원", delta=f"{diff:,}원 ({rate:+.2f}%)")
                        st.divider()
                        st.write(f"**전일종가:** {int(data.get('stck_sdpr', 0)):,}원")
                        st.write(f"**당일고가:** {int(data.get('stck_hgpr', 0)):,}원")
                        st.write(f"**당일저가:** {int(data.get('stck_lwpr', 0)):,}원")
                else:
                    st.warning("데이터 수신에 성공했으나 차트 정보가 비어있습니다.")
            else:
                st.error("증권사 서버 응답 오류: 종목코드나 API 키를 확인해 주세요.")
                
        except Exception as e:
            st.error(f"실행 중 예외 발생: {e}")
