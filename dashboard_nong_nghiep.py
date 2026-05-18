import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import timedelta

st.set_page_config(page_title="Greenhouse Pro Max", layout="wide")
st.title("🌿 Hệ Thống Giám Sát Nhà Kính Toàn Diện")

# --- 1. HÀM TÍNH TOÁN VPD (Có bù sai số) ---
def calculate_vpd(temp, humi, t_offset, h_offset):
    t_final = temp + t_offset
    h_final = humi + h_offset
    h_final = max(min(h_final, 100), 0.1) # Giới hạn ẩm 0.1-100%
    
    if pd.isna(t_final) or pd.isna(h_final): return None
    vpsat = 0.61078 * np.exp((17.27 * t_final) / (t_final + 237.3))
    vpair = vpsat * (h_final / 100)
    return round(vpsat - vpair, 2)

def get_greenhouse_advice(vpd, stage):
    if pd.isna(vpd): return "N/A", "Thiếu dữ liệu", "#808080"
    if "Cây con" in stage: ideal_min, ideal_max = 0.4, 0.8
    elif "Sinh trưởng" in stage: ideal_min, ideal_max = 0.8, 1.2
    else: ideal_min, ideal_max = 1.2, 1.5

    if vpd < ideal_min - 0.2: return "🔴 QUÁ THẤP", "Nguy cơ nấm bệnh! Tăng nhiệt hoặc giảm ẩm.", "#FF4B4B"
    if ideal_min <= vpd <= ideal_max: return "🟢 LÝ TƯỞNG", "Cây đang phát triển tốt.", "#00C851"
    if vpd > ideal_max + 0.3: return "🔴 QUÁ CAO", "Stress nhiệt nặng! Giảm nhiệt, tăng ẩm khẩn cấp.", "#8B0000"
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
    if t_cols: df['temp_raw'] = df[t_cols].bfill(axis=1).iloc[:, 0]
    h_cols = [c for c in ['Độ ẩm', 'humiKK'] if c in df.columns]
    if h_cols: df['humi_raw'] = df[h_cols].bfill(axis=1).iloc[:, 0]
        
    for col in ['temp_raw', 'humi_raw']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col].astype(str).str.extract(r'(\d+\.?\d*)')[0], errors='coerce')
            if col == 'temp_raw':
                df.loc[df[col] > 150, col] = df[col] / 10 
                df.loc[(df[col] >= 45) & (df[col] <= 120), col] = (df[col] - 32) * 5/9 
                df.loc[df[col] > 60, col] = np.nan # Loại bỏ nhiệt rác > 60 độ
    
    if 'humi_raw' in df.columns:
        df = df[(df['humi_raw'] > 0) & (df['humi_raw'] <= 100)].copy()
    
    return df

# --- 3. GIAO DIỆN ---
uploaded_file = st.sidebar.file_uploader("Tải file JSON", type=['json'])

if uploaded_file:
    df = process_data(uploaded_file)
    if not df.empty:
        # BẢNG DANH MỤC THÁNG
        st.sidebar.subheader("📅 Dữ liệu hiện có")
        df['Tháng'] = df['Thời gian'].dt.strftime('%m/%Y')
        st.sidebar.dataframe(df.groupby('Tháng').size().reset_index(name='Số dòng'), hide_index=True)

        # LỌC THỜI GIAN (ĐÃ TRẢ LẠI)
        st.sidebar.header("🔍 Bộ lọc hiển thị")
        filter_mode = st.sidebar.radio("Lọc thời gian:", ["Tất cả", "Theo tháng", "Khoảng ngày"], horizontal=True)
        
        if filter_mode == "Theo tháng":
            sel_months = st.sidebar.multiselect("Chọn tháng:", df['Tháng'].unique(), default=df['Tháng'].unique()[-1:])
            df_work = df[df['Tháng'].isin(sel_months)].copy()
        elif filter_mode == "Khoảng ngày":
            c1, c2 = st.sidebar.columns(2)
            start = pd.to_datetime(c1.date_input("Từ ngày", df['Thời gian'].min()))
            end = pd.to_datetime(c2.date_input("Đến ngày", df['Thời gian'].max())) + timedelta(days=1)
            df_work = df[(df['Thời gian'] >= start) & (df['Thời gian'] < end)].copy()
        else:
            df_work = df.copy()

        # HIỆU CHỈNH SAI SỐ
        st.sidebar.markdown("---")
        st.sidebar.header("🛠️ Hiệu chỉnh Offset")
        t_err = st.sidebar.slider("Sai số Nhiệt độ (°C)", -0.4, 0.4, 0.0, step=0.1)
        h_err = st.sidebar.slider("Sai số Độ ẩm (%)", -5.0, 5.0, 0.0, step=0.5)

        # CHỌN TRẠM & GIAI ĐOẠN
        st.sidebar.markdown("---")
        growth_stage = st.sidebar.radio("Giai đoạn cây:", ["🌱 Cây con", "🌿 Sinh trưởng", "🍅 Ra hoa"], index=1)
        stt_list = ["Tất cả"] + sorted(df_work['STT'].unique().tolist())
        sel_stt = st.sidebar.selectbox("📍 Chọn Trạm:", stt_list)
        if sel_stt != "Tất cả": df_work = df_work[df_work['STT'] == sel_stt]

        # TÍNH TOÁN DỮ LIỆU CUỐI CÙNG
        df_work['temp'] = df_work['temp_raw'] + t_err
        df_work['humi'] = df_work['humi_raw'] + h_err
        df_work['VPD'] = df_work.apply(lambda r: calculate_vpd(r['temp_raw'], r['humi_raw'], t_err, h_err), axis=1)

        # HIỂN THỊ CHỈ SỐ HIỆN TẠI
        if not df_work.empty:
            last = df_work.dropna(subset=['VPD']).iloc[-1]
            status, advice, color = get_greenhouse_advice(last['VPD'], growth_stage)
            
            st.subheader(f"📍 Trạng thái (Bù: {t_err}°C / {h_err}%)")
            c1, c2, c3 = st.columns([1, 1, 2])
            c1.metric("Nhiệt độ", f"{round(last['temp'], 1)} °C")
            c1.metric("Độ ẩm", f"{round(last['humi'], 1)} %")
            c2.markdown(f"<div style='padding:15px; border
