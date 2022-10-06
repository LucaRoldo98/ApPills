# IoT-ApPills

## HOW TO RUN THE CODE

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

## TO DO LIST

I am keeping jsons file for device (the information should come from sensors itself, but this is simulated), for telegramBot and assistantTelegramBot. ChatStates are not as important as other system information, and putting them on the catalog will require a huge amount of read and writes. 

