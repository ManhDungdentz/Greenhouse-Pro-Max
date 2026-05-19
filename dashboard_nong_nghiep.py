import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime
import time
import random

# --- CẤU HÌNH ---
st.set_page_config(page_title="Greenhouse Monitoring Pro", layout="wide")

# --- 1. HÀM TÍNH TOÁN (Fix lỗi 0.0) ---
def calculate_vpd(temp, humi):
    if pd.isna(temp) or pd.isna(humi) or temp <= 0: return 0.0
    vpsat = 0.61078 * np.exp((17.27 * temp) / (temp + 237.3))
    vpair = vpsat * (humi / 100)
    return round(vpsat - vpair, 2)

def get_status_ui(vpd, stage):
    if "Cây con" in stage: i_min, i_max = 0.4, 0.8
    elif "Sinh trưởng" in stage: i_min, i_max = 0.8, 1.2
    else: i_min, i_max = 1.2, 1.5
    
    if vpd < i_min - 0.2: return "🔵 THẤP", "Nguy cơ nấm!", "#3498db"
    if i_min <= vpd <= i_max: return "🟢 LÝ TƯỞNG", "Cây khỏe mạnh.", "#2ecc71"
    return "🔴 CAO", "Stress nhiệt!", "#e74c3c"

# --- 2. XỬ LÝ DỮ LIỆU TỪ FILE (SIÊU TỰ ĐỘNG) ---
def process_data(file):
    try:
        df = pd.read_json(file)
        if df.empty: return pd.DataFrame()

        # Tự tìm cột Nhiệt độ (bất kể tên là gì)
        t_col = next((c for c in df.columns if any(k in c.lower() for k in ['temp', 'nhiệt', 't_kk'])), None)
        # Tự tìm cột Độ ẩm
        h_col = next((c for c in df.columns if any(k in c.lower() for k in ['humi', 'ẩm', 'h_kk'])), None)
        # Tự tìm cột Thời gian
        time_col = next((c for c in df.columns if any(k in c.lower() for k in ['thời', 'time', 'date'])), None)

        if t_col and h_col:
            # Ép kiểu số và làm sạch dữ liệu (Fix lỗi image_08dd02.png)
            df['temp'] = pd.to_numeric(df[t_col].astype(str).str.extract(r'(\d+\.?\d*)')[0], errors='coerce')
            df['humi'] = pd.to_numeric(df[h_col].astype(str).str.extract(r'(\d+\.?\d*)')[0], errors='coerce')
            
            # Xử lý số liệu "lỏ" (nhiệt độ quá cao do lỗi cảm biến)
            df.loc[df['temp'] > 150, 'temp'] = df['temp'] / 10
            df = df[(df['temp'] > 5) & (df['temp'] < 55)].copy() 

            if time_col:
                df['Thời gian'] = pd.to_datetime(df[time_col], errors='coerce')
                df = df.dropna(subset=['Thời gian']).sort_values('Thời gian')
            
            df['VPD'] = df.apply(lambda r: calculate_vpd(r['temp'], r['humi']), axis=1)
            return df, t_col, h_col
        return pd.DataFrame(), None, None
    except Exception as e:
        st.error(f"Lỗi đọc file JSON: {e}")
        return pd.DataFrame(), None, None

# --- 3. THANH ĐIỀU KHIỂN ---
with st.sidebar:
    st.header("📂 Nạp dữ liệu")
    uploaded_file = st.file_uploader("Nhét file JSON vào đây 👇", type=['json'])
    
    st.divider()
    sim_on = st.toggle("🚀 Chế độ Giả lập Realtime", value=False)
    if sim_on:
        st.info("Đang chạy Random Walk (Số cực mượt)")
        off_t = st.slider("Bù Nhiệt độ", -5.0, 5.0, 0.0)
        off_h = st.slider("Bù Độ ẩm", -10.0, 10.0, 0.0)
    
    st.divider()
    stage = st.radio("Giai đoạn cây:", ["🌱 Cây con", "🌿 Sinh trưởng", "🍅 Ra hoa"], index=1)

# --- 4. LOGIC CHÍNH ---
df_display = pd.DataFrame()

if uploaded_file:
    df_display, t_found, h_found = process_data(uploaded_file)
    if not df_display.empty:
        st.sidebar.success(f"✅ Đã nhận diện: {t_found} & {h_found}")
elif sim_on:
    if 'sim_store' not in st.session_state:
        st.session_state.sim_store = pd.DataFrame(columns=['Thời gian', 'temp', 'humi', 'VPD'])
    
    # Giả lập mượt mà (Random Walk) - fix image_08f74d.png
    prev_t = st.session_state.sim_store.iloc[-1]['temp'] if not st.session_state.sim_store.empty else 27.5
    prev_h = st.session_state.sim_store.iloc[-1]['humi'] if not st.session_state.sim_store.empty else 70.0
    
    new_t = round(prev_t + random.uniform(-0.3, 0.3), 1)
    new_h = round(prev_h + random.uniform(-1.0, 1.0), 1)
    
    # Giới hạn thực tế
    new_t = max(20.0, min(35.0, new_t))
    new_h = max(45.0, min(90.0, new_h))
    
    new_row = pd.DataFrame([{'Thời gian': datetime.now(), 'temp': new_t, 'humi': new_h, 'VPD': calculate_vpd(new_t, new_h)}])
    st.session_state.sim_store = pd.concat([st.session_state.sim_store, new_row], ignore_index=True).tail(40)
    df_display = st.session_state.sim_store

# --- 5. GIAO DIỆN HIỂN THỊ ---
st.title("🌿 Hệ Thống Giám Sát Nhà Kính")

if not df_display.empty:
    last = df_display.iloc[-1]
    label, advice, color = get_status_ui(last['VPD'], stage)
    
    # Hàng 1: Chỉ số chính
    col1, col2, col3 = st.columns([1, 1, 2])
    col1.metric("Nhiệt độ", f"{last['temp']} °C")
    col1.metric("Độ ẩm", f"{last['humi']} %")
    
    # Box VPD (Fix lỗi Syntax f-string image_8c69cf.png)
    vpd_html = f"<div style='background-color:{color}; color:white; padding:20px; border-radius:15px; text-align:center;'><h2 style='margin:0;'>{last['VPD']} kPa</h2><p style='margin:0;'>{label}</p></div>"
    col2.markdown(vpd_html, unsafe_allow_html=True)
    col3.warning(f"**Lời khuyên:** {advice}")

    # Hàng 2: Biểu đồ
    st.subheader("📈 Biểu đồ xu hướng")
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.1)
    fig.add_trace(go.Scatter(x=df_display['Thời gian'], y=df_display['VPD'], name="VPD", line=dict(color='green', width=3)), row=1, col=1)
    fig.add_trace(go.Scatter(x=df_display['Thời gian'], y=df_display['temp'], name="Nhiệt độ", line=dict(color='red')), row=2, col=1)
    fig.add_trace(go.Scatter(x=df_display['Thời gian'], y=df_display['humi'], name="Độ ẩm", line=dict(color='blue')), row=2, col=1)
    fig.update_layout(height=500, margin=dict(t=20, b=20))
    st.plotly_chart(fig, use_container_width=True)

    # Hàng 3: Bảng (Fix lỗi AttributeError image_095187.png)
    st.subheader("📋 Chi tiết bản ghi")
    table_df = df_display.copy().sort_values('Thời gian', ascending=False)
    table_df['Thời gian'] = pd.to_datetime(table_df['Thời gian']).dt.strftime('%H:%M:%S')
    st.dataframe(table_df, use_container_width=True, hide_index=True)

    if sim_on and not uploaded_file:
        time.sleep(30)
        st.rerun()
else:
    st.warning("👈 Vui lòng nạp file JSON hoặc bật chế độ Giả lập ở thanh bên!")
