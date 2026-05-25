import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import time

# --- CẤU HÌNH TRANG ---
st.set_page_config(page_title="Greenhouse Pro Max", layout="wide")
st.title("🌿 Hệ Thống Giám Sát Nhà Kính")

# --- HÀM GỬI EMAIL ---
def send_email_alert(sender_mail, app_password, receiver_mail, vpd, status, temp, humi):
    # (Giữ nguyên logic gửi mail của ông)
    try:
        msg = MIMEMultipart()
        msg['Subject'] = f"🚨 CẢNH BÁO VPD: {status}"
        body = f"📍 TRẠNG THÁI: {status}\nVPD: {vpd} kPa\nNhiệt độ: {temp}°C\nĐộ ẩm: {humi}%\n\nCảnh báo từ hệ thống giám sát."
        msg.attach(MIMEText(body, 'plain', 'utf-8'))
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(sender_mail, app_password)
        server.sendmail(sender_mail, receiver_mail, msg.as_string())
        server.quit()
        return True
    except:
        return False

# --- TÍNH VPD ---
def calculate_vpd(temp, humi):
    if pd.isna(temp) or pd.isna(humi): return None
    vpsat = 0.61078 * np.exp((17.27 * temp) / (temp + 237.3))
    vpair = vpsat * (humi / 100)
    return round(vpsat - vpair, 2)

# --- NGƯỠNG VPD THEO TỪNG LOẠI CÂY ---
CROP_VPD = {
    "🌶️ Ớt chuông": {"low": 0.6, "ideal_min": 0.8, "ideal_max": 1.2, "warn_max": 1.5, "note_low": "Ẩm cao, dễ nấm.", "note_ok": "Phát triển tốt.", "note_warn": "Hơi khô.", "note_high": "Stress nhiệt."},
    "🥒 Dưa leo": {"low": 0.7, "ideal_min": 0.9, "ideal_max": 1.3, "warn_max": 1.6, "note_low": "Dễ phấn trắng.", "note_ok": "Sinh trưởng tốt.", "note_warn": "Tăng phun sương.", "note_high": "Héo nhanh."},
    "🍈 Dưa lưới": {"low": 0.8, "ideal_min": 1.0, "ideal_max": 1.4, "warn_max": 1.8, "note_low": "Dễ nứt quả.", "note_ok": "Lý tưởng.", "note_warn": "Thông gió ngay.", "note_high": "Stress nước."},
    "🍅 Cà chua": {"low": 0.7, "ideal_min": 0.8, "ideal_max": 1.2, "warn_max": 1.5, "note_low": "Mốc sương.", "note_ok": "Đậu quả tốt.", "note_warn": "Rụng hoa.", "note_high": "Ngừng đậu quả."}
}

def get_greenhouse_advice(vpd, crop):
    if pd.isna(vpd): return "N/A", "Chờ dữ liệu...", "#808080"
    c = CROP_VPD.get(crop)
    if vpd < c["low"]: return "🔵 QUÁ THẤP", c["note_low"], "#1E90FF"
    if vpd < c["ideal_min"]: return "🟡 CẢNH BÁO", c["note_warn"], "#FFA500"
    if vpd <= c["ideal_max"]: return "🟢 LÝ TƯỞNG", c["note_ok"], "#00C851"
    if vpd <= c["warn_max"]: return "🟡 CẢNH BÁO", c["note_warn"], "#FFA500"
    return "🔴 QUÁ CAO", c["note_high"], "#FF4B4B"

# --- BIỂU ĐỒ ---
def draw_chart(df_chart, c_info):
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.1, subplot_titles=("VPD (kPa)", "Nhiệt độ & Độ ẩm"))
    fig.add_trace(go.Scatter(x=df_chart['Thời gian'], y=df_chart['VPD'], name="VPD", line=dict(color='#2E7D32', width=2)), row=1, col=1)
    
    # Vùng màu ngưỡng VPD
    fig.add_hrect(y0=0, y1=c_info["low"], fillcolor="rgba(30, 144, 255, 0.2)", line_width=0, row=1, col=1)
    fig.add_hrect(y0=c_info["ideal_min"], y1=c_info["ideal_max"], fillcolor="rgba(0, 200, 81, 0.2)", line_width=0, row=1, col=1)
    
    fig.add_trace(go.Scatter(x=df_chart['Thời gian'], y=df_chart['temp'], name="Nhiệt độ (°C)", line=dict(color='#E53935')), row=2, col=1)
    fig.add_trace(go.Scatter(x=df_chart['Thời gian'], y=df_chart['humi'], name="Độ ẩm (%)", line=dict(color='#1E88E5')), row=2, col=1)
    fig.update_layout(height=500, template="plotly_white", margin=dict(l=10, r=10, t=30, b=10))
    return fig

# =========================================================
# --- SIDEBAR ---
# =========================================================
with st.sidebar:
    st.header("⚙️ Cấu hình")
    mode = st.radio("Chế độ:", ["📂 Xem file JSON", "🎲 Mô phỏng Realtime"])
    selected_crop = st.selectbox("🌱 Loại cây:", list(CROP_VPD.keys()))
    c_info = CROP_VPD[selected_crop]
    
    st.divider()
    st.header("📧 Gmail Alert")
    u_mail = st.text_input("Gmail gửi:")
    u_pass = st.text_input("Mật khẩu app:", type="password")
    t_mail = st.text_input("Gmail nhận:")

# =========================================================
# --- MAIN LOGIC ---
# =========================================================

if mode == "📂 Xem file JSON":
    uploaded_file = st.sidebar.file_uploader("Tải file JSON", type=['json'])
    if uploaded_file:
        # (Tận dụng logic xử lý file của ông ở đây)
        st.info("Đang hiển thị dữ liệu từ file...")
    else:
        st.info("👈 Hãy tải file JSON hoặc chuyển sang chế độ Mô phỏng.")

else:
    # --- CHẾ ĐỘ MÔ PHỎNG REALTIME ---
    INTERVAL = 60 
    
    if 'rt_history' not in st.session_state:
        st.session_state.rt_history = pd.DataFrame(columns=['Thời gian', 'temp', 'humi', 'VPD'])
    
    # Khu vực hiển thị động
    metric_ph = st.empty()
    chart_ph = st.empty()
    table_ph = st.empty()
    timer_ph = st.empty()

    # Nút điều khiển
    run_sim = st.sidebar.toggle("▶️ Bắt đầu mô phỏng", value=True)

    while run_sim:
        # 1. Sinh dữ liệu mới
        if st.session_state.rt_history.empty:
            t, h = 28.0, 70.0
        else:
            t = round(st.session_state.rt_history.iloc[-1]['temp'] + np.random.uniform(-0.5, 0.5), 2)
            h = round(st.session_state.rt_history.iloc[-1]['humi'] + np.random.uniform(-2, 2), 2)
        
        t = np.clip(t, 15, 40)
        h = np.clip(h, 30, 95)
        vpd = calculate_vpd(t, h)
        new_row = pd.DataFrame([{'Thời gian': datetime.now().strftime("%H:%M:%S"), 'temp': t, 'humi': h, 'VPD': vpd}])
        
        st.session_state.rt_history = pd.concat([st.session_state.rt_history, new_row], ignore_index=True).tail(50)
        
        # 2. Hiển thị Metrics
        status, advice, color = get_greenhouse_advice(vpd, selected_crop)
        with metric_ph.container():
            col1, col2, col3 = st.columns([1, 1, 2])
            col1.metric("Nhiệt độ", f"{t} °C")
            col2.metric("Độ ẩm", f"{h} %")
            col3.markdown(f"""<div style="background:{color}; color:white; padding:10px; border-radius:5px; text-align:center;">
                          <h3 style='margin:0'>VPD: {vpd} kPa</h3><b>{status}</b></div>""", unsafe_allow_html=True)
            st.warning(f"💡 **Tư vấn:** {advice}")

        # 3. Vẽ biểu đồ
        chart_ph.plotly_chart(draw_chart(st.session_state.rt_history, c_info), use_container_width=True)
        
        # 4. Bảng dữ liệu
        table_ph.dataframe(st.session_state.rt_history.iloc[::-1], use_container_width=True)

        # 5. Đếm ngược
        for i in range(INTERVAL, 0, -1):
            timer_ph.caption(f"🔄 Cập nhật tiếp theo sau: {i} giây...")
            time.sleep(1)
            if not run_sim: break
    
    if not run_sim:
        st.warning("⏸️ Mô phỏng đang tạm dừng.")
