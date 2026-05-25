import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# --- 1. CẤU HÌNH TRANG ---
st.set_page_config(page_title="Greenhouse Pro Max", layout="wide")
st.title("🌿 Hệ Thống Giám Sát Nhà Kính")

# --- 2. HÀM GỬI EMAIL ---
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
    except:
        return False

# --- 3. TÍNH VPD ---
def calculate_vpd(temp, humi):
    if pd.isna(temp) or pd.isna(humi) or humi <= 5: 
        return None
    vpsat = 0.61078 * np.exp((17.27 * temp) / (temp + 237.3))
    vpair = vpsat * (humi / 100)
    return round(max(0, vpsat - vpair), 2)

# --- 4. NGƯỠNG VPD THEO TỪNG LOẠI CÂY (NGƯỠNG ĐỎ > 1.5) ---
CROP_VPD = {
    "🌶️ Ớt chuông": {"low": 0.6, "ideal_min": 0.8, "ideal_max": 1.2, "warn_max": 1.5},
    "🥒 Dưa leo":    {"low": 0.7, "ideal_min": 0.9, "ideal_max": 1.3, "warn_max": 1.5},
    "🍈 Dưa lưới":   {"low": 0.8, "ideal_min": 1.0, "ideal_max": 1.4, "warn_max": 1.5},
    "🍅 Cà chua":    {"low": 0.7, "ideal_min": 0.8, "ideal_max": 1.2, "warn_max": 1.5},
}

def get_advice(vpd, crop):
    if pd.isna(vpd): return "N/A", "Chờ dữ liệu...", "#808080"
    c = CROP_VPD.get(crop)
    if vpd > 1.5:
        return "🔴 QUÁ CAO", "Stress nhiệt nặng, cần hạ nhiệt gấp!", "#FF4B4B"
    if vpd < c["low"]:
        return "🔵 QUÁ THẤP", "Độ ẩm quá cao, nguy cơ nấm bệnh.", "#1E90FF"
    if c["ideal_min"] <= vpd <= c["ideal_max"]:
        return "🟢 LÝ TƯỞNG", "Cây đang trong điều kiện phát triển tốt nhất.", "#00C851"
    return "🟡 CẢNH BÁO", "VPD hơi lệch, cần điều chỉnh thiết bị.", "#FFA500"

# --- 5. XỬ LÝ DỮ LIỆU & KHỬ NHIỄU "CỘT ĐÌNH" ---
def process_data(file):
    try:
        df = pd.read_json(file)
    except:
        return pd.DataFrame()

    if 'Thời gian' in df.columns:
        df['Thời gian'] = pd.to_datetime(df['Thời gian'].astype(str).str.replace('-', ' ', n=2).str.replace('-', ':'), 
                                         errors='coerce', utc=True).dt.tz_localize(None)
        df = df.dropna(subset=['Thời gian']).sort_values('Thời gian')

    # Gộp các cột sensor
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
    
    # Khử nhiễu bằng Median Rolling
    df = df.dropna(subset=['temp', 'humi']).copy()
    if len(df) > 5:
        for c in ['temp', 'humi']:
            df[c] = df[c].rolling(window=5, center=True, min_periods=1).median()
            df[c] = df[c].interpolate().ffill().bfill()

    if not df.empty:
        df['VPD'] = df.apply(lambda r: calculate_vpd(r['temp'], r['humi']), axis=1)
    return df

# --- 6. GIAO DIỆN CHÍNH ---
with st.sidebar:
    st.header("⚙️ Cấu hình")
    u_mail = st.text_input("Gmail gửi:")
    u_pass = st.text_input("Mật khẩu ứng dụng:", type="password")
    t_mail = st.text_input("Gmail nhận:")
    st.divider()
    
    uploaded_file = st.file_uploader("📂 Tải file JSON", type=['json'])
    selected_crop = st.selectbox("🌱 Loại cây:", list(CROP_VPD.keys()))
    st.divider()

if uploaded_file:
    df = process_data(uploaded_file)
    if not df.empty:
        # Bộ lọc thời gian & trạm
        st.sidebar.header("🔍 Bộ lọc")
        df['Tháng'] = df['Thời gian'].dt.strftime('%m/%Y')
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

        stt_list = ["Tất cả"] + sorted(df_work['STT'].unique().tolist())
        sel_stt = st.sidebar.selectbox("📍 Chọn Trạm:", stt_list)
        if sel_stt != "Tất cả": df_work = df_work[df_work['STT'] == sel_stt]

        # Dashboard metrics
        df_valid = df_work.dropna(subset=['VPD'])
        if not df_valid.empty:
            last = df_valid.iloc[-1]
            status, advice, color = get_advice(last['VPD'], selected_crop)
            
            st.subheader(f"📍 Trạm: {last['STT']} (Dữ liệu cuối)")
            m1, m2, m3 = st.columns([1, 1.2, 1.8])
            m1.metric("Nhiệt độ", f"{round(last['temp'], 1)} °C")
            m1.metric("Độ ẩm", f"{round(last['humi'], 1)} %")
            m2.markdown(f'<div style="background-color:{color};padding:20px;border-radius:15px;color:white;text-align:center;">'
                        f'<h2>VPD: {last["VPD"]} kPa</h2><b>{status}</b></div>', unsafe_allow_html=True)
            m3.info(f"**Chỉ đạo:** {advice}")

            if st.button("📧 Gửi Email Cảnh Báo"):
                if send_email_alert(u_mail, u_pass, t_mail, last['VPD'], status, last['temp'], last['humi']):
                    st.success("✅ Đã gửi!")
                else: st.error("❌ Lỗi cấu hình!")

            # Biểu đồ mượt (Khóa trục Y)
            fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.1)
            fig.add_trace(go.Scatter(x=df_valid['Thời gian'], y=df_valid['VPD'], name="VPD", line=dict(color='green', width=3)), row=1, col=1)
            
            # Vẽ các dải màu ngưỡng mới
            fig.add_hrect(y0=0, y1=0.5, fillcolor="rgba(30, 144, 255, 0.2)", line_width=0, row=1, col=1)
            fig.add_hrect(y0=0.5, y1=1.5, fillcolor="rgba(0, 200, 81, 0.2)", line_width=0, row=1, col=1)
            fig.add_hrect(y0=1.5, y1=3.0, fillcolor="rgba(255, 75, 75, 0.2)", line_width=0, row=1, col=1)
            
            fig.add_trace(go.Scatter(x=df_valid['Thời gian'], y=df_valid['temp'], name="Nhiệt độ"), row=2, col=1)
            fig.add_trace(go.Scatter(x=df_valid['Thời gian'], y=df_valid['humi'], name="Độ ẩm"), row=2, col=1)
            
            fig.update_layout(height=550, template="plotly_white", hovermode='x unified')
            fig.update_yaxes(range=[0, 2.5], row=1, col=1)
            st.plotly_chart(fig, use_container_width=True)

            # Bảng dữ liệu
            st.subheader("📋 Chi tiết dữ liệu")
            def highlight(row):
                return ['background-color: #FFC7CE'] * len(row) if row['VPD'] > 1.5 else [''] * len(row)
            st.dataframe(df_valid[['Thời gian', 'STT', 'temp', 'humi', 'VPD']].sort_values('Thời gian', ascending=False).style.apply(highlight, axis=1), use_container_width=True)
        else:
            st.warning("Không có dữ liệu trong khoảng này.")
else:
    st.info("👈 Hãy tải file JSON từ thanh bên để bắt đầu.")
