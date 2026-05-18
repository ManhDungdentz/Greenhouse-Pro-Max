import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import re

st.set_page_config(page_title="Hệ thống Cảnh báo VPD Pro", layout="wide")

# --- HÀM TÍNH TOÁN VPD ---
def calculate_vpd(temp, humi):
    """
    Công thức tính VPD (kPa):
    VPsat = 0.61078 * exp((17.27 * T) / (T + 237.3))
    VPair = VPsat * (RH / 100)
    VPD = VPsat - VPair
    """
    if temp is None or humi is None: return None
    vpsat = 0.61078 * np.exp((17.27 * temp) / (temp + 237.3))
    vpair = vpsat * (humi / 100)
    return round(vpsat - vpair, 2)

def get_vpd_advice(vpd):
    if vpd < 0.4:
        return "🔴 QUÁ THẤP", "Nguy cơ nấm bệnh cao. Cần: Tăng nhiệt độ hoặc Giảm độ ẩm (Bật quạt thông gió).", "#FF4B4B"
    elif 0.4 <= vpd <= 0.8:
        return "🟡 THẤP (Nhân giống)", "Phù hợp cho cây con/nhân giống. Cây lớn: Tăng nhẹ thông thoáng.", "#FFD700"
    elif 0.8 < vpd <= 1.2:
        return "🟢 LÝ TƯỞNG", "Cây quang hợp tốt nhất. Giữ nguyên điều kiện hiện tại.", "#00C851"
    elif 1.2 < vpd <= 1.6:
        return "🟡 CAO", "Cây thoát hơi nước nhanh. Cần: Giảm nhiệt độ hoặc Tăng độ ẩm (Phun sương).", "#FFA500"
    else:
        return "🔴 QUÁ CAO", "Cây bị stress nhiệt, đóng lỗ khí. Cần: Giảm nhiệt khẩn cấp, che nắng, phun sương mạnh.", "#8B0000"

# --- XỬ LÝ DỮ LIỆU ---
def process_data(file):
    df = pd.read_json(file)
    # Chuẩn hóa tên cột (Vì file của bạn có lúc dùng 'Nhiệt Độ', lúc dùng 'tempKK')
    col_map = {
        'Nhiệt Độ': 'temp', 'tempKK': 'temp',
        'Độ ẩm': 'humi', 'humiKK': 'humi',
        'Thời gian': 'time'
    }
    df = df.rename(columns=col_map)
    
    # Chuyển đổi số liệu sạch
    for col in ['temp', 'humi']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col].astype(str).str.extract('(\d+\.?\d*)')[0], errors='coerce')
    
    # Xử lý sai lệch đơn vị (Ví dụ Nhiệt độ 335 -> 33.5)
    if 'temp' in df.columns:
        df.loc[df['temp'] > 100, 'temp'] = df['temp'] / 10
    if 'humi' in df.columns:
        df.loc[df['humi'] > 100, 'humi'] = df['humi'] / 10

    # Tính VPD cho từng dòng
    if 'temp' in df.columns and 'humi' in df.columns:
        df['VPD'] = df.apply(lambda row: calculate_vpd(row['temp'], row['humi']), axis=1)
    
    return df

# --- GIAO DIỆN ---
st.title("🌿 Công cụ Phân tích & Cảnh báo VPD")

uploaded_file = st.file_uploader("Tải file dữ liệu nông nghiệp (.json)", type=['json'])

if uploaded_file:
    df = process_data(uploaded_file)
    
    # 1. Hiển thị trạng thái hiện tại (Dòng cuối cùng)
    last_row = df.iloc[-1]
    vpd_val = last_row['VPD']
    status, advice, color = get_vpd_advice(vpd_val)

    st.markdown(f"### 📍 Trạng thái hiện tại (Lần đo cuối)")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Nhiệt độ", f"{last_row['temp']} °C")
    c2.metric("Độ ẩm", f"{last_row['humi']} %")
    c3.markdown(f"<div style='padding:10px; border-radius:10px; background-color:{color}; color:white; text-align:center;'><b>VPD: {vpd_val} kPa</b><br>{status}</div>", unsafe_allow_html=True)
    c4.info(f"**Lời khuyên:** {advice}")

    # 2. Giả lập thông báo điện thoại
    if vpd_val > 1.6 or vpd_val < 0.4:
        st.toast(f"🚨 CẢNH BÁO: VPD đang ở mức nguy hiểm ({vpd_val} kPa)!", icon="⚠️")
        st.sidebar.warning(f"📲 Đang gửi thông báo tới điện thoại: VPD {status}!")

    # 3. Biểu đồ VPD theo thời gian
    st.markdown("---")
    st.subheader("📈 Biểu đồ diễn biến VPD")
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df.index, y=df['VPD'], mode='lines+markers', name='VPD (kPa)', line=dict(color='green', width=3)))
    
    # Vẽ các vùng ranh giới
    fig.add_hrect(y0=0.8, y1=1.2, fillcolor="green", opacity=0.1, annotation_text="Lý tưởng", annotation_position="top left")
    fig.add_hrect(y0=1.6, y1=3.0, fillcolor="red", opacity=0.1, annotation_text="Nguy hiểm (Khô)", annotation_position="top left")
    
    fig.update_layout(hovermode="x unified", yaxis_title="kPa")
    st.plotly_chart(fig, use_container_width=True)

    # 4. Bảng dữ liệu lọc các trường hợp bất thường
    with st.expander("🔍 Danh sách các thời điểm VPD bất thường"):
        bad_df = df[(df['VPD'] > 1.6) | (df['VPD'] < 0.4)]
        st.write(bad_df[['temp', 'humi', 'VPD']])

else:
    st.info("Vui lòng tải file để hệ thống tính toán áp suất VPD.")
