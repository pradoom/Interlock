import datetime
import time
import threading
import serial
import evdev
from evdev import categorize, InputDevice, ecodes
import requests
import re
import time
import json
import os
import multiprocessing
import traceback

file_path = "lastCycle.aispl"
readFileInterval = 10
interlockThreshold = 10

def DowntimeStatus(username,password,login_url,url):

    payload = {
        "username": username,
        "password": password
    }

    try:
       
        login_response = requests.post(login_url, json=payload)

        if login_response.status_code in [200, 201]:
            login_data = login_response.json()
            token = login_data["token"]  
            print("Login successful")

            headers = {
                "Authorization": f"Bearer {token}"
            }

            response = requests.get(url, headers=headers)
            data = response.json()

            #print("Machine status response:")
            #print(json.dumps(data, indent=2))  

         
            if data:
                downtimeStatus = data[0].get("downtimeStatus")
                #print("downtime Status:", downtimeStatus)
                return downtimeStatus

        else:
            print("Login failed. Status code:", login_response.status_code)
            print("Response:", login_response.text)

    except Exception as e:
        print("Error:", str(e))



def readconfig():
    configfilePath = "/usr/configuration/config/interlocking-config.aispl"
    with open(configfilePath, 'r') as file:
        config = json.load(file)
    file_path = config['file_path']
    readFileInterval = config['readFileInterval']
    interlockThreshold = config['interlockThreshold']
    return file_path, readFileInterval, interlockThreshold

def send_signal(value):
    data = {"I1": value, "I2": value}
    json_data = json.dumps(data)

    serial_port = '/dev/ttyUSB0'  # Change this to your serial port
    baud_rate = 9600

    ser = serial.Serial(serial_port, baud_rate)
    time.sleep(0.5)
    ser.write(json_data.encode('utf-8'))
    ser.close()


def call_api(url, method=None, headers=None,jsondata=None):
    try:
        if method.upper() == "GET":
            response = requests.get(url,headers)
        elif method.upper() == "POST":
            response = requests.post(url,headers,jsondata)
        else:
            return "Unsupported HTTP method. Use 'GET' or 'POST'."

        if response.status_code == 200 or response.status_code == 201:
            return response
        else:
            return "Failed to get data"

    except requests.exceptions.HTTPError as http_err:
        return "HTTP error occurred:".format(http_err)
    except requests.exceptions.RequestException as req_err:
        return "Request error occurred:" .format(req_err)


def convert_to_json(data):
    pairs = data.split(',')
    die_dict = {}
    for pair in pairs:
        key, value = pair.split(':', 1)
        key = key.strip()
        value = value.strip()
        die_dict[key] = value
    return die_dict


def decode_barcode_data(data):
    parts = data.split('LEFTSHIFT')
    joined_string = ''.join(parts)
    decoded_string = joined_string.replace('SEMICOLON', ':').replace('COMMA', ',').replace('MINUS', '-').replace('ENTER', '\n').replace('\n','')
    return decoded_string

def find_barcode_scanner():
    devices = [evdev.InputDevice(path) for path in evdev.list_devices()]
    for device in devices:
        # print(f"Checking Device: {device.path}, Name: {device.name}")
        # Check if the device name contains common barcode scanner identifiers
        if 'barcode' in device.name.lower() or 'scanner' in device.name.lower() or 'hid' in device.name.lower():
            return device.path
    return None

def read_timestamp_and_value(file_path):
    try:
        with open(file_path, 'r') as file:
            data = json.load(file)  # Load JSON as dictionary
            for timestamp_str, value in data.items():  # Get the first (or only) item
                timestamp = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S.%f')
                return timestamp, value
    except Exception as e:
        print("Error reading file or parsing timestamp:", e)
        return None, None


def read_file(file_path,readFileInterval , interlockThreshold,LockCondation):
    # Login credentials and machine ID
    login_url = "https://pel.quadworld.in/auth/login"
    username = "vipl@aispl.co"
    password = "Autosys@9870"
    machineId = "VIC-TOOL-0267"

    # Machine status API URL
    url = f"https://pel.quadworld.in/client/location/plant/division/line/machines?downtimeStatus=0&id={machineId}"

    
    while True:
        if LockCondation == "Punch":

            print("INTER: Loop is running Condation = PUNCH...")

            if os.path.exists(file_path):

                file_timestamp, value = read_timestamp_and_value(file_path)

                time_gap = (datetime.datetime.now() - file_timestamp).total_seconds()

                if not locked and time_gap > interlockThreshold * 60:

                    print("INTER: Time gap exceeded...")

                    downtimeStatus = DowntimeStatus(username, password, login_url, url)

                    print("INTER: Downtime Status:", downtimeStatus)

                    if downtimeStatus is not None:

                        if downtimeStatus:  # downtimeStatus is truthy (non-zero)

                            print("INTER: Reason NOT punched")

                            send_signal("1")

                            locked = True
                        else:
                            print("INTER: Reason punched")
                            
                            send_signal("0")
                    else:
                        print("INTER: Could not fetch downtime status")

                elif locked:
                    downtimeStatus = DowntimeStatus(username, password, login_url, url)
                    print("INTER: Locked check - Downtime Status:", downtimeStatus)

                    if downtimeStatus is not None and not downtimeStatus:
                        send_signal("0")
                        locked = False
                        print("INTER: Reason punched, unlocking")
                    else:
                        print("INTER: Reason NOT punched -- Machine still locked")
            else:
                print("INTER: File not found")

            time.sleep(readFileInterval)
        elif LockCondation == "None":
            print("INTER: Loop is running Condation = NOne...")
            if os.path.exists(file_path):
                file_timestamp, value = read_timestamp_and_value(file_path)
                time_gap = (datetime.datetime.now() - file_timestamp).total_seconds()

                if time_gap > interlockThreshold * 60:
                    print("Machine LOCK")
                    send_signal("1")
                    #This condation FaIl only when right diY is AssIgn.

def read_barcode_data(file_path,interval , threshold):
    print("Started barcode reading")
    device_path = find_barcode_scanner()
    if not device_path:
        print("No barcode scanner detected. Please check the connections.")
        return

    try:
        device = InputDevice(device_path)
        print("Listening to events from: {}".format(device.path))
        print("Scan a barcode to see the events. Press Ctrl+C to stop.\n")


        datadict = {}
        barcode_data = ''
        pattern = r"^[A-Z]+-[A-Z]+-\d{4}$"
        url = "http://dal.aispl.co:3030/die-logs"

        for event in device.read_loop():
            if event.type == ecodes.EV_KEY:
                key_event = categorize(event)
                if key_event.keystate == key_event.key_down:
                    barcode_data += ecodes.KEY[event.code].replace('KEY_', '')
                    if event.code == ecodes.KEY_ENTER:
                        decoded_data = decode_barcode_data(barcode_data)

                        print("Decoded Barcode Data:", decoded_data)
                        print(decoded_data[0], "DDDDDDDDDDDDDDDDDDDDDDDDDD")
                        print(datadict,"datadict.update")
                        if decoded_data[0] == "D": 
                            die_dict = convert_to_json(decoded_data)
                            datadict.update(
                                {
                                    "dieId":die_dict["D-DIEID"],
                                    "operationId":die_dict["OPERATIONID"]
                                })
                        elif decoded_data[0] == "M" or re.match(pattern, decoded_data):
                            datadict.update({"machineId":decoded_data[-13:]}) 

                        elif decoded_data == "POST":
                            print("EEEEE")
                            if "machineId" in datadict and "dieId" in datadict:
                                print("OOOOOOO")
                                response = call_api(url, method="POST",jsondata=datadict)
                                response = json.loads(response.text)
                                print("responseeee------------------" ,   response)
                                if response["linked"] == True:
                                    print("true")
                                    result = send_signal('0')
                                    print(result, " resukt of serial write on relay UNLOCK")
                                elif response["linked"] == False:
                                    print("true")
                                    send_signal("1")
                                datadict = {}
                            else:
                                print("machineID/dieID not found in datadict")
                                datadict = {}
                        barcode_data = ''
                    
    except KeyboardInterrupt:
        print("Stopped by user.")
    except Exception as e:
        # print(f"An error occurred barcode: {e}")
        pass


if __name__ =="__main__":
    datetimeFile  , interval , threshold  = readconfig()
    t1 = multiprocessing.Process(target=read_barcode_data, args=(datetimeFile,interval , threshold))
    t2 = multiprocessing.Process(target=read_file, args=(datetimeFile,interval , threshold))
    t1.start()
    t2.start()
    # t1.join()
    # t2.join()
    print("Done!")
