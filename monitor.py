import speedtest
import logging
import time
from statistics import mean, stdev

# Configuration
LEARNING_MODE_RUNS = 10  # Number of runs to determine the normal speed
SPEED_TOLERANCE_FACTOR = 2  # How much variance from the mean we tolerate
LEARNING_INTERVAL = 1
MEASURING_INTERVAL = 5
# Logging configuration
logging.basicConfig(filename='network_speed.log', level=logging.INFO, format='%(asctime)s: %(message)s')

def measure_speed():
    st = speedtest.Speedtest()
    st.download()
    st.upload()
    download_speed = st.results.download / 1e6  # Convert to Mbps
    upload_speed = st.results.upload / 1e6  # Convert to Mbps
    return download_speed, upload_speed

def learn_normal_speeds(runs=LEARNING_MODE_RUNS):
    download_speeds = []
    upload_speeds = []

    for _ in range(runs):
        download_speed, upload_speed = measure_speed()
        download_speeds.append(download_speed)
        upload_speeds.append(upload_speed)
        time.sleep(LEARNING_INTERVAL)  # Pause for a minute between measurements, adjust as needed

    # Calculate mean and standard deviation for both download and upload speeds
    download_mean = mean(download_speeds)
    upload_mean = mean(upload_speeds)
    download_std = stdev(download_speeds)
    upload_std = stdev(upload_speeds)

    # Determine "normal" speed ranges based on mean and a tolerance factor times the standard deviation
    normal_download_range = (download_mean - SPEED_TOLERANCE_FACTOR * download_std, 
                             download_mean + SPEED_TOLERANCE_FACTOR * download_std)
    normal_upload_range = (upload_mean - SPEED_TOLERANCE_FACTOR * upload_std, 
                           upload_mean + SPEED_TOLERANCE_FACTOR * upload_std)

    return normal_download_range, normal_upload_range

def monitor_speed(normal_download_range, normal_upload_range):
    while True:
        download_speed, upload_speed = measure_speed()

        # Check if the speed is outside normal ranges
        if not (normal_download_range[0] <= download_speed <= normal_download_range[1]):
            logging.info(f"Abnormal Download Speed: {download_speed:.2f} Mbps")

        if not (normal_upload_range[0] <= upload_speed <= normal_upload_range[1]):
            logging.info(f"Abnormal Upload Speed: {upload_speed:.2f} Mbps")

        print(f"Download Speed: {download_speed:.2f} Mbps, Upload Speed: {upload_speed:.2f} Mbps")
        time.sleep(MEASURING_INTERVAL)  # Check every hour, adjust as needed

def main():
    print("Learning normal speeds...")
    normal_download_range, normal_upload_range = learn_normal_speeds()
    logging.info(f"Learned normal download speed range: {normal_download_range}")
    logging.info(f"Learned normal upload speed range: {normal_upload_range}")
    print(f"Learned normal download speed range: {normal_download_range}")
    print(f"Learned normal upload speed range: {normal_upload_range}")

    monitor_speed(normal_download_range, normal_upload_range)

if __name__ == "__main__":
    main()

