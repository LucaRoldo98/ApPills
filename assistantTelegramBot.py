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
        self._paho_mqtt=PahoMQTT.Client(self.clientID, True)
        self._paho_mqtt.on_connect=self.myOnConnect
        self._paho_mqtt.on_message=self.myOnMessageReceived
        MessageLoop(self.bot, {"chat" : self.on_chat_message, 'callback_query':self.on_callback_query}).run_as_thread()
        self.chatStateFile=chatStatesFilename # It will contain the state in which each chat is in the format {chatID: state}
        # Create a new file if it doesn't exist yet
        if os.path.isfile(self.chatStateFile):
            pass
        else: 
            json.dump({}, open(self.chatStateFile, "w"))

    def myOnConnect(self, paho_mqtt, userdata, flags, rc):

        print("\n[",time.ctime(),"] - Assistant Telegram Bot connected to", self.broker, "with result code", rc)
    
    def myOnMessageReceived(self, paho_mqtt, userdata, msg):

        self.notify(msg.topic, msg.payload)

    def subscribe(self, topic):

        self._paho_mqtt.subscribe(topic,2)
        print("\n[",time.ctime(),"] - Subscribed to", topic)

    def start(self):

        self._paho_mqtt.connect(self.broker, self.port)
        self._paho_mqtt.loop_start()
        print("\n[",time.ctime(),"] - Assistant Telegram Bot ", self.clientID, "started")
        self.subscribe(self.timeShiftTopic)

    def unsubscribe(self, topic):

        self._paho_mqtt.unsubscribe(topic)

    def stop(self):

        self.unsubscribe(self.timeShiftTopic)
        self._paho_mqtt.loop_stop()
        self._paho_mqtt.disconnect()
        print("\n[",time.ctime(),"] - Assistant Telegram Bot ", self.clientID, "stopped")

    def notify(self, topic, msg):

        payload=json.loads(msg)
        patientID=str(topic.split("/")[1])
        deviceID=str(topic.split("/")[2])
        sender=str(topic.split("/")[3])
        chatIDs = requests.get(self.catalogURI+ "getAssistantChatID/" + patientID).json()["chatID"] # Request the chatIDs of the assistants that are following the patient with the notification 
        
        if chatIDs != []: # Notify only if there are assistants connected to the patient account

            # We only notify when a pill is not taken 
            if sender == "timeShift":

                slot = int(payload["e"]["slot"]) 
                slotNames = requests.get(self.catalogURI+"getSlotsName/"+str(patientID)+"/"+str(deviceID)).json()["slots"]

                pillName = slotNames[slot]
                
                if payload["e"]["message"] == 2: # Notify only if the pill wasn't taken 
                    for chatID in chatIDs: 
                        self.bot.sendMessage(chatID, text="\U000026A0 Pill '" + pillName + "' from slot " + str(slot) + " of device " + str(deviceID) + " was not taken. No more notifications will be sent.")

    def on_callback_query(self, msg):

        query_ID, chat_ID, query_data = telepot.glance(msg, flavor='callback_query')
        chatState=json.load(open(self.chatStateFile))
        #userID=requests.get(self.catalogURI+"getUserID/"+ str(chat_ID)).json()["userID"]

        # Options for the converter of html to jpg
        options = {
                'javascript-delay' : 900,
                'zoom': 2.3
            }

        if str(query_data).startswith("patient."): # Show the commands for the patient

            patientID=query_data.split(".")[1].split("£")[0]
            patientUsername=query_data.split(".")[1].split("£")[1]
            buttons=[]
            buttons.append([InlineKeyboardButton(text="Device and user statistics", callback_data="things."+str(patientID)+"£"+str(patientUsername))])
            buttons.append([InlineKeyboardButton(text="Show pill count", callback_data="pillCount."+str(patientID)+"£"+str(patientUsername))]) # Mostriamo per ogni device il pill count
            #buttons.append([InlineKeyboardButton(text="Ring device", callback_data="ring.device."+str(deviceID))])
            buttons.append([InlineKeyboardButton(text="Dissociate patient", callback_data="rmvPatient."+str(patientID)+"£"+str(patientUsername))])
            keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
            self.bot.sendMessage(chat_ID, text = "What do you want to do with device " + str(patientUsername) + "?", reply_markup=keyboard)
        
    
        elif str(query_data).startswith("pillCount."): # Show pill count for every device of the selected patient

            patientID = query_data.split(".")[1].split("£")[0]
            devices = requests.get(self.catalogURI+"getDevices/"+str(patientID)).json()["devices"] # Get all the devices of the patient
            text = ""
            for deviceID in devices: 
                deviceURI=requests.get(self.catalogURI+"getDeviceURI/"+str(patientID)+"/"+str(deviceID)).json()["deviceURI"] # Request the pills to the device 
                if deviceURI != None:
                    text += "Device " + str(deviceID) + ":"
                    count=requests.get(deviceURI+"/counters").json()["e"]["number"]
                    slotNames = requests.get(self.catalogURI+"getSlotsName/"+str(patientID)+"/"+str(deviceID)).json()["slots"]
                    for i,num in enumerate(count):
                        text += '\n\n\U000025AB Slot ' + str(i) + ' ("' + str(slotNames[i])+ '") - Pill count: '+str(num)
                    text += "\n"

            self.bot.sendMessage(chat_ID, text=text)
        
        elif str(query_data).startswith("rmvPatient."): # Stop following a patient; ask for confirmation 

            patientID = query_data.split(".")[1].split("£")[0]
            patientUsername = query_data.split(".")[1].split("£")[1]
            deviceID=query_data.split(".")[-1]
            self.bot.sendMessage(chat_ID, text='Are you sure you want to dissociate from patient '+ str(patientUsername)+'? You will not receive notifications and monitor the data regarding this patient anymore.\nType "yes" to continue, type anything else to cancel the action:')
            chatState[str(chat_ID)]="rmvPatient."+str(patientID)+"£"+str(patientUsername)
            json.dump(chatState, open(self.chatStateFile, "w"))

        elif str(query_data).startswith("things"): # Choose ThingSpeak device and graph to visualize

            patientID = query_data.split(".")[1].split("£")[0]
            devices = requests.get(self.catalogURI+"getDevices/"+str(patientID)).json()["devices"]
            buttons=[]
            for device in devices:
                buttons.append([InlineKeyboardButton(text="device"+str(device), callback_data="deviceThings."+str(patientID)+"."+str(device))])
            keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
            self.bot.sendMessage(chat_ID, text="For which device do you want to see the statistics?", reply_markup=keyboard)

        elif str(query_data).startswith("deviceThings"): # The assistant chose the device; now it has to choose the graph to visualize 
            
            patientID = query_data.split(".")[-2]
            deviceID = query_data.split(".")[-1]

            # Get the slot number, so to know how many buttons to show. However, since ThingSpeak has a maximum of 8 charts per channel, a maximum of 6 slots can be visualized 
            slotNumber = int(requests.get(catalogURI + "getSlotsNumber/" + patientID + "/" + deviceID).json()["slots"])

            buttons=[]
            buttons.append([InlineKeyboardButton(text= "Temperature", callback_data="temperatureThings.user."+str(patientID)+"."+str(deviceID))])
            buttons.append([InlineKeyboardButton(text= "Humidity", callback_data="humidityThings.user."+str(patientID)+"."+str(deviceID))])
            for i in range(slotNumber):
                buttons.append([InlineKeyboardButton(text= ("Pills taken slot " + str(i)), callback_data="slotThings." + str(i) + "."+str(patientID)+"."+str(deviceID))])
                if i >= 5: # maximum of 6 slots! 
                    break

            keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
            self.bot.sendMessage(chat_ID, text='Which statistics do you want to see?', reply_markup=keyboard)
        
        elif str(query_data).startswith("temperatureThings."): # The user chose to see the temperature graph

            patientID = query_data.split(".")[-2]
            deviceID = query_data.split(".")[-1]
            channel = requests.get(self.catalogURI+"thingSpeakChannel/"+str(patientID)+"/"+str(deviceID)).json()["channel"]
            # Check if the patient has a ThingSpeak channel
            if channel == None:
                self.bot.sendMessage(chat_ID, text="Oooops! It seems like this device doesn't have a ThingSpeak channel associated to it")
            else: # If yes, download the image, save it, and then load it in the chat 
                channel = channel.split('/')[0]
                imgkit.from_url("https://thingspeak.com/channels/"+str(channel)+"/charts/1?bgcolor=%23ffffff&color=%23ff5631&dynamic=false&type=spline&days=1", 'ThingspeakImages/'+str(patientID)+'_'+str(deviceID) +'_temperature.jpg', options = options)
                self.bot.sendPhoto(chat_ID, photo=open('ThingspeakImages/'+str(patientID)+'_'+str(deviceID) +'_temperature.jpg', 'rb'))

        elif str(query_data).startswith("humidityThings."): # The user chose to see the humidity graph

            patientID = query_data.split(".")[-2]
            deviceID = query_data.split(".")[-1]
            channel = requests.get(self.catalogURI+"thingSpeakChannel/"+str(patientID)+"/"+str(deviceID)).json()["channel"]
            # Check if the patient has a ThingSpeak channel
            if channel == None:
                self.bot.sendMessage(chat_ID, text="Oooops! It seems like this device doesn't have a ThingSpeak channel associated to it")
            else: # If yes, download the image, save it, and then load it in the chat 
                channel = channel.split('/')[0]
                imgkit.from_url("https://thingspeak.com/channels/"+str(channel)+"/charts/2?bgcolor=%23ffffff&color=%237fc5e1&dynamic=false&type=spline&days=1", 'ThingspeakImages/'+str(patientID)+'_'+str(deviceID) +'_humidity.jpg', options = options)
                self.bot.sendPhoto(chat_ID, photo=open('ThingspeakImages/'+str(patientID)+'_'+str(deviceID) +'_humidity.jpg', 'rb'))

        elif str(query_data).startswith("slotThings."): # The user chose to see the pill taken graph

            slotNumber = int(query_data.split(".")[-3])
            patientID = query_data.split(".")[-2]
            deviceID = query_data.split(".")[-1]
            channel = requests.get(self.catalogURI+"thingSpeakChannel/"+str(patientID)+"/"+str(deviceID)).json()["channel"]
            # Check if the patient has a ThingSpeak channel
            if channel == None:
                self.bot.sendMessage(chat_ID, text="Oooops! It seems like this device doesn't have a ThingSpeak channel associated to it")
            else: # If yes, download the image, save it, and then load it in the chat 
                channel = channel.split('/')[0]
                # Uncomment for the pills taken in the last week
                #imgkit.from_url("https://thingspeak.com/channels/" + str(channel) + "/charts/3?bgcolor=%23ffffff&color=%23d62020&dynamic=false&results=60&type=column&days=7", str(patientID)+'.jpg', options=options)
                imgkit.from_url("https://thingspeak.com/channels/" + str(channel) + "/charts/" + str(slotNumber + 3) + "?bgcolor=%23ffffff&color=%23d62020&dynamic=false&type=column&days=31", 'ThingspeakImages/'+str(patientID)+'_'+str(deviceID) +'_slot' + str(slotNumber) + '.jpg', options=options)
            
            self.bot.sendPhoto(chat_ID, photo=open('ThingspeakImages/'+str(patientID)+'_'+str(deviceID) +'_slot' + str(slotNumber) + '.jpg', 'rb'))       

        # If we decide to give the asissants the ability to ring the device.    
        '''
        elif str(query_data).startswith("ring."):
            deviceID=query_data.split(".")[-1]
            deviceURI=requests.get(self.catalogURI+"getDeviceURI/"+str(userID)+"/"+str(deviceID)).json()["deviceURI"]
            if deviceURI != None:
                requests.put(deviceURI+"/alarm", json.dumps({"on":1}))
                buttons=[]
                buttons.append([InlineKeyboardButton(text= "Stop ringing", callback_data="stopRing.device."+str(deviceID))])
                keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
                self.bot.sendMessage(chat_ID, text='\U000023F0 Alarm is ringing ...', reply_markup=keyboard)
            else:
                self.bot.sendMessage(chat_ID, text='Error in finding the device')
        
        elif str(query_data).startswith("stopRing."):
            deviceID=query_data.split(".")[-1]
            deviceURI=requests.get(self.catalogURI+"getDeviceURI/"+str(userID)+"/"+str(deviceID)).json()["deviceURI"]
            if deviceURI != None:
                requests.put(deviceURI+"/alarm", json.dumps({"on":0}))
                self.bot.sendMessage(chat_ID, text='Alarm was stopped')
            else:
                self.bot.sendMessage(chat_ID, text='Error in finding the device')'''


    def on_chat_message(self, msg):
        
        content_type, chat_type, chat_ID = telepot.glance(msg)

        message=msg["text"]

        chatState=json.load(open(self.chatStateFile))
        assistantID=requests.get(self.catalogURI+"getAssistantID/"+ str(chat_ID)).json()["userID"]
        print('Message "' + str(message)+'" received from chat', chat_ID, ". User:",assistantID)

        if message == "/start": # First time seeing the user
            # Associate chatID with the patient in the catalog
            if str(chat_ID) in chatState.keys():
                self.bot.sendMessage(chat_ID, text='Welcome to the Assistant ApPills Bot, the amazing interface that lets you monitor the correct assumption of pills of your assisted patient. Check what data of your assisted you can obtain by typing "/"') 
            else:
                self.bot.sendMessage(chat_ID, text="\U0001F44B Welcome to the Assistant ApPills bot.\nIt's the first time seeing you here! \U0001F604\nPlease insert a username:")
                chatState[str(chat_ID)]="username"
                json.dump(chatState, open(self.chatStateFile, "w"))

        elif chatState[str(chat_ID)] == None: # Home state, where all the "/" commands have to be done 

            if message == "/assistnewpatient": # Command to assist new patient. Wait for patientID as answer
                self.bot.sendMessage(chat_ID, text='Insert the username and password, separeted by a space, of the patient you want to start assisting using this bot.\n(Example: "Luca 123456")')
                chatState[str(chat_ID)]="assist"
                json.dump(chatState, open(self.chatStateFile, "w"))

            elif message == "/patients": # Show list of assisted patients, on which you can click and see the commands 
                patients=requests.get(self.catalogURI+"getAssistedPatients/"+str(assistantID)).json()["assistedPatients"]
                if patients == []:
                    self.bot.sendMessage(chat_ID, text="No assisted patients found!\nStart assisting a patient by using the apposite command")
                else:
                    buttons=[]
                    for patient in patients:
                        buttons.append([InlineKeyboardButton(text=str(patient["username"]), callback_data="patient."+str(patient["userID"]) + "£" + str(patient["username"]))]) 
                    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
                    self.bot.sendMessage(chat_ID, text="Select an assisted patient", reply_markup=keyboard)

            else:
                self.bot.sendMessage(chat_ID, text='"' + str(message) + '" is not an available command')

        elif chatState[str(chat_ID)] == "username": # Chat state just after the username was asked to the user on startup. So that we know that the message is actually an answer to the "username?" question 
            requests.put(self.catalogURI + "addAssistant", json.dumps({"chatID":chat_ID, "userName":message}))
            chatState[str(chat_ID)]=None
            json.dump(chatState, open(self.chatStateFile, "w"))
            self.bot.sendMessage(chat_ID, text='Your username was set correctly!\nCheck what you can do with your devices by typing "/"')

        elif chatState[str(chat_ID)] == "assist": # Answer to the "who to assist?" question. Shoud contain username and password of the patient
            data = message.split(" ")
            if len(data) != 2: # Check correct format of the answer
                chatState[str(chat_ID)]=None
                json.dump(chatState, open(self.chatStateFile, "w"))
                self.bot.sendMessage(chat_ID, text='Incorrect format! The format is the following:\n"userID username"')
            else:
                inputUsername = data[0]
                inputPassword = data[1]
                found = int(requests.put(self.catalogURI+"assistUser", json.dumps({"username":inputUsername,"password":inputPassword ,"assistantID":assistantID})).json()["found"])
                chatState[str(chat_ID)]=None
                json.dump(chatState, open(self.chatStateFile, "w"))
                if found == -1:
                    self.bot.sendMessage(chat_ID, text='You are already assisting patient named '+str(inputUsername))
                elif found == 0:
                    self.bot.sendMessage(chat_ID, text='No patient named "'+str(inputUsername) + '" with password "' + str(inputPassword) + '" was found')
                elif found == 1:
                    self.bot.sendMessage(chat_ID, text='You are now assisting the patient named "'+str(inputUsername) +'"')
                

        elif chatState[str(chat_ID)].startswith("rmvPatient"): # Answer to "you sure you want to stop assisting this patient?". Should be a "yes" or any other answer 
            patientID = chatState[str(chat_ID)].split(".")[1].split("£")[0]
            patientUsername = chatState[str(chat_ID)].split(".")[1].split("£")[1]
            data = message.lower() # Put everything lowercase so that it is not ambiguous
            if data == "yes":
                requests.delete(self.catalogURI + "dissociatePatient/"+str(assistantID)+"/"+str(patientID)) 
                self.bot.sendMessage(chat_ID, text="Patient "+ str(patientUsername) + " was successfully disassociated from your account.")
                chatState[str(chat_ID)]=None
                json.dump(chatState, open(self.chatStateFile, "w"))
            else:
                self.bot.sendMessage(chat_ID, text="Operation canceled. The patient was not dissociated")
                chatState[str(chat_ID)]=None
                json.dump(chatState, open(self.chatStateFile, "w"))



if __name__=="__main__":

    catalogURI=json.load(open(confFile))["catalogURI"]
    conf = requests.get(catalogURI+"conf").json()
    token=conf["assistant-token"]
    bot=TelegramBot(token, "SmartCase-assistantTelegramBot", conf["broker"], conf["port"], conf["baseTopic"], catalogURI, "assistantChatStates.json")
    bot.start()
    lastPing = 0
    while True:
        time.sleep(0.1) # Need high reactivity for messages
        if time.time() - lastPing > 5: # But lower frequency for pings (5 seconds)
            requests.put(catalogURI+"ping", data=json.dumps({"service": "assistantTelegramBot"}))
            lastPing = time.time()
