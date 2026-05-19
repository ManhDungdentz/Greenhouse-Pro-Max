import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import timedelta

st.set_page_config(page_title="Greenhouse Pro Max", layout="wide")
st.title("🌿 Hệ Thống Giám Sát Nhà Kính (Bộ Lọc Thép)")

# --- 1. HÀM TÍNH TOÁN VPD ---
def calculate_vpd(temp, humi, t_offset, h_offset):
    t_final = temp + t_offset
    h_final = humi + h_offset
    
    # Ép giới hạn an toàn sau khi bù sai số
    h_final = max(min(h_final, 100), 20) 
    
    if pd.isna(t_final) or pd.isna(h_final): return None
    vpsat = 0.61078 * np.exp((17.27 * t_final) / (t_final + 237.3))
    vpair = vpsat * (h_final / 100)
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

# --- 2. XỬ LÝ & LÀM SẠCH DỮ LIỆU (KỶ LUẬT THÉP) ---
def process_data(file):
    try:
        df = pd.read_json(file)
    except: return pd.DataFrame()

    if 'Thời gian' in df.columns:
        df['Thời gian'] = pd.to_datetime(df['Thời gian'].astype(str).str.replace('-', ' ', n=2).str.replace('-', ':'), errors='coerce')
        df = df.dropna(subset=['Thời gian']).sort_values('Thời gian')
    
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
                # Lọc thép: Chỉ lấy nhiệt độ từ 5 đến 55 độ C
                df.loc[(df[col] < 5) | (df[col] > 55), col] = np.nan 
                
            if col == 'humi_raw':
                # Lọc thép: Độ ẩm 0% hoặc dưới 20% xóa hết. Quá 100% cũng xóa.
                df.loc[(df[col] < 20) | (df[col] > 100), col] = np.nan 
    
    # Drop các dòng bị lỗi nhiệt/ẩm để không làm hỏng tính toán
    df = df.dropna(subset=['temp_raw', 'humi_raw']).copy()
    
    return df

# --- 3. GIAO DIỆN CHÍNH ---
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

        # HIỆU CHỈNH SAI SỐ
        st.sidebar.markdown("---")
        st.sidebar.header("🛠️ Hiệu chỉnh Offset")
        t_err = st.sidebar.slider("Bù Nhiệt độ (°C)", -0.4, 0.4, 0.0, 0.1)
        h_err = st.sidebar.slider("Bù Độ ẩm (%)", -5.0, 5.0, 0.0, 0.5)

        # CHỌN TRẠM & GIAI ĐOẠN
        st.sidebar.markdown("---")
        growth_stage = st.sidebar.radio("Giai đoạn:", ["🌱 Cây con", "🌿 Sinh trưởng", "🍅 Ra hoa"], index=1)
        stt_list = ["Tất cả"] + sorted(df_work['STT'].unique().tolist())
        sel_stt = st.sidebar.selectbox("📍 Chọn Trạm:", stt_list)
        if sel_stt != "Tất cả": df_work = df_work[df_work['STT'] == sel_stt]

        # TÍNH TOÁN VPD CUỐI CÙNG
        df_work['temp'] = df_work['temp_raw'] + t_err
        df_work['humi'] = df_work['humi_raw'] + h_err
        df_work['VPD'] = df_work.apply(lambda r: calculate_vpd(r['temp_raw'], r['humi_raw'], t_err, h_err), axis=1)

        # HIỂN THỊ THÔNG BÁO (Chỉ hiện khi có dữ liệu)
        df_valid = df_work.dropna(subset=['VPD'])
        
        if not df_valid.empty:
            last = df_valid.iloc[-1]
            status, advice, color = get_greenhouse_advice(last['VPD'], growth_stage)
            
            st.subheader(f"📍 Thông báo (Bù: {t_err}°C / {h_err}%)")
            col1, col2, col3 = st.columns([1, 1, 2])
            col1.metric("Nhiệt độ (chuẩn)", f"{round(last['temp'], 1)} °C")
            col1.metric("Độ ẩm (chuẩn)", f"{round(last['humi'], 1)} %")
            
            html_box = f"""
            <div style="padding:20px; border-radius:10px; background-color:{color}; color:white; text-align:center;">
                <span style="font-size:24px; font-weight:bold;">VPD: {last['VPD']} kPa</span><br>
                <span style="font-size:16px;">{status}</span>
            </div>
            """
            col2.markdown(html_box, unsafe_allow_html=True)
            col3.warning(f"**Chỉ đạo vận hành:** {advice}")

            # BIỂU ĐỒ
            st.markdown("---")
            fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.1)
            fig.add_trace(go.Scatter(x=df_work['Thời gian'], y=df_work['VPD'], name="VPD (kPa)", line=dict(color='green')), row=1, col=1)
            fig.add_trace(go.Scatter(x=df_work['Thời gian'], y=df_work['temp'], name="Nhiệt độ (°C)"), row=2, col=1)
            fig.add_trace(go.Scatter(x=df_work['Thời gian'], y=df_work['humi'], name="Độ ẩm (%)"), row=2, col=1)
            fig.update_layout(height=500, hovermode="x unified")
            st.plotly_chart(fig, use_container_width=True)

            # BẢNG THỐNG KÊ CHI TIẾT
            st.subheader("📋 Bảng Dữ Liệu Sau Khi Lọc Sạch")
            summary = df_valid[['temp', 'humi', 'VPD']].agg(['max', 'min', 'mean']).round(2)
            summary.index = ['Cao nhất', 'Thấp nhất', 'Trung bình']
            st.table(summary)
            
            st.dataframe(df_valid[['Thời gian', 'STT', 'temp', 'humi', 'VPD']].sort_values('Thời gian', ascending=False), use_container_width=True)
        else:
            st.error("🚨 Dữ liệu trong khoảng thời gian này toàn bộ bị lỗi (ẩm 0% hoặc nhiệt > 60°C) nên hệ thống đã tự động lọc bỏ. Không có dữ liệu chuẩn để tính toán!")
