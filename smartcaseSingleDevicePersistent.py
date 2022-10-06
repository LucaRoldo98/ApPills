#!/usr/bin/env python
# coding: utf-8
from MyMQTT import MyMQTT
import time
import json
import cherrypy
import threading
import numpy as np
import random
import requests 
import os

confFile = "conf.json" 
portNumber = 8090
deviceStorageFile = "device.json"

threadLock = threading.Lock()

def is_number(string1):
    try:
        int(string1)
        return True
    except ValueError:
        return False

class SmartCase: # Class for stateful information of the case (pills in every slots, opened or not, ...)

    def __init__ (self, numSlots):
        self.numSlots = numSlots
        self.deviceStorageFile = deviceStorageFile
        self.pills = [0 for i in range(numSlots)]
        self.alarmOn = False
        self.alarmStartTime = 0
        self.ledOn = [0 for i in range(numSlots)]
        self.userID = None
        self.deviceID = None
        self.assigned = False
        self.lidOpened = False
        threadLock.acquire()
        if os.path.isfile(self.deviceStorageFile): # If there is no file, create it
            self.read()
        else: 
            self.save()
        threadLock.release()

    def read(self): # Method to read stateful information from the json file
        savedData = json.load(open(self.deviceStorageFile))
        self.numSlots = savedData["numSlots"]
        self.pills = savedData["pills"]
        self.alarmOn = savedData["alarmOn"]
        self.alarmStartTime = savedData["alarmStartTime"]
        self.ledOn = savedData["ledOn"]
        self.userID = savedData["userID"]
        self.deviceID = savedData["deviceID"]
        self.assigned = savedData["assigned"]
        self.lidOpened = savedData["lidOpened"]

    def save(self): # Method to save the statful information in the json file 
        json.dump({
            "numSlots": self.numSlots,
            "pills":self.pills,
            "alarmOn":self.alarmOn,
            "alarmStartTime":self.alarmStartTime,
            "ledOn":self.ledOn,
            "userID": self.userID,
            "deviceID": self.deviceID,
            "assigned": self.assigned,
            "lidOpened":self.lidOpened
        }, open(self.deviceStorageFile, "w"), indent = 8)
        
class SmartCaseRESTInterface(): # Class that implements the REST WebServer interface of the device. Used for the counters, alarm, LEDs and to assign a userID to it

    exposed=True

    def __init__(self, smartCase):
        self.smartCase = smartCase # Uses a SmartCase class for the stateful information
        # Assign an ID only if its the first time starting the device 
        if smartCase.deviceID == None:  
            catalogURI = json.load(open(confFile))["catalogURI"]
            deviceID = requests.put(catalogURI + "newDevice", json.dumps({"port":portNumber, "numSlots":smartCase.numSlots})).json()["deviceID"] # Inform the catalog of the start of the new device, and receive the assigned deviceID
            self.smartCase.deviceID = deviceID
            threadLock.acquire()
            self.smartCase.save()
            threadLock.release()
        print("\n*** The deviceID for this device is:", self.smartCase.deviceID, "***\n")

    def GET(self,*uri,**params):
    
        if len(uri)!=0:

            # Return the number of pills in each slot. It is a list, where index is the slot and value is the number of pills 
            if uri[0] == "counters": 
                counter = self.smartCase.pills
                msg = {"bn":"smartCase",
                        "e":{
                            "number":counter,
                            "timestamp": str(time.time())}
                    }
                return json.dumps(msg)
    
    def PUT(self,*uri):

        if len(uri) != 0:
            
            if uri[-1]=="alarm": # Update the alarm (set from TimeShift or TelegramBot)
                body = json.loads(cherrypy.request.body.read())
                msg=self.update_alarm(body)
                
            elif uri[-1]=="led": # Update the leds (set from TimeShift)
                body = json.loads(cherrypy.request.body.read())
                msg=self.update_LED(body)
            
            if uri[-1] == "userID": # Method that is called whenever the device is assigned to a user. The device will start posting MQTT messages only when it has a userID  
                body = json.loads(cherrypy.request.body.read())
                self.smartCase.userID = int(body["userID"]) # Retrieve the userID of the patient that registered the device
                self.smartCase.assigned = True
                threadLock.acquire()
                self.smartCase.save()
                threadLock.release()
                msg = 1
                
        else:
            msg = 0
        return json.dumps({"success": msg})

    def DELETE(self,*uri):

        # Remove userID associated when the device is removed (from the TelegramBot)
        if uri[-1] == "dissociate":
            self.smartCase.userID = None
            self.smartCase.assigned = False
            threadLock.acquire()
            self.smartCase.save()
            threadLock.release()

    
    def update_alarm(self, alarm_info):
         
        self.smartCase.alarmOn = alarm_info['on'] # Set the alarm to what is written in the payload
        if alarm_info["on"] == 1:
            self.smartCase.alarmStartTime = time.time()
            print("The alarm was turned on!")
        else:
            print("The alarm was turned off!")
        threadLock.acquire()
        self.smartCase.save()
        threadLock.release()
        return 1
        
    def update_LED(self, LED_info):
    
        slot = int(LED_info["slotID"])
        self.smartCase.ledOn[slot] = int(LED_info["on"])
        if LED_info["on"] == 1:
            print("The led of slot", slot, "was turned on!")
        else:
            print("The led of slot", slot, "was turned off!")
        threadLock.acquire()
        self.smartCase.save()
        threadLock.release()
        return 1


class OpeningSimulator(): # MQTT client that simulates the publishing of the opening of the case 
    
    def __init__(self,clientID,topic,broker,port):
        self.topic=topic
        self.client=MyMQTT(clientID,broker,port,None)

    def start (self):
        self.client.start()

    def stop (self):
        self.client.stop()

    def publish(self,state,topic):
        msg = {"bn":"smartCase","e":{"open":int(state),"timestamp":str(time.time())}} # Publish the state of the opening, along with the time
        #print("Published at topic", external_topic , "message:\n", json.dumps(msg, indent=2))
        self.client.myPublish(topic,msg)

class WebServerThread(threading.Thread): # Thread to host the REST interface 
   
    def __init__(self, threadID, name, smartCase):
        threading.Thread.__init__(self)
        self.threadID = threadID
        self.name = name
        self.smartCase = smartCase
        
    def run(self):
        conf = {"/":{"request.dispatch":cherrypy.dispatch.MethodDispatcher()}}
        cherrypy.tree.mount(SmartCaseRESTInterface(self.smartCase),"/",conf)
        cherrypy.config.update({'server.socket_port':portNumber})
        cherrypy.engine.start()
        cherrypy.engine.block()
        

class Alarm_control(threading.Thread): # Thread that stop the alarm from ringing for too much
    
    def __init__(self, ThreadID, name, timeThresh, smartCase):
        """Initialise thread."""
        threading.Thread.__init__(self)
        self.ThreadID = ThreadID
        self.name = name
        self.timeThresh = timeThresh # How long the alarm can ring
        self.smartCase = smartCase
        
    def run(self):
        while True:
            time.sleep(5) # Check every 5 seconds
            if self.smartCase.alarmOn == True:
                print("[!!!] Alarm is ringing ...")
                if float(time.time())-float(self.smartCase.alarmStartTime) >= self.timeThresh: 
                    self.smartCase.alarmOn = False # Turn of the alarm if it has rung for more than timeThresh
                    threadLock.acquire()
                    self.smartCase.save()
                    threadLock.release()
                    print("The alarm rang for too long and was turned off")
                else:
                    print("The alarm has rung for",round(float(time.time())-float(self.smartCase.alarmStartTime)),"seconds")

class EnvironmentSimulator: # Class that simulates the temperature and humidity sensor of the device. It is an MQTT publisher

    def __init__(self):
        self.pastTemp = 20.0 # Initial value of temperature. Used in noisy_TempHum
        self.pastHum = 50.0 # Initial value of humidity. Used in noisy_TempHum
    
    def random_TempHumi(self): # Method that picks a random temperature and humidity in a specified range. Next method is more realistic. 
        
        humi = np.round(random.uniform(30,70),2) 
        temp = np.round(random.uniform(5,35),2)
        msg = {"bn":"smartCase",
               "e": [{
                   "name": "temperature",
                   "value": temp,
                   "timestamp":time.time(),
                    "unit": "C"},
                    {"name": "humidity",
                    "value":humi,
                    "timestamp":time.time(),
                    "unit": "%"}]
              }        
        return(msg)

    def noisy_TempHum(self):
        '''
        Basically perform a random walk: to the last past sample add a uniform r.v. in the range [-1,1].
        The average therefore will be the starting temperature and humidity.
        '''
        self.pastTemp += round(random.random()*2 - 1, 3)
        self.pastHum += round(random.random()*2 - 1, 3)
        msg = {"bn":"smartCase",
               "e": [{
                   "name": "temperature",
                   "value": round(self.pastTemp, 3),
                   "timestamp":time.time(),
                    "unit": "C"},
                    {"name": "humidity",
                    "value":round(self.pastHum, 3),
                    "timestamp":time.time(),
                    "unit": "%"}]
              }        
        return(msg)    

class EnvironmentSimulatorThread(threading.Thread): # Thread that hosts the environment simualtor 
    
    def __init__(self,threadID, smartcase, broker,port):
        threading.Thread.__init__(self)
        self.threadID = threadID
        self.smartcase = smartcase
        self.broker = broker
        self.port = port
        
    def run(self):
        test = MyMQTT(str(self.smartcase.userID), self.broker, self.port, None)
        test.start()
        simu = EnvironmentSimulator()
        while True:
            if smartcase.assigned == True and smartcase.userID != None: # Publish only if assigned to a user 
                msg = simu.noisy_TempHum() # Random walk simulator 
                # Topic not fixed because the case may change userID over time (dissociated)
                test.myPublish("smartCase/"+str(self.smartcase.userID)+"/"+str(self.smartcase.deviceID)+"/temperatureHumidity",msg)
            #print("Published at topic", self.topic, "temperature = ", msg["e"][0]["value"], " humidity = ", msg["e"][1]["value"])
            time.sleep(30) # Publish every 30 seconds                    
        
if __name__ == "__main__":

    catalogURI=json.load(open(confFile))["catalogURI"]
    conf = requests.get(catalogURI+"conf").json() # Get system configuration
    broker = conf["broker"]
    port = conf["port"]
    basetopic = conf["baseTopic"]
    clientID = "smartCaseSimulator"

    numSlots = "" # standard number, will be overwritten afterwards 

    
    if not os.path.isfile(deviceStorageFile): # If it's the first run, the json file doesn't exist. Therefore to create a new run, just delete the json file
            while not is_number(numSlots):
                inserted = input("Insert the intended number of slots of the device: ") # Scalable slots; on startup you can decide how many slots the device will have 
                if not is_number(inserted):
                    print("Not a number")
                elif int(inserted) == 0:
                    print("Zero is not a possible value")
                elif int(inserted) < 0:
                    print("Slot number must be positive")
                else:
                    numSlots = int(inserted)
    else:
        numSlots = json.load(open(deviceStorageFile))["numSlots"]
    
    smartcase = SmartCase(numSlots) # Instantiate the stateful smartcae
    wasAlreadyAssiged = smartcase.assigned and smartcase.userID!=None # Check if the SmartCase was already assigned to a user 

    thread1 = WebServerThread(1, "thread1", smartcase)
    thread1.start()
    timeThresh = 30
    thread2 = Alarm_control(2, "thread2", timeThresh, smartcase)
    thread2.start()
    time.sleep(0.5)

    if wasAlreadyAssiged:
        print("\nDevice is registered to user with userID", str(smartcase.userID))
    else:
        print("\n[...] Waiting for device to be registered to a user...") # If not assigned, wait for it to be assigned from the TelegramBot. This because without the userID the MQTT publisher don't have the full topic information 
        while smartcase.userID == None: # It will become != None when the catalog sends a PUT request
            pass 
        print("\n[*] Device was registered to user with ID", smartcase.userID, "\n")
    Open_simul = OpeningSimulator(clientID,basetopic,broker,port)
    Open_simul.client.start()
    thread3 = EnvironmentSimulatorThread("EnvironmentSimul",smartcase,broker,port)
    thread3.start()

    # From here down, console code for interacting with the device 
    while True:
        
        external_topic = basetopic + "/" + str(smartcase.userID) + "/" + str(smartcase.deviceID) + "/" + "lid" # Updated every iteration. It could change if the device is reassigned to another user
        opened= smartcase.lidOpened

        if opened == False:
            
            print("\nThe case is closed.")
            if smartcase.alarmOn == True:
                print("The alarm is ringing.")
            else:
                print("The alarm is off.")
            
            # You can see the LEDs when the device is closed 
            ledStatusText = ""
            for index,led in enumerate(smartcase.ledOn):
                ledStatusText += "\n\tSlot "+ str(index)+ " : " + str(led)
            print("Leds status:" + ledStatusText)
            
            state = input('\n[*] Open the lid?\n\tyes -> 1\n')

            if state == "1": # User opened the lid
                
                smartcase.lidOpened = True # Open the lid 
                threadLock.acquire()
                smartcase.save()
                threadLock.release()
                if smartcase.assigned == True and smartcase.userID != None: # Publish only if assigned. This is just an error case, should always be true 
                    Open_simul.publish(1,external_topic)
                # You can see the pills when the device is opened
                numberOfPillsText = ""
                for index,pills in enumerate(smartcase.pills):
                    numberOfPillsText += "\n\tSlot "+ str(index)+ " : " + str(pills)
                print("\n[!] The number of pills in the case is:", numberOfPillsText ,"\n")
                while int(state): # While the lid is opened
                    slot = input("\n[*] Which slot? Choose a number between 0 and " + str(smartcase.numSlots - 1) + "\n") 
                    if not is_number(slot):
                        print("[!!!] Incorrect slot number.")
                    elif int(slot) < 0 or int(slot) > smartcase.numSlots - 1:
                        print("[!!!] Incorrect slot number.")
                    else:
                        action = input('\n[*] What do you want to do?\n\tTake out pills -> -1\n\tFill pills -> 1\n\tDo nothing -> 0\n')
                        if action == "-1": # Take out pills 
                            counter = input("[*] How many pills do you want to take out?\n")                        
                            numPill = smartcase.pills[int(slot)]
                            if not is_number(counter):
                                print("[!!!] Number of pills not available.")
                            elif int(counter) < 0:
                                print("[!!!] Number of pills not available.")
                            elif int(counter)>numPill: 
                                print("[!!!] Number of pills not available.")
                            else:
                                smartcase.pills[int(slot)] = numPill - int(counter)
                                smartcase.alarmOn = False
                                threadLock.acquire()
                                smartcase.save()
                                threadLock.release()

                        elif action == "1": # Fill pills 
                            counter = input("\n[*] How many pills do you want to fill?\n")
                            numPill = smartcase.pills[int(slot)]
                            smartcase.pills[int(slot)] = numPill + int(counter)
                            threadLock.acquire()
                            smartcase.save()
                            threadLock.release()    
                                                                    
                        elif action == "0": # Do nothing 
                            counter = 0
                        else:
                            print("\n[!!!] Entered incorrectly\n")
                            
                    action2 = input("\n[*] Do you want to close the lid?\n\t1 -> close\n\t0 -> do nothing\n")
                    if action2 == "1": # Close the lid 
                    
                        smartcase.lidOpened = False
                        if smartcase.assigned == True and smartcase.userID != None: # Publish only if assigned
                            Open_simul.publish(0,external_topic) # Publish the closing of the lid
                        threadLock.acquire()
                        smartcase.save()
                        threadLock.release()
                        state = 0
                        
                    elif action2 == "0": # Leave the case opened and interact again with the device
                        state = 0
                    else:
                        state = 0
                        print("[!!!] Entered incorrectly\n")
            else: 
                print("[!!!] Entered incorrectly\n")
                
        
        elif opened == True: # The case was already opened 

            print("\nThe case is open!")
            # Print the number of pills in the case
            numberOfPillsText = ""
            for index,pills in enumerate(smartcase.pills):
                numberOfPillsText += "\n\tSlot "+ str(index)+ " : " + str(pills)
            print("\n[!] The number of pills in the case is:", numberOfPillsText ,"\n")
            if smartcase.alarmOn == True:
                print("\nThe alarm is ringing.")
            else:
                print("\nThe alarm is off.")

            slot = input("\n[*] Which slot? Choose a number between 0 and " + str(smartcase.numSlots - 1) + "\n") 
            if not is_number(slot):
                print("[!!!] Incorrect slot number.")
            elif int(slot) < 0 or int(slot) > smartcase.numSlots - 1:
                print("[!!!] Incorrect slot number.")
            else:
                action = input('\n[*] What do yoy want to do?\n\tTake out pills -> -1\n\tFill pills -> 1\n\tDo nothing -> 0\n')
                if action == "-1": # Take out pills
                    counter = input("\n[*] How many pills do you want to take out?\n")
                    numPill = smartcase.pills[int(slot)]
                    if int(counter)>numPill: 
                        print("[!!!] Number of pills not available")
                    else:
                        smartcase.pills[int(slot)] = numPill - int(counter)
                        smartcase.alarmOn = False
                        threadLock.acquire()
                        smartcase.save()
                        threadLock.release()
                    
                elif action == "1": # FIll pills
                    counter = input("\n[*] How many pills do you want to fill?\n")
                    numPill = smartcase.pills[int(slot)]
                    smartcase.pills[int(slot)] = numPill + int(counter)
                    threadLock.acquire()
                    smartcase.save()
                    threadLock.release()

                elif action == "0": # Do nothing
                    counter = 0

                else :
                    print("[!!!] Entered incorrectly\n")

            action2 = input("\n[*] Do you want to close the lid?\n\t1 -> close\n\t0 -> do nothing\n")
            if action2 == "1": # Close the lid 
                smartcase.lidOpened = False
                if smartcase.assigned == True and smartcase.userID != None: # Publish only if assigned
                    Open_simul.publish(0,external_topic)
                state = 0
                threadLock.acquire()
                smartcase.save()
                threadLock.release()
                
            elif action2 == "0": # Do nothing, and interact again with the device 
                state = 0
            else:
                state = 0
                print("[!!!] Entered incorrectly\n")
                                            
        else:
            print("[!!!] Error\n")
