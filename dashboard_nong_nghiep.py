import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import timedelta
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# --- 1. CẤU HÌNH TRANG ---
st.set_page_config(page_title="Greenhouse Pro Max", layout="wide")
st.title("🌿 Giám Sát Nhà Kính (Bản Full: Khử Nhiễu & Ngưỡng 1.5)")

# --- 2. HÀM GỬI EMAIL CẢNH BÁO ---
def send_email_alert(sender_mail, app_password, receiver_mail, vpd, status, temp, humi):
    try:
        msg = MIMEMultipart()
        msg['Subject'] = f"🚨 CẢNH BÁO VPD: {status}"
        body = f"📍 TRẠNG THÁI: {status}\nVPD: {vpd} kPa\nNhiệt độ: {temp}°C\nĐộ ẩm: {humi}%"
        msg.attach(MIMEText(body, 'plain', 'utf-8'))
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(sender_mail, app_password)
        server.sendmail(sender_mail, receiver_mail, msg.as_string())
        server.quit()
        return True
    except Exception:
        return False

# --- 3. CÔNG THỨC TÍNH VPD ---
def calculate_vpd(temp, humi):
    if pd.isna(temp) or pd.isna(humi) or humi <= 5: return None
    # Áp suất hơi bão hòa
    vpsat = 0.61078 * np.exp((17.27 * temp) / (temp + 237.3))
    # Áp suất hơi thực tế
    vpair = vpsat * (humi / 100)
    return round(max(0, vpsat - vpair), 2)

# --- 4. XỬ LÝ DỮ LIỆU & BỘ LỌC KHỬ NHIỄU "CỘT ĐÌNH" ---
def process_data(file):
    try:
        df = pd.read_json(file)
    except: return pd.DataFrame()
    
    # Chuẩn hóa thời gian
    if 'Thời gian' in df.columns:
        df['Thời gian'] = pd.to_datetime(df['Thời gian'].astype(str).str.replace('-', ' ', n=2).str.replace('-', ':'), errors='coerce', utc=True).dt.tz_localize(None)
        df = df.dropna(subset=['Thời gian']).sort_values('Thời gian')
    
    # Gộp các cột Nhiệt độ và Độ ẩm từ các trạm (STT) khác nhau
    t_cols = [c for c in ['Nhiệt Độ', 'tempKK'] if c in df.columns]
    if t_cols: df['temp'] = df[t_cols].bfill(axis=1).iloc[:, 0]
    h_cols = [c for c in ['Độ ẩm', 'humiKK'] if c in df.columns]
    if h_cols: df['humi'] = df[h_cols].bfill(axis=1).iloc[:, 0]
    
    for col in ['temp', 'humi']:
        if col in df.columns:
            # Chuyển về số
            df[col] = pd.to_numeric(df[col].astype(str).str.extract(r'(\d+\.?\d*)')[0], errors='coerce')
            
            # Xử lý độ F sang độ C và chặn rác vật lý cực đoan
            if col == 'temp':
                df.loc[df[col] > 150, col] = df[col] / 10 
                df.loc[(df[col] >= 45) & (df[col] <= 120), col] = (df[col] - 32) * 5/9 
                df.loc[(df[col] < 5) | (df[col] > 55), col] = np.nan
            if col == 'humi':
                df.loc[(df[col] < 15) | (df[col] > 100), col] = np.nan

    # KHỬ NHIỄU ĐA TẦNG (Smoothing)
    df = df.dropna(subset=['temp', 'humi']).copy()
    if len(df) > 5:
        for c in ['temp', 'humi']:
            # Lọc trung vị cửa sổ 5 để triệt tiêu các "cột đình" nhọn hoắt đơn lẻ
            df[c] = df[c].rolling(window=5, center=True, min_periods=1).median()
            # Xóa các bước nhảy quá lớn (> 5 đơn vị) trong thời gian ngắn
            diff = df[c].diff().abs()
            df.loc[diff > 5, c] = np.nan
            df[c] = df[c].interpolate().ffill().bfill()

    if not df.empty: 
        df['VPD'] = df.apply(lambda r: calculate_vpd(r['temp'], r['humi']), axis=1)
        # Giới hạn VPD để tránh các điểm lỗi còn sót làm hỏng scale biểu đồ
        df.loc[df['VPD'] > 2.8, 'VPD'] = np.nan
        df['VPD'] = df['VPD'].interpolate()
        
    return df

# --- 5. GIAO DIỆN CHÍNH ---
with st.sidebar:
    st.header("⚙️ Cấu Hình Hệ Thống")
    u_mail = st.text_input("Gmail gửi thông báo:")
    u_pass = st.text_input("Mật khẩu ứng dụng (App Password):", type="password")
    t_mail = st.text_input("Gmail nhận cảnh báo:")
    st.divider()
    uploaded_file = st.file_uploader("Tải file JSON dữ liệu", type=['json'])

if uploaded_file:
    df = process_data(uploaded_file)
    if not df.empty:
        # Bộ lọc Trạm và Thời gian
        st.sidebar.header("🔍 Bộ Lọc Dữ Liệu")
        stt_list = ["Tất cả"] + sorted(df['STT'].unique().tolist())
        sel_stt = st.sidebar.selectbox("Chọn Trạm (STT):", stt_list)
        df_work = df if sel_stt == "Tất cả" else df[df['STT'] == sel_stt]

        # Dashboard thông số tức thời
        df_valid = df_work.dropna(subset=['VPD'])
        if not df_valid.empty:
            last = df_valid.iloc[-1]
            vpd_val = last['VPD']
            
            # --- CÀI ĐẶT NGƯỠNG ĐỎ TRÊN 1.5 THEO YÊU CẦU ---
            if vpd_val > 1.5:
                color, status, advice = "#FF4B4B", "🔴 QUÁ CAO (STRESS)", "Cần phun sương làm mát và tăng ẩm ngay!"
            elif vpd_val < 0.5:
                color, status, advice = "#1E90FF", "🔵 QUÁ THẤP (ẨM CAO)", "Ngừng tưới, tăng thông gió để tránh nấm bệnh."
            else:
                color, status, advice = "#00C851", "🟢 LÝ TƯỞNG", "Môi trường hoàn hảo cho cây phát triển."

            st.subheader(f"📍 Trạng thái Trạm: {last['STT']}")
            m1, m2, m3 = st.columns([1, 1, 2])
            m1.metric("Nhiệt độ", f"{round(last['temp'], 1)} °C")
            m1.metric("Độ ẩm", f"{round(last['humi'], 1)} %")
            
            m2.markdown(f'''
                <div style="background-color:{color}; padding:20px; border-radius:15px; color:white; text-align:center;">
                    <h2 style="margin:0;">VPD: {vpd_val}</h2>
                    <b style="font-size:1.1em;">{status}</b>
                </div>
            ''', unsafe_allow_html=True)
            
            m3.info(f"**Chỉ đạo:** {advice}\n\n*Cập nhật: {last['Thời gian'].strftime('%H:%M - %d/%m/%Y')}*")

            if st.button("📧 Gửi Email Cảnh Báo Khẩn Cấp"):
                if send_email_alert(u_mail, u_pass, t_mail, vpd_val, status, last['temp'], last['humi']):
                    st.success("✅ Đã gửi email cảnh báo!")
                else:
                    st.error("❌ Gửi lỗi! Kiểm tra Gmail và mật khẩu ứng dụng.")

            # --- 6. BIỂU ĐỒ DIỄN BIẾN (KHÓA TRỤC Y) ---
            st.subheader("📊 Diễn biến môi trường (Đã làm mượt)")
            fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.08)
            
            # Đường biểu đồ VPD
            fig.add_trace(go.Scatter(x=df_valid['Thời gian'], y=df_valid['VPD'], 
                                     name="VPD (kPa)", line=dict(color='green', width=3)), row=1, col=1)
            
            # Vẽ các dải màu ngưỡng mới (Xanh: 0.5-1.5, Đỏ: >1.5)
            fig.add_hrect(y0=0, y1=0.5, fillcolor="rgba(30, 144, 255, 0.3)", line_width=0, row=1, col=1)
            fig.add_hrect(y0=0.5, y1=1.5, fillcolor="rgba(0, 200, 81, 0.3)", line_width=0, row=1, col=1)
            fig.add_hrect(y0=1.5, y1=2.8, fillcolor="rgba(255, 75, 75, 0.3)", line_width=0, row=1, col=1)
            
            # Đường Nhiệt độ & Độ ẩm
            fig.add_trace(go.Scatter(x=df_valid['Thời gian'], y=df_valid['temp'], name="Nhiệt độ (°C)"), row=2, col=1)
            fig.add_trace(go.Scatter(x=df_valid['Thời gian'], y=df_valid['humi'], name="Độ ẩm (%)"), row=2, col=1)
            
            fig.update_layout(height=600, template="plotly_white", hovermode='x unified',
                              margin=dict(l=20, r=20, t=20, b=20))
            # KHÓA TRỤC Y VPD ĐỂ KHÔNG BỊ "NHẢY"
            fig.update_yaxes(range=[0, 2.5], row=1, col=1)
            st.plotly_chart(fig, use_container_width=True)

            # --- 7. BẢNG DỮ LIỆU CHI TIẾT ---
            st.subheader("📋 Thống kê & Dữ liệu chi tiết")
            st.table(df_valid[['temp', 'humi', 'VPD']].agg(['max', 'min', 'mean']).round(2))
            
            def highlight_rows(row):
                if row['VPD'] > 1.5: return ['background-color: #FFC7CE; color: #9C0006'] * len(row)
                return [''] * len(row)

            st.dataframe(
                df_valid[['Thời gian', 'STT', 'temp', 'humi', 'VPD']]
                .sort_values('Thời gian', ascending=False)
                .style.apply(highlight_rows, axis=1),
                use_container_width=True
            )
        else:
            st.error("🚨 Không tìm thấy dữ liệu hợp lệ trong trạm này.")
else:
    st.info("👈 Vui lòng tải file JSON vào thanh bên để xem biểu đồ.")

