# faucet_db


Database for Faucet to store all the flows pushed to switches. 

Prerequisite:
1. RYU-Faucet Controller
2. CouchDB



Faucet_db helps us in storing installed flows on database so that application can request and get flows data directly from database. 

State of currently installed flows can be requested by large number of applications written to a controller. If they would request directly it from controller it would be overloaded and will lead to performance degradation. So we are storing information in a database corresponding to a datapath_id (UID) of the switch, then the database can provide the switch information at that point in time.

![Architecture](/images/db_architecture.png)

We have created a generic database driver(nsodbc) to support document database. we have tested and validated those APIs with couchDB.
Using those APIs we can do following operations on database.
1. Connect
2. Insert
3. Update
4. Delete
5. Get

Real-time database updation is getting supported.


