import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import timedelta, datetime
import time
import random

# Cấu hình trang Dashboard
st.set_page_config(page_title="Greenhouse Monitoring Pro", layout="wide")
st.title("🌿 Hệ Thống Giám Sát Nhà Kính (Realtime & Analytics)")

# --- 1. CÔNG CỤ TÍNH TOÁN & CẢNH BÁO ---
def calculate_vpd(temp, humi):
    """Tính toán áp suất hơi thâm hụt (VPD)"""
    if pd.isna(temp) or pd.isna(humi): return None
    # Áp suất hơi bão hòa
    vpsat = 0.61078 * np.exp((17.27 * temp) / (temp + 237.3))
    # Áp suất hơi thực tế
    vpair = vpsat * (humi / 100)
    return round(vpsat - vpair, 2)

def get_greenhouse_advice(vpd, stage):
    """Đưa ra lời khuyên dựa trên VPD và giai đoạn phát triển"""
    if pd.isna(vpd): return "N/A", "Đang chờ dữ liệu...", "#808080"
    
    # Ngưỡng lý tưởng theo giai đoạn
    if "Cây con" in stage: ideal_min, ideal_max = 0.4, 0.8
    elif "Sinh trưởng" in stage: ideal_min, ideal_max = 0.8, 1.2
    else: ideal_min, ideal_max = 1.2, 1.5

    if vpd < ideal_min - 0.2: 
        return "🔴 QUÁ THẤP", "Nguy cơ nấm bệnh! Tăng nhiệt hoặc giảm ẩm.", "#FF4B4B"
    if ideal_min <= vpd <= ideal_max: 
        return "🟢 LÝ TƯỞNG", "Cây đang phát triển tốt.", "#00C851"
    if vpd > ideal_max + 0.3: 
        return "🔴 QUÁ CAO", "Stress nhiệt nặng! Giảm nhiệt, tăng ẩm khẩn cấp.", "#8B0000"
    return "🟡 HƠI LỆCH", "Cần điều chỉnh nhẹ thiết bị.", "#FFA500"

# --- 2. QUẢN LÝ BỘ NHỚ GIẢ LẬP ---
if 'sim_df' not in st.session_state:
    st.session_state.sim_df = pd.DataFrame(columns=['Thời gian', 'STT', 'temp', 'humi', 'VPD'])

# --- 3. XỬ LÝ DỮ LIỆU TỪ FILE JSON ---
def process_data(file):
    try:
        df = pd.read_json(file)
    except: return pd.DataFrame()

    if 'Thời gian' in df.columns:
        # Chuẩn hóa định dạng thời gian
        df['Thời gian'] = pd.to_datetime(df['Thời gian'].astype(str).str.replace('-', ' ', n=2).str.replace('-', ':'), errors='coerce')
        df = df.dropna(subset=['Thời gian']).sort_values('Thời gian')
    
    # Nhận diện cột nhiệt độ và độ ẩm
    t_cols = [c for c in ['Nhiệt Độ', 'tempKK'] if c in df.columns]
    if t_cols: df['temp'] = df[t_cols].bfill(axis=1).iloc[:, 0]
    h_cols = [c for c in ['Độ ẩm', 'humiKK'] if c in df.columns]
    if h_cols: df['humi'] = df[h_cols].bfill(axis=1).iloc[:, 0]
        
    for col in ['temp', 'humi']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col].astype(str).str.extract(r'(\d+\.?\d*)')[0], errors='coerce')
            
            if col == 'temp':
                # Sửa lỗi nhiệt độ hiển thị sai (ví dụ 889 -> 88.9)
                df.loc[df[col] > 150, col] = df[col] / 10 
                # Lọc bỏ số liệu lỗi (nhiệt độ quá cao hoặc quá thấp vô lý)
                df.loc[(df[col] < 5) | (df[col] > 55), col] = np.nan 
                
            if col == 'humi':
                # Lọc bỏ độ ẩm lỗi
                df.loc[(df[col] < 10) | (df[col] > 100), col] = np.nan 
    
    # Bỏ dòng rác và tính VPD
    df = df.dropna(subset=['temp', 'humi']).copy()
    if not df.empty:
        df['VPD'] = df.apply(lambda r: calculate_vpd(r['temp'], r['humi']), axis=1)
    
    return df

# --- 4. GIAO DIỆN THANH BÊN (SIDEBAR) ---
st.sidebar.header("🕹️ Chế độ vận hành")
sim_mode = st.sidebar.toggle("Bật giả lập Realtime (30s/lần)")

uploaded_file = st.sidebar.file_uploader("Hoặc Tải file JSON dữ liệu", type=['json'], disabled=sim_mode)

st.sidebar.markdown("---")
growth_stage = st.sidebar.radio("Giai đoạn cây:", ["🌱 Cây con", "🌿 Sinh trưởng", "🍅 Ra hoa"], index=1)

# --- 5. LOGIC CHÍNH ---
df_display = pd.DataFrame()

# A. Xử lý Chế độ Giả lập
if sim_mode:
    if st.session_state.sim_df.empty:
        prev_temp, prev_humi = 28.0, 75.0 # Khởi tạo ban đầu
    else:
        prev_temp = st.session_state.sim_df.iloc[-1]['temp']
        prev_humi = st.session_state.sim_df.iloc[-1]['humi']
    
    # Thuật toán Random Walk giúp số liệu mượt mà
    new_temp = round(prev_temp + random.uniform(-0.6, 0.6), 2)
    new_humi = round(prev_humi + random.uniform(-1.5, 1.5), 2)
    
    # Khóa giới hạn thực tế
    new_temp = max(15.0, min(42.0, new_temp))
    new_humi = max(30.0, min(95.0, new_humi))
    
    new_row = pd.DataFrame([{
        'Thời gian': datetime.now(),
        'STT': 'LIVE-01',
        'temp': new_temp,
        'humi': new_humi,
        'VPD': calculate_vpd(new_temp, new_humi)
    }])
    
    st.session_state.sim_df = pd.concat([st.session_state.sim_df, new_row], ignore_index=True)
    st.session_state.sim_df = st.session_state.sim_df.tail(40) # Giữ 40 bản ghi gần nhất
    df_display = st.session_state.sim_df.copy()
    st.success(f"Dữ liệu đang được giả lập liên tục mỗi 30 giây...")

# B. Xử lý Chế độ File Offline
elif uploaded_file:
    df_raw = process_data(uploaded_file)
    if not df_raw.empty:
        stt_list = ["Tất cả"] + sorted(df_raw['STT'].unique().tolist())
        sel_stt = st.sidebar.selectbox("📍 Chọn Trạm:", stt_list)
        df_display = df_raw if sel_stt == "Tất cả" else df_raw[df_raw['STT'] == sel_stt]

# --- 6. HIỂN THỊ KẾT QUẢ ---
if not df_display.empty:
    last = df_display.iloc[-1]
    status, advice, color = get_greenhouse_advice(last['VPD'], growth_stage)
    
    # Header Trạng thái
    st.subheader(f"📍 Trạng thái hiện tại ({last['Thời gian'].strftime('%H:%M:%S')})")
    col1, col2, col3 = st.columns([1, 1, 2])
    col1.metric("Nhiệt độ", f"{round(last['temp'], 1)} °C")
    col1.metric("Độ ẩm", f"{round(last['humi'], 1)} %")
    
    # Hộp VPD đổi màu theo cảnh báo
    v_html = f"""
    <div style="padding:20px; border-radius:10px; background-color:{color}; color:white; text-align:center;">
        <span style="font-size:24px; font-weight:bold;">VPD: {last['VPD']} kPa</span><br>
        <span style="font-size:16px;">{status}</span>
    </div>
    """
    col2.markdown(v_html, unsafe_allow_html=True)
    col3.info(f"**Hướng dẫn:** {advice}")

    # Biểu đồ Plotly
    st.markdown("---")
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.1)
    fig.add_trace(go.Scatter(x=df_display['Thời gian'], y=df_display['VPD'], name="VPD (kPa)", line=dict(color='green', width=3)), row=1, col=1)
    fig.add_trace(go.Scatter(x=df_display['Thời gian'], y=df_display['temp'], name="Nhiệt độ (°C)", line=dict(color='red')), row=2, col=1)
    fig.add_trace(go.Scatter(x=df_display['Thời gian'], y=df_display['humi'], name="Độ ẩm (%)", line=dict(color='blue')), row=2, col=1)
    fig.update_layout(height=500, hovermode="x unified", margin=dict(t=20, b=20))
    st.plotly_chart(fig, use_container_width=True)

    # Bảng dữ liệu chi tiết có tô màu cảnh báo
    st.subheader("📋 Lịch sử bản ghi (Mốc an toàn: 0.5 - 1.5 kPa)")
    
    def highlight_v(val):
        # Nếu VPD nằm ngoài ngưỡng an toàn, tô nền đỏ nhạt
        return 'background-color: #ffcccc; color: #900;' if (val < 0.5 or val > 1.5) else ''

    # Format hiển thị bảng
    table_df = df_display[['Thời gian', 'STT', 'temp', 'humi', 'VPD']].sort_values('Thời gian', ascending=False)
    # Fix lỗi định dạng thời gian (AttributeError)
    table_df['Thời gian'] = pd.to_datetime(table_df['Thời gian']).dt.strftime('%Y-%m-%d %H:%M:%S')

    st.dataframe(
        table_df.style.map(highlight_v, subset=['VPD']),
        use_container_width=True,
        hide_index=True
    )
    
    # Tự động reload nếu ở chế độ giả lập
    if sim_mode:
        time.sleep(30)
        st.rerun()
else:
    st.info("Vui lòng tải file hoặc bật chế độ Giả lập để xem dữ liệu.")
