import json
from datetime import datetime, timedelta

class Statistics:
    def __init__(self, patientID, deviceID, num):
        '''
        data structures that counts for each day the number of pills taken from each slots 
        from each device + saves the time that a pill was taken 
        
        form of the data for num_slot = 3 is: 
        self.stats = {
            "patientID/deviceID":str(patientID)+"/"+str(deviceID),
            "TOTPillsDay": {
                "slot1":0,
                "slot2":0,
                "slot3":0,
            },
            "PillTaken": {
                "slot1":0,
                "slot1_update":"",
                "slot2":0,
                "slot2_update":"",
                "slot3":0,
                "slot3_update":"",
                }
        }
        
        '''
        self.num = int(num) 
        
        # create struct based on number of slots 
        self.slots = []
        for i in range(num):
            self.slots.append("slot"+str(i))
        self.stats = {
            "patientID/deviceID":str(patientID)+"/"+str(deviceID),
            "TOTPillsDay": {},
            "PillTaken": {}
        }
        for sl in self.slots:
            self.stats["TOTPillsDay"][sl] =0 
            self.stats["PillTaken"][sl] = 0
            self.stats["PillTaken"][sl+'_update'] = ""
            
        self.delta = timedelta(hours = 1) 
        
    def getIDs(self):
        return str(self.stats["patientID/deviceID"])
    
    def print_stat(self):
        print(json.dumps(self.stats, indent = 2))
        
    def updateValue(self, slot, value):
        statsUp = self.stats 
        statsUp["TOTPillsDay"][slot] = statsUp["TOTPillsDay"][slot]+ abs(value)
        statsUp["PillTaken"][slot] = 1 
        last_update = slot + "_update"
        statsUp["PillTaken"][last_update] = str(datetime.now())
        # SEND a message to telegram bot and timespeak about time and number of pills taken 
             
    def resetValue(self):
        #reset value at the end of the day 
        statsUp = self.stats
        for item in self.slots:
            statsUp["TOTPillsDay"][item] = 0 
            
    def resetTime(self):
        # if value of slot is 1, check if 1 hour has passed since the last update, if so,
        # it sets the value of the slot back to 0 
        nowTime = datetime.now()
        for item in self.slots:
            if self.stats["PillTaken"][item] == 1:  
                last_update = item + "_update"
                # timestamp in the list conve   rted to datetime
                last_temp = datetime.strptime(self.stats["PillTaken"][last_update], "%Y-%m-%d %H:%M:%S.%f")
                diff = nowTime - last_temp
                if (self.delta<=diff):
                    self.stats["PillTaken"][item] = 0 
    
    def pillTaken(self, slot):
        # check if pill is taken in the exact moment, if it is already taken do not do anything
        if self.stats["PillTaken"][slot] == 1:    
            return True # means pill is already taken, do not do anything 
        else: 
            return False # pill is not taken, set a reminder 
    
    def sendStatistics(self):
        sends = self.stats["TOTPillsDay"]
        return sends 
    
    
class ListStat(Statistics):
    def __init__(self):
        self.listData = []
        print("list created")
        
    def isPresent(self, patientID, deviceID):
        x =0 
        # check if the couple patient-device is already present in the list 
        for item in self.listData:
            if item.getIDs() == str(patientID)+"/"+ str(deviceID):
                x = 1
        # if it returns 0 it is not present, if return 1, it already exists
        return x 
        
    def addDev(self, patientID, deviceID, num): 
        # check first if it already exists in the list
        if self.isPresent(patientID, deviceID) == 0: 
            newDev = Statistics(patientID, deviceID, num)
            self.listData.append(newDev)
        else: 
            print("The device is already registered in the list")

    def updateVal(self, patientID, deviceID, slot, value):          
        # given the patient and device ids,update value
        for item in self.listData:
            if item.getIDs() == str(patientID)+"/"+ str(deviceID):
                print("value updated")
                item.updateValue(slot, value)
        if self.isPresent(patientID, deviceID) == 0: 
            print("Device not present in the list")
            
    def resetVal(self):
        for item in self.listData:
            item.resetValue()
            
    def resetTime(self):
        for item in self.listData:
            item.resetTime()
    
    def sendStatistics(self):
        dailyStat = {
            "patientID/deviceID":"",
            "stat": ""
            }
        list_dailyStat = []
        for item in self.listData:
            temp = dailyStat
            temp["patientID/deviceID"] = item.getIDs()
            temp["stat"] = item.sendStatistics()
            list_dailyStat.append(temp)
        return list_dailyStat
    
    def isPillTaken(self, patientID, deviceID,slot):
        if self.isPresent(patientID, deviceID) == 1:
           for item in self.listData:
            if item.getIDs() == str(patientID)+"/"+ str(deviceID):
                return item.pillTaken(slot)
        else:
            print("patient and device not in the list")
    
    def print_list(self):
        for item in self.listData:
            item.print_stat()

