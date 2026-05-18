import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

st.set_page_config(page_title="Dashboard AH4 Pro", layout="wide")
st.title("🌿 Hệ Thống Quản Trắc & Cảnh Báo VPD")

# --- HÀM TÍNH TOÁN VPD ---
def calculate_vpd(temp, humi):
    if pd.isna(temp) or pd.isna(humi): return None
    vpsat = 0.61078 * np.exp((17.27 * temp) / (temp + 237.3))
    vpair = vpsat * (humi / 100)
    return round(vpsat - vpair, 2)

def get_vpd_advice(vpd):
    if pd.isna(vpd): return "N/A", "Không đủ dữ liệu", "#808080"
    if vpd < 0.4: return "🔴 QUÁ THẤP", "Nguy cơ nấm bệnh. Cần tăng nhiệt hoặc giảm ẩm (bật quạt).", "#FF4B4B"
    if 0.4 <= vpd <= 0.8: return "🟡 THẤP", "Tốt cho cây con/nhân giống.", "#FFD700"
    if 0.8 < vpd <= 1.2: return "🟢 LÝ TƯỞNG", "Cây quang hợp tốt nhất. Giữ nguyên!", "#00C851"
    if 1.2 < vpd <= 1.6: return "🟡 CAO", "Cần giảm nhiệt hoặc phun sương tăng ẩm.", "#FFA500"
    return "🔴 QUÁ CAO", "Stress nhiệt nặng! Giảm nhiệt, tăng ẩm khẩn cấp.", "#8B0000"

# --- XỬ LÝ DỮ LIỆU ---
def process_data(file):
    try:
        df = pd.read_json(file)
    except: return pd.DataFrame()

    if 'Thời gian' in df.columns:
        df['Thời gian'] = pd.to_datetime(df['Thời gian'].astype(str).str.replace('-', ' ', n=2).str.replace('-', ':'), errors='coerce')
        df = df.dropna(subset=['Thời gian']).sort_values('Thời gian')
    
    # 1. Gộp các cột có ý nghĩa giống nhau thành 1 cột duy nhất (SỬA LỖI Ở ĐÂY)
    temp_cols = [c for c in ['Nhiệt Độ', 'tempKK'] if c in df.columns]
    if temp_cols:
        df['temp'] = df[temp_cols].bfill(axis=1).iloc[:, 0]
        
    humi_cols = [c for c in ['Độ ẩm', 'humiKK'] if c in df.columns]
    if humi_cols:
        df['humi'] = df[humi_cols].bfill(axis=1).iloc[:, 0]
        
    # 2. Xử lý làm sạch số liệu
    for col in ['temp', 'humi']:
        if col in df.columns:
            # Trích xuất số
            df[col] = pd.to_numeric(df[col].astype(str).str.extract(r'(\d+\.?\d*)')[0], errors='coerce')
            # Fix lỗi số liệu bị nhân 10 (VD trạm đo ra 335 thì chia 10 thành 33.5)
            df.loc[df[col] > 100, col] = df[col] / 10

    # 3. Tính áp suất VPD
    if 'temp' in df.columns and 'humi' in df.columns:
        df['VPD'] = df.apply(lambda r: calculate_vpd(r['temp'], r['humi']), axis=1)
    
    return df

uploaded_file = st.sidebar.file_uploader("Tải file JSON", type=['json'])

if uploaded_file:
    df = process_data(uploaded_file)
    if not df.empty:
        # --- Sidebar ---
        st.sidebar.header("⚙️ Cấu hình")
        view_opt = st.sidebar.selectbox("Gộp dữ liệu:", ["Gốc (Từng phút)", "Giờ", "Ngày"])
        
        if 'STT' in df.columns:
            stt_list = ["Tất cả"] + sorted(df['STT'].dropna().unique().astype(str).tolist())
            sel_stt = st.sidebar.selectbox("Chọn Trạm (STT):", stt_list)
            if sel_stt != "Tất cả":
                df = df[df['STT'].astype(str) == sel_stt]

        # --- Giao diện hiển thị ---
        if 'VPD' in df.columns and not df['VPD'].dropna().empty:
            last = df.dropna(subset=['VPD']).iloc[-1]
            status, advice, color = get_vpd_advice(last['VPD'])
            
            st.subheader(f"📍 Cảnh báo hiện tại (Lần đo cuối)")
            c1, c2, c3 = st.columns([1, 1, 2])
            c1.metric("Nhiệt độ", f"{last['temp']} °C")
            c1.metric("Độ ẩm", f"{last['humi']} %")
            c2.markdown(f"<div style='padding:15px; border-radius:10px; background-color:{color}; color:white; text-align:center; font-size:20px;'><b>VPD: {last['VPD']} kPa</b><br><small>{status}</small></div>", unsafe_allow_html=True)
            c3.info(f"**Khuyến nghị:** {advice}")

            # Xử lý gộp trung bình cho biểu đồ
            freq_map = {"Giờ": "1H", "Ngày": "1D", "Gốc (Từng phút)": None}
            freq = freq_map[view_opt]
            df_plot = df.set_index('Thời gian').resample(freq).mean(numeric_only=True).reset_index() if freq else df
            
            # Vẽ biểu đồ
            st.markdown("---")
            fig = make_subplots(rows=2, cols=1, shared_xaxes=True, subplot_titles=("Diễn biến áp suất VPD (kPa)", "Biến động Nhiệt độ & Độ ẩm"), vertical_spacing=0.1)
            
            # Biểu đồ VPD
            fig.add_trace(go.Scatter(x=df_plot['Thời gian'], y=df_plot['VPD'], name="VPD", mode='lines', line=dict(color='green', width=2)), row=1, col=1)
            fig.add_hrect(y0=0.8, y1=1.2, fillcolor="green", opacity=0.1, line_width=0, row=1, col=1, annotation_text="Vùng Lý Tưởng")
            fig.add_hrect(y0=1.6, y1=3.5, fillcolor="red", opacity=0.1, line_width=0, row=1, col=1, annotation_text="Vùng Cảnh Báo")
            
            # Biểu đồ Nhiệt & Ẩm
            fig.add_trace(go.Scatter(x=df_plot['Thời gian'], y=df_plot['temp'], name="Nhiệt độ (°C)", mode='lines'), row=2, col=1)
            fig.add_trace(go.Scatter(x=df_plot['Thời gian'], y=df_plot['humi'], name="Độ ẩm (%)", mode='lines'), row=2, col=1)
            
            fig.update_layout(height=550, hovermode="x unified")
            st.plotly_chart(fig, use_container_width=True)
            
            with st.expander("🔍 Chi tiết bảng dữ liệu"):
                st.dataframe(df_plot, use_container_width=True)
        else:
            st.warning("⚠️ Trạm này không có dữ liệu Nhiệt độ hoặc Độ ẩm để tính toán.")
    else:
        st.error("Không có dữ liệu hợp lệ trong file.")
else:
    st.info("👈 Vui lòng tải file JSON lên sidebar để bắt đầu.")
