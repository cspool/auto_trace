import os,time
if os.fork()==0:
 os.setsid()
 if os.fork()==0:time.sleep(2);os._exit(0)
 os._exit(0)
os._exit(0)
