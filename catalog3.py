# -*- coding: utf-8 -*-
import os
import cherrypy
import json
import time
import requests
import threading 

filename= "mycat.json"
threadLock = threading.Lock() # Needed to coordinate the REST interface and the service "cleaner" that checkes which service is alive 

class Catalog(object):
    
    def __init__(self,filename):
        # Create a file if its not present yet
        if os.path.isfile(filename):
            pass
        else: 
            json.dump({}, open(self.chatStateFile, "w"))
        data = self.read()
        
        self.filename = filename

        # Check what is the maximum (int) user and device IDs, so that new devices and users will be added with an ID that is progressively 1 unit higher 
        self.maxDeviceID = 0
        self.maxUserID = 0
        for patient in data["patientList"]:
            if int(patient["userID"]) > self.maxUserID:
                self.maxUserID = patient["userID"]
            for device in patient["devices"]:
                if int(device["deviceID"]) >= self.maxDeviceID:
                    self.maxDeviceID = int(device["deviceID"])

        for assistant in data["assistantList"]:
            if int(assistant["userID"]) > self.maxUserID:
                self.maxUserID = assistant["userID"]

        for device in data["newDevices"]:
            self.maxDeviceID = max(self.maxDeviceID, int(device["deviceID"]))
    
    def save(self, data): # Method to access the json file and save it
        with open(filename, 'w') as fp:
            json.dump(data, fp, indent=6)

    def read(self): # Method to access the json file and read it 
        with open(filename) as fp:
            return json.load(fp)

    def updateLU(self): # Update the last usage of the whole catalog. Method used by the Time Shift 

        threadLock.acquire()
        catalog=self.read()
        catalog["lastUpdate"] = time.ctime()
        self.save(catalog)
        threadLock.release()
    
    def getSchedule(self,userID,deviceID): # Get the alarm schedule of every slot, specifying a useriD and deviceID. Used by the Telegram Bot

        threadLock.acquire()
        catalog=self.read()
        threadLock.release()
        for user in catalog["patientList"]:
            if int(user["userID"]) == int(userID):
                for device in user["devices"]:
                    if int(device["deviceID"]) == int(deviceID):
                        result = []
                        for slot in device["slots"]:
                            result.append(slot["schedule"])
                        return json.dumps({"slots":result})
                    
    def getSchedules(self): # Get the alarm schedule for every device of every user. Used by the Time Shift.

        threadLock.acquire()
        catalog=self.read()
        threadLock.release()
        send = {}
        for user in catalog["patientList"]:
            for device in user["devices"]:
                key = str(user["userID"]) + "/" + str(device["deviceID"])
                sched = [] 
                for slot in device["slots"]:
                    sched.append(slot["schedule"])
                send[key] = sched
        return json.dumps(send)
                

    def getDeviceURI(self,userID,deviceID): # Get the device URI given the userID and the deviceID. This is used by the Telegram Bots in order to retrieve the number of pills by contacting directly the device. 

        threadLock.acquire()
        catalog=self.read()
        threadLock.release()
        found=False
        for user in catalog["patientList"]:
            if int(user["userID"]) == int(userID):
                for device in user["devices"]:
                    if int(device["deviceID"]) == int(deviceID):
                        found=True
                        return json.dumps({"deviceURI":device["deviceURI"]})
        if found==False:
            return json.dumps({"deviceURI":None})

    def getTempThresh(self,userID,deviceID): # Return the temperature thresholds. Used both by Telegram Bot and the Conservation Control
        
        threadLock.acquire()
        catalog=self.read()
        threadLock.release()
        for user in catalog["patientList"]:
            if int(user["userID"]) == int(userID):
                for device in user["devices"]:
                    if int(device["deviceID"]) == int(deviceID):
                        return json.dumps({"tempUpperThresh":device["tempUpperThresh"],"tempLowerThresh":device["tempLowerThresh"]})

    def getHumThresh(self,userID,deviceID): # Return the temperature thresholds. Used both by Telegram Bot and the Conservation Control

        threadLock.acquire()
        catalog=self.read()
        threadLock.release()
        for user in catalog["patientList"]:
            if int(user["userID"]) == int(userID):
                for device in user["devices"]:
                    if int(device["deviceID"]) == int(deviceID):
                        return json.dumps({"humUpperThresh":device["humUpperThresh"],"humLowerThresh":device["humLowerThresh"]})

    def getChatID(self,userID): # Get chatID given userID. Used for notifications on Telegram bot, when a MQTT message is received. 

        threadLock.acquire()
        catalog=self.read()
        threadLock.release()
        found=False
        for user in catalog["patientList"]:
            if int(user["userID"])==int(userID):
                found = True
                return json.dumps({"chatID":user["chatID"]})
        if found==False:
            return json.dumps({"chatID":None})

    def getDevices(self, userID): # Get the full list of devices register to the user with the specified userID 

        threadLock.acquire()
        catalog=self.read()
        threadLock.release()
        found=False
        toSend = []
        for user in catalog["patientList"]:
            if int(user["userID"])==int(userID):
                found = True
                for device in user["devices"]:
                    toSend.append(device["deviceID"])
                if len(toSend)>0:
                    return json.dumps({"devices":toSend})
                else:
                    return json.dumps({"devices":None})
        if found==False:
            return json.dumps({"devices":None})
                    
    def getUserID(self, chatID): # Given the chatID, return the userID. Used by the TelegramBot to know which user is writing on Telegram

        chatID=int(chatID)
        threadLock.acquire()
        catalog=self.read()
        threadLock.release()
        found = False
        for user in catalog["patientList"]:
            if user["chatID"]==chatID:
                found = True
                return json.dumps({"userID":int(user["userID"])})
        if found == False:
            return json.dumps({"userID":None})

    def getUserProfileData(self, userID): # Return username, password and type of useage. Used by TelegramBot. 
        
        threadLock.acquire()
        catalog=self.read()
        threadLock.release()
        found = False
        for user in catalog["patientList"]:
            if int(user["userID"]) == int(userID):
                found = True
                return json.dumps({"username":user["userName"], "password": user["password"], "usage": user["usage"]})
        if found == False:
            return json.dumps({"username":None, "password": None, "usage": None})

    def getSlotsName(self, userID, deviceID): # Return a list containing all the slots names, given userID and deviceID. Used by TelegramBot. 
        
        threadLock.acquire()
        catalog=self.read()
        threadLock.release()
        for user in catalog["patientList"]:
            if int(userID) == int(user["userID"]):
                for device in user["devices"]:
                    if deviceID == str(device["deviceID"]):
                        result = []
                        for slot in device["slots"]:
                            result.append(slot["pillName"])
                        return json.dumps({"slots":result}) 
                    
    def getSlotsNumber(self, userID, deviceID): # Return the number of slots. Used by the TelegramBot.
        
        threadLock.acquire()
        catalog=self.read()
        threadLock.release()
        for user in catalog["patientList"]:
            if int(userID) == int(user["userID"]):
                for device in user["devices"]:
                    if deviceID == str(device["deviceID"]):
                        result = len(device["slots"])
                        return json.dumps({"slots":result}) 

    def addUser(self,patient_json): # Add a new user, that just pressed /start on Telegram and inserted username and password.
        
        threadLock.acquire()
        catalog=self.read()
        for user in catalog["patientList"]:
            if user["userName"] == patient_json["userName"]:
                threadLock.release()
                return json.dumps({"usernameExists" : 1}) # There cannot be two people with the same username!!! Alert thorugh the telegram bot to chose another username 
        #Perform the same operation for the assistant list
        for user in catalog["assistantList"]:
            if user["userName"] == patient_json["userName"]:
                threadLock.release()
                return json.dumps({"usernameExists" : 1})  
        userID = self.maxUserID + 1 # UserID is the maiximum ID registered in the Catalog, +1.
        self.maxUserID += 1 # Update the maximum number of user ID
        if (patient_json["usage"].lower() == "h"): # Type of usage of the system
            usage = "hospital"
        else: 
            usage = "personal"
        # Add the record of the new user to the Catalog
        catalog["patientList"].append({"userID": int(userID), "userName":patient_json["userName"], "password":patient_json["password"], "usage": usage, "chatID":patient_json["chatID"], "last_update":time.ctime(), "devices":[], "assistants": []})
        self.save(catalog)
        threadLock.release()
        return json.dumps({"usernameExists" : 0})
    
    def addDevice(self,deviceID,userID): # Move a device from newDevices to a user that just registered it 
        
        threadLock.acquire()
        catalog=self.read()
        found = False
        for device in catalog["newDevices"]:
            if int(device["deviceID"]) == int(deviceID):
                found =True
                toAddDevice = device # Save in a variable the information of the device to be added
                catalog["newDevices"].remove(device) # Remove the device from the newDevices list 
                self.save(catalog)
                requests.put(device["deviceURI"]+"/userID", json.dumps({"userID":int(userID)})) # Inform the device that it was correctly registered, and inform to which user
                break
        
        if found == False: # If the deviceID given by the user is not present in newDevices, send an error message back 
            threadLock.release()
            return json.dumps({"found":0})

        for user in catalog["patientList"]:
            if int(userID) == int(user["userID"]):
                slots = [ {"pillName":"","schedule":[]} for _ in range(toAddDevice["numSlots"]) ]
                deviceID = toAddDevice["deviceID"]
                # Add the newly registered device to the correct user
                user["devices"].append({"deviceID": deviceID, "deviceURI":toAddDevice["deviceURI"], "thingSpeakChannel":"None", "tempUpperThresh":30.0,"tempLowerThresh":10.0, "humUpperThresh":60.0,"humLowerThresh":40.0, "numSlots": toAddDevice["numSlots"], "slots": slots})
                self.save(catalog)
                threadLock.release()
                return json.dumps({"found":1})  

        # In the case user ID was not found
        threadLock.release()

    def addPill(self,pill_json,userID,deviceID,slotNum): # Give a pill name to a slot. Information coming from the TelegramBot. 
        
        threadLock.acquire()
        catalog=self.read()
        
        for user in catalog["patientList"]:
            if int(userID) == int(user["userID"]):
                for device in user["devices"]:
                    if deviceID == str(device["deviceID"]):
                        device["slots"][slotNum]["pillName"]=pill_json["pillName"]
                        self.save(catalog)
                        threadLock.release()
                        return json.dumps({"added":1})
        
        threadLock.release()
                    
    def addSchedule(self,schedule_json,userID,deviceID,slotNumber): # Add an alarm schedule for a pill. Information coming from the TelegramBot.
        
        threadLock.acquire()
        catalog=self.read()
        
        for user in catalog["patientList"]:
            if int(userID) == int(user["userID"]):
                for device in user["devices"]:
                    if deviceID == str(device["deviceID"]):
                        device["slots"][slotNumber]["schedule"].append({"alarm":0,"numPill":int(schedule_json["numPill"]),"time":schedule_json["time"] + ":00"})                            
                        self.save(catalog)
                        threadLock.release()
                        return json.dumps({"added":1})
        threadLock.release()

    def updateTempThresh(self, new_thresh_json, userID, deviceID): # Change temperature threshold. Information coming from the TelegramBot.

        threadLock.acquire()
        catalog=self.read()

        for user in catalog["patientList"]:
            if int(userID) == int(user["userID"]):
                for device in user["devices"]:
                    if deviceID == str(device["deviceID"]):
                        device["tempUpperThresh"]=float(new_thresh_json["upperThresh"])
                        device["tempLowerThresh"]=float(new_thresh_json["lowerThresh"])
                        self.save(catalog)
                        threadLock.release()
                        return json.dumps({"added":1})
        threadLock.release()
                    
    def updateChannel(self, channel, userID, deviceID): # Update ThingSpeak Channel
        
        threadLock.acquire()
        catalog = self.read()
        
        for user in catalog["patientList"]:
            if int(userID) == int(user["userID"]):
                for device in user["devices"]:
                    if deviceID == str(device["deviceID"]):
                        device['thingSpeakChannel'] = channel
                        self.save(catalog)
                        threadLock.release()
                        return json.dumps({"added":1})
        threadLock.release()

    def updateHumThresh(self, new_thresh_json, userID, deviceID): # Change temperature threshold. Information coming from the TelegramBot.

        threadLock.acquire()
        catalog=self.read()

        for user in catalog["patientList"]:
            if int(userID) == int(user["userID"]):
                for device in user["devices"]:
                    if deviceID == str(device["deviceID"]):
                        device["humUpperThresh"]=float(new_thresh_json["upperThresh"])
                        device["humLowerThresh"]=float(new_thresh_json["lowerThresh"])
                        self.save(catalog) 
                        threadLock.release()
                        return json.dumps({"added":1})
        threadLock.release()

    def deleteAlarm(self, userID, deviceID, slotNum, alarmNum): # Delete an alarm for a pill. Information coming from the TelegramBot.
        
        threadLock.acquire()
        catalog=self.read()

        for user in catalog["patientList"]:
            if int(userID) == int(user["userID"]):
                for device in user["devices"]:
                    if deviceID == str(device["deviceID"]):
                            del device["slots"][slotNum]["schedule"][int(alarmNum)]
                            self.save(catalog)
                            threadLock.release()
                            return json.dumps({"deleted":1}) 
        threadLock.release()

    def deleteDevice(self, userID, deviceID): # Move a device from being associated, to the newDevice list. Information coming from the TelegramBot.

        threadLock.acquire()
        catalog=self.read()

        for user in catalog["patientList"]:
            if int(userID) == int(user["userID"]):
                for device in user["devices"]:
                    if deviceID == str(device["deviceID"]):
                            user["devices"].remove(device) # Remove from the user
                            catalog["newDevices"].append(device) # Append to the newDevices 
                            requests.delete(device["deviceURI"]+"/dissociate") # Tell also the device to remove the userID to whom it is associated 
                            self.save(catalog)
                            threadLock.release()
                            return json.dumps({"deleted":1})
        threadLock.release()

    def newDevice(self): # New device just started for the first time. Add it to the newDevices list, with all the relevant information.

        threadLock.acquire()
        catalog=self.read() 
        deviceID = self.maxDeviceID + 1 # Assign the device ID as the max deviceID in the catalog + 1
        self.maxDeviceID += 1  # Update the max deviceID
        IP = cherrypy.request.remote.ip # Store the URI of the device, because it will have to be addressed for other operations (ex. getPillCount)
        body = json.loads(cherrypy.request.body.read())
        port = body["port"]
        numSlots = body["numSlots"]
        catalog["newDevices"].append({"deviceID":deviceID, "deviceURI": "http://" + str(IP)+ ":" + str(port), "numSlots":numSlots})
        self.save(catalog)
        threadLock.release()
        return deviceID

    def addAssistant(self, assistant_json): # A new assistant just pressed /start on the assistantBot. Add him to the assistantList.
        
        threadLock.acquire()
        catalog=self.read()
        assisted = []
        userID = self.maxUserID + 1 # ID as max userID +1
        self.maxUserID += 1 # Update the user ID 
        catalog["assistantList"].append({"userID": int(userID), "userName":assistant_json["userName"], "chatID":assistant_json["chatID"], "last_update":time.ctime(), "assistedPatients":assisted})
        self.save(catalog)
        threadLock.release()
        return json.dumps({"added":1})

    def getAssistantID(self, chatID): # Get the assistantID given the chat ID. Used by assistantTelegramBot to know who is writing on telegram. 

        chatID=int(chatID)
        threadLock.acquire()
        catalog=self.read()
        found = False
        for assistant in catalog["assistantList"]:
            if assistant["chatID"]==chatID:
                found = True
                threadLock.release()
                return json.dumps({"userID":int(assistant["userID"])})
        if found == False:
            threadLock.release()
            return json.dumps({"userID":None})
  
    def assistUser(self, data_json): # An assistant just entered commands, username and password on telegram to start assisting a new user 

        threadLock.acquire()
        catalog=self.read()
        username = data_json["username"]
        password = data_json["password"]
        assistantID = int(data_json["assistantID"])
        found = False
        for user in catalog["patientList"]:
            if user["userName"] == username and user["password"] == password:
                found = True
                if {"assistantID": assistantID} not in user["assistants"]: # Check if it is not already assiting
                    user["assistants"].append({"assistantID": assistantID}) # Add the assistant to user assistant List 
                    for assistant in catalog["assistantList"]: # Update also the "global" assistant List, containing all the assistants
                        if int(assistant["userID"]) == assistantID:
                            assistant["assistedPatients"].append({"patientID":int(user["userID"])}) 
                            break
                    self.save(catalog)
                    threadLock.release()
                    return json.dumps({"found":1})
                else: 
                    threadLock.release()
                    return json.dumps({"found":-1}) # -1 means that the assistant is alredy assisting the user

        threadLock.release()
        if found == False:
            return json.dumps({"found":0})

    def getAssistantChatID(self,userID): # Get the assistants chatID, given userID. Used by assistantBot to know who to send notifications to. 
        
        threadLock.acquire()
        catalog=self.read()
        threadLock.release()
        found = False
        for user in catalog["patientList"]:
            if user["userID"] ==  int(userID):
                found = True 
                chatIDs= [] # There can be more than one assistants
                # Now we have to return the chatID of each assistant 
                for assistantObject in user["assistants"]: 
                    assistantID = assistantObject["assistantID"] # Get every assistant following the patient
                    for assistant in catalog["assistantList"]:
                        if int(assistantID) == int(assistant["userID"]):
                            chatIDs.append(assistant["chatID"])
                            break
                return json.dumps({"chatID":chatIDs}) 
                    
        if found == False: # For coherence, we return an empty list if the user was not found
            return json.dumps({"chatID":[]})

    def getAssistedPatients(self, assistantID): # Return a list of assisted patients currently followed by assistant with assistantID. Used by assistantTelegramBot
        
        threadLock.acquire()
        catalog=self.read()
        threadLock.release()
        for assistant in catalog["assistantList"]:
            if assistant["userID"] == int(assistantID):
                patients = [] # An assistant can follow more than one patient 
                for assistedPatientObject in assistant["assistedPatients"]:
                    assistedPatientID = assistedPatientObject["patientID"] # Get every patient that is being followed 
                    for patient in catalog["patientList"]:
                        if int(patient["userID"]) == int(assistedPatientID):
                            patients.append({"username":patient["userName"], "userID":int(patient["userID"])})
                            break
                return json.dumps({"assistedPatients":patients})

    def getAssistants(self, patientID): # Similar to getAssistantChatID, but instead of chatIDs it returns the username and assistnatID of all assistants following patient with patientID

        threadLock.acquire()
        catalog=self.read()
        threadLock.release()
        for patient in catalog["patientList"]:
            if patient["userID"] == int(patientID):
                assistantsToSend = []
                for assistantObject in patient["assistants"]:
                    assistantID = assistantObject["assistantID"]
                    for assistant in catalog["assistantList"]:
                        if int(assistant["userID"]) == int(assistantID):
                            assistantsToSend.append({"username":assistant["userName"], "userID":int(assistant["userID"])})
                            break
                return json.dumps({"assistants":assistantsToSend})

    def dissociatePatient(self,assistantID, patientID): # Stop following a patient. Used by the assistantBot.
        
        threadLock.acquire()
        catalog=self.read()
        for assistant in catalog["assistantList"]:
            if int(assistant["userID"]) == int(assistantID):
                assistant["assistedPatients"].remove({"patientID": int(patientID)}) # Remove the patient for the assistants assistedPatients list
        for patient in catalog["patientList"]:
            if int(patient["userID"]) == int(patientID):
                patient["assistants"].remove({"assistantID": int(assistantID)}) # Remove the assistant for the patients assistants list
        self.save(catalog)
        threadLock.release()
        return json.dumps({"deleted":1})
 
    def changePassword(self, userID, json_data): # Change the password of a patient. Used by TelegramBot
        
        threadLock.acquire()
        catalog = self.read()
        newPassoword = json_data["password"]
        for user in catalog["patientList"]:
            if int(user["userID"]) == int(userID):
                user["password"] = newPassoword
                self.save(catalog)
                threadLock.release()
                return json.dumps({"added":1})
        threadLock.release()

    def getThingSpeakChannel(self, userID, deviceID): # Return ThingSpeak channel. Used by Telegram to know where to find the correct charts
                
        threadLock.acquire()
        catalog = self.read()
        threadLock.release()
        for user in catalog["patientList"]:
            if int(userID) == int(user["userID"]):
                for device in user["devices"]:
                    if deviceID == str(device["deviceID"]):
                        return json.dumps({"channel":device["thingSpeakChannel"]})

    def getConf(self): # Return the configuration of the whole system. Used by every microservice.
        
        threadLock.acquire()
        catalog = self.read()
        threadLock.release()
        return json.dumps({"baseTopic":catalog["baseTopic"], "broker":catalog["broker"], "port": catalog["port"], "token": catalog["token"], "apiKeyWrite": catalog["apiKeyWrite"], "assistant-token": catalog["assistant-token"]})

    def getNumSlots(self, userID, deviceID): # Return the number of slots 

        threadLock.acquire()
        catalog = self.read()
        threadLock.release()
        for user in catalog["patientList"]:
            if int(userID) == int(user["userID"]):
                for device in user["devices"]:
                    if deviceID == str(device["deviceID"]):
                        return json.dumps({"numSlots":device["numSlots"]})

    def getAllThresholds(self): # Return all temperature and humidity thresholds for every device of the system. Used by the conservationControl, that retrieves this info continuously

        threadLock.acquire()
        catalog = self.read()
        threadLock.release()
        result = []

        for user in catalog["patientList"]:
            for device in user["devices"]:
                result.append({"deviceID":device["deviceID"], "tempUpperThresh":device["tempUpperThresh"], "tempLowerThresh":device["tempLowerThresh"], "humUpperThresh":device["humUpperThresh"], "humLowerThresh":device["humLowerThresh"]})

        return {"thresholds": result}

    # Service catalog: every service pings continuously the catalog, to say it is alive, and retrieves the data it needs. Differen services have different answers to the ping message
    def servicePing(self, serviceName):

        threadLock.acquire()
        catalog = self.read()
        # Find if the service exists already
        for element in catalog["aliveServices"]:
            if element["service"] == serviceName: # If it exists, just update it
                element["lastSeen"] = time.time()
                self.save(catalog)
                threadLock.release()
                # Return the required information to every service
                if serviceName == "openingControl":
                    return json.dumps({"times" : catalog["times"]})
                elif serviceName == "conservationControl":
                    return json.dumps(self.getAllThresholds())
                elif serviceName == "pillDifference":
                    return json.dumps({"pillCount" : catalog["pillCount"]})
                else:
                    return json.dumps({})
        
        # If the service is not in the aliveServices list, add it
        catalog["aliveServices"].append({"service": serviceName, "lastSeen": time.time()})
        self.save(catalog)
        threadLock.release()
        # Return the required information to every service
        if serviceName == "openingControl":
            return json.dumps(catalog["times"])
        elif serviceName == "conservationControl":
            return json.dumps(self.getAllThresholds())
        elif serviceName == "pillDifference":
            return json.dumps(catalog["pillCount"])
        else:
            return json.dumps({})

    def addOpeningTime(self, stats): # Add a record to the "times" list, recording an opening time for a device. Used by the openingControl, that is listening to the opening to every device

        threadLock.acquire()
        catalog = self.read()
        catalog["times"].append(stats)
        self.save(catalog)
        threadLock.release()
        return json.dumps({"success":1})

    def deleteOpeningTime(self, patientID, deviceID): # Remove the record of the opening time, since the device was closed. Used by the OpeningControl

        threadLock.acquire()
        catalog = self.read()
        for item in catalog["times"]: 
            if item["patientID/deviceID"]==(patientID+"/"+deviceID): 
                catalog["times"].remove(item)
                break
        self.save(catalog)
        threadLock.release()
        return json.dumps({"success":1})

    def addOpeningPills(self, stats): # Add to the pillCount list a record containing the number of pills in every slot when the device was opened. Used by the PillDifferenceCalculator

        threadLock.acquire()
        catalog = self.read()
        catalog["pillCount"].append(stats)
        self.save(catalog)
        threadLock.release()
        return json.dumps({"success":1})

    def deleteOpeningPills(self, patientID, deviceID): # Return a record of the opening number of pills and delete it from the list. Used by pillDifferenceCalculator, to... well, to calculate the difference of pills.

        threadLock.acquire()
        catalog = self.read()
        for item in catalog["pillCount"]: 
            if item["patientID/deviceID"]==(patientID+"/"+deviceID): 
                print("Deleted", item)
                catalog["pillCount"].remove(item)
                self.save(catalog)
                threadLock.release()
                return json.dumps({"countOpened":item["countOpened"]})
        threadLock.release()
        

class WebServer(): # Create the WebServer class
    exposed=True

    def __init__(self):
        self.catalog = Catalog(filename) # Only propriety is the catalog, in order to access every generated method 

    def GET(self,*uri,**params):
        
        #get the entire catalog
        if uri[0] == "getCatalog":
            return (json.dumps(self.catalog.read(), indent = 10))
        
        elif uri[0] == "getLU":

            return json.dumps({"LU":self.catalog.read()["lastUpdate"]})

        elif uri[0] == "getSchedule":

            userID = uri[1]
            deviceID = uri[2]
            return self.catalog.getSchedule(userID,deviceID)
        
        elif uri[0] == "getSchedules":
            
            return self.catalog.getSchedules()

        elif uri[0] == "getDeviceURI":

            userID = uri[1]
            deviceID = uri[2]
            return self.catalog.getDeviceURI(userID,deviceID)
        

        elif uri[0] == "getTempThresh":

            userID = uri[1]
            deviceID = uri[2]
            return self.catalog.getTempThresh(userID, deviceID)

        elif uri[0] == "getHumThresh":

            userID = uri[1]
            deviceID = uri[2]
            return self.catalog.getHumThresh(userID, deviceID)
        
        elif uri[0] == "getSlotsNumber":
            
            userID = uri[1]
            deviceID = uri[2]
            return self.catalog.getSlotsNumber(userID, deviceID)

        elif uri[0] == "getSlotsName":
            
            userID = uri[1]
            deviceID = uri[2]
            return self.catalog.getSlotsName(userID, deviceID)

        elif uri[0] == "getChatID":

            userID=uri[1]
            return self.catalog.getChatID(userID)

        elif uri[0]== "getDevices":

            userID=uri[1]
            return self.catalog.getDevices(userID)

        elif uri[0]=="getUserID":

            chatID=uri[1]
            return self.catalog.getUserID(chatID)
        
        elif uri[0] == "profileData":

            userID = str(uri[1])
            return self.catalog.getUserProfileData(userID)

        elif uri[0] == "getAssistantID":

            chatID = uri[1]
            return self.catalog.getAssistantID(chatID)

        elif uri[0] == "getAssistantChatID":

            userID=uri[1]
            return self.catalog.getAssistantChatID(userID)

        elif uri[0] == "getAssistedPatients":

            assistantID = uri[1]
            return self.catalog.getAssistedPatients(assistantID)

        elif uri[0] == "getAssistants":

            patientID = uri[1]
            return self.catalog.getAssistants(patientID)

        elif uri[0] == "thingSpeakChannel":

            patientID = uri[1]
            deviceID = uri[2]
            return self.catalog.getThingSpeakChannel(patientID, deviceID)

        elif uri[0] == "conf":
            
            return self.catalog.getConf()

        elif uri[0] == "numSlots":

            patientID = uri[1]
            deviceID = uri[2]
            return self.catalog.getNumSlots(patientID, deviceID)

    def PUT(self,*uri,**params):
         
        if uri[0] == "addUser":
            
            body = json.loads(cherrypy.request.body.read())  # Read body data
            result = self.catalog.addUser(body)
            self.catalog.updateLU()
            return(result)

        elif uri[0] == "addDevice":
            
            body = json.loads(cherrypy.request.body.read())  # Read body data
            userID = uri[1]
            ans = self.catalog.addDevice(body["deviceID"], userID)
            self.catalog.updateLU()
            return ans

        elif uri[0] == "updateTempThresh":
            
            body = json.loads(cherrypy.request.body.read())
            userID = uri[1]
            deviceID = uri[2]
            self.catalog.updateTempThresh(body, userID, deviceID)
            self.catalog.updateLU()
            return json.dumps({"added":1})

        elif uri[0] == "updateHumThresh":
            
            body = json.loads(cherrypy.request.body.read())
            userID = uri[1]
            deviceID = uri[2]
            self.catalog.updateHumThresh(body, userID, deviceID)
            self.catalog.updateLU()
            return json.dumps({"added":1})

        elif uri[0] == "addPill":
            
            body = json.loads(cherrypy.request.body.read())
            userID = uri[1]
            deviceID = uri[2]
            slotNumber = int(uri[3])
            self.catalog.addPill(body, userID, deviceID, slotNumber)
            self.catalog.updateLU()
            return json.dumps({"added":1})

        elif uri[0] == "addSchedule":

            body = json.loads(cherrypy.request.body.read())
            userID = uri[1]
            deviceID = uri[2]
            slotNumber = int(uri[3])
            self.catalog.addSchedule(body, userID, deviceID, slotNumber)
            self.catalog.updateLU()
            return json.dumps({"added":1})

        elif uri[0] == "newDevice":
            
            deviceID = self.catalog.newDevice()
            self.catalog.updateLU()
            return(json.dumps({"deviceID":deviceID}))

        elif uri[0] == "addAssistant":

            body = json.loads(cherrypy.request.body.read())
            return self.catalog.addAssistant(body)
        
        elif uri[0] == "assistUser":

            body = json.loads(cherrypy.request.body.read())
            return self.catalog.assistUser(body)

        elif uri[0] == "changePassword":

            body = json.loads(cherrypy.request.body.read())
            userID = uri[1]
            return self.catalog.changePassword(userID, body)
        
        elif uri[0] == "addChannel":

            body = json.loads(cherrypy.request.body.read())
            userID = uri[1]
            deviceID = uri[2]
            body = body['channel']
            ret = self.catalog.updateChannel(body, userID, deviceID)
            self.catalog.updateLU()
            return ret        
        
        elif uri[0] == "ping":

            service = json.loads(cherrypy.request.body.read())["service"]
            return self.catalog.servicePing(service)

        elif uri[0] == "addOpeningTime":

            body = json.loads(cherrypy.request.body.read())
            return self.catalog.addOpeningTime(body)    
        
        elif uri[0] == "addOpeningPills":

            body = json.loads(cherrypy.request.body.read())
            return self.catalog.addOpeningPills(body)    
        
    
    def DELETE(self,*uri,**params):
        
        if uri[0] == "rmvAlarm":

            userID = uri[1]
            deviceID = uri[2]
            slotNum = int(uri[3])
            alarmNum = int(uri[4])
            self.catalog.deleteAlarm(userID, deviceID, slotNum, alarmNum)
            self.catalog.updateLU()

        elif uri[0] == "rmvDevice":

            userID = uri[1]
            deviceID = uri[2]
            self.catalog.deleteDevice(userID, deviceID)

        elif uri[0] == "dissociatePatient":

            assistantID = uri[1]
            patientID = uri[2]
            self.catalog.dissociatePatient(assistantID, patientID)
        
        elif uri[0] == "rmvOpeningTime":

            patientID = uri[1]
            deviceID = uri[2]
            return self.catalog.deleteOpeningTime(patientID, deviceID)
        
        elif uri[0] == "rmvOpeningPills":

            patientID = uri[1]
            deviceID = uri[2]
            return self.catalog.deleteOpeningPills(patientID, deviceID)

# Thread for the REST interface of the catalog, to run the WebServer
class RESTCatalogThread(threading.Thread):

    def __init__(self):
        threading.Thread.__init__(self)
    
    def run(self):
        conf={
        '/': {
                'request.dispatch':cherrypy.dispatch.MethodDispatcher(),
                'tool.session.on':True
            }
        }
        cherrypy.config.update({'server.socket_port':8080})
        cherrypy.quickstart(WebServer(),'/',conf)
        cherrypy.engine.start()
        cherrypy.engine.block()  

# Thread for the service "cleaner", that removes services that didn't ping for too much time
class ServiceCatalogCheck(threading.Thread):

    def __init__(self):
        threading.Thread.__init__(self)
    
    def run(self):
        while True:
            threadLock.acquire()
            cat = json.load(open(filename))
            for service in cat["aliveServices"]:
                if time.time() - service["lastSeen"] > 60: # If the service wasn't seen for a minute
                    cat["aliveServices"].remove(service)
                    print("\n[", time.ctime(), "] - Service", service["service"], "is not reachable. Removed from active services.\n")
                    json.dump(cat, open(filename, "w"), indent = 6)
            threadLock.release()
            time.sleep(30) # Check every 30 secs


if __name__ == "__main__":
    
    RESTThread = RESTCatalogThread()
    ServiceCatalogThread = ServiceCatalogCheck()
    RESTThread.start()
    ServiceCatalogThread.start()