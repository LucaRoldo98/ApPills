import json
import time
import requests
import paho.mqtt.client as PahoMQTT

confFile = "conf.json"

class OpeningControl:
    
    def __init__(self, broker, port, baseTopic, clientID, catalogURI):
        self.broker=broker
        self.port=port
        self.clientID=clientID
        self.baseTopic=baseTopic
        self.sub_topic_external=baseTopic+"/+/+/lid"
        self._paho_mqtt= PahoMQTT.Client(clientID,True)
        self.catalogURI=catalogURI 
        self._paho_mqtt.on_connect=self.myOnConnect
        self._paho_mqtt.on_message=self.myOnMessageReceived
        self.__msg={
            "bn":self.clientID,
            "e":{
                "openedTooMuch":None,
                "timestamp":""
            }
        }
    
    def myOnConnect(self, paho_mqtt, userdata, flags, rc):
        print("\n[",time.ctime(),"] - Opening Control connected to", self.broker, "with result code", rc)

    def myOnMessageReceived(self, paho_mqtt, userdata, msg):
        self.notify(msg.topic, msg.payload)

    def publish(self, topic):
        msg=self.__msg
        msg['e']["openedTooMuch"]=True 
        msg['e']["timestamp"]=time.time() # Publish message setting a flag for saying device was opened for too much time. Notification for the TelegramBot.
        self._paho_mqtt.publish(topic, json.dumps(msg), 2) 
        #print("\n[",time.ctime(),"] - Published message: ", json.dumps(msg, indent=2), "at topic", topic)

    def subscribe(self, topic):
        self._paho_mqtt.subscribe(topic,2)
        print("\n[",time.ctime(),"] - Subscribed to", topic)

    def start(self):
        self._paho_mqtt.connect(self.broker, self.port)
        self._paho_mqtt.loop_start()
        print("\n[",time.ctime(),"] - Opening control", self.clientID, "started")
        self.subscribe(self.sub_topic_external)

    def unsubscribe(self):
        self._paho_mqtt.unsubscribe(self.sub_topic_external)
        
    def stop(self):
        self.unsubscribe()
        self._paho_mqtt.loop_stop()
        self._paho_mqtt.disconnect()
        print("\n[",time.ctime(),"] - Opening control", self.clientID, "stopped")
    
    def notify(self,topic,msg):
        payload=json.loads(msg)
        patientID=str(topic.split("/")[1])
        deviceID=str(topic.split("/")[2])
        if payload["e"]["open"]==1: # If the case was opened  
            stats={
                "patientID/deviceID":patientID+"/"+deviceID,
                "timeOpened": payload["e"]["timestamp"]
            }
            requests.put(self.catalogURI+"addOpeningTime", data = json.dumps(stats)) # Save the opening time on the catalog
            print("\n[",time.ctime(),"] - Device", deviceID, "of patient", patientID, "was opened.")
        
        elif payload["e"]["open"]==0: # If the case has just been closed

            requests.delete(self.catalogURI+"rmvOpeningTime/"+ patientID + "/" + deviceID) # Delete the record of the opening time from the catalog. No notification is needed.
            print("\n[",time.ctime(),"] - Device", deviceID, "of patient", patientID, "was closed.")

if __name__=="__main__":
    
    timeThresh=300 # set the time after which a warning is sent to the user 
    lastWarnings={} # Don't send a warning every time if the case is still opened; check the last warning so you send it every timeThresh minutes
    
    catalogURI=json.load(open(confFile))["catalogURI"]
    conf = requests.get(catalogURI+"conf").json() # Get the system configuration 
    controller=OpeningControl(conf['broker'], conf["port"], conf["baseTopic"], "appPills-OpeningControl", catalogURI)
    baseTopic = conf["baseTopic"]
    controller.start()
    while True:
        # Ping every 5 seconds and get the latest opening times 
        openingTimes = requests.put(catalogURI+"ping", data=json.dumps({"service": "openingControl"})).json()["times"]
        now=time.time()
        for item in openingTimes: # Check if there is a device opened for too much time 
            if float(now)-float(item["timeOpened"])>=float(timeThresh): # If the case was opened for more than the threshold
                if item["patientID/deviceID"] in lastWarnings.keys(): # If we already sent a warning
                    if float(now)-float(lastWarnings[item["patientID/deviceID"]])>=float(timeThresh): # More than timeThresh minutes ago
                        controller.publish(baseTopic+"/"+item["patientID/deviceID"]+"/openingControl") # Send warning to be received by the telegramBot
                        lastWarnings[item["patientID/deviceID"]] = time.time() # Update last warning time
                        print("\n[",time.ctime(), "] - ", item["patientID/deviceID"], " opened for too much time; warning sent")
                else: # Send immediately a warning, to be received by the TelegramBot
                    controller.publish(baseTopic+"/"+item["patientID/deviceID"]+"/openingControl") 
                    lastWarnings[item["patientID/deviceID"]] = time.time() # Update last warning time
                    print("\n[",time.ctime(), "] - ", item["patientID/deviceID"], "opened for too much time; warning sent")
        time.sleep(5)
