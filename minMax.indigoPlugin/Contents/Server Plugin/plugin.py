#! /usr/bin/env python
# -*- coding: utf-8 -*-
####################
# Plugin miMax
# Developed by Karl Wachs
# karlwachs@me.com
# last change dec 14, 2015

import os, sys, re, Queue, threading, subprocess, pwd,urllib2
import datetime, time
import simplejson as json
from time import gmtime, strftime, localtime
import urllib
import fcntl
import signal
import copy
import myLogPgms.myLogPgms 




'''
how it works:
user selects dates from to and the devces/ states or variables to track 
the main loop check teh sqllite3 db every x minutes and build the min/max/averages for each device/state/variable and fills 
device_state_date_min  or max or ave with the values. 
in addition it will also fill _date  with the point in time when the min/macx occured, if the option is selected.

'''
Version="7.5.2"

tagsTimes     =["thisHour","lastHour","thisDay","lastDay","thisWeek","lastWeek","thisMonth","lastMonth","last7Days"]
tagsMMA       =["Max","Min","Ave"]
tagsDateCount =["Date","Date","Count"]

################################################################################
class Plugin(indigo.PluginBase):

####----------------- logfile  ---------
	def __init__(self, pluginId, pluginDisplayName, pluginVersion, pluginPrefs):
		indigo.PluginBase.__init__(self, pluginId, pluginDisplayName, pluginVersion, pluginPrefs)
		self.pathToPlugin       =os.getcwd()+"/"
		## = /Library/Application Support/Perceptive Automation/Indigo 6/Plugins/INDIGOPLOTD.indigoPlugin/Contents/Server Plugin
		p=max(0,self.pathToPlugin.lower().find("/plugins/"))+1
		self.indigoPath         = self.pathToPlugin[:p]
		self.pluginState        = "init"
		self.pluginVersion      = pluginVersion
		self.pluginId           = pluginId
		self.pluginName         = pluginId.split(".")[-1]
		self.pluginShortName    = "minMax"
	
	
####-----------------   ---------
	def __del__(self):
		indigo.PluginBase.__del__(self)
	
####-----------------   ---------
	def startup(self):


		self.myPID = os.getpid()
		self.MACuserName   = pwd.getpwuid(os.getuid())[0]

		self.MAChome                    = os.path.expanduser(u"~")
		self.userIndigoDir              = self.MAChome + "/indigo/"
		self.userIndigoPluginDir        = self.userIndigoDir +self.pluginShortName+ u"/"
 
		if True:
			if not os.path.exists(self.userIndigoDir):
				os.mkdir(self.userIndigoDir)

			if not os.path.exists(self.userIndigoPluginDir):
				os.mkdir(self.userIndigoPluginDir)
	
				if not os.path.exists(self.userIndigoPluginDir):
					self.errorLog("error creating the plugin data dir did not work, can not create: "+ self.userIndigoPluginDir)
					self.sleep(1000)
					exit()
				
		self.debugLevel = []
		for d in ["Loop","Sql","Setup","all"]:
			if self.pluginPrefs.get(u"debug"+d, False): self.debugLevel.append(d)
		self.ML = myLogPgms.myLogPgms.MLX()
		self.setLogfile(unicode(self.pluginPrefs.get("logFileActive2", "standard")))

		self.refreshRate        = float(self.pluginPrefs.get("refreshRate",5))
		self.liteOrPsql         = self.pluginPrefs.get(     "liteOrPsql",       "sqlite")
		self.liteOrPsqlString   = self.pluginPrefs.get(     "liteOrPsqlString", "/Library/PostgreSQL/bin/psql indigo_history postgres ")
		self.devList            = json.loads(self.pluginPrefs.get("devList","{}"))
		delID=[]
		for devId in self.devList:
			if "devOrVar" not in self.devList[devId]:
				delID.append(devId)
			if "states" not in self.devList[devId]:
				delID.append(devId)
		for devId in delID:
			try:
				del self.devList[devId]
			except:
				pass

		for devId in self.devList:
			#self.ML.myLog( text="devid devList "+ str(devId)+ " " +unicode(self.devList[devId]) )
			if "states" not in self.devList[devId]: continue
			for state in self.devList[devId]["states"]:   
				if "ignoreLess"    not in self.devList[devId]["states"][state]:
					self.devList[devId]["states"][state]["ignoreLess"]        =-9876543210.
				if "ignoreGreater" not in self.devList[devId]["states"][state]:
					self.devList[devId]["states"][state]["ignoreGreater"]     =+9876543210.


					
		self.variFolderName     = self.pluginPrefs.get("variFolderName","minMax")
		self.saveNow            = False
		self.devID              = 0
		self.devIDExist			= 0
		self.devOrVarExist      = "Var"
		self.devOrVar           = "Var"
		self.quitNow            = "" # set to !="" when plugin should exit ie to restart, needed for subscription -> loop model
		self.printConfigCALLBACK()
		self.stopConcurrentCounter = 0
		self.pluginPrefs["devList"] =json.dumps(self.devList)
		return

####-----------------   ---------
	####-----------------    ---------
	def setLogfile(self,lgFile):
		self.logFileActive =lgFile
		if   self.logFileActive =="standard":   self.logFile = ""
		elif self.logFileActive =="indigo":     self.logFile = self.indigoPath.split("Plugins/")[0]+"Logs/"+self.pluginId+"/plugin.log"
		else:                                   self.logFile = self.userIndigoPluginDir +"plugin.log"
		self.ML.myLogSet(debugLevel = self.debugLevel ,logFileActive=self.logFileActive, logFile = self.logFile)

####-----------------   ---------
	def deviceStartComm(self, dev):
		dev.stateListOrDisplayStateIdChanged()
		return
	
####-----------------   ---------
	def deviceStopComm(self, dev):
		return
####-----------------   ---------
	def stopConcurrentThread(self):
		self.stopConcurrentCounter +=1
		self.ML.myLog( text=u"stopConcurrentThread called " + str(self.stopConcurrentCounter))
		if self.stopConcurrentCounter ==1:
			self.stopThread = True


 
####-----------------  set the geneeral config parameters---------
	def validatePrefsConfigUi(self, valuesDict):

		self.debugLevel = []
		for d in ["Loop","Sql","Setup","all"]:
			if valuesDict[u"debug"+d]: self.debugLevel.append(d)

		self.setLogfile(valuesDict[u"logFileActive2"])


		self.variFolderName     = valuesDict[u"variFolderName"]
		self.refreshRate        = float(valuesDict[u"refreshRate"])
		self.liteOrPsql         = valuesDict["liteOrPsql"]
		self.liteOrPsqlString   = valuesDict["liteOrPsqlString"]

		try:
			indigo.variables.folder.create(self.variFolderName)
		except:
			pass
		return True, valuesDict


####-----------------   ---------
	def dummyCALLBACK(self):
		
		return
####-----------------   ---------
	def printConfigCALLBACK(self,devstr=""):
		try:
			self.ML.myLog( text="Configuration: Dev-Name    DevID            State       ignoreLess  ignoreGreater; tracking states: -------")
			for devid in self.devList:
				if devid == devstr or devstr=="":
					for state in self.devList[devid]["states"]:
						out="  "+"%15.0f"%self.devList[devid]["states"][state]["ignoreLess"]+" "+"%15.0f"%(self.devList[devid]["states"][state]["ignoreGreater"])+" "
						for tt in self.devList[devid]["states"][state]:
							if tt =="ignoreLess" or tt == "ignoreGreater": continue
							for ss in self.devList[devid]["states"][state][tt]:
								if  self.devList[devid]["states"][state][tt][ss]["use"]:
									out+= tt+"_"+ss+"  "
						if self.devList[devid]["devOrVar"]=="Var":           
							self.ML.myLog( text= indigo.variables[int(devid)].name.ljust(20) +"; "+devid.ljust(10)+"; "+state.rjust(15)+out )
						else:           
							self.ML.myLog( text= indigo.devices[int(devid)].name.ljust(20) +"; "+devid.ljust(10)+"; "+state.rjust(15)+ out )
		except  Exception, e:
			if len(unicode(e)) > 5:
				self.ML.myLog( text= "error in  Line '%s' ;  error='%s'" % (sys.exc_traceback.tb_lineno, e),)
			self.ML.myLog( text=unicode(self.devList))
		return



####-----------------  ---------
	def getMenuActionConfigUiValues(self, menuId):
		
		valuesDict=indigo.Dict()
		if menuId == "defineDeviceStates":
			for tt in tagsTimes:
				for ss in tagsMMA:
					valuesDict[tt+ss]=False
				valuesDict[tt+"Date"]=False
			valuesDict["showM"]=False          
			valuesDict["ignoreGreater"]="+9876543210."          
			valuesDict["ignoreLess"]   ="-9876543210."          

		return valuesDict




########### --- delete dev/states from tracking 
####-----------------   ---------
	def pickExistingDeviceCALLBACK(self,valuesDict="",typeId=""):               # Select only device/properties that are supported
		if self.ML.decideMyLog(u"Setup"): self.ML.myLog( text =unicode(valuesDict))
		if valuesDict["device"].find("-V") >-1:
			self.devOrVarExist="Var"
			self.devIDExist= int(valuesDict["device"][:-2])# drop -V
		else:        
			self.devIDExist= int(valuesDict["device"])
			self.devOrVarExist="Dev"

####-----------------   ---------
	def filterExistingDevices(self,filter="",valuesDict="",typeId=""):  
		retList = []
		for devId in self.devList:
			try: retList.append([devId,indigo.devices[int(devId)].name])
			except: pass
		return retList
####-----------------   ---------
	def filterExistingStates(self,filter="",valuesDict="",typeId=""):                
		if self.devOrVarExist ==0: return [(0,0)]
		devstr= str(self.devIDExist)
		retList=[]
		if devstr in self.devList:
			if self.devOrVarExist =="Var":
				retList.append(("value", "value"))
				return retList
			for test in self.devList[devstr]["states"]:
				retList.append((test,test))             
		return retList
####-----------------   ---------
	def buttonRemoveCALLBACK(self,valuesDict="",typeId=""):               # Select only device/properties that are supported
		devstr= str(self.devIDExist)
		state= valuesDict["state"]
		if devstr in self.devList:
			if  state in self.devList[devstr]["states"]:
				del self.devList[devstr]["states"][state]
			if len(self.devList[devstr]["states"]) ==0:
				del self.devList[devstr]
		self.devIDExist 	= 0
		valuesDict["state"] = ""
		return valuesDict




########### --- add dev/states to tracking 
####-----------------   ---------
	def pickDeviceCALLBACK(self,valuesDict="",typeId=""):               # Select only device/properties that are supported
		if self.ML.decideMyLog(u"Setup"): self.ML.myLog( text =unicode(valuesDict))
		if valuesDict["device"].find("-V") >-1:
			self.devOrVar="Var"
			self.devID= int(valuesDict["device"][:-2])# drop -V
		else:        
			self.devID= int(valuesDict["device"])
			self.devOrVar="Dev"


####-----------------   ---------
	def filterDevicesThatQualify(self,filter="",valuesDict="",typeId=""):               
		retList= copy.copy(self.listOfPreselectedDevices )
		return retList


####-----------------   ---------
	def filterStatesThatQualify(self,filter="",valuesDict="",typeId=""):                
	
		if self.devID ==0: return [(0,0)]

		retList=[]
		if self.devOrVar =="Var":
			retList.append(("value", "value"))
			return retList
		
		dev=indigo.devices[self.devID]
		retList=[]
		theStates = dev.states.keys()
		for test in theStates:
				count=0
				try:
					if "Mode" in test or "All" in test or ".ui" in test:
						skip= True
					else:
						skip= False
				except:
					skip=False
				if not skip:    
					val= dev.states[test]
					x = self.getNumber(val)
					if x!="x" :
						count +=1
				if count>0:                                                 
					retList.append((test,test))             
		return retList
####-----------------   ---------
	def buttonConfirmStateCALLBACK(self,valuesDict="",typeId=""):               # Select only device/properties that are supported
		devstr= str(self.devID)
		if self.devOrVar=="Var":
			dev=indigo.variables[int(self.devID)]
		else:
			dev=indigo.devices[int(self.devID)]
		
		state= valuesDict["state"]
		if devstr not in  self.devList:
			self.devList[devstr]={}
			self.devList[devstr]["states"]={}

		self.devList[devstr]["devOrVar"]=self.devOrVar

			
		if  state not in self.devList[devstr]["states"]:
			self.devList[devstr]["states"][state]={}
			
		for tt in tagsTimes:
			if tt not in self.devList[devstr]["states"][state]:
				self.devList[devstr]["states"][state][tt] = {}
				
			for ss in tagsMMA:
				if ss not in self.devList[devstr]["states"][state][tt]:
					self.devList[devstr]["states"][state][tt][ss] = {"use":False,"dateCount":[False,False,False]}

		for tt in self.devList[devstr]["states"][state]:
			if tt =="ignoreLess" or tt == "ignoreGreater": continue
			TTS= self.devList[devstr]["states"][state][tt]
			for ss in TTS:
				valuesDict[tt+tagsDateCount[0]] = False
				if self.devList[devstr]["states"][state][tt][ss]["use"]:
					valuesDict[tt+ss]= True
					valuesDict[tt+tagsDateCount[0]] = True
				else:   
					valuesDict[tt+ss]= False
					
		for state in self.devList[devstr]["states"]:   
				if "ignoreLess"    not in self.devList[devstr]["states"][state]:
					self.devList[devstr]["states"][state]["ignoreLess"]        =-9876543210.
				if "ignoreGreater" not in self.devList[devstr]["states"][state]:
					self.devList[devstr]["states"][state]["ignoreGreater"]     =+9876543210.


		valuesDict["ignoreLess"]    = str(self.devList[devstr]["states"][state]["ignoreLess"])
		valuesDict["ignoreGreater"] = str(self.devList[devstr]["states"][state]["ignoreGreater"])
		valuesDict["showM"]=True          
		return valuesDict                        


####-----------------   ---------
	def buttonConfirmCALLBACK(self,valuesDict="",typeId=""):                # Select only device/properties that are supported
		try:
			devstr= str(self.devID)
			if self.devOrVar=="Var":
				dev=indigo.variables[int(self.devID)]
			else:
				dev=indigo.devices[int(self.devID)]

			if devstr not in self.devList:
				self.devList[devstr] = {}
				
			self.devList[devstr]["devOrVar"]= self.devOrVar
		
			state = valuesDict["state"]
			for tt in  tagsTimes:
				use=False
				for ss in tagsMMA: 
					if valuesDict[tt+ss]:
						#self.ML.myLog( text= unicode(self.devList[devstr]) )
						self.devList[devstr]["states"][state][tt][ss]["use"]=True
						use=True
					else:    
						self.devList[devstr]["states"][state][tt][ss]["use"]=False
					if use:    
						uu= tagsDateCount[0]
						if valuesDict[tt+uu]:
							for vv in range(len(tagsDateCount)):
								self.devList[devstr]["states"][state][tt][ss]["dateCount"][vv]=True
						else:
							for vv in range(len(tagsDateCount)):
								#self.ML.myLog( text=" ss0  "+unicode(self.devList[devstr][state][tt]))
								self.devList[devstr]["states"][state][tt][ss]["dateCount"][vv]=False
			try:                    
				self.devList[devstr]["states"][state]["ignoreLess"]        =float(valuesDict["ignoreLess"])
			except:
				pass
			try:                    
				self.devList[devstr]["states"][state]["ignoreGreater"]     =float(valuesDict["ignoreGreater"])
			except:
				pass
					  
			self.saveNow=True
		
			self.printConfigCALLBACK(devstr=devstr)
		except  Exception, e:
			if len(unicode(e)) > 5:
				self.ML.myLog( errorType = u"bigErr", text ="error in  Line '%s' ;  error='%s'" % (sys.exc_traceback.tb_lineno, e))
		valuesDict["showM"]=False          

		return valuesDict



####----------------- main loop -- start  ---------
	def runConcurrentThread(self):

		self.dateLimits=[["2015-11-00 00:00:00","2015-12-00 00:00:00"],["2015-12-00 00:00:00","2015-12-12 00:00:00"]]
		self.firstDate="2015-11-00 00:00:00"
		self.hourLast       =999 # last hour
		self.dayLast        =999 # last day of month
		self.dayOfweekLast  =999 # last day of week
		self.weekLast       =999 # last week
		self.timeFormat="%Y-%m-%d-%H:%M:%S"
		nextQuerry=time.time()   -1
		lastSave=time.time()
		self.preSelectDevices()
		try:
			while self.quitNow =="":
				now=time.time()
				dd= datetime.datetime.now()
				day =dd.day         # day in month
				wDay=dd.weekday()   # day of week
				hour=dd.hour        # hour in day
				
				if now < nextQuerry:
					self.sleep(10)
					continue
					
				if hour != self.hourLast: # recalculate the limits
					self.doDateLimits() 
					self.hourLast= hour 
					self.preSelectDevices()  
					
					
				if self.saveNow or lastSave +600 < now:
					self.pluginPrefs["devList"] =json.dumps(self.devList)
					self.saveNow=False
					
					
				delList=[]    
				for devID in self.devList:
					if int(devID) >0:
						try:
							if self.devList[devID]["devOrVar"]=="Var":
								devName= indigo.variables[int(devID)].name
							else:                            
								devName= indigo.devices[int(devID)].name
						except  Exception, e:
							if unicode(e).find("timeout waiting") > -1:
								self.ML.myLog( text = u"in Line '%s' has error='%s'" % (sys.exc_traceback.tb_lineno, e))
								self.ML.myLog( text ="communication to indigo is interrupted")
								return
							self.ML.myLog( text=" error; device with indigoID = "+ str(devID) +" does not exist, removing from tracking") 
							delList.append(devID)
							continue
							   
#tagsTimes   =["thisHour","lastHour","thisDay","lastDay","thisWeek","lastWeek","thisMonth","lastMonth","last7Days"]
#tagsMMA     =["max","min","ave"]
#tagsDates   =["date","date","count"]
#self.devList[devstr]["states"][state]["tags"][ss][uu]=1
					ddd =self.devList[devID]["states"]
					for state in ddd:
						params=ddd[state]
						vn0= devName.replace(" ","_")+"_"+state.replace(" ","_")
						dataSQL= self.doSQL(devID,state,self.devList[devID]["devOrVar"])
						dataClean=self.removeDoublesInSQL(dataSQL,ddd[state]["ignoreLess"],ddd[state]["ignoreGreater"])
						values= self.calculate(dataClean)
						if self.ML.decideMyLog(u"Loop"): self.ML.myLog( text ="variName "+vn0)
						
						for tag in tagsTimes:
							if tag not in params: continue
							ii = tagsTimes.index(tag)
							
							for mma in tagsMMA:
								if mma not in params[tag]: continue
								if not params[tag][mma]["use"]: continue
								jj = tagsMMA.index(mma)
								value=values[ii]
								try:
									if abs(value[jj][0]) == 987654321000. : continue
									if value[jj][1] == "" : continue
									if value[jj][1] == 0 : continue
								except:
									pass    
								if self.ML.decideMyLog(u"Loop"): self.ML.myLog( text =tag+" "+unicode(value))
								try:
									vari = indigo.variables[vn0+"_"+tag+"_"+mma]
								except:
									try:
										indigo.variable.create(vn0+"_"+tag+"_"+mma,      "0", self.variFolderName)
									except:
										pass    
								indigo.variable.updateValue(vn0+"_"+tag+"_"+mma,          ("%6.1f"%(value[jj][0])).strip())
								if params[tag][mma]["dateCount"][jj]:
									xx = tagsDateCount[jj]
									try:
										vari = indigo.variables[vn0+"_"+tag+"_"+mma+"_"+xx]
									except:
										try:
											indigo.variable.create(vn0+"_"+tag+"_"+mma+"_"+xx,      "0",     self.variFolderName)
										except:
											pass    
									if xx.find("Count")>-1:    
										indigo.variable.updateValue(vn0+"_"+tag+"_"+mma+"_"+xx,   str(value[jj][1]))
									else:    
										indigo.variable.updateValue(vn0+"_"+tag+"_"+mma+"_"+xx,   str(value[jj][1]))
 
				nextQuerry= now+self.refreshRate        
						

				for devID in delList:
					del self.devList[devID]
				
				
				
				
			self.stopConcurrentCounter = 1
			serverPlugin = indigo.server.getPlugin(self.pluginId)
			serverPlugin.restart(waitUntilDone=False)
			self.sleep(1)
		except  Exception, e:
			if len(unicode(e)) > 5:
				self.ML.myLog( errorType = u"bigErr", text ="error in  Line '%s' ;  error='%s'" % (sys.exc_traceback.tb_lineno, e))
		self.pluginPrefs["devList"] =json.dumps(self.devList)
		self.quitNow =""
		return


####-----------------  do the calculations and sql statements  ---------
	def doDateLimits(self):
#       self.dateLimits=[["2015-11-00 00:00:00","2015-12-00 00:00:00"],["2015-12-00 00:00:00","2015-12-12 00:00:00"]]

		try:
			now=time.time()
			dd      = datetime.datetime.now()
			day     = dd.day         # day in month
			wDay    = dd.weekday()   # day of week
			hour    = dd.hour        # hour in day
			nDay    = dd.timetuple().tm_yday
			nDay7   = nDay-7
			self.firstDate =(dd-datetime.timedelta(dd.day+31,hours=dd.hour)).strftime(self.timeFormat)      # last day of 2 months ago so that we always get 2 months
		##-- hour:
			hour0= dd-datetime.timedelta(minutes=dd.minute,seconds=dd.second)
			# current hour
			dh0=hour0.strftime(self.timeFormat)
			dh1=(hour0+datetime.timedelta(hours=1)).strftime(self.timeFormat)
			self.dateLimits=[[dh0,dh1]]
			#lastHour
			dh1=dh0
			dh0=(hour0-datetime.timedelta(hours=1)).strftime(self.timeFormat)
			self.dateLimits.append([dh0,dh1])
			# current day
			day0= dd-datetime.timedelta(hours=dd.hour,minutes=dd.minute,seconds=dd.second)
			dh0=day0.strftime(self.timeFormat)
			dh1=(day0+datetime.timedelta(hours=24)).strftime(self.timeFormat)
			self.dateLimits.append([dh0,dh1])
			#last day
			dh1=day0.strftime(self.timeFormat)
			dh0=(day0-datetime.timedelta(days=1)).strftime(self.timeFormat)
			self.dateLimits.append([dh0,dh1])
			# this week 
			week0= dd-datetime.timedelta(days=dd.weekday(),hours=dd.hour,minutes=dd.minute,seconds=dd.second)
			dh0=week0.strftime(self.timeFormat)
			dh1=(dd+datetime.timedelta(hours=24)).strftime(self.timeFormat)
			self.dateLimits.append([dh0,dh1])
			#last week
			dh1=week0.strftime(self.timeFormat)
			dh0=(week0-datetime.timedelta(days=7)).strftime(self.timeFormat)
			self.dateLimits.append([dh0,dh1])
			# this months 
			month0= dd-datetime.timedelta(days=dd.day,hours=dd.hour,minutes=dd.minute,seconds=dd.second)
			dh0=month0.strftime(self.timeFormat)
			dh1=(dd+datetime.timedelta(hours=24)).strftime(self.timeFormat)
			self.dateLimits.append([dh0,dh1])
			#last lastMonth
			dh1=month0.strftime(self.timeFormat)
			dh0=(month0-datetime.timedelta(days=1))
			dh0=(month0-datetime.timedelta(days=dh0.day)).strftime(self.timeFormat)    
			self.dateLimits.append([dh0,dh1])
			#last 7 days
			day0= dd
			day7= day0 - datetime.timedelta(days=7,hours=dd.hour,minutes=dd.minute,seconds=dd.second) 
			dh1=dd.strftime(self.timeFormat)
			dh0=day7.strftime(self.timeFormat)
			self.dateLimits.append([dh0,dh1])

			if self.ML.decideMyLog(u"Loop"): 
				self.ML.myLog( text ="first-Date:  "+unicode(self.firstDate))
				self.ML.myLog( text ="date-limits: "+unicode(self.dateLimits))
		except  Exception, e:
			if len(unicode(e)) > 5:
				self.ML.myLog( errorType = u"bigErr", text ="error in  Line '%s' ;  error='%s'" % (sys.exc_traceback.tb_lineno, e))
		return 
					



####----------------- do the sql statement  ---------
	def doSQL(self,devId,state,devOrVar):               
		try:
			ii=0
			while ii<3:

				if devOrVar== "Dev":
					sql2 = state+" from device_history_"+str(devId)
				else:    
					sql2=" value from variable_history_"+str(devId)

				if self.liteOrPsql =="sqlite": 
					sql= "/usr/bin/sqlite3  -separator \";\" '"+self.indigoPath+ "logs/indigo_history.sqlite' \"select strftime('%Y-%m-%d-%H:%M:%S',ts,'localtime'), "
					sql4="  where ts > '"+ self.firstDate+"';\""
					cmd=sql+sql2+sql4

				else:    
					sql= self.liteOrPsqlString+ " -t -A -F ';' -c \"SELECT to_char(ts,'YYYY-mm-dd HH24:MI:ss'), "
					sql4="  where to_char(ts,'YYYY-mm-dd HH24:MI:ss') > '"+ self.firstDate+"'  ORDER by id  ;\""
					cmd=sql+sql2+sql4
					
				if self.ML.decideMyLog(u"Sql"): self.ML.myLog( text =cmd)
				p=subprocess.Popen(cmd,shell=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
				out=p.communicate()
				p.stdout.close()        
				p.stderr.close()        
				p.wait
				if unicode(out).find("ERROR")>-1:
					ii+=1
					self.sleep(1)
					continue
				break    
			dataOut=out[0]
			if self.ML.decideMyLog(u"Sql"): self.ML.myLog( text ="data-out: "+out[0][:300])
			if self.ML.decideMyLog(u"Sql"): self.ML.myLog( text ="err-out:  "+out[1][:300])
		except  Exception, e:
			if len(unicode(e)) > 5:
				self.ML.myLog( errorType = u"bigErr", text ="error in  Line '%s' ;  error='%s'" % (sys.exc_traceback.tb_lineno, e))
		
		return dataOut
		
####----------------- calculate ave min max for all  ---------
	def calculate(self,dataIn):             
		dataOut=[]
		line=""
		value=""
		try:
			ll= len(self.dateLimits)
			for ii in range(ll):
				dataOut.append( [ [-987654321000.,""],  [987654321000.,""],  [0.,0] ] )
			if len(dataIn) >1:     
				for line in dataIn:
					date=line[1]
					value=self.getNumber(line[0])
					if value =="x": continue
					if date == "": continue
					for ii in range(ll):
						try:
							 if  date  < self.dateLimits[ii][0]:  ## in date range?
								 dataOut[ii][0][0]=value;  dataOut[ii][0][1]=date  # min, datestamp
								 dataOut[ii][1][0]=value;  dataOut[ii][1][1]=date  # max, datestamp
								 dataOut[ii][2][0]=value;  dataOut[ii][2][1]=1    # sum for average, count
							 if  date  > self.dateLimits[ii][0] and  date <=  self.dateLimits[ii][1]:  ## in date range?
								 if dataOut[ii][0][0] < value:  dataOut[ii][0][0]=value;  dataOut[ii][0][1]=date  # min, datestamp
								 if dataOut[ii][1][0] > value:  dataOut[ii][1][0]=value;  dataOut[ii][1][1]=date  # max, datestamp
								 dataOut[ii][2][0]+=value; dataOut[ii][2][1]+=1    # sum for average, count
						except Exception, e:
							self.ML.myLog( text="error in  Line '%s' ;  error='%s'" % (sys.exc_traceback.tb_lineno, e))
							self.ML.myLog( text=unicode(line))
							self.ML.myLog( text=unicode(value))
							continue            
				for ii in range(ll):
						if  dataOut[ii][0][1] !="" and dataOut[ii][0][1] <   self.dateLimits[ii][0]: dataOut[ii][0][1] = self.dateLimits[ii][0]      
						if  dataOut[ii][1][1] !="" and dataOut[ii][1][1] <   self.dateLimits[ii][0]: dataOut[ii][1][1] = self.dateLimits[ii][0]      
						dataOut[ii][2][0]= dataOut[ii][2][0]/max(dataOut[ii][2][1],1)    # make average
		except  Exception, e:
			if len(unicode(e)) > 5:
				self.ML.myLog( errorType = u"bigErr", text ="error in  Line '%s' ;  error='%s'" % (sys.exc_traceback.tb_lineno, e))
		return dataOut

####----------------- prep sql return data  ---------
	def removeDoublesInSQL(self,dataLines,ignoreLess,ignoreGreater):    # remove doubles same date/timestamp            
		dataOut=[]
		try:
			dataIn=dataLines.split("\n")
			t= dataIn[0].split(";")
			if len(t)!=2: return []
			if self.ML.decideMyLog(u"Loop"): self.ML.myLog( text =unicode(t))
			date=t[0]
			try:
				value=self.getNumber(t[1])
			except:
				value=0.
			if value =="x": value=0.
	

			for line in dataIn:
				if len(line) < 20: continue
				line=line.split(";")
 
				if line[0] == date: 
					try:
						v=self.getNumber(line[1])
						if v =="x": continue
						if v > ignoreGreater:   continue
						if v < ignoreLess:      continue
						value=v
					except:
						pass    
					continue
					
				dataOut.append((value,date))
				try:
						v=self.getNumber(line[1])
						if v =="x": continue
						if v > ignoreGreater:   continue
						if v < ignoreLess:      continue
						value=v
						date=line[0]
				except:
						pass    
			if len(dataOut) >0:   
				if dataOut[len(dataOut)-1][0] !=date:   
					dataOut.append((value,date))   

 
			else:
				dataOut=[[0.,""]]                 
		except  Exception, e:
			if len(unicode(e)) > 5:
				self.ML.myLog( errorType = u"bigErr", text ="error in  Line '%s' ;  error='%s'" % (sys.exc_traceback.tb_lineno, e))
		

		return dataOut


####-----------------   ---------
	def preSelectDevices(self):             # Select only device/properties that are supported:  numbers, bool, but not props that have "words"
		self.listOfPreselectedDevices=[]
		self.devIdToTypeandName={}


		for theVar in indigo.variables:
			val = theVar.value
			x = self.getNumber(val)
			if x !="x":
				try:
					self.listOfPreselectedDevices.append((str(theVar.id)+"-V", "Var-"+unicode(theVar.name)))
				except  Exception, e:
					self.ML.myLog( errorType = u"bigErr", text ="Line '%s' has error='%s'" % (sys.exc_traceback.tb_lineno, e))
		#self.ML.myLog( text="after var: "+ unicode(self.listOfPreselectedDevices)))

		for dev in indigo.devices.iter():
			theStates = dev.states.keys()
			count =0
			for test in theStates:
				try:
					if "Mode" in test or "All" in test or ".ui" in test:
						skip= True
					else:
						skip= False
				except:
					skip=False
				if not skip:    
					val= dev.states[test]
					x = self.getNumber(val)
					if x!="x" :
						count +=1
			if count>0:                                                 # add to the selection list
				try:
					self.listOfPreselectedDevices.append((dev.id, dev.name))                ## give all id's and names of  devices that have at least one of the keys we can track
				except  Exception, e:
					self.ML.myLog( errorType = u"bigErr", text ="Line '%s' has error='%s'" % (sys.exc_traceback.tb_lineno, e))
		return





####----------------- get path to indigo programs ---------
	def getNumber(self,val):
	# test if a val contains a valid number, if not return ""
	# return the number if any meaningful number (with letters before and after return that number)
	# u"a-123.5e" returns -123.5
	# -1.3e5 returns -130000.0
	# -1.3e-5 returns -0.000013
	# u"1.3e-5" returns -0.000013
	# u"1.3e-5x" returns "" ( - sign not first position  ..need to include)
	# True, u"truE" u"on" "ON".. returns 1.0;  False u"faLse" u"off" returns 0.0
	# u"1 2 3" returns ""
	# u"1.2.3" returns ""
	# u"12-5" returns ""
		try:
			return                                                           float(val)
		except:
			if type(val) is bool                                           : return 1.0 if val else 0.0
		if val ==""                                                        : return "x"
		try:
			xx = ''.join([c for c in val if c in '-1234567890.'])                               # remove non numbers 
			lenXX= len(xx)
			if lenXX > 0:                                                                       # found numbers..
				if len( ''.join([c for c in xx if c in '.']) )           >1: return "x"         # remove strings that have 2 or more dots " 5.5 6.6"
				if len( ''.join([c for c in xx if c in '-']) )           >1: return "x"         # remove strings that have 2 or more -    " 5-5 6-6"
				if len( ''.join([c for c in xx if c in '1234567890']) ) ==0: return "x"         # remove strings that just no numbers, just . amd - eg "abc.xyz- hij"
				if lenXX ==1                                               : return float(xx)   # just one number
				if xx.find("-") > 0                                        : return "x"         # reject if "-" is not in first position
				valList = list(val)                                                             # make it a list
				count = 0                                                                       # count number of numbers
				for i in range(len(val)-1):                                                     # reject -0 1 2.3 4  not consecutive numbers:..
					if (len(''.join([c for c in valList[i] if c in '-1234567890.'])) ==1 ):     # check if this character is a number, if yes:
						count +=1                                                               # 
						if count >= lenXX                                   : break             # end of # of numbers, end of test: break, its a number
						if (len(''.join([c for c in valList[i+1] if c in '-1234567890.'])) )== 0: return "x" #  next is not a number and not all numbers accounted for, so it is numberXnumber
				return                                                      float(xx)           # must be a real number, everything else is excluded
			else:                                                                               # only text left,  no number in this string
				 return "x"                                                                     # all tests failed ... nothing there, return "
		except:
			return "x"                                                                          # something failed eg unicode only ==> return ""
		return "x"                                                                              # should not happen just for safety
