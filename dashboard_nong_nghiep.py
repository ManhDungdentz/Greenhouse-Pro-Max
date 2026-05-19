import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

st.set_page_config(page_title="Greenhouse Monitoring", layout="wide")
st.title("🌿 Hệ Thống Giám Sát Nhà Kính")

# --- 1. TÍNH TOÁN VPD ---
def calculate_vpd(temp, humi):
    if pd.isna(temp) or pd.isna(humi): return None
    vpsat = 0.61078 * np.exp((17.27 * temp) / (temp + 237.3))
    vpair = vpsat * (humi / 100)
    return round(vpsat - vpair, 2)

# --- 2. XỬ LÝ DỮ LIỆU & LỌC SAI SỐ ---
def process_data(file):
    try:
        df = pd.read_json(file)
    except: return pd.DataFrame()

    if 'Thời gian' in df.columns:
        df['Thời gian'] = pd.to_datetime(df['Thời gian'].astype(str).str.replace('-', ' ', n=2).str.replace('-', ':'), errors='coerce')
        df = df.dropna(subset=['Thời gian']).sort_values('Thời gian')
    
    t_cols = [c for c in ['Nhiệt Độ', 'tempKK'] if c in df.columns]
    if t_cols: df['temp'] = df[t_cols].bfill(axis=1).iloc[:, 0]
    h_cols = [c for c in ['Độ ẩm', 'humiKK'] if c in df.columns]
    if h_cols: df['humi'] = df[h_cols].bfill(axis=1).iloc[:, 0]
        
    for col in ['temp', 'humi']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col].astype(str).str.extract(r'(\d+\.?\d*)')[0], errors='coerce')
            if col == 'temp':
                df.loc[df[col] > 150, col] = df[col] / 10 
                df.loc[(df[col] >= 45) & (df[col] <= 120), col] = (df[col] - 32) * 5/9 
                # Lọc bỏ nhiệt độ rác > 50 độ C để tránh VPD ảo (51.39 kPa)
                df.loc[df[col] > 50, col] = np.nan 
            if col == 'humi':
                # Lọc bỏ độ ẩm < 10% (thường là lỗi cảm biến)
                df.loc[df[col] < 10, col] = np.nan 
    
    df = df.dropna(subset=['temp', 'humi']).copy()
    df['VPD'] = df.apply(lambda r: calculate_vpd(r['temp'], r['humi']), axis=1)
    return df

# --- 3. GIAO DIỆN ---
uploaded_file = st.sidebar.file_uploader("Tải file JSON", type=['json'])

if uploaded_file:
    df = process_data(uploaded_file)
    if not df.empty:
        # Chọn trạm
        stt_list = ["Tất cả"] + sorted(df['STT'].unique().tolist())
        sel_stt = st.sidebar.selectbox("📍 Chọn Trạm:", stt_list)
        df_work = df if sel_stt == "Tất cả" else df[df['STT'] == sel_stt]

        if not df_work.empty:
            last = df_work.iloc[-1]
            
            # Hiển thị chỉ số lớn
            c1, c2, c3 = st.columns(3)
            c1.metric("Nhiệt độ", f"{last['temp']} °C")
            c2.metric("Độ ẩm", f"{last['humi']} %")
            
            # Cảnh báo mốc 0.5 - 1.5 kPa
            vpd_val = last['VPD']
            color = "green" if 0.5 <= vpd_val <= 1.5 else "red"
            c3.markdown(f"""
                <div style="padding:10px; border-radius:10px; background-color:{color}; color:white; text-align:center;">
                    <b style="font-size:20px;">VPD: {vpd_val} kPa</b><br>
                    {"Lý tưởng" if color=="green" else "Cảnh báo sai số/Môi trường xấu"}
                </div>
            """, unsafe_allow_html=True)

            # Bảng chi tiết kèm màu sắc
            st.subheader("📋 Chi tiết bản ghi (Mốc an toàn 0.5 - 1.5 kPa)")
            
            def highlight_vpd(val):
                color = 'background-color: #ffcccc' if (val < 0.5 or val > 1.5) else ''
                return color

            # Hiển thị bảng có tô màu những dòng ngoài ngưỡng 0.5-1.5
            st.dataframe(
                df_work[['Thời gian', 'STT', 'temp', 'humi', 'VPD']]
                .sort_values('Thời gian', ascending=False)
                .style.applymap(highlight_vpd, subset=['VPD']),
                use_container_width=True
            )

            # Gợi ý vận hành
            if vpd_val > 1.5:
                st.warning("⚠️ **Chỉ đạo:** VPD đang cao (>1.5). Hãy bật phun sương hoặc Cooling Pad ngay!")
            elif vpd_val < 0.5:
                st.info("ℹ️ **Chỉ đạo:** VPD thấp (<0.5). Cần tăng thông thoáng để giảm ẩm.")

else:
    st.info("Vui lòng tải file lên.")
