import streamlit as st
import mojito
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta

# 1. 앱 기본 설정
st.set_page_config(page_title="KIS 실시간 주식 리포트", layout="wide")
st.title("📈 KIS 실시간 통합 리포트")

# 2. 보안 키 불러오기 (Streamlit Secrets)
try:
    APP_KEY = st.secrets["kis"]["app_key"]
    APP_SECRET = st.secrets["kis"]["app_secret"]
    ACC_NO = st.secrets["kis"]["acc_no"]
    ACC_NO_PS = st.secrets["kis"]["acc_no_ps"]
except Exception as e:
    st.error("Secrets 설정이 올바르지 않습니다. 대시보드 설정을 확인해 주세요.")
    st.stop()

# 3. KIS API 연결 함수
@st.cache_resource
def get_broker():
    # 최신 버전 mojito는 KoreaInvestment 클래스를 사용합니다.
    return mojito.KoreaInvestment(
        api_key=APP_KEY,
        api_secret=APP_SECRET,
        acc_no=f"{ACC_NO}-{ACC_NO_PS}",
        mock=False  # 실전투자 모드
    )

broker = get_broker()

# 4. 사이드바 검색창
st.sidebar.write("### 🔍 종목 검색")
st.sidebar.caption("정확한 분석을 위해 6자리 종목코드를 입력해 주세요.")
symbol = st.sidebar.text_input("종목코드 (예: 005930)", value="005930")

# 5. 메인 로직 시작
if symbol:
    with st.spinner(f"종목코드 '{symbol}'의 실시간 데이터를 가져오는 중..."):
        try:
            # [A] 실시간 현재가 정보 가져오기
            resp = broker.fetch_price(symbol)
            
            if resp and 'output' in resp:
                data = resp['output']
                name = data.get('hts_kor_isnm', symbol)
                curr_price = int(data.get('stck_prpr', 0))
                diff = int(data.get('prdy_vrss', 0))
                rate = float(data.get('prdy_ctrt', 0.0))
                
                # [B] 차트용 과거 데이터 가져오기 (최근 30거래일)
                end_day = datetime.now().strftime("%Y%m%d")
                start_day = (datetime.now() - timedelta(days=60)).strftime("%Y%m%d")
                
                chart_resp = broker.fetch_ohlcv(
                    symbol=symbol,
                    timeframe='D',
                    start_day=start_day,
                    end_day=end_day
                )
                
                if chart_resp and 'output2' in chart_resp:
                    # 데이터 프레임 생성 및 정제
                    df = pd.DataFrame(chart_resp['output2'])
                    df['stck_bsop_date'] = pd.to_datetime(df['stck_bsop_date'])
                    
                    # 숫자형으로 변환
                    cols = ['stck_oprc', 'stck_hgpr', 'stck_lwpr', 'stck_clpr']
                    df[cols] = df[cols].apply(pd.to_numeric)
                    
                    # --- 화면 레이아웃 구성 ---
                    col1, col2 = st.columns([3, 1])
                    
                    with col1:
                        st.subheader(f"📊 {name}({symbol}) 분석 차트")
                        fig = go.Figure(data=[go.Candlestick(
                            x=df['stck_bsop_date'],
                            open=df['stck_oprc'],
                            high=df['stck_hgpr'],
                            low=df['stck_lwpr'],
                            close=df['stck_clpr'],
                            increasing_line_color='#FF4136', 
                            decreasing_line_color='#0074D9',
                            name='주가'
                        )])
                        
                        # 이동평균선 추가 (간단한 예시: 5일선)
                        df['MA5'] = df['stck_clpr'].rolling(window=5).mean()
                        fig.add_trace(go.Scatter(
                            x=df['stck_bsop_date'], 
                            y=df['MA5'], 
                            name='5일선', 
                            line=dict(color='orange', width=1.5)
                        ))
                        
                        fig.update_layout(
                            xaxis_rangeslider_visible=False, 
                            height=500,
                            margin=dict(l=10, r=10, t=10, b=10)
                        )
                        st.plotly_chart(fig, use_container_width=True)
                    
                    with col2:
                        st.subheader("💰 현재 정보")
                        st.metric(
                            label="현재가", 
                            value=f"{curr_price:,}원", 
                            delta=f"{diff:,}원 ({rate:+.2f}%)"
                        )
                        st.divider()
                        st.write(f"**상한가:** {int(data.get('stck_mxpr', 0)):,}원")
                        st.write(f"**하한가:** {int(data.get('stck_llam', 0)):,}원")
                        st.write(f"**거래량:** {int(data.get('acml_vol', 0)):,}주")
                        st.write(f"**전일종가:** {int(data.get('stck_sdpr', 0)):,}원")
                        
                    # 추가 정보 섹션
                    st.divider()
                    st.info(f"💡 {name} 종목의 실시간 데이터 분석이 완료되었습니다. 증권사 API를 통해 안정적으로 수신 중입니다.")
                
                else:
                    st.warning("차트 데이터를 가져오지 못했습니다. 장 종료 후나 서버 점검 시간일 수 있습니다.")
            else:
                st.error("종목 정보를 찾을 수 없습니다. 종목코드를 다시 확인해 주세요.")
                
        except Exception as e:
            st.error(f"데이터를 처리하는 중 오류가 발생했습니다: {e}")
