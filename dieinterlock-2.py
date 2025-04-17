import threading
from datetime import datetime
import time
import serial
import evdev
from evdev import categorize, InputDevice, ecodes
import requests
import re
import json
import os
import multiprocessing
import traceback
#import logging
#logging.basicConfig(level=logging.DEBUG,format='%(asctime)s %(message)s',filename='InterlokingLog.log',filemode='a')

#file_path = "lastCycle.aispl"
# readFileInterval = 10
# interlockThreshold = 10
UnlockStatus=False
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
            #print("TOKEN:",token)
        #print("Login successful")
        #logging.info("Login Successfull")

        headers = {
                "Authorization": f"Bearer {token}"
            }

        try:
            response = requests.get(url, headers=headers)
            data = response.json()
            return data
        except Exception as e:
            print("GET ERROR:",e)

    except Exception as e:
        print("POST ERROR:", e)



def readconfig():
    configfilePath = "/home/aispl/Interlock/interlocking-config.aispl"
    with open(configfilePath, 'r') as file:
        config = json.load(file)
    file_path = config['file_path']
    readFileInterval = config['readFileInterval']
    interlockThreshold = config['interlockThreshold']
    LockCondation = config['LockCondation']
    machineId_=config['machineId']
    return file_path, readFileInterval, interlockThreshold, LockCondation,machineId_

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


def Find_BarCodeScanner():
    devices = [evdev.InputDevice(path) for path in evdev.list_devices()]
    
    for device in devices:
        if 'barcode' in device.name.lower() or 'scanner' in device.name.lower() or 'hid' in device.name.lower():
            return device.path
        else:
            return 0

#MachineID :M-VIC-TOOL-0267
#DieID :D-DIEID:WMA0022,OPERATIONID:WMA0022-10,CAVITY:1

def StringToDict(data):
    list1=data.split(",")
    #print(list1)
    dict={}
    for pair in list1:
        key, value = pair.split(':', 1)
        key = key.strip()
        value = value.strip()
        dict[key] = value

    return dict

def read_timestamp_and_value(file_path):
    try:
        with open(file_path, 'r') as file:
            data = json.load(file)
            for timestamp_str, value in data.items():
                timestamp = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S.%f')
                return timestamp, value
    except Exception as e:
        print("Error reading file or parsing timestamp:", e)
        return None, None


def read_file(file_path,readFileInterval,interlockThreshold,LockCondation,mId):
    global UnlockStatus
    # Login credentials and machine ID
    login_url = "https://pel.quadworld.in/auth/login"
    username = "Autosys@aispl.co"
    password = "Autosys@123"
    machineId = mId
    locked= False
    # Machine status API URL
    url = f"https://pel.quadworld.in/client/location/plant/division/line/machines?downtimeStatus=0&id={machineId}"

    if(LockCondation==""):
        print("ERROR:Assign Lockcondation in config")
        return


    while True:
        if LockCondation == "Punch":

            print("DEBUG: LockCondition = PUNCH")
            #logging.info("DEBUG: Loop is running, Condation = PUNCH")

            try:
                if os.path.exists(file_path):

                    file_timestamp, value = read_timestamp_and_value(file_path)

                    time_gap = (datetime.now() - file_timestamp).total_seconds()

                    if not locked and time_gap > interlockThreshold * 60:

                        print("DEBUG: Time gap exceeded...")
                        #logging.info("DEBUG: Time gap exceeded.."

                        downtimeStatus = DowntimeStatus(username, password, login_url, url)

                        #print("DEBUG: Downtime Status:", downtimeStatus)

                        if downtimeStatus:  # downtimeStatus is true

                            print("DEBUG: Reason NOT punched")
                            #logging.info("DEBUG: Reason NOT punched")
                            send_signal("1")

                            locked = True
                        else:
                            print("DEBUG: Reason punched")
                            #logging.info("DEBUG: Reason punched")
                            send_signal("0")
                            current_time=datetime.now()
                            with open(file_path, 'w') as file:
                                file.write(str(json.dumps({current_time.strftime('%Y-%m-%d %H:%M:%S.%f'):0})))

                            locked = False

                    elif locked:
                        downtimeStatus = DowntimeStatus(username, password, login_url, url)
                        #print("DEBUG: Locked check - Downtime Status:", downtimeStatus)

                        file_timestamp, value = read_timestamp_and_value(file_path)

                        time_gap = (datetime.now() - file_timestamp).total_seconds()

                        if not downtimeStatus or UnlockStatus==True:
                            send_signal("0")
                            locked = False
                            
                            UnlockStatus=False
                            print("DEBUG: Reason punched, unlocking")
                            if not downtimeStatus:
                                print("rrrrrrrrrrrrrrrrrrrrrrrrrrrrrrrrrrrrr")
                                current_time=datetime.now()
                                with open(file_path, 'w') as file:
                                    file.write(str(json.dumps({current_time.strftime('%Y-%m-%d %H:%M:%S.%f'):0})))
                            #logging.info("DEBUG: Reason punched, unlocking")
                        else:
                            print("DEBUG: Reason NOT punched -- Machine still locked")
                            #logging.info("DEBUG: Reason NOT punched -- Machine still locked")
            except Exception as e:
                print("FILE ERROR:",e)
                #logging.debug("FILE ERROR:",e)


        elif LockCondation == "None":
            print("DEBUG: LockCondition = None")
            if os.path.exists(file_path):
                file_timestamp, value = read_timestamp_and_value(file_path)
                time_gap = (datetime.now() - file_timestamp).total_seconds()

                if(time_gap > interlockThreshold * 60):
                    print("Machine LOCK")
                    send_signal("1")
                    
                    current_time=datetime.now()
                    with open(file_path, 'w') as file:
                        file.write(str(json.dumps({current_time.strftime('%Y-%m-%d %H:%M:%S.%f'):0})))
                        #print("time Reset in file", current_time)

                    #This condation FaIl only when right diY is AssIgn.
        else:
            print("Invalid Lockcondition assign in config!")
            #logging.info("Invalid Lockcondation assign in config!")

        time.sleep(readFileInterval)

def read_barcode_data(file_path,interval,LockCondation,mId):

    global UnlockStatus
    # Login credentials and machine ID
    login_url = "https://pel.quadworld.in/auth/login"
    username = "Autosys@aispl.co"
    password = "Autosys@123"
    machineId = mId
    # Machine status API URL
    url = f"https://pel.quadworld.in/client/location/plant/division/line/machines?downtimeStatus=0&id={machineId}"


    urldie = "http://dal.aispl.co:3030/die-logs"
    PostDict={}
    barcode_data = ''
    device=Find_BarCodeScanner()
    if device!=0:
        device_path = InputDevice(device)      
        for event in device_path.read_loop():
            if event.type == ecodes.EV_KEY:
                key_event = categorize(event)
                #print(key_event)    
                if key_event.keystate == key_event.key_down:  
                    barcode_data += ecodes.KEY[event.code].replace('KEY_','')
                    #print(barcode_data)   
                    if event.code == ecodes.KEY_ENTER:
                        
                        data=("".join(barcode_data.split("LEFTSHIFT"))).replace('SEMICOLON', ':').replace('COMMA', ',').replace('MINUS', '-').replace('ENTER', '\n').replace('\n','').replace('SLASH','/').replace('SPACE','')
                        print(data)
                        if(data[0]=="D"):
                            #print("D:",data)
                            TempDict=StringToDict(data)
                            PostDict.update({"dieId":TempDict["D-DIEID"],"operationId":TempDict["OPERATIONID"]})
                            print("DieID:",PostDict)
                          
                        elif(data[0]=="M" or re.match(r"^[A-Z]+-[A-Z]+-\d{4}$",data)):
                            #print("M:",data)
                            #data=data.split()
                            #print(len(data))
                            PostDict.update({"machineId":data})
                            print("machineID:",PostDict)
                           
                        elif(data=="POST"):
                            print("Data POST")

                            if "dieId" in PostDict and "machineId" in PostDict:

                                #print("DieID:",len(PostDict["dieId"]))
                                #print("Machine",len(PostDict["machineId"]))

                                try:
                                    status=requests.post(urldie,data=PostDict)
                                    response = json.loads(status.text)

                                except Exception as e:
                                    print("POST ERROR:",e)
                            
                                if(response["linked"]==True):
                                    print("response:",response["linked"])
                                    if(LockCondation == "None"):
                                        #downtimeStatus = DowntimeStatus(username, password, login_url, url)
                                        if(not DowntimeStatus(username, password, login_url, url)):
                                            print("#####------------Die link and downtimebutton punched!-----------#####")
                                            send_signal("0")
                                    elif(LockCondation == "Punch"):
                                        
                                        UnlockStatus=True
                                        send_signal("0")
                                        current_time=datetime.now()
                                        with open(file_path, 'w') as file:
                                            file.write(str(json.dumps({current_time.strftime('%Y-%m-%d %H:%M:%S.%f'):0})))
                                            print("time Reset in file", current_time)
                                    else:
                                        print("Assigned Proper Condition : Punch/None in Config!")
                                else:
                                    send_signal("1")
                                    print("response:",response["linked"])

                            else:
                                print("Machine ID/Die Id Not Scan!")


                        barcode_data = ''
                        #data=''

                    
    else:
        print("Barcode Device Not Found")
        #logging.info("Barcode Device not Found")


if __name__ == "__main__":
    
    datetimeFile, interval, threshold, Lockcondation,mId = readconfig()
    try:
        t1 = threading.Thread(target=read_barcode_data, args=(datetimeFile, interval,Lockcondation,mId))
        t2 = threading.Thread(target=read_file, args=(datetimeFile, interval, threshold, Lockcondation,mId))
        t1.start()
        t2.start()
        #t1.join()
        #t2.join()
    except Exception as e:
        print("Thread ERROR: ",e)

    print("Both threads started.-----------------")


