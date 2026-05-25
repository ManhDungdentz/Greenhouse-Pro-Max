import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# ==========================================
# 1. CẤU HÌNH GIAO DIỆN & CSS (GIỮ NGUYÊN)
# ==========================================
st.set_page_config(page_title="Hệ Thống Giám Sát VPD Nhà Kính", layout="wide")

st.markdown("""
    <style>
    .main { background-color: #f5f7f9; }
    .stMetric { background-color: #ffffff; padding: 15px; border-radius: 10px; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }
    .status-card { padding: 20px; border-radius: 15px; color: white; text-align: center; margin-bottom: 20px; }
    </style>
    """, unsafe_allow_html=True)

# ==========================================
# 2. HÀM GỬI EMAIL (GIỮ NGUYÊN)
# ==========================================
def send_email_alert(sender_email, app_password, receiver_email, vpd_value, status, temp, humi):
    try:
        msg = MIMEMultipart()
        msg['From'] = sender_email
        msg['To'] = receiver_email
        msg['Subject'] = f"🚨 CẢNH BÁO VPD: {status}"
        
        body = f"""
        Hệ thống ghi nhận trạng thái bất thường:
        - Trạng thái: {status}
        - Chỉ số VPD: {vpd_value} kPa
        - Nhiệt độ: {temp} °C
        - Độ ẩm: {humi} %
        - Thời gian: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
        
        Vui lòng kiểm tra lại hệ thống điều hòa và phun sương!
        """
        msg.attach(MIMEText(body, 'plain'))
        
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(sender_email, app_password)
        server.send_message(msg)
        server.quit()
        return True
    except Exception as e:
        st.error(f"Lỗi gửi mail: {e}")
        return False

# ==========================================
# 3. HÀM TÍNH TOÁN VPD (CHUẨN TOÁN HỌC)
# ==========================================
def calculate_vpd(temp, humi):
    if pd.isna(temp) or pd.isna(humi) or humi <= 0:
        return None
    # Áp suất hơi bão hòa
    vpsat = 0.61078 * np.exp((17.27 * temp) / (temp + 237.3))
    # Áp suất hơi thực tế
    vpair = vpsat * (humi / 100)
    return round(vpsat - vpair, 2)

# ==========================================
# 4. XỬ LÝ DỮ LIỆU (CHỖ NÀY ĐÃ SỬA THEO Ý ÔNG)
# ==========================================
def process_data(file):
    try:
        df = pd.read_json(file)
    except:
        return pd.DataFrame()

    if 'Thời gian' in df.columns:
        df['Thời gian'] = pd.to_datetime(df['Thời gian'].astype(str).str.replace('-', ' ', n=2).str.replace('-', ':'), errors='coerce')
        df = df.dropna(subset=['Thời gian']).sort_values('Thời gian')

    # --- ĐẢO NGƯỢC: NHIỆT LẤY TỪ HUMIKK, ẨM LẤY TỪ TEMPKK ---
    # Không chia 10, giữ nguyên số thực (ví dụ 46.32)
    if 'humiKK' in df.columns and 'tempKK' in df.columns:
        df['temp'] = pd.to_numeric(df['humiKK'], errors='coerce')
        df['humi'] = pd.to_numeric(df['tempKK'], errors='coerce')
    
    # Nếu file có dạng Nhiệt Độ/PH (chia 10)
    elif 'Nhiệt Độ' in df.columns and 'PH' in df.columns:
        df['temp'] = pd.to_numeric(df['Nhiệt Độ'], errors='coerce') / 10
        df['humi'] = pd.to_numeric(df['PH'], errors='coerce') / 10

    # Tính VPD dựa trên cột đã đảo
    df = df.dropna(subset=['temp', 'humi'])
    if not df.empty:
        df['VPD'] = df.apply(lambda r: calculate_vpd(r['temp'], r['humi']), axis=1)
    
    return df

# ==========================================
# 5. GIAO DIỆN CHÍNH (FULL 300 DÒNG)
# ==========================================
def main():
    st.title("🌿 Hệ Thống Giám Sát & Điều Khiển VPD")
    
    # --- SIDEBAR CẤU HÌNH ---
    with st.sidebar:
        st.header("⚙️ Cấu hình")
        u_mail = st.text_input("Gmail gửi thông báo:")
        u_pass = st.text_input("Mật khẩu App (Gmail):", type="password")
        t_mail = st.text_input("Gmail nhận thông báo:")
        
        st.divider()
        crop_type = st.selectbox("🌱 Loại cây trồng:", ["🌶️ Ớt chuông", "🥒 Dưa leo", "🍈 Dưa lưới", "🍅 Cà chua"])
        
        # Ngưỡng VPD
        if crop_type == "🌶️ Ớt chuông":
            low, ideal_min, ideal_max, warn_max = 0.6, 0.8, 1.2, 1.5
        elif crop_type == "🥒 Dưa leo":
            low, ideal_min, ideal_max, warn_max = 0.7, 0.9, 1.3, 1.6
        else:
            low, ideal_min, ideal_max, warn_max = 0.8, 1.0, 1.4, 1.8
            
        uploaded_file = st.file_uploader("Tải file dữ liệu JSON", type=['json'])

    if uploaded_file:
        df = process_data(uploaded_file)
        
        if not df.empty:
            last_row = df.iloc[-1]
            cur_vpd = last_row['VPD']
            cur_temp = last_row['temp']
            cur_humi = last_row['humi']
            
            # Xác định trạng thái
            if cur_vpd < low:
                status, advice, color = "🔵 QUÁ THẤP", "Ẩm độ quá cao, hãy bật quạt thông gió!", "#1E90FF"
            elif ideal_min <= cur_vpd <= ideal_max:
                status, advice, color = "🟢 LÝ TƯỞNG", "Môi trường hoàn hảo cho cây!", "#00C851"
            elif cur_vpd <= warn_max:
                status, advice, color = "🟡 CẢNH BÁO", "Hơi khô, xem xét phun sương.", "#FFA500"
            else:
                status, advice, color = "🔴 QUÁ CAO", "Quá khô và nóng! Bật phun sương ngay!", "#FF4B4B"

            # --- HIỂN THỊ STATUS CARD ---
            st.markdown(f"""
                <div class="status-card" style="background-color: {color};">
                    <h1 style="margin:0;">VPD: {cur_vpd} kPa</h1>
                    <h2 style="margin:0;">Trạng thái: {status}</h2>
                    <p style="font-size: 1.2em;">{advice}</p>
                </div>
                """, unsafe_allow_html=True)

            # --- METRICS ---
            c1, c2, c3 = st.columns(3)
            with c1: st.metric("Nhiệt độ (Đã đảo)", f"{cur_temp} °C")
            with c2: st.metric("Độ ẩm (Đã đảo)", f"{cur_humi} %")
            with c3:
                if st.button("🚀 Gửi Mail Báo Cáo"):
                    if u_mail and u_pass and t_mail:
                        if send_email_alert(u_mail, u_pass, t_mail, cur_vpd, status, cur_temp, cur_humi):
                            st.success("Đã gửi email!")
                    else:
                        st.error("Thiếu cấu hình Email!")

            # --- BIỂU ĐỒ (SỬ DỤNG SUBPLOTS CHO DÀI) ---
            st.divider()
            fig = make_subplots(rows=2, cols=1, shared_xaxes=True, 
                               vertical_spacing=0.1,
                               subplot_titles=("Biến thiên VPD", "Nhiệt độ & Độ ẩm"))
            
            fig.add_trace(go.Scatter(x=df['Thời gian'], y=df['VPD'], name="VPD (kPa)", 
                                    line=dict(color='green', width=3)), row=1, col=1)
            fig.add_trace(go.Scatter(x=df['Thời gian'], y=df['temp'], name="Nhiệt độ (°C)", 
                                    line=dict(color='red')), row=2, col=1)
            fig.add_trace(go.Scatter(x=df['Thời gian'], y=df['humi'], name="Độ ẩm (%)", 
                                    line=dict(color='blue')), row=2, col=1)
            
            fig.update_layout(height=600, showlegend=True, template="plotly_white")
            st.plotly_chart(fig, use_container_width=True)

            # --- DATA TABLE ---
            with st.expander("Dữ liệu chi tiết"):
                st.write(df[['Thời gian', 'temp', 'humi', 'VPD']].sort_values('Thời gian', ascending=False))
        else:
            st.error("File không hợp lệ!")

if __name__ == "__main__":
    main()
