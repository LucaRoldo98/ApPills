# -*- coding: utf-8 -*-
import time
import json
import threading
import requests 
import paho.mqtt.client as PahoMQTT 

confFile = "conf.json"

'''
Reads from the catalog all the pairs patient-device. For each pair, it generates 
a channel on thingspeak (in not premium version, up to 5 channels) and it will
create a list where it associates each pair to its own channel ID and api-key.
It is subscribed to the messages from the smart case regarding humidity and temperature, 
and from timeshift, overall statics on the number of pills taken each day from a device. 
Everytime a message is received by the broker, TSadaptor will update the value 
on thingspeak sending a POST. 
'''


# create list of thingspeak channel ID for each pair user-device
listID={}
lock = threading.Lock()
 
class TSupload:
    def __init__(self,apiKeyWrite,Data_list):
        self.Data_list = Data_list
        self.apiKeyWrite = apiKeyWrite
        self.baseUrl = "https://api.thingspeak.com/update?api_key="+self.apiKeyWrite     
    def upload(self):
        
        baseUrl = self.baseUrl
        for pair in self.Data_list:
            url = baseUrl+"&field"+str(pair[0])+"="+str(pair[1])
            print(url)
            time.sleep(16)
            response = requests.post(url)


class MQTTinterface:

    def __init__(self, broker, port, baseTopic, clientID):
        self.broker = broker 
        self.port = port
        self.clientID = clientID 
        self.baseTopic = baseTopic
        self.timeShiftTopic=baseTopic+"/+/+/timeShift"
        self.tempHumTopic=baseTopic+"/+/+/temperatureHumidity"
        self._paho_mqtt = PahoMQTT.Client(clientID, True)
        self._paho_mqtt.on_connect = self.myOnConnect
        self._paho_mqtt.on_message = self.myOnMessageReceived 
       
    def myOnConnect(self, paho_mqtt, userdata, flags, rc):
        pass
        #print("[",time.ctime(),"] - Time shift connected to", self.broker, "with result code", rc)

    def myOnMessageReceived(self, paho_mqtt, userdata, msg):
        self.notify(msg.topic, msg.payload)
        
    def publish(self, top, value, slot):
        msg = self.__msg
        topic = self.baseTopic + "/" + top
        msg["e"]["message"] = value
        msg["e"]["slot"] = slot
        self._paho_mqtt.publish(topic, json.dumps(msg), 2)     
        print(f"message published to topic {topic}" )
        
    def subscribe(self, topic):
        self._paho_mqtt.subscribe(topic,2)
        print("[",time.ctime(),"] - Subscribed to", topic)
        
    def start(self):
        self._paho_mqtt.connect(self.broker, self.port)
        self._paho_mqtt.loop_start()
        print("[",time.ctime(),"] - Thingspeak adaptor", self.clientID, "started")
        self.subscribe(self.timeShiftTopic)
        self.subscribe(self.tempHumTopic)
        
    def unsubscribe(self):
        self._paho_mqtt.unsubscribe(self.timeShiftTopic)
        
        
    def stop(self):
        self.unsubscribe()
        self._paho_mqtt.loop_stop()
        self._paho_mqtt.disconnect()
        print("[",time.ctime(),"] - Thingspeak adaptor", self.clientID, "stopped")
    
    def notify(self,topic,msg):
        payload=json.loads(msg)
        #print(payload)
        patientID = str(topic.split("/")[1])
        deviceID = str(topic.split("/")[2])
        
        
        try:
            apikey_user = str(listID[patientID+'/'+deviceID]).split('/')[1]
        except: 
            print('not available')
            return
            
        # send values of temperature and humidity
        if payload["bn"] == "smartCase":
            Enviro_list = []
            for data in payload["e"]:
                Data_list = []
                print(data)
                if data["name"]== "temperature":
                    f1 ="1"
                    Data_list.append(f1)
                    v1 = str(data["value"])
                    Data_list.append(v1)
                    Enviro_list.append(Data_list)
                elif data["name"] == 'humidity':
                    f2 ="2"
                    Data_list.append(f2)
                    v2 = str(data["value"])
                    Data_list.append(v2)
                    Enviro_list.append(Data_list)
            TSup = TSupload(apikey_user,Enviro_list)
            TSup.upload()    
            
            
        # send values of daily statistics statistics  
        if payload["bn"] == "appPills-TimeShift":
            if payload["e"]["message"] == 5: # daily stat
                # request the number of channels for each device
                print("STATS RECEIVED")
                num = requests.get(catalogURI+"getSlotsNumber/"+patientID+'/'+deviceID).json()
                num_slots = num["slots"]
                stat = payload["e"]["slot"]
                stat_list = []
                list_slots = []
                for i in range(num_slots):
                    list_slots.append("slot"+str(i))
                for i, sl in enumerate(list_slots):
                    if i<=5: 
                        data_list = []
                        field = str(i+3)
                        value = stat[sl]
                        data_list.append(field)
                        data_list.append(value)
                        stat_list.append(data_list)
                TSup = TSupload(apikey_user,stat_list)
                TSup.upload()   
                
                    
                
class Thread1(threading.Thread):
    """generate MQTT receiver that receives all messages
    from the timeshift and devices"""
    def __init__(self, ThreadID, name): 
        threading.Thread.__init__(self)
        self.ThreadID = ThreadID
        self.name = name
    
    def run(self): 
        catalogURI=json.load(open(confFile))["catalogURI"]
        conf = requests.get(catalogURI+"conf").json()
        # run mqtt receiver
        ts_rec = MQTTinterface(conf["broker"], conf["port"], conf["baseTopic"], "appPills-ThingSpeak")
        ts_rec.start() 

    
if __name__ == '__main__':
    # read in the conf file the info 
    catalogURI=json.load(open(confFile))["catalogURI"]
    conf = requests.get(catalogURI+"conf").json()
    broker = conf["broker"]
    port = conf["port"]
    baseTopic = conf["baseTopic"]
    apiKeyWrite = conf["apiKeyWrite"]
    listID={}
    last_update_cat = '00:00:00'
    channels = {
            "api_key": apiKeyWrite,
            "description": "Statistics of App-Pills Application",
            "public_flag" : True,
            "field1": "temp",
            "field2": "hum" , 
        }
    headers = {
        'Content-Type': 'application/json'
        }
    print("start")
    
    cat_last_update = requests.get("http://127.0.0.1:8080"+'/getLU').json()["LU"]
    cat_last_update = cat_last_update.split(" ")[3]
    if cat_last_update!=last_update_cat:
        last_update_cat = cat_last_update
        lock.acquire()
        catalog = requests.get(catalogURI + "getCatalog").json()
        for patient in catalog["patientList"]:
                userID = patient["userID"]
                for device in patient["devices"]:
                    deviceID = device["deviceID"]
                    k=str(userID)+"/"+str(deviceID)
                    num = requests.get(catalogURI+"getSlotsNumber/"+k).json()
                    num_slots = num["slots"]
                    channels1 = channels
                    for i in range(num_slots): 
                        if i<=5: 
                            channels1["field"+str(i+3)] = "slot"+str(i+1)
                        else:
                            print("No more than 8 field available on thingspeak")
                    ch = requests.get(catalogURI + "thingSpeakChannel/"+k).json()["channel"]
                    print(ch)
                    if ch!="None": 
                        listID[k]=ch
                        
                    else: 
                         header = {
                              'Content-Type': 'application/json'
                            }
                         print('generate new channel')
                         payload = json.dumps(channels1)
                         req = requests.request("POST", 'https://api.thingspeak.com/channels.json', headers = header, data=payload).json()
                         
                         try:
                         # need both channel ID and channel api_key to upload data on thingspeak 
                             name = str(req['api_keys'][0]['api_key'])
                             listID[k] = str(req['id']) + '/' + name
                             res = requests.put(catalogURI + "addChannel/"+str(userID)+"/"+str(deviceID), json.dumps({"channel": str(req['id']) + '/' + name}))
                             print('add apikey')
                         except:
                            print('Not more channels available')
                            pass
                                                  # need both channel ID and channel api_key to upload data on thingspeak 
                      
        lock.release()
    thread1 = Thread1(1, "thread1")
    thread1.start()
    print(listID)
    # read in cat all couples user-device and for each create a 
    # channel on thingspeak and save the id and write it in the catalog
    while True: 

        # Ping every 5 seconds to say I'm alive 
        requests.put(catalogURI+"ping", data=json.dumps({"service": "thingSpeakAdapter"}))
        # check the last update of the catalog and update the list if catalog has been changed
        cat_last_update = requests.get("http://127.0.0.1:8080"+'/getLU').json()["LU"]
        cat_last_update = cat_last_update.split(" ")[3]
        if cat_last_update!=last_update_cat:
            last_update_cat = cat_last_update
            print("update Tthingspeak")
            lock.acquire()
            catalog = requests.get(catalogURI + "getCatalog").json()
            for patient in catalog["patientList"]:
                userID = patient["userID"]
                for device in patient["devices"]:
                    deviceID = device["deviceID"]
                    k=str(userID)+"/"+str(deviceID)
                    num = requests.get(catalogURI+"getSlotsNumber/"+k).json()
                    num_slots = num["slots"]
                    channels1 = channels
                    for i in range(num_slots): 
                        if i<=5: 
                            channels1["field"+str(i+3)] = "slot"+str(i+1)
                        else:
                            print("No more than 8 field available on thingspeak")
                    ch = requests.get(catalogURI + "thingSpeakChannel/"+k).json()["channel"]
                    print(ch)
                    if ch!="None": 
                        listID[k]=ch
                    else: 
                         header = {
                              'Content-Type': 'application/json'
                            }
                         payload = json.dumps(channels1)
                         print('generate new channel')
                         req = requests.request("POST", 'https://api.thingspeak.com/channels.json', headers = header, data=payload).json()
                         try:
                         # need both channel ID and channel api_key to upload data on thingspeak 
                             name = str(req['api_keys'][0]['api_key'])
                             listID[k] = str(req['id']) + '/' + name
                             res = requests.put(catalogURI + "addChannel/"+str(userID)+"/"+str(deviceID), json.dumps({"channel": str(req['id']) + '/' + name}))
                             print('add apikey')
                         except:
                            print('Not more channels available')
                            pass
                       
            lock.release()
        time.sleep(5) # or more, no many updates
    
                
                
                
