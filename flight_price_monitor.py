import csv
import json
import os
import random
import smtplib
import time
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formatdate
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import requests

from configFile import FLIGHT_CONFIGS, email_password, email_sender, env

# Constants
script_dir = os.path.dirname(os.path.abspath(__file__))

DATA_FILE = os.path.join(script_dir, 'previous_flights.json')
API_ERROR_LOG_FILE = os.path.join(script_dir, 'api_error_log.json')
GENERAL_ERROR_LOG_FILE = os.path.join(script_dir, 'error_log.txt')
LAST_RUN_LOG_FILE = os.path.join(script_dir, 'last_run.txt')
CSV_FILE = os.path.join(script_dir, 'flight_prices_log.csv')

REQUEST_TIMEOUT = 30
DEFAULT_HEADERS = {
    'accept': 'application/json, text/plain, */*',
    'accept-language': 'fi-FI,fi;q=0.9,en-US;q=0.8',
    'cache-control': 'no-cache',
    'pragma': 'no-cache',
    'user-agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/120.0.0.0 Safari/537.36'
    )
}


def log_error_to_file(error_message):
    with open(GENERAL_ERROR_LOG_FILE, 'a', encoding='utf-8') as error_log_file:
        error_log_file.write(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - {error_message}\n")
    print(f"Error logged: {error_message}")


def handle_api_error(error_message):
    error_logged_today = False
    today_str = datetime.now().strftime('%Y-%m-%d')
    if os.path.exists(API_ERROR_LOG_FILE):
        with open(API_ERROR_LOG_FILE, 'r', encoding='utf-8') as f:
            error_log = json.load(f)
            last_error_date = error_log.get('last_error_date')
            if last_error_date == today_str:
                error_logged_today = True
    else:
        error_log = {}
    if not error_logged_today:
        send_error_email(error_message)
        error_log['last_error_date'] = today_str
        with open(API_ERROR_LOG_FILE, 'w', encoding='utf-8') as f:
            json.dump(error_log, f)


def send_error_email(error_message):
    msg = MIMEMultipart()
    msg['From'] = email_sender
    msg['To'] = email_sender
    msg['Date'] = formatdate(localtime=True)
    msg['Subject'] = "Flight Monitor Error Alert"
    body = (
        "An error occurred while fetching flight data:\n\n"
        f"Error: {error_message}\n\n"
        "This notification is sent once per day for repeating issues."
    )
    msg.attach(MIMEText(body, 'plain'))
    try:
        server = smtplib.SMTP_SSL('smtp.gmail.com', 465)
        server.login(email_sender, email_password)
        server.sendmail(email_sender, email_sender, msg.as_string())
        server.quit()
        print("Error email sent.")
    except Exception as exc:
        print(f"Failed to send error email: {exc}")


def build_url_with_page(api_url, page_number):
    parsed = urlparse(api_url)
    query_params = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query_params['page'] = str(page_number)
    new_query = urlencode(query_params)
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, new_query, parsed.fragment))


def fetch_flight_page(api_url, page_number):
    url_with_page = build_url_with_page(api_url, page_number)
    print(f"Requesting {url_with_page}")
    try:
        response = requests.get(url_with_page, headers=DEFAULT_HEADERS, timeout=REQUEST_TIMEOUT)
    except requests.RequestException as exc:
        handle_api_error(str(exc))
        return None
    if response.status_code != 200:
        handle_api_error(f"Status {response.status_code} for {url_with_page}")
        return None
    try:
        return response.json()
    except ValueError:
        handle_api_error("Failed to decode JSON response")
        return None


def load_previous_flights():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return {}
    return {}


def save_current_flights(flights_data):
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(flights_data, f, ensure_ascii=False, indent=2)


def normalize_value(value):
    if isinstance(value, str):
        return value.strip().lower()
    return value


def flight_matches_criteria(flight, criteria):
    if not criteria:
        return False
    for key, expected in criteria.items():
        actual = flight.get(key)
        if actual is None:
            return False
        if normalize_value(actual) != normalize_value(expected):
            return False
    return True


def find_flight_for_config(config):
    page = 1
    max_pages = None
    while True:
        response_data = fetch_flight_page(config['api_url'], page)
        if response_data is None:
            return None
        flights_section = response_data.get('flights', {})
        if flights_section.get('error'):
            handle_api_error(flights_section['error'])
            return None
        flight_results = flights_section.get('flight_results') or []
        for flight in flight_results:
            if flight_matches_criteria(flight, config['match']):
                return flight
        pages_value = flights_section.get('pages') or 1
        if max_pages is None:
            try:
                max_pages = int(pages_value)
            except (TypeError, ValueError):
                max_pages = 1
        if page >= max_pages:
            break
        page += 1
    return None


def format_date_for_log(iso_date_str):
    try:
        dt_obj = datetime.strptime(iso_date_str, '%Y-%m-%d')
        return dt_obj.strftime('%d-%m-%Y')
    except (TypeError, ValueError):
        return iso_date_str or ''


def log_flight_price(flight, config_name):
    flight_date = format_date_for_log(flight.get('r1_dep_date'))
    flight_time = flight.get('r1_dep_time') or ''
    departure = flight.get('r1_dep_iata') or ''
    destination = flight.get('r1_arr_iata') or ''
    price = flight.get('price')
    current_time = datetime.now()
    log_date = current_time.strftime('%Y-%m-%d')
    log_time = current_time.strftime('%H:%M:%S')
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
    print(f"Logged price for {config_name}: {price}€ on {flight_date} {flight_time}")


def normalize_emails(emails_field):
    if isinstance(emails_field, str):
        return [email.strip() for email in emails_field.split(',') if email.strip()]
    return [email.strip() for email in emails_field if email.strip()]


def should_send_price_alert(price, prev_price, threshold):
    if price is None:
        return False
    if threshold is None:
        return False
    if price >= threshold:
        return False
    if prev_price is None:
        return True
    if price < prev_price:
        return True
    return False


def build_price_alert_body(config, flight, threshold):
    outbound = f"{flight.get('r1_dep_iata')} -> {flight.get('r1_arr_iata')}"
    outbound_time = f"{flight.get('r1_dep_date')} {flight.get('r1_dep_time')}"
    if flight.get('r2_dep_iata') and flight.get('r2_arr_iata'):
        return_leg = f"{flight.get('r2_dep_iata')} -> {flight.get('r2_arr_iata')}"
    else:
        return_leg = 'N/A'
    if flight.get('r2_dep_date'):
        return_time = f"{flight.get('r2_dep_date')} {flight.get('r2_dep_time')}"
    else:
        return_time = 'N/A'
    deeplink = flight.get('r1_deeplink') or flight.get('r2_deeplink') or config['api_url']
    return (
        f"Price alert for {config['name']}\n\n"
        f"Current price: {flight.get('price')}€ (threshold {threshold}€)\n"
        f"Flight id: {flight.get('id')}\n"
        f"Outbound: {outbound} on {outbound_time}\n"
        f"Return: {return_leg} on {return_time}\n\n"
        f"Book here: {deeplink}\n"
        f"Data source: {config['api_url']}\n"
    )


def send_price_alert_email(config, flight, recipients, threshold):
    config_name = config.get('name') or 'Configured flight'
    subject = f"Flight alert • {config_name} • {flight.get('price')}€"
    body = build_price_alert_body(config, flight, threshold)
    for recipient in recipients:
        msg = MIMEMultipart()
        msg['From'] = email_sender
        msg['To'] = recipient
        msg['Date'] = formatdate(localtime=True)
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'plain'))
        try:
            server = smtplib.SMTP_SSL('smtp.gmail.com', 465)
            server.login(email_sender, email_password)
            server.sendmail(email_sender, recipient, msg.as_string())
            server.quit()
            print(f"Alert email sent to {recipient} for {config_name}")
        except Exception as exc:
            print(f"Failed to send email to {recipient}: {exc}")


def write_last_run_log():
    with open(LAST_RUN_LOG_FILE, 'w', encoding='utf-8') as f:
        f.write(f"Last run: {datetime.now()}\n")


def build_flight_state_key(config):
    match_snapshot = json.dumps(config.get('match') or {}, sort_keys=True)
    api_fragment = config.get('api_url', '')
    return f"{api_fragment}|{match_snapshot}"


def process_flight_config(config, previous_flights, current_flights):
    required_keys = ('name', 'api_url', 'match', 'emails', 'price_threshold')
    missing = [key for key in required_keys if not config.get(key)]
    if missing:
        print(f"Skipping config {config.get('name', 'Unnamed')} due to missing keys: {missing}")
        return 0
    config_name = config.get('name') or 'Configured flight'
    recipients = normalize_emails(config['emails'])
    if not recipients:
        print(f"Skipping {config_name} because no valid email recipients were provided.")
        return 0
    match_criteria = config.get('match')
    if not isinstance(match_criteria, dict) or not match_criteria:
        print(f"Skipping {config_name} because match criteria are missing or invalid.")
        return 0
    required_match = ('r2_dep_date', 'r2_dep_time')
    missing_match = [field for field in required_match if field not in match_criteria]
    if missing_match:
        print(f"Skipping {config_name} because match must include: {', '.join(missing_match)}")
        return 0
    try:
        threshold = int(config['price_threshold'])
    except (TypeError, ValueError):
        print(f"Invalid price_threshold for {config_name}. Expected integer value.")
        return 0
    flight = find_flight_for_config(config)
    if flight is None:
        print(f"Flight not found for config {config_name}.")
        return 0
    try:
        price = int(flight.get('price'))
        flight['price'] = price
    except (TypeError, ValueError):
        print(f"Invalid price for flight in config {config_name}. Skipping alert.")
        return 0
    log_flight_price(flight, config_name)
    flight_key = build_flight_state_key(config)
    prev_data = previous_flights.get(flight_key, {})
    prev_price = prev_data.get('price')
    alerts_sent = 0
    if should_send_price_alert(price, prev_price, threshold):
        send_price_alert_email(config, flight, recipients, threshold)
        alerts_sent = len(recipients)
    current_flights[flight_key] = {
        'price': price,
        'flight_id': flight.get('id'),
        'last_checked': datetime.now().isoformat(),
        'name': config_name
    }
    return alerts_sent


def main():
    if env != 'dev':
        delay = random.uniform(123, 1231)
        time.sleep(delay)
        print(f"Running in {env} environment. Delayed start of {delay:.2f} seconds.")
    if not FLIGHT_CONFIGS:
        print('No flight configurations found. Exiting.')
        return
    previous_flights = load_previous_flights()
    # Start from prior snapshot so transient failures do not drop state and retrigger alerts
    current_flights = previous_flights.copy()
    total_alerts = 0
    for config in FLIGHT_CONFIGS:
        alerts_sent = process_flight_config(config, previous_flights, current_flights)
        total_alerts += alerts_sent
    save_current_flights(current_flights)
    write_last_run_log()
    print(f"Run completed. Emails sent: {total_alerts}")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        error_message = f"Unexpected error in main(): {str(e)}"
        log_error_to_file(error_message)
