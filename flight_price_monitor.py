import requests
from bs4 import BeautifulSoup
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.utils import formatdate
import json
import os
import time
import random
from datetime import datetime
from configFile import (
    email_sender,
    email_password,
    dates_to_track,
    url,
    host,
    env
)
import csv

# Constants
script_dir = os.path.dirname(os.path.abspath(__file__))

DATA_FILE = os.path.join(script_dir, 'previous_flights.json')
API_ERROR_LOG_FILE = os.path.join(script_dir, 'api_error_log.json')
GENERAL_ERROR_LOG_FILE = os.path.join(script_dir, 'error_log.txt')
LAST_RUN_LOG_FILE = os.path.join(script_dir, 'last_run.txt')
CSV_FILE = os.path.join(script_dir, 'flight_prices_log.csv')


def log_error_to_file(error_message):
    with open(GENERAL_ERROR_LOG_FILE, 'a') as error_log_file:
        error_log_file.write(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - {error_message}\n")
    print(f"Error logged: {error_message}")


def has_future_dates():
    today = datetime.now().date()
    print("Checking future dates...")
    for flight_str in dates_to_track:
        # Expected example:
        # "20-01-2025 · 16:55 | target.email@example.com | OUL | LPA | 1600"
        try:
            parts = flight_str.split(" | ")
            if len(parts) != 5:
                raise ValueError("Incorrect number of fields.")
            date_time_part = parts[0].strip()  # e.g., "20-01-2025 · 16:55"
            just_date_str = date_time_part.split('·')[0].strip()  # e.g., "20-01-2025"
            flight_date = datetime.strptime(just_date_str, '%d-%m-%Y').date()
            if flight_date >= today:
                print(f"Future date found: {flight_date}")
                return True
        except (ValueError, IndexError):
            print(f"Invalid format in dates_to_track entry: {flight_str}")
            continue
    print("No future dates to track.")
    return False


def fetch_flight_data(custom_url):
    headers = {
        'Host': host,
        'User-Agent': 'curl/8.5.0',
        'Accept': '*/*',
    }
    print(f"Fetching flight data from URL: {custom_url}")
    try:
        response = requests.get(custom_url, headers=headers)
        if response.status_code != 200:
            print(f"Error: Failed to fetch data. Status code: {response.status_code}, Response text: {response.text}")
            handle_api_error(response.status_code)
            return None
        response.raise_for_status()
        print("Flight data fetched successfully.")
        with open(LAST_RUN_LOG_FILE, "w") as f:
            f.write(f"Last run: {datetime.now()}\n")
        return response.text
    except requests.RequestException as e:
        print(f"RequestException occurred: {str(e)}")
        handle_api_error(str(e))
        return None


def handle_api_error(error_message):
    error_logged_today = False
    today_str = datetime.now().strftime('%Y-%m-%d')
    if os.path.exists(API_ERROR_LOG_FILE):
        with open(API_ERROR_LOG_FILE, 'r') as f:
            error_log = json.load(f)
            last_error_date = error_log.get('last_error_date')
            if last_error_date == today_str:
                error_logged_today = True
    else:
        error_log = {}
    if not error_logged_today:
        send_error_email(error_message)
        error_log['last_error_date'] = today_str
        with open(API_ERROR_LOG_FILE, 'w') as f:
            json.dump(error_log, f)


def send_error_email(error_message):
    # Using email_sender as recipient for error emails
    msg = MIMEMultipart()
    msg['From'] = email_sender
    msg['To'] = email_sender
    msg['Date'] = formatdate(localtime=True)
    msg['Subject'] = "Flight Monitor Error Alert"
    body = f"""
An error occurred while fetching flight data:

Error: {error_message}

This is a notification to inform you of the issue.
    """
    msg.attach(MIMEText(body, 'plain'))
    try:
        server = smtplib.SMTP_SSL('smtp.gmail.com', 465)
        server.login(email_sender, email_password)
        server.sendmail(email_sender, email_sender, msg.as_string())
        server.quit()
        print("Error email sent.")
    except Exception as e:
        print(f"Failed to send error email: {e}")


def parse_flight_data(html_content):
    soup = BeautifulSoup(html_content, 'html.parser')
    flight_rows = soup.select('a.lms-row')
    flights = []
    print(f"Parsing {len(flight_rows)} flights from the HTML content.")
    for row in flight_rows:
        departure_info = row.select_one('div.departy p:nth-of-type(1)').text.strip()
        date_info = row.select_one('div.departy p:nth-of-type(2)').text.strip()
        destination_info = row.select_one('div.destiny p:nth-of-type(2)').text.strip()
        price_info = row.select_one('div.pricey p.current-price').text.strip()
        hurry_element = row.select_one('div.hurry p')
        hurry_text = hurry_element.text.strip() if hurry_element else None
        price = int(''.join(filter(str.isdigit, price_info)))
        flight = {
            'departure_info': departure_info,
            'date_info': date_info,
            'destination_info': destination_info,
            'price': price,
            'link': row['href'],
            'hurry_text': hurry_text
        }
        flights.append(flight)
    print(f"Total flights parsed: {len(flights)}")
    return flights


def load_previous_flights():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r') as f:
            return json.load(f)
    return {}


def save_current_flights(flights_data):
    with open(DATA_FILE, 'w') as f:
        json.dump(flights_data, f)


def send_individual_email(alert, target_email):
    msg = MIMEMultipart()
    msg['From'] = email_sender
    msg['To'] = target_email
    msg['Date'] = formatdate(localtime=True)
    msg['Subject'] = "Flight Alert Notification"
    if alert['type'] == 'price_drop':
        body = f"""
Price Drop Alert:

Flight Date: {alert['flight']['date_info']}
New Price: {alert['flight']['price']} euros
Destination: {alert['flight']['destination_info']}
Booking Link: {alert['flight']['link']}

----------------------------------------
"""
    elif alert['type'] == 'hurry':
        body = f"""
Hurry Alert:

Limited Seats for Flight on {alert['flight']['date_info']}
Seats Left: {alert['flight']['hurry_text']}
Price: {alert['flight']['price']} euros
Destination: {alert['flight']['destination_info']}
Booking Link: {alert['flight']['link']}

----------------------------------------
"""
    else:
        body = "Unknown alert type."
    msg.attach(MIMEText(body, 'plain'))
    try:
        server = smtplib.SMTP_SSL('smtp.gmail.com', 465)
        server.login(email_sender, email_password)
        server.sendmail(email_sender, target_email, msg.as_string())
        server.quit()
        print(f"Alert email sent to {target_email}.")
    except Exception as e:
        print(f"Failed to send email to {target_email}: {e}")


def log_flight_price(flight_date, flight_time, departure, destination, price):
    current_time = datetime.now()
    log_date = current_time.strftime("%Y-%m-%d")
    log_time = current_time.strftime("%H:%M:%S")
    with open(CSV_FILE, 'a', newline='', encoding='utf-8') as csvfile:
        fieldnames = ['log_date', 'log_time', 'flight_date', 'flight_time', 'departure', 'destination', 'price']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        if csvfile.tell() == 0:
            writer.writeheader()
        writer.writerow({
            'log_date': log_date,
            'log_time': log_time,
            'flight_date': flight_date,
            'flight_time': flight_time,
            'departure': departure,
            'destination': destination,
            'price': price
        })


def get_flight_configs_grouped():
    """
    Groups flight configurations by (airport, destination).
    Returns a dictionary where keys are (airport, destination) tuples and values are lists of flight configs.
    """
    grouped_configs = {}
    for flight_str in dates_to_track:
        parts = flight_str.split(" | ")
        if len(parts) != 5:
            print(f"Skipping invalid entry: {flight_str}")
            continue
        fc_date_time = parts[0].strip()   # "DD-MM-YYYY · HH:MM"
        # Split emails by comma and strip extra spaces
        fc_email_str = parts[1].strip()
        fc_emails = [email.strip() for email in fc_email_str.split(',')]
        fc_airport = parts[2].strip()
        fc_destination = parts[3].strip()
        fc_threshold = parts[4].strip()
        try:
            threshold = int(fc_threshold)
        except ValueError:
            print(f"Invalid price threshold in entry: {flight_str}")
            continue
        config = {
            'date_time': fc_date_time,
            'emails': fc_emails,
            'airport': fc_airport,
            'destination': fc_destination,
            'price_threshold': threshold
        }
        key = (fc_airport, fc_destination)
        grouped_configs.setdefault(key, []).append(config)
    return grouped_configs


def main():
    if env != "dev":
        delay = random.uniform(123, 1231)
        time.sleep(delay)
        print(f"Running in {env} environment. Delayed start of {delay:.2f} seconds.")
    if not has_future_dates():
        print("No future dates available for tracking. Exiting.")
        return
    previous_flights = load_previous_flights()
    current_flights = {}
    grouped_configs = get_flight_configs_grouped()
    all_alerts = []
    for (airport, destination), configs in grouped_configs.items():
        custom_url = url.replace("{airport}", airport).replace("{destination}", destination)
        html_content = fetch_flight_data(custom_url)
        if html_content is None:
            print(f"No HTML content fetched for {airport} -> {destination}. Skipping.")
            continue
        flights = parse_flight_data(html_content)
        flights_lookup = {f['date_info']: f for f in flights}
        for config in configs:
            date_time = config['date_time']  # e.g., "20-01-2025 · 16:55"
            target_emails = config['emails']  # List of emails
            price_threshold = config['price_threshold']
            matching_flight = flights_lookup.get(date_time)
            if not matching_flight:
                print(f"No matching flight found for {date_time} in {airport} -> {destination}.")
                continue
            flight_date, flight_time = date_time.split(' · ')
            departure = matching_flight['departure_info']
            destination_info = matching_flight['destination_info']
            price = matching_flight['price']
            log_flight_price(flight_date, flight_time, departure, destination_info, price)
            flight_key = f"{date_time} | {airport} | {destination}"
            current_flights.setdefault(flight_key, {'price': price, 'hurry_alert_sent': False})
            prev_flight_data = previous_flights.get(flight_key, {})
            prev_price = prev_flight_data.get('price')
            hurry_alert_sent = prev_flight_data.get('hurry_alert_sent', False)
            if matching_flight['hurry_text'] and not hurry_alert_sent:
                alert = {
                    'type': 'hurry',
                    'flight': matching_flight
                }
                # Append a tuple containing the alert and the list of target emails
                all_alerts.append((alert, target_emails))
                current_flights[flight_key]['hurry_alert_sent'] = True
            else:
                current_flights[flight_key]['hurry_alert_sent'] = hurry_alert_sent
            if price <= price_threshold:
                current_flights[flight_key]['price'] = price
                if prev_price is None or price < prev_price:
                    alert = {
                        'type': 'price_drop',
                        'flight': matching_flight
                    }
                    all_alerts.append((alert, target_emails))
    for alert, target_emails in all_alerts:
        for target_email in target_emails:
            send_individual_email(alert, target_email)
    save_current_flights(current_flights)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        error_message = f"Unexpected error in main(): {str(e)}"
        log_error_to_file(error_message)
