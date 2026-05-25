import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import timedelta
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# --- CẤU HÌNH TRANG ---
st.set_page_config(page_title="Greenhouse Pro Max", layout="wide")
st.title("🌿 Hệ Thống Giám Sát Nhà Kính (Bản Mượt Triệt Để)")

# --- HÀM GỬI EMAIL ---
def send_email_alert(sender_mail, app_password, receiver_mail, vpd, status, temp, humi):
    try:
        msg = MIMEMultipart()
        msg['Subject'] = f"🚨 CẢNH BÁO VPD: {status}"
        body = f"📍 TRẠNG THÁI: {status}\nVPD: {vpd} kPa\nNhiệt độ: {temp}°C\nĐộ ẩm: {humi}%"
        msg.attach(MIMEText(body, 'plain', 'utf-8'))
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(sender_mail, app_password)
        server.sendmail(sender_mail, receiver_mail, msg.as_string())
        server.quit()
        return True
    except: return False

# --- TÍNH VPD ---
def calculate_vpd(temp, humi):
    if pd.isna(temp) or pd.isna(humi): return None
    vpsat = 0.61078 * np.exp((17.27 * temp) / (temp + 237.3))
    vpair = vpsat * (humi / 100)
    return round(vpsat - vpair, 2)

def get_greenhouse_advice(vpd, stage, s_min, s_max):
    if pd.isna(vpd): return "N/A", "Chờ dữ liệu...", "#808080"
    if vpd < 0.8: return "🔵 QUÁ THẤP", "Độ ẩm quá cao!", "#1E90FF"
    if 0.8 <= vpd <= 1.2: return "🟢 LÝ TƯỞNG", "Cây phát triển tốt.", "#00C851"
    return "🔴 QUÁ CAO", "Cây đang stress nhiệt!", "#FF4B4B"

# --- XỬ LÝ DỮ LIỆU & LỌC NHIỄU "CỘT ĐÌNH" ---
def process_data(file):
    try:
        df = pd.read_json(file)
    except: return pd.DataFrame()
    if 'Thời gian' in df.columns:
        df['Thời gian'] = pd.to_datetime(df['Thời gian'].astype(str).str.replace('-', ' ', n=2).str.replace('-', ':'), errors='coerce', utc=True).dt.tz_localize(None)
        df = df.dropna(subset=['Thời gian']).sort_values('Thời gian')
    t_cols, h_cols = [c for c in ['Nhiệt Độ', 'tempKK'] if c in df.columns], [c for c in ['Độ ẩm', 'humiKK'] if c in df.columns]
    if t_cols: df['temp'] = df[t_cols].bfill(axis=1).iloc[:, 0]
    if h_cols: df['humi'] = df[h_cols].bfill(axis=1).iloc[:, 0]
    for col in ['temp', 'humi']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col].astype(str).str.extract(r'(\d+\.?\d*)')[0], errors='coerce')
            if col == 'temp':
                df.loc[df[col] > 150, col] = df[col] / 10 
                df.loc[(df[col] >= 45) & (df[col] <= 120), col] = (df[col] - 32) * 5/9 
    df = df.dropna(subset=['temp', 'humi']).copy()
    
    # LỌC NHIỄU MẠNH: Loại bỏ các điểm nhảy vọt bất thường (>5 đơn vị so với điểm trước)
    if len(df) > 5:
        for c in ['temp', 'humi']:
            diff = df[c].diff().abs()
            df.loc[diff > 5, c] = np.nan # Đánh dấu điểm nhiễu là NaN
            df[c] = df[c].interpolate().ffill().bfill() # Vẽ lại đường mượt qua điểm đó
            
    if not df.empty: df['VPD'] = df.apply(lambda r: calculate_vpd(r['temp'], r['humi']), axis=1)
    return df

# --- GIAO DIỆN ---
with st.sidebar:
    st.header("📧 Cấu hình")
    u_mail, u_pass, t_mail = st.text_input("Gmail gửi:"), st.text_input("Pass:", type="password"), st.text_input("Gmail nhận:")
    uploaded_file = st.file_uploader("Tải JSON", type=['json'])

if uploaded_file:
    df = process_data(uploaded_file)
    if not df.empty:
        st.sidebar.header("🔍 Lọc")
        df['Tháng'] = df['Thời gian'].dt.strftime('%m/%Y')
        sel_m = st.sidebar.multiselect("Tháng:", df['Tháng'].unique(), default=df['Tháng'].unique()[-1:])
        df_work = df[df['Tháng'].isin(sel_m)].copy()
        
        growth_stage = st.sidebar.radio("Giai đoạn:", ["🌱 Cây con", "🌿 Sinh trưởng", "🍅 Ra hoa"], index=1)
        stt_list = ["Tất cả"] + sorted(df_work['STT'].unique().tolist())
        sel_stt = st.sidebar.selectbox("📍 Trạm:", stt_list)
        if sel_stt != "Tất cả": df_work = df_work[df_work['STT'] == sel_stt]
        
        def_val = (0.4, 0.8) if "Cây con" in growth_stage else (0.8, 1.2)
        safe_range = st.sidebar.slider("🎚️ VPD An toàn", 0.0, 3.0, def_val, 0.1)
        
        df_valid = df_work.dropna(subset=['VPD'])
        if not df_valid.empty:
            last = df_valid.iloc[-1]
            status, advice, color = get_greenhouse_advice(last['VPD'], growth_stage, safe_range[0], safe_range[1])
            
            c1, c2, c3 = st.columns([1, 1.2, 1.8])
            c1.metric("Nhiệt độ", f"{round(last['temp'], 1)}°C"), c1.metric("Độ ẩm", f"{round(last['humi'], 1)}%")
            c2.markdown(f'<div style="background-color:{color};padding:15px;border-radius:10px;color:white;text-align:center;"><h3>VPD: {last["VPD"]}</h3><b>{status}</b></div>', unsafe_allow_html=True)
            c3.info(advice)

            # BIỂU ĐỒ SẠCH - DẢI MÀU ĐẬM - ĐƯỜNG XANH LÁ
            fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.1)
            fig.add_trace(go.Scatter(x=df_valid['Thời gian'], y=df_valid['VPD'], name="VPD", line=dict(color='green', width=3)), row=1, col=1)
            # Dải màu đậm (opacity 0.4)
            fig.add_hrect(y0=0, y1=0.8, fillcolor="rgba(30, 144, 255, 0.4)", line_width=0, row=1, col=1)
            fig.add_hrect(y0=0.8, y1=1.2, fillcolor="rgba(0, 200, 81, 0.4)", line_width=0, row=1, col=1)
            fig.add_hrect(y0=1.2, y1=3.0, fillcolor="rgba(255, 75, 75, 0.4)", line_width=0, row=1, col=1)
            
            fig.add_trace(go.Scatter(x=df_valid['Thời gian'], y=df_valid['temp'], name="Temp"), row=2, col=1)
            fig.add_trace(go.Scatter(x=df_valid['Thời gian'], y=df_valid['humi'], name="Humi"), row=2, col=1)
            fig.update_layout(height=550, template="plotly_white")
            st.plotly_chart(fig, use_container_width=True)
            
            st.table(df_valid[['temp', 'humi', 'VPD']].agg(['max', 'min', 'mean']).round(2))
            st.dataframe(df_valid[['Thời gian', 'STT', 'temp', 'humi', 'VPD']].sort_values('Thời gian', ascending=False), use_container_width=True)
        else: st.error("🚨 Lỗi dữ liệu.")
else: st.info("👈 Tải file đi.")
