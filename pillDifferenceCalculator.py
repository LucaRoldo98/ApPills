import json
import time
import requests
import paho.mqtt.client as PahoMQTT

confFile = "conf.json"

class DifferenceCalculator:
    
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
                "difference": [], # difference contian a list with the difference for every slot when opened and closed 
                "timestamp":""
            }
        }
    
    def myOnConnect(self, paho_mqtt, userdata, flags, rc):
        print("\n[",time.ctime(),"] - Pill Difference Calculator connected to", self.broker, "with result code", rc)

    def myOnMessageReceived(self, paho_mqtt, userdata, msg):
        self.notify(msg.topic, msg.payload)

    def publish(self, topic, variationList):
        msg=self.__msg
        msg['e']["difference"]=variationList
        msg['e']["timestamp"]=time.time()
        self._paho_mqtt.publish(topic, json.dumps(msg), 2)
        #print("\n[",time.ctime(),"] - Published message: ", json.dumps(msg, indent=2), "at topic", topic)

    def subscribe(self, topic):
        self._paho_mqtt.subscribe(topic,2)
        print("\n[",time.ctime(),"] - Subscribed to", topic)

    def start(self):
        self._paho_mqtt.connect(self.broker, self.port)
        self._paho_mqtt.loop_start()
        print("\n[",time.ctime(),"] - Pill Difference Calculator", self.clientID, "started")
        self.subscribe(self.sub_topic_external)

    def unsubscribe(self):
        self._paho_mqtt.unsubscribe(self.sub_topic_external)
        
    def stop(self):
        self.unsubscribe()
        self._paho_mqtt.loop_stop()
        self._paho_mqtt.disconnect()
        print("\n[",time.ctime(),"] - Pill Difference Calculator", self.clientID, "stopped")
    
    def notify(self,topic,msg):

        payload=json.loads(msg)
        patientID=str(topic.split("/")[1])
        deviceID=str(topic.split("/")[2])
        deviceURI=requests.get(self.catalogURI+"getDeviceURI"+"/"+patientID+"/"+deviceID).json()["deviceURI"] # Request the deviceURI, needed to retrieve the number of pills in each slot
        if deviceURI != None:
            if payload["e"]["open"]==1: # If the case was opened
                
                try: # Code gives error if the device is not reachable 
                    numPillsList=requests.get(deviceURI+"/counters").json()["e"]["number"] # Request pill count in every slot to the device 
                    stats={
                        "patientID/deviceID":patientID+"/"+deviceID,
                        "countOpened": numPillsList
                    }   
                    requests.put(self.catalogURI+"addOpeningPills", data = json.dumps(stats))
                    print("\n[",time.ctime(),"] - Device", deviceID, "of patient", patientID, "was opened.")

                except:
                    print("[",time.ctime(),"] Device", deviceID, "of user", patientID, "is not reachable.")
            
            elif payload["e"]["open"]==0: # If the case has just been closed

                try: # Code gives error if the device is not reachable 
                    numPillsList=requests.get(deviceURI+"/counters").json()["e"]["number"]
                    try:
                        countOpened = requests.delete(self.catalogURI+"rmvOpeningPills/"+ patientID + "/" + deviceID).json()["countOpened"] # Remove the opening count record from catalog and retrieve it
                        difference = [ numPillsList[i] - countOpened[i] for i in range(len(numPillsList)) ] # Calculate the difference of pills for each slot
                        self.publish(self.baseTopic+"/"+patientID+"/"+deviceID+"/pillDifference", difference)
                        print("\n[",time.ctime(),"] - Device", deviceID, "of patient", patientID, "was closed. Difference of pills is", difference)
                    except:
                        pass
                except:
                    print("[",time.ctime(),"] Device", deviceID, "of user", patientID, "is not reachable.")

if __name__=="__main__":
    
    catalogURI=json.load(open(confFile))["catalogURI"]
    conf = requests.get(catalogURI+"conf").json() # Get the system configuration 
    controller=DifferenceCalculator(conf['broker'], conf["port"], conf["baseTopic"], "appPills-pillDifferenceCalculator", catalogURI)
    controller.start()
    while True:
        # Ping every 5 seconds
        requests.put(catalogURI+"ping", data=json.dumps({"service": "differenceCalculator"}))
        time.sleep(5) 
