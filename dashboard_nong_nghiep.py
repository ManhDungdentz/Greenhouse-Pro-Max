import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import timedelta
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# --- CẤU HÌNH GMAIL (THÊM MỚI) ---
GMAIL_USER = "email_cua_ong@gmail.com" 
GMAIL_PASSWORD = "ma_16_chu_so" # Mật khẩu ứng dụng Google
RECEIVER_EMAIL = "email_nhan_canh_bao@gmail.com"

def send_alert(vpd, status, t, h):
    try:
        msg = MIMEMultipart()
        msg['Subject'] = f"🚨 CẢNH BÁO VPD: {status}"
        body = f"Chỉ số nhà kính bất thường:\nVPD: {vpd} kPa\nNhiệt độ: {t}°C\nĐộ ẩm: {h}%"
        msg.attach(MIMEText(body, 'plain'))
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(GMAIL_USER, GMAIL_PASSWORD)
        server.sendmail(GMAIL_USER, RECEIVER_EMAIL, msg.as_string())
        server.quit()
        return True
    except: return False

st.set_page_config(page_title="Greenhouse Pro Max", layout="wide")
st.title("🌿 Hệ Thống Giám Sát Nhà Kính (Bản Gốc + Mail)")

# --- 1. TÍNH TOÁN VPD (GIỮ NGUYÊN) ---
def calculate_vpd(temp, humi):
    if pd.isna(temp) or pd.isna(humi): return None
    vpsat = 0.61078 * np.exp((17.27 * temp) / (temp + 237.3))
    vpair = vpsat * (humi / 100)
    return round(vpsat - vpair, 2)

def get_greenhouse_advice(vpd, stage):
    if pd.isna(vpd): return "N/A", "Đang chờ dữ liệu chuẩn...", "#808080"
    if "Cây con" in stage: ideal_min, ideal_max = 0.4, 0.8
    elif "Sinh trưởng" in stage: ideal_min, ideal_max = 0.8, 1.2
    else: ideal_min, ideal_max = 1.2, 1.5

    if vpd < ideal_min - 0.2: return "🔴 QUÁ THẤP", "Nguy cơ nấm bệnh! Tăng nhiệt hoặc giảm ẩm.", "#FF4B4B"
    if ideal_min <= vpd <= ideal_max: return "🟢 LÝ TƯỞNG", "Cây đang phát triển tốt.", "#00C851"
    if vpd > ideal_max + 0.3: return "🔴 QUÁ CAO", "Stress nhiệt nặng! Giảm nhiệt, tăng ẩm khẩn cấp.", "#8B0000"
    return "🟡 HƠI LỆCH", "Cần điều chỉnh nhẹ thiết bị.", "#FFA500"

# --- 2. XỬ LÝ DỮ LIỆU (GIỮ NGUYÊN + FIX TIMEZONE) ---
def process_data(file):
    try:
        df = pd.read_json(file)
    except: return pd.DataFrame()

    if 'Thời gian' in df.columns:
        df['Thời gian'] = pd.to_datetime(df['Thời gian'].astype(str).str.replace('-', ' ', n=2).str.replace('-', ':'), errors='coerce', utc=True).dt.tz_localize(None)
        df = df.dropna(subset=['Thời gian']).sort_values('Thời gian')
    
    t_cols = [c for c in ['Nhiệt Độ', 'tempKK'] if c in df.columns]
    if t_cols: df['temp'] = df[t_cols].bfill(axis=1).iloc[:, 0]
    h_cols = [c for c in ['Độ ẩm', 'humiKK'] if c in df.columns]
    if h_cols: df['humi'] = df[h_cols].bfill(axis=1).iloc[:, 0]
        
    for col in ['temp', 'humi']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col].astype(str).str.extract(r'(\d+\.?\d*)')[0], errors='coerce')
            if col == 'temp':
                df.loc[df[col] > 150, col] = df[col] / 10 
                df.loc[(df[col] >= 45) & (df[col] <= 120), col] = (df[col] - 32) * 5/9 
                df.loc[(df[col] < 5) | (df[col] > 55), col] = np.nan 
            if col == 'humi':
                df.loc[(df[col] < 20) | (df[col] > 100), col] = np.nan 
    
    df = df.dropna(subset=['temp', 'humi']).copy()
    if not df.empty:
        df['VPD'] = df.apply(lambda r: calculate_vpd(r['temp'], r['humi']), axis=1)
    return df

# --- 3. GIAO DIỆN CHÍNH (GIỮ NGUYÊN CỦA ÔNG) ---
uploaded_file = st.sidebar.file_uploader("Tải file JSON", type=['json'])

if uploaded_file:
    df = process_data(uploaded_file)
    if not df.empty:
        # DANH MỤC THÁNG
        st.sidebar.subheader("📅 Dữ liệu hợp lệ")
        df['Tháng'] = df['Thời gian'].dt.strftime('%m/%Y')
        st.sidebar.table(df.groupby('Tháng').size().reset_index(name='Số dòng'))

        # BỘ LỌC THỜI GIAN
        st.sidebar.header("🔍 Lọc dữ liệu")
        filter_mode = st.sidebar.radio("Lọc theo:", ["Tất cả", "Tháng", "Khoảng ngày"])
        if filter_mode == "Tháng":
            sel_m = st.sidebar.multiselect("Chọn tháng:", df['Tháng'].unique(), default=df['Tháng'].unique()[-1:])
            df_work = df[df['Tháng'].isin(sel_m)].copy()
        elif filter_mode == "Khoảng ngày":
            c1, c2 = st.sidebar.columns(2)
            start = pd.to_datetime(c1.date_input("Từ", df['Thời gian'].min()))
            end = pd.to_datetime(c2.date_input("Đến", df['Thời gian'].max())) + timedelta(days=1)
            df_work = df[(df['Thời gian'] >= start) & (df['Thời gian'] < end)].copy()
        else:
            df_work = df.copy()

        # CHỌN TRẠM & GIAI ĐOẠN
        st.sidebar.markdown("---")
        growth_stage = st.sidebar.radio("Giai đoạn:", ["🌱 Cây con", "🌿 Sinh trưởng", "🍅 Ra hoa"], index=1)
        stt_list = ["Tất cả"] + sorted(df_work['STT'].unique().tolist())
        sel_stt = st.sidebar.selectbox("📍 Chọn Trạm:", stt_list)
        if sel_stt != "Tất cả": df_work = df_work[df_work['STT'] == sel_stt]

        df_valid = df_work.dropna(subset=['VPD'])
        
        if not df_valid.empty:
            last = df_valid.iloc[-1]
            status, advice, color = get_greenhouse_advice(last['VPD'], growth_stage)
            
            st.subheader(f"📍 Thông báo trạng thái")
            col1, col2, col3 = st.columns([1, 1, 2])
            col1.metric("Nhiệt độ (chuẩn)", f"{round(last['temp'], 1)} °C")
            col1.metric("Độ ẩm (chuẩn)", f"{round(last['humi'], 1)} %")
            
            html_box = f'<div style="padding:20px; border-radius:10px; background-color:{color}; color:white; text-align:center;"><span style="font-size:24px; font-weight:bold;">VPD: {last['VPD']} kPa</span><br><span style="font-size:16px;">{status}</span></div>'
            col2.markdown(html_box, unsafe_allow_html=True)
            col3.warning(f"**Chỉ đạo vận hành:** {advice}")

            # NÚT GỬI MAIL (CHÈN THÊM VÀO GIỮA)
            if "🔴" in status:
                if st.button("📧 Gửi Email Cảnh Báo"):
                    if send_alert(last['VPD'], status, last['temp'], last['humi']):
                        st.success("Đã gửi mail!")
                    else: st.error("Lỗi gửi mail!")

            # BIỂU ĐỒ (Y HỆT CŨ)
            st.markdown("---")
            fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.1)
            fig.add_trace(go.Scatter(x=df_valid['Thời gian'], y=df_valid['VPD'], name="VPD (kPa)", line=dict(color='green')), row=1, col=1)
            fig.add_trace(go.Scatter(x=df_valid['Thời gian'], y=df_valid['temp'], name="Nhiệt độ (°C)"), row=2, col=1)
            fig.add_trace(go.Scatter(x=df_valid['Thời gian'], y=df_valid['humi'], name="Độ ẩm (%)"), row=2, col=1)
            fig.update_layout(height=500, hovermode="x unified")
            st.plotly_chart(fig, use_container_width=True)

            # BẢNG THỐNG KÊ (Y HỆT CŨ)
            st.subheader("📋 Bảng Dữ Liệu Sau Khi Lọc Sạch")
            summary = df_valid[['temp', 'humi',
