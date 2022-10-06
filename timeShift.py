import json
import time
import requests
import paho.mqtt.client as PahoMQTT 
import threading
from datetime import datetime, timedelta
from statisObj import ListStat

DAILY_LIST = [] 
MY_SCHED = {}
lock = threading.Lock()
confFile = "conf.json"

'''
Microservices that manages the schedules of each device:
from the catalog, it reads for each pair patient-device all the pills scheduled and 
it creates a list in which it associates the time with patient-device ID, slot, numbers of pills 
and alarm. When the catalog is updated, the list will be created again in order to not lose
any new update.
Every 5 seconds, it checks if any user has a pill scheduled, if that is the case, it will first check 
whether the pill was taken in the previous hour, if it is not the case, it will send a message 
to telegram to remind to take the pill.
It will remind the user every 10 minutes to take the pill, after 1 hour it will consider it as not-taken.
Moreover, it keeps track of the total number of pills taken by each pair patient-device and at the end 
of the day, it will send the statistics to thingspeak.  
'''


def ch():
    MY_SCHED = {}

class TimeShift:
    
    def __init__(self, broker, port, baseTopic, clientID, catalogURI):
        self.broker = broker 
        self.port = port
        self.clientID = clientID 
        self.baseTopic = baseTopic
        self.subTopic_opCon = baseTopic + "/+/+/pillDifference"
        self.catalogURI = catalogURI
        self._paho_mqtt = PahoMQTT.Client(clientID, True)
        self._paho_mqtt.on_connect = self.myOnConnect
        self._paho_mqtt.on_message = self.myOnMessageReceived 
        self.__msg = {
            "bn": self.clientID,
            "e": {
                "message": None, # 0->pill needs to be taken in the precise moment, 1-> send a reminder to take the pill, 2 -> pill is not taken, 5 -> daily stat
                "slot":"",
                "timestamp": ""
            }
        }
           
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
        
    def pub_stat(self, data):
        for item in data: 
            msg = self.__msg
            user_dev = item['patientID/deviceID']
            topic = self.baseTopic +'/'+ user_dev +'/timeShift'
            msg["e"]["message"] = 5
            msg["e"]["slot"] = item['stat']
            self._paho_mqtt.publish(topic, json.dumps(msg), 2)    
            print(f"message published to topic {topic}" )
        
    def subscribe(self, topic):
        self._paho_mqtt.subscribe(topic,2)
        print("[",time.ctime(),"] - Subscribed to", topic)
        
    def start(self):
        self._paho_mqtt.connect(self.broker, self.port)
        self._paho_mqtt.loop_start()
        print("[",time.ctime(),"] - Time Shift", self.clientID, "started")
        self.subscribe(self.subTopic_opCon)
        
    def unsubscribe(self):
        self._paho_mqtt.unsubscribe(self.subTopic_opCon)
        
    def stop(self):
        self.unsubscribe()
        self._paho_mqtt.loop_stop()
        self._paho_mqtt.disconnect()
        print("[",time.ctime(),"] - Time shift", self.clientID, "stopped")
        
    def notify(self,topic,msg):
        payload = json.loads(msg)
                #payload = json.loads(payload1)
        patientID = str(topic.split("/")[1])
        deviceID = str(topic.split("/")[2])
        # print("ricevuto")
        # for the particular "patientID/deviceID" update the daily statistics 
        num = requests.get(self.catalogURI+"getSlotsNumber/"+patientID +'/'+deviceID).json()
        num = int(num["slots"])
        
        slots = []
        for s in range(num):
            slots.append("slot"+str(s))
        
        for j,slot in enumerate(slots):
            if payload["e"]["difference"][j]<0:
                DAILY_LIST.updateVal(patientID, deviceID, slot, payload["e"]["difference"][j])
                # Switch off the led
                deviceURI = requests.get(self.catalogURI+"getDeviceURI/"+patientID+"/"+deviceID).json()["deviceURI"]
                led_msg= {
                                "bn":"appPills-TimeShift",
                                'slotID':int(slot[-1]),
                                'on':0 
                                }
                # send a post to turn off the led. We don't need to know if it was scheduled or not, since if the led was off, this request won't do anything
                requests.put(url =deviceURI+"/led", data = json.dumps(led_msg))
                '''
                alarm_msg= {
                                "bn": "appPills-TimeShift",
                                "on": 0
                                }
                requests.put(url =deviceURI+"/alarm", data = json.dumps(alarm_msg))'''
                print('pill taken')
              
        
class SchedulingThread(threading.Thread):
    """Scheduling thread to call strategy. In this thread the timeshift runs 
    and the scheduled is checked every 5 sec"""

    def __init__(self, ThreadID, name, catalogURI):
        """Initialise thread."""
        threading.Thread.__init__(self)
        self.ThreadID = ThreadID
        self.name = name
        self.catalogURI = catalogURI
       
    def run(self):
        
        # read configuration file
        catalogURI=json.load(open("conf.json"))["catalogURI"]
        conf = requests.get(catalogURI+"conf").json()
        # create TimeShift 
        timeShift = TimeShift(conf["broker"], conf["port"], conf["baseTopic"], "appPills-TimeShift", self.catalogURI)
        timeShift.start() 
        reset_time = '23:59:50'
        
        # generates all time interval where actions need to be executed 
        delta = timedelta(seconds=5) # minimum time 
        delta1 = timedelta(hours=1,seconds=6) # max time in which patient can take the pill before it is counted as lost 
        delta2 = timedelta(minutes=10) # every ten min remind a pill has to be taken
        delta3 = timedelta(minutes=1) 
        reminder = {}
        
        #loop that runs every 5 sec that check the schedule and update the value inside DAILY_LIST
        while(True):
            #print('**')
            lock.acquire()
            DAILY_LIST.resetTime() 
            lock.release()
            now_time = datetime.now().strftime('%H:%M:%S') #REMEMBER, TIME IN TIME SHIFT IS HOUR:MIN:SEC  
            
            # SEND BEFORE THE MIDNIGNT ALL STATISTICS OF THE DAY 
            # check if it's 11:59:00 to send the statistics to thinkspeak and reset the values
            res_delta = datetime.strptime(now_time, '%H:%M:%S') - datetime.strptime(reset_time, '%H:%M:%S')
          
            if res_delta.days < 0: # check if midnight has passed
                res_delta = timedelta(
                    days=0,
                    seconds=res_delta.seconds,
                    microseconds=res_delta.microseconds
                )
            # if the difference between time in the schedule and current time is smaller than 5sec, send stat and reset value
            if(res_delta)<delta: 
                print("SEND ALL STATISTICS")
                # send statistics about daily activity
                data = DAILY_LIST.sendStatistics()
                timeShift.pub_stat(data)
                DAILY_LIST.resetVal()
            
            
            # create a copy of MY_SCHED 
            copyMY_SCHED = MY_SCHED.copy()
           
            # CHECK FOR ALL ELEMENTS IN SCHEDULA IF IT'S TIME TO TAKE PILL
            # before sending the message check if it was already taken in the previous hour 
            for item in copyMY_SCHED:
                #print(MY_SCHED[item])
                tdelta = datetime.strptime(now_time, '%H:%M:%S') - datetime.strptime(MY_SCHED[item], '%H:%M:%S')
                #print(tdelta)
                if tdelta.days < 0: # check if midnight has passed
                    tdelta = timedelta(
                        days=0,
                        seconds=tdelta.seconds,
                        microseconds=tdelta.microseconds
                    )
    
                # if the difference between time in the schedule and current time is smaller than 5sec, pill has to be taken
                if(tdelta)<delta:  
                    # check if it is already taken in the previous hour
                    patID = item.split('/')[0]
                    devID = item.split('/')[1]
                    slot = item.split('/')[2]
                    deviceURI = item.split('+')[1]
                    
                    if DAILY_LIST.isPillTaken(patID, devID, slot)==False:
                        print("take the pill")
                        # send a message to telegram bot to remind to take the pill 
                        topic = patID +"/"+devID+"/timeShift"
                        timeShift.publish(topic, 0, slot[-1])
                        # check if the alarm is set on or off
                        # if alarm is 0, do not send the message, if it is equal to 1 activate it
                        #if item.split('/')[3][-1] == '1': 
                        alarm_msg= {
                            "bn": "appPills-TimeShift",
                            "on": 1
                            }
                        requests.put(url =deviceURI+"/alarm", data = json.dumps(alarm_msg))
                        led_msg= {
                            "bn":"appPills-TimeShift",
                            'slotID':int(slot[-1]),
                            'on':1
                            }
                        print("TAKE THE PILL NOW!!!")
                       
                        requests.put(url =deviceURI+"/led", data = json.dumps(led_msg))
                        reminder[item] = MY_SCHED[item]  # insert it in the reminder list 
                    
            
            if len(reminder)>0:
                '''
                Inside reminder there are stored all the pills that have to be taken. Every ten min it sends to the user 
                a reminder to take the pill, after 1 hour the pill is considered as not taken and a message is sent to 
                thinkspeak. Every 10 sec it checks if the pill is taken so in that case it deletes the element from the list 
                and turn off the led for that particular slot
                '''
                copy_reminder = reminder.copy()
              
                #print("REMINDER ACTIVE")
                for item in copy_reminder:
                    patID = item.split('/')[0]
                    devID = item.split('/')[1]
                    slot = item.split('/')[2]
                    deviceURI = item.split('+')[1]
                    if DAILY_LIST.isPillTaken(patID, devID, slot)==True:
                        reminder.pop(item)
                        led_msg= {
                            "bn":"appPills-TimeShift",
                            'slotID':int(slot[-1]),
                            'on':0 
                            }
                        r1 = requests.put(url =deviceURI+"/led", data = json.dumps(led_msg))
                    else:
                        tdelta1 = datetime.strptime(now_time, '%H:%M:%S') - datetime.strptime(reminder[item], '%H:%M:%S')
                        if tdelta.days < 0: # check if midnight has passed
                            tdelta = timedelta(
                                days=0,
                                seconds=tdelta.seconds,
                                microseconds=tdelta.microseconds
                            )
                        if (tdelta1> delta1):  # if 1 hour has passed consider pill as not taken and send a message to thinkspeak
                            reminder.pop(item)
                            #deviceURI=requests.get(catalogURI+patID+"/"+devID)
                            led_msg= {
                                "bn":"appPills-TimeShift",
                                'slotID':int(slot[-1]),
                                'on':0 
                                }
                            # send a put to turn off the led
                            requests.put(url =deviceURI+"/led", data = json.dumps(led_msg))
                            topic = patID +"/"+devID+"/timeShift"
                            timeShift.publish(topic, 2, slot[-1]) # send to thinkspeak that pill is not taken 
                        # every 10 min check and remind to take the pill
                        if (tdelta1>delta3 and tdelta1 % delta2 < delta):  #add if tdelta>1min  # time % 10min < 5 sec
                            topic = patID +"/"+devID+"/timeShift"
                            timeShift.publish(topic, 1,slot[-1])
                            print('remind to take the pill')
                        
            time.sleep(5)
        
        
    
if __name__ == "__main__":

    DAILY_LIST = ListStat()   
    # read from the conf file the URI of the catalog 
    catalogURI=json.load(open(confFile))["catalogURI"]
    conf = requests.get(catalogURI+"conf").json()
    
    # request to the catalog the schedule from every pair of user-device
    cat = requests.get(catalogURI+'getSchedules').json()
    last_update_cat = '00:00:00' 
    ''' 
    generate an ID for each time a pill is scheduled: it is going to be
    patient/device/slot/alarm/rep+deviceURI  and it corresponds to the key, while the time scheduled is 
    the value. all pairs key-value are stored in a list ordered by the value (so by the time)
    iterate for all devices
    '''
    # save all pairs user-device
    user = cat.keys()
    
    # add every pill scheduled to the list
    for us in user:
        temp1 = str(us)
        temp_pat = temp1.split('/')[0]
        temp_dev = temp1.split('/')[1]
        num = requests.get(catalogURI+"getSlotsNumber/"+temp1).json()
        dev_URI = requests.get(catalogURI+"getDeviceURI/"+temp1).json() 
        dev_URI = dev_URI["deviceURI"]
        DAILY_LIST.addDev(temp_pat, temp_dev,num["slots"])
        for i, slot in enumerate(cat[us]):
            # add to list only slot that has a schedule
            if slot: 
                temp2 = temp1 + '/slot' + str(i)
                rep = 0 
                for sch in slot:
                    # add if alarm is on or off with 1 and 0 
                    code = temp2 + '/' + str(sch['alarm']) + '/' + str(rep) + '+' + dev_URI
                    rep = rep + 1
                    sch_time = str(sch['time'])
                    MY_SCHED[code]=sch_time

    thread1 = SchedulingThread(1, "thread1", catalogURI)
    thread1.start()
    
    print('--------------')
    # every 10 sec make a request to the catalog to read the schedule for each patient/device 
    while True:
        # Ping the catalog every 5 seconds saying that I'm alive 
        requests.put(catalogURI+"ping", data=json.dumps({"service": "timeShift"}))
        # save in a variable last update of catalog, check everytime if the time is the same,
        # if it's not, read catalog again
        cat_last_update = requests.get(catalogURI+'getLU').json()["LU"]
        cat_last_update = cat_last_update.split(" ")[4]
        
        if cat_last_update!=last_update_cat:
            print("update catalog")
            schedul =  requests.get(catalogURI+'getSchedules').json() 
            lock.acquire()
            MY_SCHED={}
            
            user = schedul.keys()
            for us in user:
                temp1 = str(us)
                temp_pat = temp1.split('/')[0]
                temp_dev = temp1.split('/')[1]
                dev_URI = requests.get(catalogURI+"getDeviceURI/"+temp1).json() 
                dev_URI = dev_URI["deviceURI"]
                num = requests.get(catalogURI+"getSlotsNumber/"+temp1).json()
                DAILY_LIST.addDev(temp_pat, temp_dev, num["slots"])
                for i, slot in enumerate(schedul[us]):
                    # add to list only slots that have a schedule
                    if slot: 
                        temp2 = temp1 + '/slot' + str(i)
                        rep = 0 
                        for sch in slot:
                            # add if alarm is on or off with 1 and 0 
                            code = temp2 + '/' + str(sch['alarm']) + '/' + str(rep) + '+' + dev_URI
                            rep = rep + 1
                            sch_time = str(sch['time'])
                            MY_SCHED[code]=sch_time
                            
            last_update_cat = cat_last_update
            lock.release()
        
        time.sleep(5)
