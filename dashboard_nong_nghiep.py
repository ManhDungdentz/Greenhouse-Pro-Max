import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import timedelta

st.set_page_config(page_title="Greenhouse Pro Max", layout="wide")
st.title("🌿 Hệ Thống Giám Sát Nhà Kính Toàn Diện")

# --- 1. HÀM TÍNH TOÁN & LOGIC ---
def calculate_vpd(temp, humi):
    if pd.isna(temp) or pd.isna(humi) or humi <= 0: return None
    vpsat = 0.61078 * np.exp((17.27 * temp) / (temp + 237.3))
    vpair = vpsat * (humi / 100)
    return round(vpsat - vpair, 2)

def get_greenhouse_advice(vpd, stage):
    if pd.isna(vpd): return "N/A", "Thiếu dữ liệu", "#808080"
    if "Cây con" in stage: ideal_min, ideal_max = 0.4, 0.8
    elif "Sinh trưởng" in stage: ideal_min, ideal_max = 0.8, 1.2
    else: ideal_min, ideal_max = 1.2, 1.5

    if vpd < ideal_min - 0.2: return "🔴 QUÁ THẤP", "Nguy cơ nấm bệnh! Bật quạt thông gió ngay.", "#FF4B4B"
    if ideal_min <= vpd <= ideal_max: return "🟢 LÝ TƯỞNG", "Cây đang phát triển tốt. Giữ nguyên trạng thái.", "#00C851"
    if vpd > ideal_max + 0.3: return "🔴 QUÁ CAO", "Stress nhiệt! Bật phun sương/Cooling Pad.", "#8B0000"
    return "🟡 HƠI LỆCH", "Cần điều chỉnh nhẹ thiết bị.", "#FFA500"

# --- 2. XỬ LÝ DỮ LIỆU SẠCH ---
def process_data(file):
    try:
        df = pd.read_json(file)
    except: return pd.DataFrame()

    if 'Thời gian' in df.columns:
        df['Thời gian'] = pd.to_datetime(df['Thời gian'].astype(str).str.replace('-', ' ', n=2).str.replace('-', ':'), errors='coerce')
        df = df.dropna(subset=['Thời gian']).sort_values('Thời gian')
    
    # Gộp cột Nhiệt/Ẩm
    t_cols = [c for c in ['Nhiệt Độ', 'tempKK'] if c in df.columns]
    if t_cols: df['temp'] = df[t_cols].bfill(axis=1).iloc[:, 0]
    h_cols = [c for c in ['Độ ẩm', 'humiKK'] if c in df.columns]
    if h_cols: df['humi'] = df[h_cols].bfill(axis=1).iloc[:, 0]
        
    for col in ['temp', 'humi']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col].astype(str).str.extract(r'(\d+\.?\d*)')[0], errors='coerce')
            if col == 'temp':
                # CHUẨN HÓA NHIỆT ĐỘ:
                df.loc[df[col] > 150, col] = df[col] / 10 # Fix lỗi 331 -> 33.1
                df.loc[(df[col] >= 45) & (df[col] <= 120), col] = (df[col] - 32) * 5/9 # Đổi độ F sang C
                df.loc[df[col] > 60, col] = np.nan # Lọc rác
    
    # Lọc bỏ độ ẩm lỗi (0% hoặc >100%)
    if 'humi' in df.columns:
        df = df[(df['humi'] > 0) & (df['humi'] <= 100)].copy()

    if 'temp' in df.columns and 'humi' in df.columns:
        df['VPD'] = df.apply(lambda r: calculate_vpd(r['temp'], r['humi']), axis=1)
    
    return df

# --- 3. GIAO DIỆN CHÍNH ---
uploaded_file = st.sidebar.file_uploader("Tải file JSON", type=['json'])

if uploaded_file:
    df = process_data(uploaded_file)
    if not df.empty:
        # SIDEBAR CẤU HÌNH
        st.sidebar.header("🎯 Cài đặt vận hành")
        growth_stage = st.sidebar.radio("Giai đoạn cây:", ["🌱 Cây con", "🌿 Sinh trưởng", "🍅 Ra hoa"], index=1)
        
        st.sidebar.markdown("---")
        st.sidebar.header("📅 Lọc thời gian")
        df['Tháng_năm'] = df['Thời gian'].dt.strftime('%m/%Y')
        filter_mode = st.sidebar.radio("Chọn theo:", ["Tháng", "Khoảng ngày"], horizontal=True)
        if filter_mode == "Tháng":
            sel_months = st.sidebar.multiselect("Chọn tháng:", df['Tháng_năm'].unique(), default=df['Tháng_năm'].unique()[-1:])
            df_filtered = df[df['Tháng_năm'].isin(sel_months)].copy()
        else:
            c1, c2 = st.sidebar.columns(2)
            start = pd.to_datetime(c1.date_input("Từ", df['Thời gian'].min()))
            end = pd.to_datetime(c2.date_input("Đến", df['Thời gian'].max())) + timedelta(days=1)
            df_filtered = df[(df['Thời gian'] >= start) & (df['Thời gian'] < end)].copy()

        st.sidebar.markdown("---")
        stt_list = ["Tất cả"] + sorted(df_filtered['STT'].unique().tolist())
        sel_stt = st.sidebar.selectbox("📍 Chọn Trạm:", stt_list)
        if sel_stt != "Tất cả": df_filtered = df_filtered[df_filtered['STT'] == sel_stt]

        # HIỂN THỊ CHỈ SỐ
        if not df_filtered.empty:
            last = df_filtered.dropna(subset=['VPD']).iloc[-1]
            status, advice, color = get_greenhouse_advice(last['VPD'], growth_stage)
            
            st.subheader("📍 Trạng thái hiện tại")
            c1, c2, c3 = st.columns([1, 1, 2])
            c1.metric("Nhiệt độ", f"{round(last['temp'], 2)} °C")
            c1.metric("Độ ẩm", f"{last['humi']} %")
            c2.markdown(f"<div style='padding:15px; border-radius:10px; background-color:{color}; color:white; text-align:center; font-size:20px;'><b>VPD: {last['VPD']} kPa</b><br><small>{status}</small></div>", unsafe_allow_html=True)
            c3.success(f"**Chỉ đạo:** {advice}")

            # BIỂU ĐỒ
            st.markdown("---")
            fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.1)
            fig.add_trace(go.Scatter(x=df_filtered['Thời gian'], y=df_filtered['VPD'], name="VPD", line=dict(color='green')), row=1, col=1)
            fig.add_trace(go.Scatter(x=df_filtered['Thời gian'], y=df_filtered['temp'], name="Nhiệt độ"), row=2, col=1)
            fig.add_trace(go.Scatter(x=df_filtered['Thời gian'], y=df_filtered['humi'], name="Độ ẩm"), row=2, col=1)
            fig.update_layout(height=500, hovermode="x unified")
            st.plotly_chart(fig, use_container_width=True)

            # BẢNG TÓM TẮT & CHI TIẾT (ĐÃ TRẢ LẠI)
            st.subheader("📋 Thống kê & Dữ liệu chi tiết")
            summary = df_filtered[['temp', 'humi', 'VPD']].agg(['max', 'min', 'mean']).round(2)
            summary.index = ['Cao nhất', 'Thấp nhất', 'Trung bình']
            st.table(summary)
            
            st.dataframe(df_filtered[['Thời gian', 'STT', 'temp', 'humi', 'VPD']].sort_values('Thời gian', ascending=False), use_container_width=True)
        else:
            st.warning("Không có dữ liệu trong khoảng này.")
else:
    st.info("👈 Tải file JSON lên để bắt đầu.")
