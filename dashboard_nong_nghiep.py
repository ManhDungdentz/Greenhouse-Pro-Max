import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import timedelta
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# --- CẤU HÌNH GMAIL ---
# Bạn cần tạo App Password tại: https://myaccount.google.com/apppasswords
GMAIL_USER = "your_email@gmail.com"  # Thay bằng email của bạn
GMAIL_PASSWORD = "your_app_password" # Thay bằng mật khẩu ứng dụng 16 ký tự
RECEIVER_EMAIL = "receiver_email@gmail.com" # Email nhận cảnh báo

def send_email_alert(vpd_value, status, temp, humi):
    try:
        msg = MIMEMultipart()
        msg['From'] = GMAIL_USER
        msg['To'] = RECEIVER_EMAIL
        msg['Subject'] = f"🚨 CẢNH BÁO NHÀ KÍNH: VPD {status}"

        body = f"""
        Hệ thống ghi nhận chỉ số bất thường:
        - VPD: {vpd_value} kPa ({status})
        - Nhiệt độ: {temp} °C
        - Độ ẩm: {humi} %
        - Thời gian: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')}
        
        Vui lòng kiểm tra lại thiết bị điều khiển nhà kính!
        """
        msg.attach(MIMEText(body, 'plain'))

        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(GMAIL_USER, GMAIL_PASSWORD)
        server.send_message(msg)
        server.quit()
        return True
    except Exception as e:
        print(f"Lỗi gửi mail: {e}")
        return False

st.set_page_config(page_title="Greenhouse Pro Max", layout="wide")
st.title("🌿 Hệ Thống Giám Sát Nhà Kính (Bản Full + Email)")

# --- 1. TÍNH TOÁN VPD ---
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

    if vpd < ideal_min - 0.2: 
        return "🔴 QUÁ THẤP", "Nguy cơ nấm bệnh! Tăng nhiệt hoặc giảm ẩm.", "#FF4B4B", True
    if ideal_min <= vpd <= ideal_max: 
        return "🟢 LÝ TƯỞNG", "Cây đang phát triển tốt.", "#00C851", False
    if vpd > ideal_max + 0.3: 
        return "🔴 QUÁ CAO", "Stress nhiệt nặng! Giảm nhiệt, tăng ẩm khẩn cấp.", "#8B0000", True
    return "🟡 HƠI LỆCH", "Cần điều chỉnh nhẹ thiết bị.", "#FFA500", False

# --- 2. XỬ LÝ & LÀM SẠCH DỮ LIỆU ---
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

# --- 3. GIAO DIỆN CHÍNH ---
uploaded_file = st.sidebar.file_uploader("Tải file JSON", type=['json'])

if uploaded_file:
    df = process_data(uploaded_file)
    if not df.empty:
        # Bộ lọc Sidebar (giữ nguyên logic cũ của bạn)
        st.sidebar.header("🔍 Lọc dữ liệu")
        growth_stage = st.sidebar.radio("Giai đoạn:", ["🌱 Cây con", "🌿 Sinh trưởng", "🍅 Ra hoa"], index=1)
        
        df_valid = df.dropna(subset=['VPD'])
        
        if not df_valid.empty:
            last = df_valid.iloc[-1]
            # Sửa hàm để nhận biết có cần gửi mail không
            status, advice, color, is_danger = get_greenhouse_advice(last['VPD'], growth_stage)
            
            st.subheader(f"📍 Thông báo trạng thái")
            # Hiển thị Metric...
            
            # --- LOGIC GỬI MAIL TỰ ĐỘNG ---
            if is_danger:
                if st.button("📧 Gửi cảnh báo ngay cho quản lý"):
                    with st.spinner('Đang gửi mail...'):
                        success = send_email_alert(last['VPD'], status, last['temp'], last['humi'])
                        if success: st.success("Đã gửi email cảnh báo thành công!")
                        else: st.error("Gửi mail thất bại. Kiểm tra cấu hình GMAIL_USER/PASSWORD.")

            # (Các phần Biểu đồ và Bảng dữ liệu giữ nguyên như bản cũ của bạn)
            # ... (Phần code biểu đồ của bạn bên dưới)
