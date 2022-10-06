<p align="center>
  <img src = "https://user-images.githubusercontent.com/80349484/194348556-ca043a1d-9b60-4878-9764-62955d82fae5.png"  width = 100>
</p>

# ApPills
IoT platfrom, composed of several microservices, for a Smart Pill Case. 
Trough the development of a TelegramBot, the system implements several useful functions:
- Reminds the person to take pills at the right time
- Tracks if pills were taken or not
- Allows to retrieve everyitime and everywhere the current number of pills in the case
- Controls if the case was left opened for too long 
- Controls the correct environmental preservation of pills
- Provides useful graphs and statistics
- Allows assistants, through their own TelegramBot, to follow a patient account to see their current pill count and get informed on the incorrect intake of the pills. 

The whole platform is scalable in terms of users, devices and number of slots that compose each case, as well as microservices. 
The main utilized communcation protocols are MQTT for asynchronous communication and REST for synchronous communication.  

## The smartcase

The smartcase was simulated, since the project was developed during COVID-19 and it was not possible to obtain a Raspberry Pi.

![Schermata 2022-10-06 alle 17 07 18](https://user-images.githubusercontent.com/80349484/194351247-b8505d42-223d-4990-a0eb-64f65f4330fd.png)

## System Structure

![Schermata 2022-10-06 alle 17 11 12](https://user-images.githubusercontent.com/80349484/194351386-960eac33-9c88-4c11-a588-82251ce98260.png)

## How to run the code

To run the whole project, launch the programs in the following order:
1. catalog3.py  ->  Writes on the "mycat.json" file.
2. conservationControl.py   ->   Needs the "conf.json" file to read the catalogURI.
3. openingControl.py   ->   Needs the "conf.json" file to read the catalogURI.
4. pillDifferenceCalculator.py   ->    Needs the "conf.json" file to read the catalogURI.
5. telegramBot.py -> Writes on the "chatStates.json" file. Needs the "conf.json" file to read the catalogURI.
6. assistantTelegramBot.py -> Writes on the "assistantChatStates.json" file. Needs the "conf.json" file to read the catalogURI.
7. timeShift2.py -> Needs the "conf.json" file to read the catalogURI.
8. TSadaptor1.py -> Needs the "conf.json" file to read the catalogURI.
9. smartcaseSingleDevicePersistent.py (device simulator) -> Writes on the "device.json" file. Needs the "conf.json" file to read the catalogURI.

