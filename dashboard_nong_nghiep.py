import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime
import time
import random

# --- CẤU HÌNH DASHBOARD ---
st.set_page_config(page_title="Greenhouse Smart Monitor", layout="wide")
st.title("🌿 Hệ Thống Giám Sát Nhà Kính ")

# --- 1. HÀM TÍNH TOÁN & LOGIC ---
def calculate_vpd(temp, humi):
    if pd.isna(temp) or pd.isna(humi): return None
    # Áp suất hơi bão hòa (kPa)
    vpsat = 0.61078 * np.exp((17.27 * temp) / (temp + 237.3))
    # Áp suất hơi thực tế (kPa)
    vpair = vpsat * (humi / 100)
    return round(vpsat - vpair, 2)

def get_advice(vpd, stage):
    if vpd is None: return "N/A", "Chờ dữ liệu...", "#808080"
    # Ngưỡng lý tưởng
    if "Cây con" in stage: i_min, i_max = 0.4, 0.8
    elif "Sinh trưởng" in stage: i_min, i_max = 0.8, 1.2
    else: i_min, i_max = 1.2, 1.5

    if vpd < i_min - 0.2: return "🔴 QUÁ THẤP", "Nguy cơ nấm bệnh! Tăng nhiệt/giảm ẩm.", "#FF4B4B"
    if i_min <= vpd <= i_max: return "🟢 LÝ TƯỞNG", "Cây đang phát triển rất tốt.", "#00C851"
    if vpd > i_max + 0.3: return "🔴 QUÁ CAO", "Stress nhiệt nặng! Cần phun sương làm mát.", "#8B0000"
    return "🟡 HƠI LỆCH", "Cần điều chỉnh nhẹ thiết bị.", "#FFA500"

# --- 2. QUẢN LÝ BỘ NHỚ ---
if 'sim_data' not in st.session_state:
    st.session_state.sim_data = pd.DataFrame(columns=['Thời gian', 'STT', 'temp', 'humi', 'VPD'])

# --- 3. THANH ĐIỀU KHIỂN (SIDEBAR) ---
st.sidebar.header("🛠️ Cài đặt hệ thống")
sim_on = st.sidebar.toggle("Kích hoạt Giả lập (30s)", value=True)

st.sidebar.subheader("⚙️ Hiệu chỉnh Offset")
off_t = st.sidebar.slider("Bù Nhiệt độ (°C)", -5.0, 5.0, 0.0, 0.1)
off_h = st.sidebar.slider("Bù Độ ẩm (%)", -10.0, 10.0, 0.0, 1.0)

st.sidebar.markdown("---")
stage = st.sidebar.radio("Giai đoạn phát triển:", ["🌱 Cây con", "🌿 Sinh trưởng", "🍅 Ra hoa"], index=1)

# --- 4. XỬ LÝ DỮ LIỆU ---
df = pd.DataFrame()

if sim_on:
    # Thuật toán Random Walk mượt mà
    if st.session_state.sim_data.empty:
        curr_t, curr_h = 26.5, 75.0
    else:
        curr_t = st.session_state.sim_data.iloc[-1]['temp']
        curr_h = st.session_state.sim_data.iloc[-1]['humi']
    
    # Biến thiên nhỏ, không bị "lỏ"
    new_t = round(curr_t + random.uniform(-0.4, 0.4) + off_t, 2)
    new_h = round(curr_h + random.uniform(-1.2, 1.2) + off_h, 2)
    
    # Khóa giới hạn thực tế nhà kính
    new_t = max(18.0, min(36.0, new_t))
    new_h = max(45.0, min(95.0, new_h))
    
    new_row = pd.DataFrame([{
        'Thời gian': datetime.now(),
        'STT': 'SENSOR-01',
        'temp': new_t,
        'humi': new_h,
        'VPD': calculate_vpd(new_t, new_h)
    }])
    
    st.session_state.sim_data = pd.concat([st.session_state.sim_data, new_row], ignore_index=True).tail(30)
    df = st.session_state.sim_data.copy()
else:
    st.info("Chế độ giả lập đang tắt. Vui lòng bật ở thanh bên.")

# --- 5. HIỂN THỊ DASHBOARD ---
if not df.empty:
    last = df.iloc[-1]
    stat, adv, color = get_advice(last['VPD'], stage)
    
    # Khu vực Widget
    st.subheader(f"📍 Trạng thái (Cập nhật lúc: {last['Thời gian'].strftime('%H:%M:%S')})")
    c1, c2, c3 = st.columns([1, 1, 2])
    
    c1.metric("Nhiệt độ hiệu chỉnh", f"{last['temp']} °C", f"{off_t} °C")
    c1.metric("Độ ẩm hiệu chỉnh", f"{last['humi']} %", f"{off_h} %")
    
    # HTML Box sửa lỗi syntax
    vpd_box = f"""
    <div style="padding:20px; border-radius:12px; background-color:{color}; color:white; text-align:center;">
        <div style="font-size:14px; opacity:0.8;">CHỈ SỐ VPD</div>
        <div style="font-size:32px; font-weight:bold;">{last['VPD']} kPa</div>
        <div style="font-size:18px; margin-top:5px;">{stat}</div>
    </div>
    """
    c2.markdown(vpd_box, unsafe_allow_html=True)
    c3.warning(f"**Chỉ đạo vận hành:** {adv}")

    # Biểu đồ Realtime
    st.markdown("---")
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.1)
    fig.add_trace(go.Scatter(x=df['Thời gian'], y=df['VPD'], name="VPD", line=dict(color='green', width=3)), row=1, col=1)
    fig.add_trace(go.Scatter(x=df['Thời gian'], y=df['temp'], name="Nhiệt độ", line=dict(color='red')), row=2, col=1)
    fig.add_trace(go.Scatter(x=df['Thời gian'], y=df['humi'], name="Độ ẩm", line=dict(color='blue')), row=2, col=1)
    fig.update_layout(height=450, hovermode="x unified", margin=dict(t=20, b=20))
    st.plotly_chart(fig, use_container_width=True)

    # Bảng lịch sử có tô màu
    st.subheader("📋 Nhật ký dữ liệu (Mốc an toàn: 0.5 - 1.5 kPa)")
    
    def style_vpd(val):
        return 'background-color: #ffcccc; color: #900;' if (val < 0.5 or val > 1.5) else ''

    table_df = df.sort_values('Thời gian', ascending=False)
    # Fix AttributeError bằng cách ép kiểu pd.to_datetime
    table_df['Thời gian'] = pd.to_datetime(table_df['Thời gian']).dt.strftime('%H:%M:%S')

    st.dataframe(
        table_df.style.map(style_vpd, subset=['VPD']),
        use_container_width=True, hide_index=True
    )
    
    # Tự động reload sau 30s
    if sim_on:
        time.sleep(30)
        st.rerun()
