import streamlit as st
import mojito
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
import requests
from bs4 import BeautifulSoup
import urllib.parse
import xml.etree.ElementTree as ET
import numpy as np
import FinanceDataReader as fdr

# 1. 앱 설정 (모바일 최적화 레이아웃 및 다크모드 대응)
st.set_page_config(page_title="스마트 주식 비서 Pro", layout="wide")

# [핵심 수정] 다크모드 호환을 위해 고정된 흰색 배경(#ffffff) 제거, Streamlit 기본 테마 색상 사용
st.markdown("""
    <style>
    .main .block-container { padding-top: 1rem; padding-bottom: 1rem; padding-left: 0.5rem; padding-right: 0.5rem; }
    div[data-testid="stMetric"] { padding: 10px; border-radius: 10px; border: 1px solid rgba(128, 128, 128, 0.2); }
    /* 관심종목 칩 스타일 */
    .stButton>button { border-radius: 20px; border: 1px solid #0074D9; color: #0074D9; padding: 0px 15px; }
    @media (max-width: 640px) { .stTabs [data-baseweb="tab-list"] { gap: 10px; } .stTabs [data-baseweb="tab"] { padding-left: 10px; padding-right: 10px; } }
    </style>
    """, unsafe_allow_html=True)

# 2. 보안 키 로드 및 API 연결
try:
    APP_KEY = st.secrets["kis"]["app_key"]
    APP_SECRET = st.secrets["kis"]["app_secret"]
    ACC_NO = st.secrets["kis"]["acc_no"]
    ACC_NO_PS = st.secrets["kis"]["acc_no_ps"]
except Exception:
    st.error("⚠️ Streamlit Secrets 설정을 확인해주세요.")
    st.stop()

@st.cache_resource
def get_broker():
    return mojito.KoreaInvestment(
        api_key=APP_KEY, api_secret=APP_SECRET, 
        acc_no=f"{ACC_NO}-{ACC_NO_PS}", mock=False
    )

@st.cache_data(ttl=86400) 
def get_stock_dict():
    try:
        krx_df = fdr.StockListing('KRX')
        return dict(zip(krx_df['Name'], krx_df['Code']))
    except:
        return {"삼성전자": "005930", "SK하이닉스": "000660"}

broker = get_broker()
STOCK_DICT = get_stock_dict()

# [신규 기능 4] 빛의 속도 데이터 로딩 (캐싱 적용)
@st.cache_data(ttl=300) # 5분간 데이터 기억
def fetch_stock_data(target_code, timeframe):
    tf_map = {"일봉": "D", "주봉": "W", "월봉": "M"}
    end_d = datetime.now().strftime("%Y%m%d")
    start_d = (datetime.now() - timedelta(days=500)).strftime("%Y%m%d")
    res = broker.fetch_ohlcv(target_code, tf_map[timeframe], start_d, end_d)['output2']
    
    df = pd.DataFrame(res)
    df['date'] = pd.to_datetime(df['stck_bsop_date'])
    for col in ['stck_clpr', 'stck_oprc', 'stck_hgpr', 'stck_lwpr', 'acml_vol']:
        df[col] = pd.to_numeric(df[col])
    
    df = df.sort_values(by='date').reset_index(drop=True)
    df['date_str'] = df['date'].dt.strftime('%Y-%m-%d')
    
    # 기본 지표
    df['MA5'] = df['stck_clpr'].rolling(window=5).mean()
    df['MA20'] = df['stck_clpr'].rolling(window=20).mean()
    
    # [신규 기능 1] 보조지표 계산 (볼린저 밴드, RSI)
    df['std'] = df['stck_clpr'].rolling(window=20).std()
    df['Upper_BB'] = df['MA20'] + (df['std'] * 2)
    df['Lower_BB'] = df['MA20'] - (df['std'] * 2)
    
    delta = df['stck_clpr'].diff()
    up = delta.clip(lower=0)
    down = -1 * delta.clip(upper=0)
    ema_up = up.ewm(com=13, adjust=False).mean()
    ema_down = down.ewm(com=13, adjust=False).mean()
    rs = ema_up / ema_down
    df['RSI'] = 100 - (100 / (1 + rs))
    
    return df

# [신규 기능 3] 펀더멘털 크롤링
@st.cache_data(ttl=3600)
def get_fundamental(code):
    try:
        url = f"https://finance.naver.com/item/main.naver?code={code}"
        res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'})
        soup = BeautifulSoup(res.text, 'html.parser')
        
        market_cap = soup.select_one('#_market_sum').text.strip().replace('\t', '').replace('\n', '')
        per = soup.select_one('#_per').text.strip() if soup.select_one('#_per') else "N/A"
        pbr = soup.select_one('#_pbr').text.strip() if soup.select_one('#_pbr') else "N/A"
        div = soup.select_one('#_dvr').text.strip() + "%" if soup.select_one('#_dvr') else "N/A"
        
        return {"시총": market_cap, "PER": per, "PBR": pbr, "배당률": div}
    except:
        return {"시총": "-", "PER": "-", "PBR": "-", "배당률": "-"}


# 3. 상단 UI (관심종목, 검색, 설정)
st.write("### ⭐ 관심 종목")
# [신규 기능 2] 관심종목 빠른 이동 칩
fav_cols = st.columns(4)
fav_list = ["삼성전자", "SK하이닉스", "화신정공", "아비코전자"]
selected_fav = None
for i, fav in enumerate(fav_list):
    with fav_cols[i%4]:
        if st.button(fav, use_container_width=True):
            selected_fav = fav

with st.expander("⚙️ 검색 및 설정", expanded=(selected_fav is None)):
    col1, col2 = st.columns([2, 1])
    with col1:
        # 관심종목 버튼을 누르면 검색창 값에 덮어씌움
        default_val = selected_fav if selected_fav else "삼성전자"
        user_input = st.text_input("종목명 또는 코드 입력", value=default_val)
        timeframe = st.radio("차트 주기", ("일봉", "주봉", "월봉"), horizontal=True)
    with col2:
        up_color = st.color_picker("상승 색상", "#FF4136")
        down_color = st.color_picker("하락 색상", "#0074D9")

target_code = None
target_name = None

if user_input:
    if user_input.isdigit() and len(user_input) == 6:
        target_code = user_input
        target_name = next((n for n, c in STOCK_DICT.items() if c == target_code), user_input)
    elif user_input in STOCK_DICT:
        target_code = STOCK_DICT[user_input]
        target_name = user_input
    else:
        clean_input = user_input.replace(" ", "")
        matches = [name for name in STOCK_DICT.keys() if clean_input in name.replace(" ", "")]
        if matches:
            st.info(f"💡 혹시 '{matches[0]}'을(를) 찾으시나요?")
            selected_match = st.selectbox("정확한 종목 선택", ["여기를 눌러 선택..."] + matches)
            if selected_match != "여기를 눌러 선택...":
                target_code = STOCK_DICT[selected_match]
                target_name = selected_match

# 4. 메인 리포트
if target_code:
    with st.spinner(f"{target_name} 데이터 로딩 중..."):
        try:
            # 실시간 주가
            price_resp = broker.fetch_price(target_code)['output']
            curr_p = int(price_resp['stck_prpr'])
            diff = int(price_resp['prdy_vrss'])
            rate = float(price_resp['prdy_ctrt'])
            vol = int(price_resp['acml_vol'])
            
            # 차트 및 지표 데이터 (캐싱 적용)
            df = fetch_stock_data(target_code, timeframe)
            
            # 기업 정보 크롤링
            fund_data = get_fundamental(target_code)

            # --- [핵심 수정] 통합 정보 박스 (현재가, 거래량, 펀더멘털 통합) ---
            st.write(f"### 📈 {target_name} ({target_code})")
            
            # 하나의 컨테이너 안에 모든 핵심 지표를 담습니다.
            with st.container(border=True):
                st.write("#### 💰 핵심 지표")
                c1, c2, c3, c4, c5 = st.columns([2, 2, 1.5, 1.5, 1.5])
                c1.metric("현재가", f"{curr_p:,}원", f"{diff:,}원 ({rate:+.2f}%)")
                c2.metric("거래량", f"{vol:,}주")
                c3.metric("시가총액", fund_data['시총'])
                c4.metric("PER / PBR", f"{fund_data['PER']} / {fund_data['PBR']}")
                c5.metric("배당수익률", fund_data['배당률'])

            # --- 인터랙티브 차트 (이동평균선 + 볼린저 밴드) ---
            view_limit = df.tail(30)
            min_y = view_limit['Lower_BB'].min() * 0.95 # 볼린저 하단까지 고려한 Y축 설정
            max_y = view_limit['Upper_BB'].max() * 1.05
            y_range = [min_y, max_y]

            fig = make_subplots(
                rows=2, cols=1, shared_xaxes=True, 
                vertical_spacing=0.03, row_heights=[0.7, 0.3]
            )

            # 주가 캔들
            fig.add_trace(go.Candlestick(
                x=df['date_str'], open=df['stck_oprc'], high=df['stck_hgpr'],
                low=df['stck_lwpr'], close=df['stck_clpr'],
                increasing_line_color=up_color, decreasing_line_color=down_color,
                name='주가'
            ), row=1, col=1)
            
            # 이동평균선
            fig.add_trace(go.Scatter(x=df['date_str'], y=df['MA5'], name='5일선', line=dict(color='orange', width=1)), row=1, col=1)
            fig.add_trace(go.Scatter(x=df['date_str'], y=df['MA20'], name='20일선', line=dict(color='purple', width=1)), row=1, col=1)
            
            # 볼린저 밴드 (투명한 영역 표시)
            fig.add_trace(go.Scatter(x=df['date_str'], y=df['Upper_BB'], name='볼린저 상단', line=dict(color='rgba(173, 216, 230, 0.5)', width=1), showlegend=False), row=1, col=1)
            fig.add_trace(go.Scatter(x=df['date_str'], y=df['Lower_BB'], name='볼린저 하단', line=dict(color='rgba(173, 216, 230, 0.5)', width=1), fill='tonexty', fillcolor='rgba(173, 216, 230, 0.1)', showlegend=False), row=1, col=1)

            # 거래량
            vol_colors = np.where(df['stck_clpr'] >= df['stck_oprc'], up_color, down_color)
            fig.add_trace(go.Bar(
                x=df['date_str'], y=df['acml_vol'],
                marker_color=vol_colors, name='거래량'
            ), row=2, col=1)
            
            # 레이아웃 
            fig.update_layout(
                height=550, template='plotly_white', margin=dict(l=0, r=0, t=10, b=0),
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                yaxis=dict(range=y_range, fixedrange=False, side='right', showgrid=True, gridcolor='rgba(128,128,128,0.2)'),
                yaxis2=dict(side='right', showgrid=False),
                dragmode='pan',
                paper_bgcolor='rgba(0,0,0,0)', # 다크모드 대응: 차트 배경 투명
                plot_bgcolor='rgba(0,0,0,0)'
            )
            
            zoom_start = max(0, len(df) - 30)
            fig.update_xaxes(type='category', range=[zoom_start, len(df)], rangeslider_visible=False, showgrid=False)

            st.plotly_chart(fig, use_container_width=True, config={'scrollZoom': True, 'displayModeBar': False})

            # --- 하단 분석 탭 ---
            st.divider()
            tab1, tab2, tab3, tab4 = st.tabs(["📊 수급동향", "🔬 기술적 지표", "🎯 투자전략", "📰 뉴스피드"])
            
            with tab1:
                try:
                    h = {'User-Agent': 'Mozilla/5.0'}
                    n_url = f"https://finance.naver.com/item/frgn.naver?code={target_code}"
                    n_res = requests.get(n_url, headers=h, timeout=5)
                    n_res.encoding = 'euc-kr'
                    rows = BeautifulSoup(n_res.text, 'html.parser').select('table.type2 tr')
                    t_html = '<div style="overflow-x:auto;"><table style="width:100%; border-collapse:collapse; font-size:12px; text-align:center;">'
                    t_html += '<tr style="border-bottom: 1px solid gray;"><th>날짜</th><th>개인</th><th>외인</th><th>기관</th></tr>'
                    count = 0
                    for r in rows:
                        tds = r.select('td')
                        if len(tds) == 9 and tds[0].text.strip():
                            fv, iv = int(tds[6].text.strip().replace(',','')), int(tds[5].text.strip().replace(',',''))
                            pv = -(fv + iv)
                            def s(v): return f'color:{"#FF4136" if v>0 else "#0074D9" if v<0 else "inherit"}'
                            t_html += f'<tr><td>{tds[0].text[5:]}</td><td style="{s(pv)}">{pv:+,}</td><td style="{s(fv)}">{fv:+,}</td><td style="{s(iv)}">{iv:+,}</td></tr>'
                            count += 1
                            if count >= 7: break
                    st.markdown(t_html + '</table></div>', unsafe_allow_html=True)
                except: st.write("수급 데이터 오류")

            with tab2:
                # RSI 해석 추가
                curr_rsi = df['RSI'].iloc[-1]
                rsi_status = "과매수 (조정 주의)" if curr_rsi >= 70 else "과매도 (반등 가능성)" if curr_rsi <= 30 else "중립"
                
                st.write(f"**📈 RSI (상대강도지수):** {curr_rsi:.1f} / 100")
                st.info(f"💡 **AI 해석:** 현재 RSI 지표는 **'{rsi_status}'** 구간입니다. (70 이상 매도 고려, 30 이하 매수 고려)")
                
                bb_width = ((df['Upper_BB'].iloc[-1] - df['Lower_BB'].iloc[-1]) / df['MA20'].iloc[-1]) * 100
                st.write(f"**🌊 볼린저 밴드 폭:** {bb_width:.1f}%")

            with tab3:
                volatility = df['stck_clpr'].pct_change().std()
                v_f = volatility * 100
                st.write(f"**현재 변동성:** {v_f:.2f}%")
                
                strat = {
                    "초단기 (3일)": [int(curr_p*0.99), int(curr_p*(1+0.02*v_f)), int(curr_p*0.97)],
                    "단기 (1개월)": [int(curr_p*0.97), int(curr_p*(1+0.05*v_f)), int(curr_p*0.93)],
                    "장기 (1년+)": [int(curr_p*0.90), int(curr_p*(1+0.30*v_f)), int(curr_p*0.75)]
                }
                s_df = pd.DataFrame(strat, index=["추천 매수가", "목표가", "손절가"])
                st.table(s_df.style.format("{:,}원"))

            with tab4:
                try:
                    enc_name = urllib.parse.quote(target_name)
                    rss_url = f"https://news.google.com/rss/search?q={enc_name}&hl=ko&gl=KR&ceid=KR:ko"
                    root = ET.fromstring(requests.get(rss_url).content)
                    for item in root.findall('.//item')[:6]:
                        title = item.find('title').text
                        link = item.find('link').text
                        pub_date = item.find('pubDate').text
                        date_str = pub_date[:16]
                        st.markdown(f"🔹 **[{title}]({link})**")
                        st.caption(f"📅 {date_str}")
                except: st.write("뉴스를 불러올 수 없습니다.")

        except Exception as e:
            st.error(f"데이터 수신 중 오류 발생: {e}")
