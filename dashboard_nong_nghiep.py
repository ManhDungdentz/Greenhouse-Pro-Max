import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# --- 1. CẤU HÌNH ---
st.set_page_config(page_title="Greenhouse Analytics Pro", layout="wide")

# --- 2. HÀM TÍNH TOÁN & CHẨN ĐOÁN ---
def calculate_vpd(temp, humi):
    if pd.isna(temp) or pd.isna(humi) or temp <= 0: return 0.0
    vpsat = 0.61078 * np.exp((17.27 * temp) / (temp + 237.3))
    vpair = vpsat * (humi / 100)
    return round(vpsat - vpair, 2)

def get_status_ui(vpd, stage):
    # Ngưỡng lý tưởng tùy theo giai đoạn
    if "Cây con" in stage: i_min, i_max = 0.4, 0.8
    elif "Sinh trưởng" in stage: i_min, i_max = 0.8, 1.2
    else: i_min, i_max = 1.2, 1.5
    
    if vpd < i_min - 0.2: return "🔵 THẤP", "Nguy cơ nấm bệnh cao!", "#3498db"
    if i_min <= vpd <= i_max: return "🟢 LÝ TƯỞNG", "Cây đang phát triển tối ưu.", "#2ecc71"
    return "🔴 CAO", "Cây bị stress nhiệt/thoát hơi nước quá nhanh!", "#e74c3c"

# --- 3. THANH ĐIỀU KHIỂN (SIDEBAR) ---
with st.sidebar:
    st.header("📂 Quản lý dữ liệu")
    uploaded_file = st.file_uploader("Nhét file JSON 13MB vào đây 👇", type=['json'])
    
    st.divider()
    st.header("🌱 Cài đặt nông nghiệp")
    stage = st.radio("Giai đoạn phát triển:", ["🌱 Cây con", "🌿 Sinh trưởng", "🍅 Ra hoa"], index=1)
    
    st.divider()
    st.info("Bản này đã fix lỗi Mixed Timezone và lọc số liệu sensor lỗi.")

# --- 4. XỬ LÝ DỮ LIỆU TỪ FILE ---
if uploaded_file is not None:
    try:
        df_raw = pd.read_json(uploaded_file)
        
        # Tự động nhận diện cột (Mapping)
        t_col = next((c for c in df_raw.columns if any(k in c.lower() for k in ['temp', 'nhiệt', 't_kk'])), None)
        h_col = next((c for c in df_raw.columns if any(k in c.lower() for k in ['humi', 'ẩm', 'h_kk'])), None)
        time_col = next((c for c in df_raw.columns if any(k in c.lower() for k in ['thời', 'time', 'date'])), None)

        if t_col and h_col:
            # Làm sạch và ép kiểu
            df_raw['temp'] = pd.to_numeric(df_raw[t_col].astype(str).str.extract(r'(\d+\.?\d*)')[0], errors='coerce')
            df_raw['humi'] = pd.to_numeric(df_raw[h_col].astype(str).str.extract(r'(\d+\.?\d*)')[0], errors='coerce')
            
            # Fix lỗi nhiệt độ nhảy số (331 -> 33.1)
            df_raw.loc[df_raw['temp'] > 150, 'temp'] = df_raw['temp'] / 10
            # Lọc bỏ dòng lỗi nặng
            df = df_raw[(df_raw['temp'] > 5) & (df_raw['temp'] < 60)].copy()

            # FIX LỖI TIMEZONE
            if time_col:
                df['Thời gian'] = pd.to_datetime(df[time_col], errors='coerce', utc=True).dt.tz_localize(None)
                df = df.dropna(subset=['Thời gian']).sort_values('Thời gian')

            # Tính VPD
            df['VPD'] = df.apply(lambda r: calculate_vpd(r['temp'], r['humi']), axis=1)

            # --- 5. GIAO DIỆN HIỂN THỊ ---
            st.title("🌿 Phân Tích Vi Khí Hậu Nhà Kính")
            
            last = df.iloc[-1]
            label, advice, color = get_status_ui(last['VPD'], stage)

            # Hàng 1: Thẻ tóm tắt
            col1, col2, col3 = st.columns([1, 1, 2])
            col1.metric("Nhiệt độ hiện tại", f"{last['temp']} °C")
            col1.metric("Độ ẩm hiện tại", f"{last['humi']} %")
            
            # Thẻ VPD trung tâm
            vpd_html = f"""
                <div style="background-color:{color}; color:white; padding:20px; border-radius:15px; text-align:center;">
                    <h2 style="margin:0; font-size:35px;">{last['VPD']} kPa</h2>
                    <p style="margin:0; font-weight:bold; font-size:20px;">{label}</p>
                </div>
            """
            col2.markdown(vpd_html, unsafe_allow_html=True)
            col3.warning(f"**Chẩn đoán:** {advice}")

            # Hàng 2: Biểu đồ
            st.subheader("📈 Biểu đồ lịch sử biến thiên")
            fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.1)
            fig.add_trace(go.Scatter(x=df['Thời gian'], y=df['VPD'], name="VPD (kPa)", line=dict(color='green', width=3)), row=1, col=1)
            fig.add_trace(go.Scatter(x=df['Thời gian'], y=df['temp'], name="Nhiệt độ (°C)", line=dict(color='red')), row=2, col=1)
            fig.add_trace(go.Scatter(x=df['Thời gian'], y=df['humi'], name="Độ ẩm (%)", line=dict(color='blue')), row=2, col=1)
            fig.update_layout(height=550, hovermode="x unified", margin=dict(t=20, b=20))
            st.plotly_chart(fig, use_container_width=True)

            # Hàng 3: Bảng dữ liệu chi tiết
            st.subheader("📋 Nhật ký thông số chi tiết")
            df_table = df[['Thời gian', 'temp', 'humi', 'VPD']].sort_values('Thời gian', ascending=False)
            # Ép kiểu string cho thời gian để hiện lên bảng đẹp
            df_table['Thời gian'] = df_table['Thời gian'].dt.strftime('%Y-%m-%d %H:%M:%S')
            st.dataframe(df_table, use_container_width=True, hide_index=True)

        else:
            st.error("❌ Không tìm thấy cột dữ liệu phù hợp trong file JSON!")
            
    except Exception as e:
        st.error(f"❌ Lỗi xử lý file: {e}")
else:
    # Màn hình chờ
    st.info("👋 Chào bạn! Hãy nhét file JSON vào thanh bên trái để bắt đầu phân tích dữ liệu thực tế.")
    st.image("https://img.freepik.com/free-vector/greenhouse-concept-illustration_114360-1234.jpg", width=400)
