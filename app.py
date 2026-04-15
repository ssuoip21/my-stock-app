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

# 1. 앱 설정 (모바일 최적화 레이아웃)
st.set_page_config(page_title="스마트 주식 비서", layout="wide")

st.markdown("""
    <style>
    .main .block-container { padding-top: 1rem; padding-bottom: 1rem; padding-left: 0.5rem; padding-right: 0.5rem; }
    div[data-testid="stMetric"] { background-color: #ffffff; border: 1px solid #f0f2f6; padding: 10px; border-radius: 10px; }
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

# 3. 상단 검색 및 설정
with st.expander("⚙️ 종목 검색 및 설정", expanded=True):
    col1, col2 = st.columns([2, 1])
    with col1:
        user_input = st.text_input("종목명 또는 코드 입력 (예: 삼성전기, 009150)", value="삼성전자")
        timeframe = st.radio("차트 주기", ("일봉", "주봉", "월봉"), horizontal=True)
    with col2:
        up_color = st.color_picker("상승 색상 (양봉)", "#FF4136")
        down_color = st.color_picker("하락 색상 (음봉)", "#0074D9")

tf_map = {"일봉": "D", "주봉": "W", "월봉": "M"}
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
            st.info(f"💡 '{user_input}'(이)가 포함된 종목을 찾았습니다. 아래에서 선택해주세요.")
            selected_match = st.selectbox("정확한 종목 선택", ["여기를 눌러 선택하세요..."] + matches)
            if selected_match != "여기를 눌러 선택하세요...":
                target_code = STOCK_DICT[selected_match]
                target_name = selected_match
        else:
            st.error("❌ 일치하는 상장 종목이 없습니다. 정확한 이름이나 6자리 코드를 입력해주세요.")

# 4. 메인 리포트 시작
if target_code:
    with st.spinner(f"{target_name} 데이터 분석 중..."):
        try:
            price_resp = broker.fetch_price(target_code)['output']
            curr_p = int(price_resp['stck_prpr'])
            diff = int(price_resp['prdy_vrss'])
            rate = float(price_resp['prdy_ctrt'])
            
            end_d = datetime.now().strftime("%Y%m%d")
            start_d = (datetime.now() - timedelta(days=500)).strftime("%Y%m%d")
            chart_res = broker.fetch_ohlcv(target_code, tf_map[timeframe], start_d, end_d)['output2']
            
            df = pd.DataFrame(chart_res)
            df['date'] = pd.to_datetime(df['stck_bsop_date'])
            for col in ['stck_clpr', 'stck_oprc', 'stck_hgpr', 'stck_lwpr', 'acml_vol']:
                df[col] = pd.to_numeric(df[col])
            
            df = df.sort_values(by='date').reset_index(drop=True)
            df['date_str'] = df['date'].dt.strftime('%Y-%m-%d')
            
            df['MA5'] = df['stck_clpr'].rolling(window=5).mean()
            df['MA20'] = df['stck_clpr'].rolling(window=20).mean()

            view_limit = df.tail(30)
            min_y = view_limit['stck_lwpr'].min()
            max_y = view_limit['stck_hgpr'].max()
            y_margin = (max_y - min_y) * 0.05
            y_range = [min_y - y_margin, max_y + y_margin]

            st.write(f"### 📈 {target_name} ({target_code})")
            
            m1, m2 = st.columns(2)
            m1.metric("현재가", f"{curr_p:,}원", f"{diff:,}원 ({rate:+.2f}%)")
            m2.metric("거래량", f"{int(price_resp['acml_vol']):,}주")

            fig = make_subplots(
                rows=2, cols=1, shared_xaxes=True, 
                vertical_spacing=0.03, row_heights=[0.7, 0.3]
            )

            fig.add_trace(go.Candlestick(
                x=df['date_str'], open=df['stck_oprc'], high=df['stck_hgpr'],
                low=df['stck_lwpr'], close=df['stck_clpr'],
                increasing_line_color=up_color, decreasing_line_color=down_color,
                name='주가'
            ), row=1, col=1)
            
            fig.add_trace(go.Scatter(x=df['date_str'], y=df['MA5'], name='5일선', line=dict(color='orange', width=1)), row=1, col=1)
            fig.add_trace(go.Scatter(x=df['date_str'], y=df['MA20'], name='20일선', line=dict(color='purple', width=1)), row=1, col=1)

            vol_colors = np.where(df['stck_clpr'] >= df['stck_oprc'], up_color, down_color)
            fig.add_trace(go.Bar(
                x=df['date_str'], y=df['acml_vol'],
                marker_color=vol_colors, name='거래량'
            ), row=2, col=1)
            
            fig.update_layout(
                height=550, template='plotly_white', margin=dict(l=0, r=0, t=10, b=0),
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                yaxis=dict(range=y_range, fixedrange=False, side='right', showgrid=True, gridcolor='#f0f0f0'),
                yaxis2=dict(side='right', showgrid=False),
                dragmode='pan' # [핵심] 터치 및 드래그 시 확대(Zoom) 대신 화면 이동(Pan) 모드 활성화
            )
            
            zoom_start = max(0, len(df) - 30)
            fig.update_xaxes(
                type='category', 
                range=[zoom_start, len(df)], 
                rangeslider_visible=False,
                showgrid=False
            )

            st.plotly_chart(fig, use_container_width=True, config={'scrollZoom': True, 'displayModeBar': False})

            st.divider()
            tab1, tab2, tab3 = st.tabs(["📊 수급동향", "📰 뉴스피드", "🎯 투자전략"])
            
            with tab1:
                try:
                    h = {'User-Agent': 'Mozilla/5.0'}
                    n_url = f"https://finance.naver.com/item/frgn.naver?code={target_code}"
                    n_res = requests.get(n_url, headers=h, timeout=5)
                    n_res.encoding = 'euc-kr'
                    rows = BeautifulSoup(n_res.text, 'html.parser').select('table.type2 tr')
                    t_html = '<div style="overflow-x:auto;"><table style="width:100%; border-collapse:collapse; font-size:12px; text-align:center;">'
                    t_html += '<tr style="background:#f8f9fa;"><th>날짜</th><th>개인</th><th>외인</th><th>기관</th></tr>'
                    count = 0
                    for r in rows:
                        tds = r.select('td')
                        if len(tds) == 9 and tds[0].text.strip():
                            fv, iv = int(tds[6].text.strip().replace(',','')), int(tds[5].text.strip().replace(',',''))
                            pv = -(fv + iv)
                            def s(v): return f'color:{"#FF4136" if v>0 else "#0074D9" if v<0 else "black"}'
                            t_html += f'<tr><td>{tds[0].text[5:]}</td><td style="{s(pv)}">{pv:+,}</td><td style="{s(fv)}">{fv:+,}</td><td style="{s(iv)}">{iv:+,}</td></tr>'
                            count += 1
                            if count >= 7: break
                    st.markdown(t_html + '</table></div>', unsafe_allow_html=True)
                except: st.write("수급 데이터 일시 오류")

            with tab2:
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

        except Exception as e:
            st.error(f"데이터 수신 중 오류 발생: {e}")
