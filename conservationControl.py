import json
import time
import requests
import paho.mqtt.client as PahoMQTT

confFile = "conf.json"

class ConservationControl:

    def __init__(self, broker, port, baseTopic, clientID, catalogURI):
        self.broker=broker
        self.port=port
        self.clientID=clientID
        self.baseTopic=baseTopic
        self.subTopic=baseTopic+"/+/+/temperatureHumidity"
        self._paho_mqtt=PahoMQTT.Client(clientID, True)
        self.catalogURI=catalogURI
        self._paho_mqtt.on_connect=self.myOnConnect
        self._paho_mqtt.on_message=self.myOnMessageReceived
        self.threshs = [] # List of thresholds of every device. Every element is a json with the following structure: {"deviceID":, "tempUpperThresh":, tempLowerThresh:, humUpperThresh:, humLowerThresh:}

    def myOnConnect (self, paho_mqtt, userdata, flags, rc):
        print("\n[",time.ctime(),"] - Conservation Control connected to", self.broker, "with result code", rc)

    def myOnMessageReceived(self, paho_mqtt, userdata, msg):
        self.notify(msg.topic, msg.payload)

    def publish(self, topic, critTemp=None, critHum=None):
        msg={
            "bn": self.clientID,
            "e":[]
        }
        if critTemp!=None or critHum!=None: # Publish only if there is a crit value
            if critTemp!=None:
                temp={
                    "sensorName":"temperature",
                    "value": critTemp["value"],
                    "unit": critTemp["unit"],
                    "timestamp": critTemp["timestamp"] 
                    }
                msg["e"].append(temp)
            if critHum!=None:
                temp={
                    "sensorName":"humidity",
                    "value": critHum["value"],
                    "unit": critHum["unit"],
                    "timestamp": critHum["timestamp"] 
                    }
                msg["e"].append(temp)
            self._paho_mqtt.publish(topic, json.dumps(msg), 2)
            #print("published message at topic",topic,"\n", json.dumps(msg, indent=2))

    def subscribe(self, topic):
        self._paho_mqtt.subscribe(topic,2)
        print("\n[",time.ctime(),"] - Subscribed to", topic)

    def start(self):
        self._paho_mqtt.connect(self.broker, self.port)
        self._paho_mqtt.loop_start()
        print("\n[",time.ctime(),"] - Conservation control", self.clientID, "started")
        self.subscribe(self.subTopic)

    def unsubscribe(self):
        self._paho_mqtt.unsubscribe(self.subTopic)
    
    def stop(self):
        self.unsubscribe()
        self._paho_mqtt.loop_stop()
        self._paho_mqtt.disconnect()
        print("\n[",time.ctime(),"] - Conservation control", self.clientID, "stopped")

    def notify(self, topic, msg):
        payload=json.loads(msg)
        patientID=str(topic.split("/")[1])
        deviceID=str(topic.split("/")[2])
        
        thresholdsTemp= {}
        thresholdsHum= {}
        found = False
        for device in self.threshs: # Find the correct thresholds for the device
            if int(device["deviceID"]) == int(deviceID):
                found = True
                thresholdsTemp["up"] = device["tempUpperThresh"]
                thresholdsTemp["low"] = device["tempLowerThresh"]
                thresholdsHum["up"] = device["humUpperThresh"]
                thresholdsHum["low"] = device["humLowerThresh"]
                break
        if not found: # If we receive env. data from a device that is not registered to any user. We set the thresholds nonetheless. The MQTT message however will not be received by anyone (no subscribers)
            thresholdsTemp["up"] = 30.0
            thresholdsTemp["low"] = 10.0
            thresholdsHum["up"] = 40.0
            thresholdsHum["low"] = 60.0
        tempCritMeasure=None 
        humCritMeasure=None # Set to none; if a measure is critical, they will be set to the crit measure
        for item in payload["e"]: # There are both humidity and temperature in the payload, in the "e" list
            if item["name"]=="temperature":
                if (float(item["value"])>float(thresholdsTemp["up"]) or float(item["value"])<float(thresholdsTemp["low"])): # Out of the set temperature range
                    tempCritMeasure=item # Store the critical value
                    print("\n[",time.ctime(),"] - Temperature out of range! Detected temperature:", item["value"], item ["unit"], "for device", deviceID, "of patient", patientID)
            if item["name"]=="humidity":
                if (float(item["value"])>float(thresholdsHum["up"]) or float(item["value"])<float(thresholdsHum["low"])): # Out of the set humidity range
                    humCritMeasure=item # Store the critical value
                    print("\n[",time.ctime(),"] - Humidity out of range! Detected humidity:", item["value"], item ["unit"],"for device", deviceID,"of patient", patientID)
        self.publish(self.baseTopic+"/"+str(patientID)+"/"+str(deviceID)+"/conservationControl", tempCritMeasure, humCritMeasure) # Publish both values. If one in None, the method will disregard it. Notification for the TelegramBot. 

    def updateThresholds(self, threshList): # Update the ConservationControl thresholds, coming from the catalog
        self.threshs = threshList

if __name__=="__main__":
    catalogURI=json.load(open(confFile))["catalogURI"] 
    conf = requests.get(catalogURI+"conf").json() # Get the system configuration from the catalog 
    controller=ConservationControl(conf["broker"], conf["port"], conf["baseTopic"], "appPills-ConservationControl", catalogURI)
    controller.start()
    while True:
        # Ping cotinuously the server to say I'm alive and get the latest thresholds 
        thresholds = requests.put(catalogURI+"ping", data=json.dumps({"service": "conservationControl"})).json()["thresholds"]
        controller.updateThresholds(thresholds)
        time.sleep(5) # Ping every 5 seconds 