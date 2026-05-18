import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import timedelta
import re

st.set_page_config(page_title="Dashboard AH4 Pro", layout="wide")
st.title("🌿 Hệ Thống Quản Trắc & Cảnh Báo VPD")

# --- HÀM TÍNH TOÁN VPD ---
def calculate_vpd(temp, humi):
    if temp is None or humi is None or pd.isna(temp) or pd.isna(humi): return None
    vpsat = 0.61078 * np.exp((17.27 * temp) / (temp + 237.3))
    vpair = vpsat * (humi / 100)
    return round(vpsat - vpair, 2)

def get_vpd_advice(vpd):
    if vpd is None or pd.isna(vpd): return "N/A", "Không đủ dữ liệu", "#808080"
    if vpd < 0.4: return "🔴 QUÁ THẤP", "Nguy cơ nấm bệnh. Cần tăng nhiệt hoặc giảm ẩm.", "#FF4B4B"
    if 0.4 <= vpd <= 0.8: return "🟡 THẤP", "Tốt cho nhân giống.", "#FFD700"
    if 0.8 < vpd <= 1.2: return "🟢 LÝ TƯỞNG", "Cây quang hợp tốt nhất.", "#00C851"
    if 1.2 < vpd <= 1.6: return "🟡 CAO", "Cần giảm nhiệt hoặc phun sương tăng ẩm.", "#FFA500"
    return "🔴 QUÁ CAO", "Stress nhiệt nặng! Cần giảm nhiệt khẩn cấp.", "#8B0000"

# --- XỬ LÝ DỮ LIỆU ---
def process_data(file):
    try:
        df = pd.read_json(file)
    except: return pd.DataFrame()

    if 'Thời gian' in df.columns:
        df['Thời gian'] = pd.to_datetime(df['Thời gian'].astype(str).str.replace('-', ' ', n=2).str.replace('-', ':'), errors='coerce')
        df = df.dropna(subset=['Thời gian']).sort_values('Thời gian')
    
    # Chuẩn hóa tên cột để tính VPD
    col_map = {'Nhiệt Độ': 'temp', 'tempKK': 'temp', 'Độ ẩm': 'humi', 'humiKK': 'humi'}
    df = df.rename(columns=col_map)
    
    # Sửa lỗi AttributeError: Kiểm tra cột có tồn tại hay không trước khi xử lý
    for col in ['temp', 'humi']:
        if col in df.columns:
            # Trích xuất số từ chuỗi (Xử lý trường hợp dữ liệu có kèm đơn vị)
            df[col] = pd.to_numeric(df[col].astype(str).str.extract(r'(\d+\.?\d*)')[0], errors='coerce')
            
            # Xử lý sai lệch đơn vị (VD: 335 -> 33.5)
            max_val = df[col].max()
            if col == 'temp' and max_val > 100: df[col] = df[col] / 10
            if col == 'humi' and max_val > 100: df[col] = df[col] / 10

    if 'temp' in df.columns and 'humi' in df.columns:
        df['VPD'] = df.apply(lambda r: calculate_vpd(r.get('temp'), r.get('humi')), axis=1)
    
    return df

uploaded_file = st.sidebar.file_uploader("Tải file JSON", type=['json'])

if uploaded_file:
    df = process_data(uploaded_file)
    if not df.empty:
        # --- Sidebar: Lọc dữ liệu ---
        st.sidebar.header("⚙️ Cấu hình")
        view_opt = st.sidebar.selectbox("Gộp dữ liệu:", ["Gốc", "Giờ", "Ngày"])
        
        if 'STT' in df.columns:
            stt_list = ["Tất cả"] + sorted(df['STT'].unique().astype(str).tolist())
            sel_stt = st.sidebar.selectbox("Chọn Trạm (STT):", stt_list)
            if sel_stt != "Tất cả":
                df = df[df['STT'].astype(str) == sel_stt]

        # --- Hiển thị VPD Hiện Tại ---
        if 'VPD' in df.columns and not df['VPD'].dropna().empty:
            last = df.dropna(subset=['VPD']).iloc[-1]
            status, advice, color = get_vpd_advice(last['VPD'])
            
            st.subheader("📍 Cảnh báo trạng thái mới nhất")
            c1, c2, c3 = st.columns([1, 1, 2])
            c1.metric("Nhiệt độ", f"{last['temp']}°C")
            c1.metric("Độ ẩm", f"{last['humi']}%")
            c2.markdown(f"<div style='padding:20px; border-radius:10px; background-color:{color}; color:white; text-align:center; font-size:24px;'><b>VPD: {last['VPD']} kPa</b><br><small>{status}</small></div>", unsafe_allow_html=True)
            c3.info(f"**Lời khuyên:** {advice}")

            # --- Biểu đồ ---
            freq_map = {"Giờ": "1H", "Ngày": "1D", "Gốc": None}
            freq = freq_map[view_opt]
            df_p = df.set_index('Thời gian').resample(freq).mean(numeric_only=True).reset_index() if freq else df
            
            fig = make_subplots(rows=2, cols=1, shared_xaxes=True, subplot_titles=("Diễn biến VPD (kPa)", "Nhiệt độ & Độ ẩm"))
            fig.add_trace(go.Scatter(x=df_p['Thời gian'], y=df_p['VPD'], name="VPD", line=dict(color='green')), row=1, col=1)
            fig.add_trace(go.Scatter(x=df_p['Thời gian'], y=df_p['temp'], name="Nhiệt độ"), row=2, col=1)
            fig.add_trace(go.Scatter(x=df_p['Thời gian'], y=df_p['humi'], name="Độ ẩm"), row=2, col=1)
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.warning("Dữ liệu trạm này không có đủ thông số Nhiệt độ/Độ ẩm để tính VPD.")
