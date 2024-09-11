import speedtest
import logging
import time
from statistics import mean, stdev
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from flask import Flask, render_template, jsonify, send_file
from flask_socketio import SocketIO
import threading
import matplotlib
import matplotlib.pyplot as plt
from io import BytesIO
from datetime import datetime
matplotlib.use('Agg')

# Configuration. This only effectively makes a difference if you're using the email functionality
SEND_EMAILS = False
LEARNING_MODE_RUNS = 100  # Number of runs to determine the normal speed
SPEED_TOLERANCE_FACTOR = 3  # How much variance from the mean we tolerate
LEARNING_PHASE_SLEEP_INTERVAL = 60   # Seconds to wait between learning phase runs
MONITORING_PHASE_SLEEP_INTERVAL = 600     # Seconds to wait between monitoring phase runs

# Data storage for plotting
download_speeds_over_time = []
upload_speeds_over_time = []
timestamps = []

# Store the latest speed results
latest_download_speed = None
latest_upload_speed = None
speed_test_running = False

# Create a global lock. It's a little redundant but good for safety
speed_test_lock = threading.Lock()

app = Flask(__name__)
socketio = SocketIO(app)

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

logging.basicConfig(filename='network_speed.log', level=logging.INFO, format='%(asctime)s: %(message)s') # set up logfile

def send_notification(message):
    """Sends an email with the given message based on config file"""
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
    """Measures network speed"""
    attempt = 0
    while attempt < retries:
        try:
            st = speedtest.Speedtest()
            st.download()
            st.upload()
            download_speed = st.results.download / 1e6  # Convert to Mbps
            upload_speed = st.results.upload / 1e6  # Convert to Mbps
            timestamp = datetime.now()  # Capture the current time

            download_speeds_over_time.append(download_speed)
            upload_speeds_over_time.append(upload_speed)
            timestamps.append(timestamp)  # Store the timestamp
            
            return download_speed, upload_speed
        except Exception as e:
            print(f"Attempt {attempt + 1} failed: {e}")
            attempt += 1
            time.sleep(10)
    return None, None
def measure_notify_speed():
    """Measures the speed and sends dashboard updates, using only a lock."""
    global latest_download_speed, latest_upload_speed, speed_test_running

    # Acquire the lock to ensure no other thread runs this simultaneously
    with speed_test_lock:
        notify_status('Running')
        speed_test_running = True       
        download_speed, upload_speed = measure_speed()
        latest_download_speed, latest_upload_speed = download_speed, upload_speed
        notify_clients()  # Notify the client when new data is available
        notify_status('Idle')
        speed_test_running = False
    return download_speed, upload_speed

def learn_normal_speeds(runs=LEARNING_MODE_RUNS):
    """Runs multiple times to gather network speed data and return bounds"""
    download_speeds = []
    upload_speeds = []

    for _ in range(runs):
        #download_speed, upload_speed = measure_speed()
        download_speed, upload_speed = measure_notify_speed()
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
def check_bounds(speed, normal_range, label):
    """Checks if the speed is within the normal range, logs and sends notifications if it's abnormal."""
    if not (normal_range[0] <= speed <= normal_range[1]):
        message = f"Abnormal {label} Speed: {speed:.2f} Mbps"
        logging.info(message)
        print(message)
        if SEND_EMAILS:
            send_notification(message)
def monitor_speed(normal_download_range, normal_upload_range):
    """Monitors the network continously in a closed loop. This method should be threaded"""
    while True:
        if not speed_test_running:  # Don't test if already testing
            download_speed, upload_speed = measure_notify_speed()   #runs a speed test and handles dashboard updates
            if download_speed is not None and upload_speed is not None:
                print(f"Download Speed: {download_speed:.2f} Mbps, Upload Speed: {upload_speed:.2f} Mbps")
                # Check download speed and upload speed using the helper function
                check_bounds(download_speed, normal_download_range, "Download")
                check_bounds(upload_speed, normal_upload_range, "Upload")
                    
            else:
                print("Error in measuring speed. Skipping this run.")
        time.sleep(MONITORING_PHASE_SLEEP_INTERVAL)     #sleep this thread before next loop

def notify_status(status):
    """When only updating status"""
    socketio.emit('status_update', {'status': status})
def notify_clients():
    """Updates speeds and status"""
    global latest_download_speed, latest_upload_speed
    socketio.emit('speed_update', {
        'download_speed': latest_download_speed or 0,
        'upload_speed': latest_upload_speed or 0,
    })

# Flask Dashboard
@socketio.on('connect')
def handle_connect():
    print('Client connected')
    # Send the current speed and status when the client connects
    status = 'Initializing' if latest_download_speed is None else 'Running' if speed_test_running else 'Idle'
    notify_status(status)
    notify_clients()

@app.route('/')
def dashboard():
    return render_template('dashboard.html')

@app.route('/speedtest')
def run_speed_test():
    if speed_test_running:
        return jsonify({'error': 'Speed test is already running'}), 400
    else:
        # Run the speed test in a separate thread to avoid blocking the server
        threading.Thread(target=measure_notify_speed).start()

    return jsonify({'status': 'Speed test started'})

@app.route('/plot')
def plot_speed():
    fig, ax = plt.subplots()
    ax.plot(timestamps, download_speeds_over_time, label='Download Speed (Mbps)')
    ax.plot(timestamps, upload_speeds_over_time, label='Upload Speed (Mbps)')
    ax.set_xlabel('Time')
    ax.set_ylabel('Speed (Mbps)')
    ax.legend()

    # Format the x-axis to display human-readable time
    ax.xaxis.set_major_formatter(matplotlib.dates.DateFormatter('%H:%M:%S'))
    ax.xaxis.set_major_locator(matplotlib.dates.AutoDateLocator())

    # Rotate and align the x labels for better readability
    fig.autofmt_xdate()

    img = BytesIO()
    plt.savefig(img, format='png')
    img.seek(0)
    plt.close(fig)
    
    return send_file(img, mimetype='image/png')

def main():
    # Start the Flask app with SocketIO in a separate thread
    socketio_thread = threading.Thread(target=lambda: socketio.run(app, host='0.0.0.0', port=5000))
    socketio_thread.daemon = True
    socketio_thread.start()

    print("Learning normal speeds...")
    normal_download_range, normal_upload_range = learn_normal_speeds()
    logging.info(f"Learned normal download speed range: {normal_download_range}")
    logging.info(f"Learned normal upload speed range: {normal_upload_range}")
    print(f"Learned normal download speed range: {normal_download_range}")
    print(f"Learned normal upload speed range: {normal_upload_range}")

    monitor_speed(normal_download_range, normal_upload_range)

if __name__ == "__main__":
    main()
