import telepot 
from telepot.loop import MessageLoop
from telepot.namedtuple import InlineKeyboardMarkup, InlineKeyboardButton
import json
import time
import paho.mqtt.client as PahoMQTT
import requests
import os
import imgkit 

confFile = "conf.json"

def is_number(string):
    try:
        float(string)
        return True
    except ValueError:
        return False

def isTimeFormat(input):
    try:
        time.strptime(input, '%H:%M')
        return True
    except ValueError:
        return False

def representsInt(s):
    try: 
        int(s)
        return True
    except ValueError:
        return False

class TelegramBot:

    def __init__(self, token, clientID, broker, port, baseTopic, catalogURI, chatStatesFilename):

        self.tokenBot=token
        self.bot=telepot.Bot(self.tokenBot)
        self.clientID=clientID
        self.broker=broker
        self.port=port
        self.catalogURI=catalogURI
        self.timeShiftTopic=baseTopic+"/+/+/timeShift"
        self.conservControlTopic=baseTopic+"/+/+/conservationControl"
        self.openingControlTopic=baseTopic+"/+/+/openingControl"
        self.pillDifferenceTopic=baseTopic+"/+/+/pillDifference"
        self._paho_mqtt=PahoMQTT.Client(self.clientID, True)
        self._paho_mqtt.on_connect=self.myOnConnect
        self._paho_mqtt.on_message=self.myOnMessageReceived
        MessageLoop(self.bot, {"chat" : self.on_chat_message, 'callback_query':self.on_callback_query}).run_as_thread()
        self.chatStateFile=chatStatesFilename # It will contain the state in which each chat is in the format {chatID: state}
        # Create the file if it doesn't already exist
        if os.path.isfile(self.chatStateFile):
            pass
        else: 
            json.dump({}, open(self.chatStateFile, "w"))

    def myOnConnect(self, paho_mqtt, userdata, flags, rc):

        print("\n[",time.ctime(),"] - TelegramBot connected to", self.broker, "with result code", rc)
    
    def myOnMessageReceived(self, paho_mqtt, userdata, msg):

        self.notify(msg.topic, msg.payload)

    def subscribe(self, topic):

        self._paho_mqtt.subscribe(topic,2)
        print("\n[",time.ctime(),"] - Subscribed to", topic)

    def start(self):

        self._paho_mqtt.connect(self.broker, self.port)
        self._paho_mqtt.loop_start()
        print("\n[",time.ctime(),"] - Telegram Bot ", self.clientID, "started")
        self.subscribe(self.timeShiftTopic)
        self.subscribe(self.conservControlTopic)
        self.subscribe(self.openingControlTopic)
        self.subscribe(self.pillDifferenceTopic)

    def unsubscribe(self, topic):

        self._paho_mqtt.unsubscribe(topic)

    def stop(self):

        self.unsubscribe(self.conservControlTopic)
        self.unsubscribe(self.timeShiftTopic)
        self.unsubscribe(self.openingControlTopic)
        self.unsubscribe(self.pillDifferenceTopic)
        self._paho_mqtt.loop_stop()
        self._paho_mqtt.disconnect()
        print("\n[",time.ctime(),"] - Telegram Bot ", self.clientID, "stopped")

    def notify(self, topic, msg): # Dealing with MQTT notification from microservices

        payload=json.loads(msg)
        patientID=str(topic.split("/")[1])
        deviceID=str(topic.split("/")[2])
        sender=str(topic.split("/")[3]) # Microservice ClientID
        # Notifications come from MQTT messages from the microservices. These messages have the userID in the topic, therefore in order to send messages we need to find the correspondent chatID
        chatID = requests.get(self.catalogURI+ "getChatID/" + patientID).json()["chatID"] 
        
        if chatID!=None:

            if sender == "openingControl": # Informs of case being opened for too much
        
                self.bot.sendMessage(chatID, text="\t\t\U000026A0 WARNING! \U000026A0\nSmartCase " + str(deviceID) + " is still opened! Close the SmartCase")

            if sender == "pillDifference": # Informs of pills being filled or taken
        
                slotNames = requests.get(self.catalogURI+"getSlotsName/"+str(patientID)+"/"+str(deviceID)).json()["slots"] # Slot names, for better understanding
                difference = payload["e"]["difference"]
                
                for i,diff in enumerate(difference):
                    if diff > 0:
                        self.bot.sendMessage(chatID, text="\U0001F48A Device " + str(deviceID) + " -> " + str(diff) + ' pills added into slot ' + str(i) + ' (pill name: "'+ slotNames[i] +'").') 
                    elif diff < 0:
                        self.bot.sendMessage(chatID, text="\U0001F48A Device " + str(deviceID) + " -> " + str(-diff) + ' pills taken from slot ' + str(i) + ' (pill name: "'+ slotNames[i] + '").')
                
            elif sender == "conservationControl": # Informs that the SmartCase is not in good conservation conditions
                
                if len(payload["e"]) == 2: # Both temp and hum are out of range
                    for crit in payload["e"]:

                        if crit["sensorName"] == "temperature": 
                            critTemp = crit["value"]
                            tempUnit = crit["unit"]

                        if crit["sensorName"] == "humidity":
                            critHum = crit["value"]
                            humUnit = crit["unit"]

                    self.bot.sendMessage(chatID, text="\t\t \U000026A0 WARNING! \U000026A0\nBoth temperature and humidity out of range for device " + str(deviceID) + ". Store the pills in another location!\n\U0001F321 Detected temperature: "+str(critTemp) + " °" + str(tempUnit) + "\n\U0001F4A7 Detected humidity: " + str(critHum) + " " + str(humUnit))

                elif len(payload["e"]) == 1: # Only one critical value
                    
                    crit = payload["e"][0]

                    if payload["e"][0]["sensorName"] == "temperature": 
                        critTemp = crit["value"]
                        tempUnit = crit["unit"]
                        self.bot.sendMessage(chatID, text="\t\t \U000026A0 WARNING! \U000026A0\nTemperature out of range for device " + str(deviceID) + ". Store the pills in another location!\n\U0001F321 Detected temperature: "+str(critTemp) + " °" + str(tempUnit))

                    elif payload["e"][0]["sensorName"] == "humidity":
                        critHum = crit["value"]
                        humUnit = crit["unit"]
                        self.bot.sendMessage(chatID, text="\t\t \U000026A0 WARNING! \U000026A0 \nHumidity out of range for device " + str(deviceID) + ". Store the pills in another location!\n\U0001F4A7 Detected humidity: " + str(critHum) + " " + str(humUnit))

            elif sender == "timeShift": # Informs of an alarm ringing, reminds to take the pill or informs that too much time has passed for taking the scheduled pill

                slot = int(payload["e"]["slot"]) 
                slotNames = requests.get(self.catalogURI+"getSlotsName/"+str(patientID)+"/"+str(deviceID)).json()["slots"]
                
                pillName = slotNames[slot] # Get the pill name for the slot of interest

                if payload["e"]["message"] == 0: # Message 0 is alarm just rung 
                    self.bot.sendMessage(chatID, text="\U000023F0 It's time to take the pill " + pillName + " from slot " + str(slot) + " of device " + str(deviceID))

                elif payload["e"]["message"] == 1: # Message 1 is a reminder that the pill hasn't yet been taken 
                    self.bot.sendMessage(chatID, text="\U000026A0 \U000023F0 You still haven't taken the pill " + pillName + " from slot " + str(slot) + " of device " + str(deviceID) + "!")
                    # Maybe add a callback here to silence the messages (user is not planning to take the pill, so continuous messages will be annoying)

                elif payload["e"]["message"] == 2: # Message 2 is the pill hasn't been taken for an hour, so it will be considered as not taken
                    self.bot.sendMessage(chatID, text="\U000026A0 Pill " + pillName + " from slot " + str(slot) + " of device " + str(deviceID) + " was not taken. No more notifications will be sent.")

    def on_callback_query(self, msg): # Dealing with the callback queries, that are the button presses on Telegram

        query_ID, chat_ID, query_data = telepot.glance(msg, flavor='callback_query')
        chatState=json.load(open(self.chatStateFile)) # The chat state for each chat is stored in a json file
        userID=requests.get(self.catalogURI+"getUserID/"+ str(chat_ID)).json()["userID"] # Opposite from the notifications, when a user presses a button we only know his chatID. Therefore we need to find the userID to know who we to address. 

        # Options for the converter of html to jpg
        options = {
                'javascript-delay' : 900,
                'zoom': 2.3
            }

        if str(query_data).startswith("device."): # The user has just clicked on one of his devices 
            
            deviceID=query_data.split(".")[-1]
            buttons=[]
            buttons.append([InlineKeyboardButton(text="Edit conservation thresholds", callback_data="conservThresh.device."+str(deviceID))])
            buttons.append([InlineKeyboardButton(text="Edit alarms", callback_data="editAlarms.device."+str(deviceID))])
            buttons.append([InlineKeyboardButton(text="Show pill count", callback_data="pillCount.device."+str(deviceID))])
            buttons.append([InlineKeyboardButton(text="Associate pill type to slot", callback_data="addPill.device."+str(deviceID))])
            buttons.append([InlineKeyboardButton(text="Device and user statistics", callback_data="stats.device."+str(userID)+"."+str(deviceID))])
            buttons.append([InlineKeyboardButton(text="Ring device", callback_data="ring.device."+str(deviceID))])
            buttons.append([InlineKeyboardButton(text="Remove device", callback_data="rmvDevice.device."+str(deviceID))])
            keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
            self.bot.sendMessage(chat_ID, text = "What do you want to do with device " + str(deviceID) + "?", reply_markup=keyboard)
        
        elif str(query_data).startswith("conservThresh."): # User just clicked on edit conservation thresholds
            
            deviceID=query_data.split(".")[-1]
            # Get the threshold in order to show them to the user 
            tempThresholds = requests.get(self.catalogURI+"getTempThresh/"+str(userID)+"/"+str(deviceID)).json()
            humThresholds = requests.get(self.catalogURI+"getHumThresh/"+str(userID)+"/"+str(deviceID)).json() 
            tempUp = tempThresholds["tempUpperThresh"]
            tempDown = tempThresholds["tempLowerThresh"]
            humUp = humThresholds["humUpperThresh"]
            humDown = humThresholds["humLowerThresh"]
            buttons=[]
            buttons.append([InlineKeyboardButton(text="Edit temperature thresholds", callback_data="editTempThresh.device."+str(deviceID))])
            buttons.append([InlineKeyboardButton(text="Edit humidity thresholds", callback_data="editHumThresh.device."+str(deviceID))])
            keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
            self.bot.sendMessage(chat_ID, "Current conservation thresholds are set to:\n\U0001F321 Temperature: ["+str(tempDown)+", "+str(tempUp)+"] °C\n\U0001F4A7 Humidity: ["+str(humDown)+", "+str(humUp)+"] %\nSelect an action:", reply_markup=keyboard)

        elif str(query_data).startswith("editTempThresh."): # User just clicked on edit temperature thresholds
            
            deviceID=query_data.split(".")[-1]
            self.bot.sendMessage(chat_ID, text='Insert the new temperature thresholds, with a space between the lower and upper threshold.\n(Example: "10.3 30")')
            chatState[str(chat_ID)]="modifyTempThresh.device."+str(deviceID)
            json.dump(chatState, open(self.chatStateFile, "w")) # Save the state! So that the bot knows that the next message from this user is a reply to "insert new temp thresholds"

        elif str(query_data).startswith("editHumThresh."): # User just clicked on edit humidity thresholds
            
            deviceID=query_data.split(".")[-1]
            self.bot.sendMessage(chat_ID, text='Insert the new humidity thresholds, with a space between the lower and upper threshold.\n(Example: "10.3 30")')
            chatState[str(chat_ID)]="modifyHumThresh.device."+str(deviceID)
            json.dump(chatState, open(self.chatStateFile, "w"))

        elif str(query_data).startswith("editAlarms."): # User just clicked on edit alarm 
            
            deviceID=query_data.split(".")[-1]
            slotsSchedule = requests.get(self.catalogURI+"getSchedule/"+str(userID)+"/"+str(deviceID)).json()["slots"] # Get schedules to show them
            slotNames = requests.get(self.catalogURI+"getSlotsName/"+str(userID)+"/"+str(deviceID)).json()["slots"] # Get slot names for better understanding
            toPrint = 'Current schedule is:'
            
            for i,item in enumerate(slotsSchedule):
                toPrint += '\n\n\t- Slot '+ str(i) + ' ("'+slotNames[i]+'"):'
                for j,alarm in enumerate(item): 
                    toPrint += "\n\t\t#"+str(j)+" -> "+alarm["time"] + " - Number of pills: " + str(alarm["numPill"])

            toPrint += '\n\nChoose an action to perform:'
            
            buttons=[]
            buttons.append([InlineKeyboardButton(text="Add new alarm", callback_data="addAlarm.device."+str(deviceID))])
            buttons.append([InlineKeyboardButton(text="Remove alarm", callback_data="rmvAlarm.device."+str(deviceID))])
            keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)

            self.bot.sendMessage(chat_ID, text=toPrint, reply_markup=keyboard)            

        elif str(query_data).startswith("addAlarm."): # User clicked on adding a new alarm
            deviceID=query_data.split(".")[-1]
            self.bot.sendMessage(chat_ID, text='Insert the time of the alarm, which slot it is intended for and the number of pills to take at that time using the following format:\n"hh:mm slot #pills"\nExample: "15:00 1 2"')
            chatState[str(chat_ID)]="addAlarm.device."+str(deviceID)
            json.dump(chatState, open(self.chatStateFile, "w")) # Save state! So that the bot knows the next message from this user is a reply to "insert new alarm"

        elif str(query_data).startswith("rmvAlarm."): # User clicked on removing an alarm
            deviceID=query_data.split(".")[-1]
            self.bot.sendMessage(chat_ID, text='Select the alarm to remove using the following format:\n"slot #alarm"\nExample: "1 2"')
            chatState[str(chat_ID)]="rmvAlarm.device."+str(deviceID)
            json.dump(chatState, open(self.chatStateFile, "w"))

        elif str(query_data).startswith("pillCount."): # User clicked on the pill count in every slot button
            deviceID=query_data.split(".")[-1]
            deviceURI=requests.get(self.catalogURI+"getDeviceURI/"+str(userID)+"/"+str(deviceID)).json()["deviceURI"] # Request the deviceURI, because we need to address it directly 
            if deviceURI != None: # Error check
                count=requests.get(deviceURI+"/counters").json()["e"]["number"] # Ask directly to the device the number of pills
                slotNames = requests.get(self.catalogURI+"getSlotsName/"+str(userID)+"/"+str(deviceID)).json()["slots"]
                text = ""
                for i,num in enumerate(count):
                    text += '\n\n\U000025AB Slot ' + str(i) + ' ("' + str(slotNames[i])+ '") - Pill count: '+str(num)

                self.bot.sendMessage(chat_ID, text='The pills inside the SmartCase are:' + text)

        elif str(query_data).startswith("addPill."): # User clicked on the associate pill type to slot button 
            deviceID=query_data.split(".")[-1]
            self.bot.sendMessage(chat_ID, text='Insert the slot and the pill name you want associate it to, using the following format:\n"slot pillName"\nExample: "1 Robilas"\n(If a slot is already associated to a pill type, this action will overwrite the associated pill type)')
            chatState[str(chat_ID)]="addPill.device."+str(deviceID)
            json.dump(chatState, open(self.chatStateFile, "w"))

        elif str(query_data).startswith("ring."): # User clicked on the ring device button 
            deviceID=query_data.split(".")[-1]
            deviceURI=requests.get(self.catalogURI+"getDeviceURI/"+str(userID)+"/"+str(deviceID)).json()["deviceURI"] # We need to address the device directly
            if deviceURI != None: # Error check
                requests.put(deviceURI+"/alarm", json.dumps({"on":1})) # Start the alarm 
                buttons=[]
                buttons.append([InlineKeyboardButton(text= "Stop ringing", callback_data="stopRing.device."+str(deviceID))])
                keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
                self.bot.sendMessage(chat_ID, text='\U000023F0 Alarm is ringing ...', reply_markup=keyboard)
            else:
                self.bot.sendMessage(chat_ID, text='Error in finding the device')
        
        elif str(query_data).startswith("stopRing."): # User clicked on the stop alarm 
            deviceID=query_data.split(".")[-1]
            deviceURI=requests.get(self.catalogURI+"getDeviceURI/"+str(userID)+"/"+str(deviceID)).json()["deviceURI"]
            if deviceURI != None:
                requests.put(deviceURI+"/alarm", json.dumps({"on":0}))
                self.bot.sendMessage(chat_ID, text='Alarm was stopped')
            else:
                self.bot.sendMessage(chat_ID, text='Error in finding the device')

        elif str(query_data).startswith("rmvDevice."): # Ask for confirmation to remove the device from your account 
            deviceID=query_data.split(".")[-1]
            self.bot.sendMessage(chat_ID, text='Are you sure you want to delete the device? All the information, including alarms, will be deleted.\nType "yes" to continue, type anything else to cancel the action:')
            chatState[str(chat_ID)]="rmvDevice.device."+str(deviceID)
            json.dump(chatState, open(self.chatStateFile, "w"))

        elif str(query_data).startswith("rmvAssistant."): # Ask for confirmation for stop being assisted by an assistant
            assistantID = query_data.split(".")[1].split("£")[0] # Previous choice 
            assistantUsername = query_data.split(".")[1].split("£")[1]
            self.bot.sendMessage(chat_ID, text='Are you sure you want to dissociate assistant '+str(assistantUsername) +' from your account? He will not be able to monitor your SmartCase anymore.\nType "yes" to continue, type anything else to cancel the action:')
            chatState[str(chat_ID)]="rmvAssistant."+str(assistantID)+"£"+str(assistantUsername)
            json.dump(chatState, open(self.chatStateFile, "w"))

        elif str(query_data).startswith("changePassword."): # User clicked on the change password button 
            patientID = query_data.split(".")[-1]
            self.bot.sendMessage(chat_ID, text='Insert the new password: ')
            chatState[str(chat_ID)]="changePassword."+str(patientID)
            json.dump(chatState, open(self.chatStateFile, "w"))

        elif str(query_data).startswith("stats."): # User clicked on the user statistics button

            patientID = query_data.split(".")[-2]
            deviceID = query_data.split(".")[-1]

            # Get the slot number, so to know how many buttons to show. However, since ThingSpeak has a maximum of 8 charts per channel, a maximum of 6 slots can be visualized 
            slotNumber = int(requests.get(catalogURI + "getSlotsNumber/" + patientID + "/" + deviceID).json()["slots"])

            buttons=[]
            buttons.append([InlineKeyboardButton(text= "Temperature", callback_data="temperatureThings."+str(patientID)+"."+str(deviceID))])
            buttons.append([InlineKeyboardButton(text= "Humidity", callback_data="humidityThings."+str(patientID)+"."+str(deviceID))])
            for i in range(slotNumber):
                buttons.append([InlineKeyboardButton(text= ("Pills taken slot " + str(i)), callback_data="slotThings." + str(i) + "."+str(patientID)+"."+str(deviceID))])
                if i >= 5: # maximum of 6 slots! 
                    break
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
            self.bot.sendMessage(chat_ID, text='Which statistics do you want to see?', reply_markup=keyboard)

        elif str(query_data).startswith("temperatureThings."): # User requested the temperature chart

            patientID = query_data.split(".")[-2]
            deviceID = query_data.split(".")[-1]
            channel = requests.get(self.catalogURI+"thingSpeakChannel/"+str(patientID)+"/"+str(deviceID)).json()["channel"] # Request the channel to the catalog
            if channel == None:
                self.bot.sendMessage(chat_ID, text="Oooops! It seems like this device doesn't have a ThingSpeak channel associated to it")
            else:
                channel = channel.split('/')[0]
                # Get the image and save it in the correct folder
                imgkit.from_url("https://thingspeak.com/channels/"+str(channel)+"/charts/1?bgcolor=%23ffffff&color=%23ff5631&dynamic=false&type=spline&days=1", 'ThingspeakImages/'+str(patientID)+'_'+str(deviceID) +'_temperature.jpg', options = options)
                # Send the saved picture 
                self.bot.sendPhoto(chat_ID, photo=open('ThingspeakImages/'+str(patientID)+'_'+str(deviceID) +'_temperature.jpg', 'rb'))

        elif str(query_data).startswith("humidityThings."): # User requested the humidity chart

            patientID = query_data.split(".")[-2]
            deviceID = query_data.split(".")[-1]
            channel = requests.get(self.catalogURI+"thingSpeakChannel/"+str(patientID)+"/"+str(deviceID)).json()["channel"]
            if channel == None:
                self.bot.sendMessage(chat_ID, text="Oooops! It seems like this device doesn't have a ThingSpeak channel associated to it")
            else:
                channel = channel.split('/')[0]
                imgkit.from_url("https://thingspeak.com/channels/"+str(channel)+"/charts/2?bgcolor=%23ffffff&color=%237fc5e1&dynamic=false&type=spline&days=1", 'ThingspeakImages/'+str(patientID)+'_'+str(deviceID) +'_humidity.jpg', options = options)
                self.bot.sendPhoto(chat_ID, photo=open('ThingspeakImages/'+str(patientID)+'_'+str(deviceID) +'_humidity.jpg', 'rb'))

        elif str(query_data).startswith("slotThings."): # User requested the number of pills taken every day chart

            slotNumber = int(query_data.split(".")[-3])
            patientID = query_data.split(".")[-2]
            deviceID = query_data.split(".")[-1]
            channel = requests.get(self.catalogURI+"thingSpeakChannel/"+str(patientID)+"/"+str(deviceID)).json()["channel"]
            if channel == None:
                self.bot.sendMessage(chat_ID, text="Oooops! It seems like this device doesn't have a ThingSpeak channel associated to it")
            else:
                channel = channel.split('/')[0]
                # Uncomment for the pills taken in the last week
                #imgkit.from_url("https://thingspeak.com/channels/" + str(channel) + "/charts/3?bgcolor=%23ffffff&color=%23d62020&dynamic=false&results=60&type=column&days=7", str(patientID)+'.jpg', options=options)
                imgkit.from_url("https://thingspeak.com/channels/" + str(channel) + "/charts/" + str(slotNumber + 3) + "?bgcolor=%23ffffff&color=%23d62020&dynamic=false&type=column&days=31", 'ThingspeakImages/'+str(patientID)+'_'+str(deviceID) +'_slot' + str(slotNumber) + '.jpg', options=options)
            
            self.bot.sendPhoto(chat_ID, photo=open('ThingspeakImages/'+str(patientID)+'_'+str(deviceID) +'_slot' + str(slotNumber) + '.jpg', 'rb'))

    def on_chat_message(self, msg): # Dealing with chat messages, that are either the "/" commands or replies to previous questions
        
        content_type, chat_type, chat_ID = telepot.glance(msg)

        message=msg["text"]

        chatState=json.load(open(self.chatStateFile)) # Important to know if the message is an answer or a "fresh" conversation
        userID=requests.get(self.catalogURI+"getUserID/"+ str(chat_ID)).json()["userID"] # Get the userID given the chatID 
        print('Message "' + str(message)+'" received from chat', chat_ID, ". User:",userID)

        if message == "/start": # Start off command
            
            if str(chat_ID) in chatState.keys(): # User is already registered 
                self.bot.sendMessage(chat_ID, text='Welcome to the ApPills Bot. Check what you can do with your devices by typing "/"') 
            else: # First time seeing the user. Associate chatID with the patient in the catalog
                self.bot.sendMessage(chat_ID, text='\U0001F44B Welcome to the ApPills bot.\nIt is the first time seeing you here! \U0001F604\nPlease insert a the usage type ("P" for Personal or "H" for Hospital) username and a password, separated by a space.\nExample: "P Luca 123456"\nBE CAREFUL: The username you are going to type CANNOT be changed, so choose an adequate username')
                chatState[str(chat_ID)]="username" # Next message from this user will be the reply to "usage, username, password" 
                json.dump(chatState, open(self.chatStateFile, "w"))

        elif chatState[str(chat_ID)] == None: # Home state: the new message will be the beginning of the "conversation". All the "/" commands have to be done here

            if message == "/registernewdevice": # User wants to register a new device
                self.bot.sendMessage(chat_ID, text="Insert the ID of the device you want to register: ")
                chatState[str(chat_ID)]="reg1"
                json.dump(chatState, open(self.chatStateFile, "w"))

            elif message == "/managedevices": # User wants to get the list of devices he owns 
                devices=requests.get(self.catalogURI+"getDevices/"+str(userID)).json()["devices"] # Get list of devices
                if devices == None: 
                    self.bot.sendMessage(chat_ID, text="No devices found!\nPlease register your device using the apposite command")
                else:
                    buttons=[]
                    for device in devices:
                        buttons.append([InlineKeyboardButton(text="device"+str(device), callback_data="device."+str(device))])
                    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
                    self.bot.sendMessage(chat_ID, text="Which device do you want to manage?", reply_markup=keyboard)
                
            elif message == "/profile": # User wants to check his profile data
                userData = requests.get(self.catalogURI+"profileData/"+str(userID)).json() # Get it from the catalog
                buttons=[]
                buttons.append([InlineKeyboardButton(text="Change password", callback_data="changePassword."+str(userID))])
                keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
                self.bot.sendMessage(chat_ID, text="This is your profile data. Share it only with you assistant!\n\nusername:\t" + str(userData["username"]) + "\npassword:\t" + str(userData["password"]), reply_markup=keyboard)

            elif message =="/assistants": # User wants to see the list of assistants followint him
                assistants = requests.get(self.catalogURI+"getAssistants/"+str(userID)).json()["assistants"] # List of assistant names
                toSend = "" # We need to format the text nicely 
                buttons=[]
                for assistant in assistants:
                    toSend += "\U000025AB "+ str(assistant["username"]) + "\n"
                    buttons.append([InlineKeyboardButton(text=str(assistant["username"]), callback_data="rmvAssistant."+str(assistant["userID"])+"£"+str(assistant["username"]))])
                keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
                if len(assistants) == 0:
                    self.bot.sendMessage(chat_ID, text='No assistant is associated to your account!\nAn assistant can start monitoring your SmartCase by using the "ApPillsAssistantBot"')
                else:    
                    self.bot.sendMessage(chat_ID, text="These are the current assistants associated to your account:\n"+toSend +"Do you want to remove an assistant?", reply_markup=keyboard)
            
            else: # Unknown command
                self.bot.sendMessage(chat_ID, text='"' + str(message) + '" is not an available command')

        elif chatState[str(chat_ID)] == "username": # Answer to the "/start" reply from the bot
            data = message.split(" ")
            if len(data) == 3 and (data[0].lower() == "h" or data[0].lower() == "p"): # Check if the input was formatted correctly
                # Check if the username exists
                check = requests.put(self.catalogURI + "addUser", json.dumps({"chatID":chat_ID, "userName":data[1], "password": data[2], "usage" : data[0].lower()})).json()["usernameExists"]
                if int(check) == 0: # Username doesn't exist
                    chatState[str(chat_ID)]=None
                    json.dump(chatState, open(self.chatStateFile, "w"))
                    self.bot.sendMessage(chat_ID, text='Your username was set correctly!\nCheck what you can do with your devices by typing "/"')
                else: # Username exists already 
                    self.bot.sendMessage(chat_ID, text='Username already exists!\nPlease chose another username:')
            else: 
                self.bot.sendMessage(chat_ID, text='Usage, username and password entered incorrectly!\nInsert again the intended usage ("P" or "H"), username and password separated by a space.\nExample: "P Luca 123456"')

        elif chatState[str(chat_ID)] == "reg1": # Answer to the "/registernewdevice" reply
            try: # Check that the input is an integer 
                message = int(message)
                found = requests.put(self.catalogURI+"addDevice/"+str(userID), data=json.dumps({"deviceID":message})).json()["found"]
            except ValueError:
                found = 0
            if found == 0: # Either not a new device or wrong input of deviceID from user
                txt = "Device with ID " + str(message) + " is not available. Please check again the ID of your device."
                self.bot.sendMessage(chat_ID, text=txt)
            else: # Everything went well
                self.bot.sendMessage(chat_ID, text="Device was added!")
            chatState[str(chat_ID)]=None # Reset to idle
            json.dump(chatState, open(self.chatStateFile, "w"))

        elif chatState[str(chat_ID)].startswith("modifyTempThresh"): # Answer to the button for modifying the temperature thresholds 
            deviceID=chatState[str(chat_ID)].split(".")[-1]
            newThresh = message.split(" ")
            if len(newThresh)!=2 or not is_number(newThresh[0]) or not is_number(newThresh[1]): # Check format of answer
                self.bot.sendMessage(chat_ID, text='Incorrect format! The format is the following:\n"lower_threshold upper_threshold"\nInsert again the new temperature thresholds:')
            else:
                tempDown = newThresh[0]
                tempUp = newThresh[1]
                requests.put(self.catalogURI + "updateTempThresh/"+str(userID)+"/"+str(deviceID), json.dumps({"upperThresh": tempUp, "lowerThresh": tempDown})) # Update new thresholds on the catalog 
                self.bot.sendMessage(chat_ID, text="Temperature threshold updated!")
                chatState[str(chat_ID)]=None
                json.dump(chatState, open(self.chatStateFile, "w"))

        elif chatState[str(chat_ID)].startswith("modifyHumThresh"): # Answer to the button for modifying the humidity thresholds
            deviceID=chatState[str(chat_ID)].split(".")[-1]
            newThresh = message.split(" ")
            if len(newThresh)!=2 or not is_number(newThresh[0]) or not is_number(newThresh[1]): # Check format of answer
                self.bot.sendMessage(chat_ID, text='Incorrect format! The format is the following:\n"lower_threshold upper_threshold"\nInsert again the new humidity thresholds:')
            else:
                humDown = newThresh[0]
                humUp = newThresh[1]
                requests.put(self.catalogURI + "updateHumThresh/"+str(userID)+"/"+str(deviceID), json.dumps({"upperThresh": humUp, "lowerThresh": humDown})) 
                self.bot.sendMessage(chat_ID, text="Humidity threshold updated!")
                chatState[str(chat_ID)]=None
                json.dump(chatState, open(self.chatStateFile, "w"))

        elif chatState[str(chat_ID)].startswith("addAlarm"): # Answer to the add new alarm button 
            deviceID=chatState[str(chat_ID)].split(".")[-1]
            data = message.split(" ")
            numSlots = int(requests.get(self.catalogURI + "numSlots/"+str(userID)+"/"+str(deviceID)).json()["numSlots"]) # In order to check that the input slot is feasible
            # Check format and feasibility of the answer 
            if len(data)!= 3:
                self.bot.sendMessage(chat_ID, text='Incorrect format!\nThe correct format is the following:\n"hh:mm slot #pills"\nTry again:')
            elif not isTimeFormat(data[0]):
                self.bot.sendMessage(chat_ID, text='Incorrect time format!\nThe correct format is "hh:mm"\nTry again:')
            elif not representsInt(data[1]):
                self.bot.sendMessage(chat_ID, text='Incorrect format!\nThe correct format is the following:\n"hh:mm slot #pills"\nTry again:')
            elif int(data[1])<0 or int(data[1])>numSlots-1:
                self.bot.sendMessage(chat_ID, text="Incorrect slot number!\nSlot numbers go from 0 to " + str(numSlots - 1) + "\nTry again:")
            elif not representsInt(data[2]):
                self.bot.sendMessage(chat_ID, text="Incorrect number of pills!\nTry again:")
            elif int(data[2])<0:
                self.bot.sendMessage(chat_ID, text="Incorrect number of pills!\nTry again:")
            else: # Correct format
                # Update the catalog
                slot = data[1]
                requests.put(self.catalogURI + "addSchedule/"+str(userID)+"/"+str(deviceID)+"/"+slot, json.dumps({"numPill": data[2], "time": data[0]})) 
                self.bot.sendMessage(chat_ID, text="Added an alarm at "+data[0]+ " for slot "+ data[1]+"!")
                chatState[str(chat_ID)]=None # Reset state
                json.dump(chatState, open(self.chatStateFile, "w"))

        elif chatState[str(chat_ID)].startswith("rmvAlarm"): # Answer to the remove alarm button 
            deviceID=chatState[str(chat_ID)].split(".")[-1]
            data = message.split(" ")
            numSlots = int(requests.get(self.catalogURI + "numSlots/"+str(userID)+"/"+str(deviceID)).json()["numSlots"]) # To check for feasibility
            if len(data)!=2:
                self.bot.sendMessage(chat_ID, text='Incorrect format!\nThe correct format is the following:\n"slot #alarm"\nTry again:')
            elif not representsInt(data[0]):
                self.bot.sendMessage(chat_ID, text='Incorrect format!\nThe correct format is the following:\n"slot #alarm"\nTry again:')
            elif int(data[0])<0 or int(data[0])>numSlots-1:
                self.bot.sendMessage(chat_ID, text="Incorrect slot number!\nSlot numbers go from 0 to " + str(numSlots - 1) + "\nTry again:")
            elif not representsInt(data[1]):
                self.bot.sendMessage(chat_ID, text='Incorrect format!\nThe correct format is the following:\n"slot #alarm"\nTry again:')
            elif int(data[1])<0:
                self.bot.sendMessage(chat_ID, text='Incorrect format!\nThe correct format is the following:\n"slot #alarm"\nTry again:')
            else: # Correct format
                slotSchedule = requests.get(self.catalogURI+"getSchedule/"+str(userID)+"/"+str(deviceID)).json()["slots"][int(data[0])] # In order to check that the alarm actually exists
                if int(data[1])>len(slotSchedule): # Check that the alarm exists
                    self.bot.sendMessage(chat_ID, text='Device'+str(deviceID)+' does not have alarm '+ str(data[1])+' for slot ' + str(data[0]))
                    chatState[str(chat_ID)]=None
                    json.dump(chatState, open(self.chatStateFile, "w"))
                else: # Alarm exists
                    requests.delete(self.catalogURI + "rmvAlarm/"+str(userID)+"/"+str(deviceID)+"/"+str(data[0])+"/"+str(data[1])) 
                    self.bot.sendMessage(chat_ID, text="Removed alarm "+ data[1] + " from slot "+ data[0] +"!")
                    chatState[str(chat_ID)]=None
                    json.dump(chatState, open(self.chatStateFile, "w"))

        elif chatState[str(chat_ID)].startswith("addPill"): # Answer to associate pill type to slot button 
            deviceID=chatState[str(chat_ID)].split(".")[-1]
            data = message.split(" ")
            numSlots = int(requests.get(self.catalogURI + "numSlots/"+str(userID)+"/"+str(deviceID)).json()["numSlots"]) # To check feasibility
            # Check the format of the input
            if len(data)!=2:
                self.bot.sendMessage(chat_ID, text='Incorrect format!\nThe correct format is the following:\n"slot pillName"\nTry again:')
            elif not representsInt(data[0]):
                self.bot.sendMessage(chat_ID, text='Incorrect format!\nThe correct format is the following:\n"slot pillName"\nTry again:')
            elif int(data[0])<0 or int(data[0])>numSlots-1:
                self.bot.sendMessage(chat_ID, text="Incorrect slot number!\nSlot numbers go from 0 to " + str(numSlots - 1) + "\nTry again:")
            else: # Correct format
                requests.put(self.catalogURI + "addPill/"+str(userID)+"/"+str(deviceID)+"/"+str(data[0]), json.dumps({"pillName": data[1]})) 
                self.bot.sendMessage(chat_ID, text="Associated pill "+ data[1] + " to slot " + data[0] + "!")
                chatState[str(chat_ID)]=None
                json.dump(chatState, open(self.chatStateFile, "w"))

        elif chatState[str(chat_ID)].startswith("rmvDevice"): # Answer to the confirmation for removing the device  
            deviceID=chatState[str(chat_ID)].split(".")[-1]
            data = message.lower() # Unambiguous if all letters are lowercase
            if data == "yes": # Confirm
                requests.delete(self.catalogURI + "rmvDevice/"+str(userID)+"/"+str(deviceID)) 
                self.bot.sendMessage(chat_ID, text="Device "+ str(deviceID) + " was successfully deleted.")
                chatState[str(chat_ID)]=None
                json.dump(chatState, open(self.chatStateFile, "w"))
            else: 
                self.bot.sendMessage(chat_ID, text="Operation canceled. The device was not deleted")
                chatState[str(chat_ID)]=None
                json.dump(chatState, open(self.chatStateFile, "w"))
        
        elif chatState[str(chat_ID)].startswith("rmvAssistant"): # Answer to the confirmation for removing an assistant 
            assistantID = chatState[str(chat_ID)].split(".")[1].split("£")[0] # Information from the previous state of the conversation, needed to send the request to the catalog in case of confirmation 
            assistantUsername = chatState[str(chat_ID)].split(".")[1].split("£")[1]
            data = message.lower() # Unambiguous
            if data == "yes": # Confirmation 
                requests.delete(self.catalogURI + "dissociatePatient/"+str(assistantID)+"/"+str(userID)) 
                self.bot.sendMessage(chat_ID, text="Assistant "+ str(assistantUsername) + " was successfully dissociated from your account.")
                chatState[str(chat_ID)]=None
                json.dump(chatState, open(self.chatStateFile, "w"))
            else:
                self.bot.sendMessage(chat_ID, text="Operation canceled. The assistant was not dissociated")
                chatState[str(chat_ID)]=None
                json.dump(chatState, open(self.chatStateFile, "w"))

        elif chatState[str(chat_ID)].startswith("changePassword"): # Answer to the change password button 
            if len(message.split(" ")) != 1: # The password should be only one word
                self.bot.sendMessage(chat_ID, text="Incorrect password format! Password should be a single word.\nInsert again the new password:")
            else:
                patientID = chatState[str(chat_ID)].split(".")[-1]
                password = message
                requests.put(self.catalogURI+"changePassword/"+str(patientID), data=json.dumps({"password":password}))
                self.bot.sendMessage(chat_ID, text="Password was changed successfully")
                chatState[str(chat_ID)]=None
                json.dump(chatState, open(self.chatStateFile, "w"))




if __name__=="__main__":

    catalogURI=json.load(open(confFile))["catalogURI"]
    conf = requests.get(catalogURI+"conf").json() # Get system configuration from the catalog
    token=conf["token"] # Get bot token
    bot=TelegramBot(token, "SmartCase-telegramBot", conf["broker"], conf["port"], conf["baseTopic"], catalogURI, "chatStates.json")
    bot.start()
    lastPing = 0
    while True:
        time.sleep(0.1) # Need high reactivity for messages
        if time.time() - lastPing > 5: # But lower frequency for pings (5 seconds)
            requests.put(catalogURI+"ping", data=json.dumps({"service": "telegramBot"}))
            lastPing = time.time()
