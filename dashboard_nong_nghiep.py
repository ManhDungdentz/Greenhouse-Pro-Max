import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import timedelta

st.set_page_config(page_title="Greenhouse VPD Pro", layout="wide")
st.title("🌿 Hệ Thống Giám Sát VPD Nhà Kính")

# --- HÀM TÍNH TOÁN VPD ---
def calculate_vpd(temp, humi):
    if pd.isna(temp) or pd.isna(humi): return None
    vpsat = 0.61078 * np.exp((17.27 * temp) / (temp + 237.3))
    vpair = vpsat * (humi / 100)
    return round(vpsat - vpair, 2)

# --- LOGIC CẢNH BÁO RIÊNG CHO NHÀ KÍNH ---
def get_greenhouse_advice(vpd, stage):
    if pd.isna(vpd): return "N/A", "Không đủ dữ liệu", "#808080"
    
    # Thiết lập khoảng VPD lý tưởng theo giai đoạn
    if stage == "🌱 Cây con / Ươm mầm (0.4 - 0.8 kPa)":
        ideal_min, ideal_max = 0.4, 0.8
    elif stage == "🌿 Sinh trưởng phát triển (0.8 - 1.2 kPa)":
        ideal_min, ideal_max = 0.8, 1.2
    else: # 🍅 Ra hoa / Đậu quả
        ideal_min, ideal_max = 1.2, 1.5

    if vpd < ideal_min - 0.2:
        return "🔴 QUÁ THẤP", "Nguy cơ nấm bệnh! TÁC ĐỘNG: Bật quạt thông gió (hút ẩm ra ngoài) hoặc bật sưởi nền.", "#FF4B4B"
    elif vpd < ideal_min:
        return "🟡 HƠI THẤP", "Dưới mức tối ưu. TÁC ĐỘNG: Mở hé cửa lùi/cửa mái nhà kính để giảm ẩm.", "#FFD700"
    elif ideal_min <= vpd <= ideal_max:
        return "🟢 LÝ TƯỞNG", "Tuyệt vời! Cây đang quang hợp tối đa. Duy trì trạng thái thiết bị hiện tại.", "#00C851"
    elif vpd <= ideal_max + 0.3:
        return "🟡 HƠI CAO", "Cây bắt đầu hụt nước. TÁC ĐỘNG: Kéo rèm cắt nắng, bật phun sương (Fogging) ngắn hạn.", "#FFA500"
    else:
        return "🔴 QUÁ CAO", "Stress nhiệt nặng (Đóng lỗ khí)! TÁC ĐỘNG: Bật ngay Tường nước (Cooling Pad) + Quạt hút, che 100% rèm.", "#8B0000"

# --- XỬ LÝ DỮ LIỆU ---
def process_data(file):
    try:
        df = pd.read_json(file)
    except: return pd.DataFrame()

    if 'Thời gian' in df.columns:
        df['Thời gian'] = pd.to_datetime(df['Thời gian'].astype(str).str.replace('-', ' ', n=2).str.replace('-', ':'), errors='coerce')
        df = df.dropna(subset=['Thời gian']).sort_values('Thời gian')
    else: return pd.DataFrame()
    
    temp_cols = [c for c in ['Nhiệt Độ', 'tempKK'] if c in df.columns]
    if temp_cols: df['temp'] = df[temp_cols].bfill(axis=1).iloc[:, 0]
        
    humi_cols = [c for c in ['Độ ẩm', 'humiKK'] if c in df.columns]
    if humi_cols: df['humi'] = df[humi_cols].bfill(axis=1).iloc[:, 0]
        
    for col in ['temp', 'humi']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col].astype(str).str.extract(r'(\d+\.?\d*)')[0], errors='coerce')
            df.loc[df[col] > 100, col] = df[col] / 10

    if 'temp' in df.columns and 'humi' in df.columns:
        df['VPD'] = df.apply(lambda r: calculate_vpd(r['temp'], r['humi']), axis=1)
    
    return df

uploaded_file = st.sidebar.file_uploader("Tải file JSON số liệu nhà kính", type=['json'])

if uploaded_file:
    df = process_data(uploaded_file)
    if not df.empty:
        # --- SIDEBAR CỦA NHÀ KÍNH ---
        st.sidebar.header("🎯 Cài đặt Vận hành")
        
        # Thêm tùy chọn chọn giai đoạn cây trồng
        growth_stage = st.sidebar.radio(
            "Giai đoạn của cây trồng:",
            ["🌱 Cây con / Ươm mầm (0.4 - 0.8 kPa)", 
             "🌿 Sinh trưởng phát triển (0.8 - 1.2 kPa)", 
             "🍅 Ra hoa / Đậu quả (1.2 - 1.5 kPa)"],
             index=1
        )
        
        st.sidebar.markdown("---")
        st.sidebar.header("📅 Lọc thời gian")
        df['Tháng_năm'] = df['Thời gian'].dt.strftime('%m/%Y')
        filter_mode = st.sidebar.radio("Cách chọn mốc:", ["Theo tháng", "Khoảng ngày"], horizontal=True)
        
        if filter_mode == "Theo tháng":
            sel_months = st.sidebar.multiselect("Bấm chọn tháng:", df['Tháng_năm'].unique(), default=df['Tháng_năm'].unique()[-1:])
            df_filtered = df[df['Tháng_năm'].isin(sel_months)].copy()
        else:
            min_dt, max_dt = df['Thời gian'].min().date(), df['Thời gian'].max().date()
            c1, c2 = st.sidebar.columns(2)
            start_date = pd.to_datetime(c1.date_input("Từ ngày", min_dt))
            end_date = pd.to_datetime(c2.date_input("Đến ngày", max_dt)) + timedelta(days=1)
            df_filtered = df[(df['Thời gian'] >= start_date) & (df['Thời gian'] < end_date)].copy()

        st.sidebar.markdown("---")
        st.sidebar.header("⚙️ Hiển thị")
        if 'STT' in df_filtered.columns:
            stt_list = ["Tất cả"] + sorted(df_filtered['STT'].dropna().unique().astype(str).tolist())
            sel_stt = st.sidebar.selectbox("📍 Chọn Trạm/Khu vực:", stt_list)
            if sel_stt != "Tất cả":
                df_filtered = df_filtered[df_filtered['STT'].astype(str) == sel_stt]

        view_opt = st.sidebar.selectbox("📊 Gộp dữ liệu:", ["Gốc (Từng phút)", "Giờ", "Ngày"])

        # --- GIAO DIỆN HIỂN THỊ CHÍNH ---
        if not df_filtered.empty:
            if 'VPD' in df_filtered.columns and not df_filtered['VPD'].dropna().empty:
                last = df_filtered.dropna(subset=['VPD']).iloc[-1]
                
                # Gọi hàm lời khuyên mới truyền vào giai đoạn cây
                status, advice, color = get_greenhouse_advice(last['VPD'], growth_stage)
                
                st.subheader(f"📍 Chỉ đạo vận hành nhà kính (Số liệu hiện tại)")
                col1, col2, col3 = st.columns([1, 1, 2])
                col1.metric("Nhiệt độ hiện tại", f"{last['temp']} °C")
                col1.metric("Độ ẩm hiện tại", f"{last['humi']} %")
                col2.markdown(f"<div style='padding:15px; border-radius:10px; background-color:{color}; color:white; text-align:center; font-size:20px;'><b>VPD: {last['VPD']} kPa</b><br><small>{status}</small></div>", unsafe_allow_html=True)
                col3.info(f"**Lệnh thiết bị:** {advice}")

                freq_map = {"Giờ": "1h", "Ngày": "1d", "Gốc (Từng phút)": None}
                freq = freq_map[view_opt]
                df_plot = df_filtered.set_index('Thời gian').resample(freq).mean(numeric_only=True).reset_index() if freq else df_filtered
                
                st.markdown("---")
                fig = make_subplots(rows=2, cols=1, shared_xaxes=True, subplot_titles=("Diễn biến áp suất VPD (kPa)", "Biến động Nhiệt độ & Độ ẩm"), vertical_spacing=0.1)
                
                # Biểu đồ VPD (Cập nhật vùng lý tưởng theo giai đoạn)
                if "Cây con" in growth_stage: y_min, y_max = 0.4, 0.8
                elif "Sinh trưởng" in growth_stage: y_min, y_max = 0.8, 1.2
                else: y_min, y_max = 1.2, 1.5

                fig.add_trace(go.Scatter(x=df_plot['Thời gian'], y=df_plot['VPD'], name="VPD", mode='lines', line=dict(color='green', width=2)), row=1, col=1)
                fig.add_hrect(y0=y_min, y1=y_max, fillcolor="green", opacity=0.15, line_width=0, row=1, col=1, annotation_text=f"Lý tưởng ({y_min}-{y_max})")
                
                fig.add_trace(go.Scatter(x=df_plot['Thời gian'], y=df_plot['temp'], name="Nhiệt độ (°C)", mode='lines'), row=2, col=1)
                fig.add_trace(go.Scatter(x=df_plot['Thời gian'], y=df_plot['humi'], name="Độ ẩm (%)", mode='lines'), row=2, col=1)
                
                fig.update_layout(height=550, hovermode="x unified")
                st.plotly_chart(fig, use_container_width=True)
                
                with st.expander("🔍 Xem dữ liệu thô"):
                    st.dataframe(df_plot.drop(columns=['Tháng_năm'], errors='ignore'), use_container_width=True)
            else:
                st.warning("⚠️ Không đủ số liệu nhiệt/ẩm để tính VPD.")
        else:
            st.warning("Không có dữ liệu. Vui lòng chọn lại mốc thời gian!")
    else:
        st.error("Lỗi đọc file.")
else:
    st.info("👈 Tải file JSON nhà kính lên sidebar để xem.")
