import speedtest
import logging
import time
from statistics import mean, stdev
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from flask import Flask, render_template, jsonify, send_file
import threading
import matplotlib
import matplotlib.pyplot as plt
from io import BytesIO
import base64
matplotlib.use('Agg')
# Configuration
LEARNING_MODE_RUNS = 2#5
SPEED_TOLERANCE_FACTOR = 3
LEARNING_PHASE_SLEEP_INTERVAL = 1#60
MONITORING_PHASE_SLEEP_INTERVAL = 5#3600

# Data storage for plotting
download_speeds_over_time = []
upload_speeds_over_time = []

# Store the latest speed results
latest_download_speed = None
latest_upload_speed = None
speed_test_running = False

app = Flask(__name__)

# Function to read configurations
def read_email_config():
    config = {}
    with open("config.txt", "r") as file:
        for line in file:
            key, value = line.strip().split('=', 1)
            config[key] = value
    return config

config = read_email_config()

EMAIL_SENDER = config['EMAIL_SENDER']
EMAIL_PASSWORD = config['EMAIL_PASSWORD']
EMAIL_RECEIVER = config['EMAIL_RECEIVER']
SMTP_SERVER = config['SMTP_SERVER']
SMTP_PORT = int(config['SMTP_PORT'])

logging.basicConfig(filename='network_speed.log', level=logging.INFO, format='%(asctime)s: %(message)s')

def send_notification(message):
    msg = MIMEMultipart()
    msg['From'] = EMAIL_SENDER
    msg['To'] = EMAIL_RECEIVER
    msg['Subject'] = 'Network Speed Alert'
    msg.attach(MIMEText(message, 'plain'))

    try:
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(EMAIL_SENDER, EMAIL_PASSWORD)
        text = msg.as_string()
        server.sendmail(EMAIL_SENDER, EMAIL_RECEIVER, text)
        server.quit()
        print("Notification sent successfully.")
    except Exception as e:
        print(f"Failed to send notification: {e}")

def measure_speed(retries=3):
    attempt = 0
    while attempt < retries:
        try:
            st = speedtest.Speedtest()
            st.download()
            st.upload()
            download_speed = st.results.download / 1e6  # Convert to Mbps
            upload_speed = st.results.upload / 1e6  # Convert to Mbps
            download_speeds_over_time.append(download_speed)
            upload_speeds_over_time.append(upload_speed)
            return download_speed, upload_speed
        except Exception as e:
            print(f"Attempt {attempt + 1} failed: {e}")
            attempt += 1
            time.sleep(10)
    return None, None

def learn_normal_speeds(runs=LEARNING_MODE_RUNS):
    download_speeds = []
    upload_speeds = []

    for _ in range(runs):
        download_speed, upload_speed = measure_speed()
        if download_speed is not None and upload_speed is not None:
            download_speeds.append(download_speed)
            upload_speeds.append(upload_speed)
        time.sleep(LEARNING_PHASE_SLEEP_INTERVAL)

    download_mean = mean(download_speeds)
    upload_mean = mean(upload_speeds)
    download_std = stdev(download_speeds)
    upload_std = stdev(upload_speeds)

    normal_download_range = (download_mean - SPEED_TOLERANCE_FACTOR * download_std, 
                             download_mean + SPEED_TOLERANCE_FACTOR * download_std)
    normal_upload_range = (upload_mean - SPEED_TOLERANCE_FACTOR * upload_std, 
                           upload_mean + SPEED_TOLERANCE_FACTOR * upload_std)

    return normal_download_range, normal_upload_range

def monitor_speed(normal_download_range, normal_upload_range):
    global speed_test_running
    global latest_download_speed, latest_upload_speed
    while True:
        if not speed_test_running:  #Don't go if running elsewhere
            speed_test_running = True
            download_speed, upload_speed = measure_speed()
            latest_download_speed, latest_upload_speed = download_speed, upload_speed
            if download_speed is not None and upload_speed is not None:
                print(f"Download Speed: {download_speed:.2f} Mbps, Upload Speed: {upload_speed:.2f} Mbps")
                if not (normal_download_range[0] <= download_speed <= normal_download_range[1]):
                    message = f"Abnormal Download Speed: {download_speed:.2f} Mbps"
                    logging.info(message)
                    print(message)
                    send_notification(message)

                if not (normal_upload_range[0] <= upload_speed <= normal_upload_range[1]):
                    message = f"Abnormal Upload Speed: {upload_speed:.2f} Mbps"
                    logging.info(message)
                    print(message)
                    send_notification(message)
                    
            else:
                print("Error in measuring speed. Skipping this run.")
            speed_test_running = False
        time.sleep(MONITORING_PHASE_SLEEP_INTERVAL)

# Flask Dashboard

@app.route('/')
def dashboard():
    return render_template('dashboard.html')

@app.route('/latest_speed')
def get_latest_speed():
    global latest_download_speed, latest_upload_speed, speed_test_running
    if latest_download_speed is None or latest_upload_speed is None:
        return jsonify({'download_speed': 0, 'upload_speed': 0, 'status': 'Initializing'})
    if speed_test_running:
        return jsonify({
            'download_speed': latest_download_speed,
            'upload_speed': latest_upload_speed,
            'status': 'Running'
        })
    else:
        return jsonify({
            'download_speed': latest_download_speed,
            'upload_speed': latest_upload_speed,
            'status': 'Idle'
        })

@app.route('/speedtest')
def run_speed_test():
    global latest_download_speed, latest_upload_speed, speed_test_running

    if speed_test_running:
        return jsonify({'error': 'Speed test is already running'}), 400
    
    def run_test():
        global latest_download_speed, latest_upload_speed, speed_test_running
        try:
            speed_test_running = True
            download_speed, upload_speed = measure_speed()
            if download_speed is None or upload_speed is None:
                raise ValueError("Speed test failed")
            latest_download_speed = download_speed
            latest_upload_speed = upload_speed
        finally:
            speed_test_running = False

    # Run the speed test in a separate thread to avoid blocking the server
    threading.Thread(target=run_test).start()

    return jsonify({'status': 'Speed test started'})

@app.route('/plot')
def plot_speed():
    fig, ax = plt.subplots()
    ax.plot(download_speeds_over_time, label='Download Speed (Mbps)')
    ax.plot(upload_speeds_over_time, label='Upload Speed (Mbps)')
    ax.set_xlabel('Time')
    ax.set_ylabel('Speed (Mbps)')
    ax.legend()

    # Save the plot to the file system to debug
    # fig.savefig('speed_plot_debug.png')

    img = BytesIO()
    plt.savefig(img, format='png')
    img.seek(0)
    plot_url = base64.b64encode(img.getvalue()).decode()
    plt.close(fig)
    
    return send_file(img, mimetype='image/png')
    #return f'<img src="data:image/png;base64,{plot_url}"/>'

def main():
    print("Learning normal speeds...")
    normal_download_range, normal_upload_range = learn_normal_speeds()
    logging.info(f"Learned normal download speed range: {normal_download_range}")
    logging.info(f"Learned normal upload speed range: {normal_upload_range}")
    print(f"Learned normal download speed range: {normal_download_range}")
    print(f"Learned normal upload speed range: {normal_upload_range}")

    # Start monitoring in a separate thread
    monitoring_thread = threading.Thread(target=monitor_speed, args=(normal_download_range, normal_upload_range))
    monitoring_thread.daemon = True
    monitoring_thread.start()

    # Start the Flask app
    app.run(host='0.0.0.0', port=5000)

if __name__ == "__main__":
    main()
