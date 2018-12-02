#! /usr/bin/env python
# -*- coding: utf-8 -*-
####################
# Plugin miMax
# Developed by Karl Wachs
# karlwachs@me.com
# last change dec 14, 2015

import os, sys, subprocess, pwd
import datetime
import time
import simplejson as json
#from time import strftime
import urllib
import fcntl
import signal
import copy
import myLogPgms.myLogPgms 

import cProfile
import pstats




'''
how it works:
user selects dates from to and the devces/ states or variables to track 
the main loop check the sqllogger db every x minutes and build the min/max/averages ...  for each device/state/variable and fills 
device_state_Min  .. Max   Ave DateMin DateMax Count Count1 with the values. 
'''

_tagsTimes     =["thisHour","lastHour","thisDay","lastDay","thisWeek","lastWeek","thisMonth","lastMonth","last7Days"]
_tagsMMA       =["Min","Max","DateMin","DateMax","Ave","Count","Count1"]

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

		self.epoch = datetime.datetime(1970, 1, 1)

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
		self.timeFormatInternal	= "%Y-%m-%d-%H:%M:%S"
		self.refreshRate        = float(self.pluginPrefs.get("refreshRate",5))
		self.liteOrPsql         = self.pluginPrefs.get(     "liteOrPsql",       "sqlite")
		self.liteOrPsqlString   = self.pluginPrefs.get(     "liteOrPsqlString", "/Library/PostgreSQL/bin/psql indigo_history postgres ")
		self.timeFormatDisplay  = self.pluginPrefs.get(     "timeFormatDisplay", self.timeFormatInternal)
		self.devList            = json.loads(self.pluginPrefs.get("devList","{}"))

		self.checkcProfile()

		self.ML = myLogPgms.myLogPgms.MLX()
		self.setLogfile(unicode(self.pluginPrefs.get("logFileActive2", "standard")))

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
			#self.ML.myLog( text="devId devList "+ str(devId)+ " " +unicosde(self.devList[devId]) )
			if "states" not in self.devList[devId]: continue
			for state in self.devList[devId]["states"]:   
				if "ignoreLess"    not in self.devList[devId]["states"][state]:
						self.devList[devId]["states"][state]["ignoreLess"]			= -9876543210.
				if "ignoreGreater" not in self.devList[devId]["states"][state]:
						self.devList[devId]["states"][state]["ignoreGreater"]		= +9876543210.
				if "measures" not in self.devList[devId]["states"][state]:
						self.devList[devId]["states"][state]["measures"] 			= {}
				if "formatNumbers" not in self.devList[devId]["states"][state]:
						self.devList[devId]["states"][state]["formatNumbers"] 		= "%.1f"
				if "timeFormatDisplay" not in self.devList[devId]["states"][state]:
						self.devList[devId]["states"][state]["timeFormatDisplay"] 	= self.timeFormatInternal
				if "shortName" not in self.devList[devId]["states"][state]:
						self.devList[devId]["states"][state]["shortName"] 			= ""

		self.variFolderName			= self.pluginPrefs.get("variFolderName","minMax")
		self.saveNow				= False
		self.devIDSelected					= 0
		self.devIDSelectedExist				= 0
		self.devOrVarExist			= "Var"
		self.devOrVar				= "Var"
		self.quitNow				= "" # set to !="" when plugin should exit ie to restart, needed for subscription -> loop model
		self.stopConcurrentCounter	= 0
		self.pluginPrefs["devList"]	= json.dumps(self.devList)
		self.dateLimits				= [["2015-11-00-00:00:00","2015-12-00-00:00:00",0,0],["2015-12-00-00:00:00","2015-12-12-00:00:00",0,0]]
		self.firstDate				= "2015-11-00-00:00:00"
		self.hourLast				= 999 # last hour
		self.dayLast				= 999 # last day of month
		self.dayOfweekLast			= 999 # last day of week
		self.weekLast				= 999 # last week

		self.printConfigCALLBACK()
		return

####-----------------   ---------
	####-----------------    ---------
	def setLogfile(self,lgFile):
		self.logFileActive =lgFile
		if   self.logFileActive =="standard":   self.logFile = ""
		elif self.logFileActive =="indigo":     self.logFile = self.indigoPath.split("Plugins/")[0]+"Logs/"+self.pluginId+"/plugin.log"
		else:                                   self.logFile = self.userIndigoPluginDir +"plugin.log"
		self.ML.myLogSet(debugLevel = self.debugLevel ,logFileActive=self.logFileActive, logFile = self.logFile)
		self.ML.myLog( text="Date format: "+ self.timeFormatDisplay +" ==> "+ (datetime.datetime.now()).strftime(self.timeFormatDisplay), destination="standard" )

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
		self.ML.myLog( text=u"stopConcurrentThread called " + str(self.stopConcurrentCounter), destination="standard" )
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
		self.timeFormatDisplay  = valuesDict["timeFormatDisplay"]

		try:
			indigo.variables.folder.create(self.variFolderName)
		except:
			pass
		return True, valuesDict


####-----------------   ---------
	def dummyCALLBACK(self):
		
		return
####-----------------   ---------
	def printConfigCALLBACK(self, printDevId=""):
		try:
			self.ML.myLog( text="Configuration: ... date format: "+ self.timeFormatDisplay +" ==> "+ (datetime.datetime.now()).strftime(self.timeFormatDisplay), destination="standard"  )
			self.ML.myLog( text="Dev-Name-----                   DevID            State       ignoreLess   ignoreGreater  format tracking measures: -------", destination="standard" )
			for devId in self.devList:
				if devId == printDevId or printDevId=="":
					for state in self.devList[devId]["states"]:
						out="  "+"%15.0f"%self.devList[devId]["states"][state]["ignoreLess"]+" "+"%15.0f"%(self.devList[devId]["states"][state]["ignoreGreater"])+(" '"+self.devList[devId]["states"][state]["formatNumbers"]+"'").rjust(8)+" "
						measures =""
						for tt in self.devList[devId]["states"][state]["measures"]:
							for ss in self.devList[devId]["states"][state]["measures"][tt]:
								##indigo.server.log( state+"  "+ tt+"  "+ss+" "+unicode(self.devList[devId]["states"][state]["measures"][tt][ss]))
								if  self.devList[devId]["states"][state]["measures"][tt][ss]:
									measures+= tt+"_"+ss+" "
						if measures == "":
							measures ="--- no measure selected, no variable will be created---"
						if self.devList[devId]["devOrVar"]=="Var":           
							self.ML.myLog( text= indigo.variables[int(devId)].name.ljust(25) +"; "+devId.ljust(10)+"; "+state.rjust(15)+out+measures, destination="standard"  )
						else:           
							self.ML.myLog( text= indigo.devices[int(devId)].name.ljust(25) +"; "+devId.ljust(10)+"; "+state.rjust(15)+ out+measures, destination="standard"  )
		except  Exception, e:
			if len(unicode(e)) > 5:
				self.ML.myLog( text= "printConfigCALLBACK error in  Line '%s' ;  error='%s'" % (sys.exc_traceback.tb_lineno, e), destination="standard" )
			self.ML.myLog( text=unicode(self.devList))
		return



####-----------------  ---------
	def getMenuActionConfigUiValues(self, menuId):
		
		valuesDict=indigo.Dict()
		if menuId == "defineDeviceStates":
			for tt in _tagsTimes:
				for ss in _tagsMMA:
					valuesDict[tt+ss]	= False
				valuesDict[tt+"Date"]	= False
			valuesDict["showM"]			= False          
			valuesDict["ignoreGreater"]	= "+9876543210."
			valuesDict["ignoreLess"]	= "-9876543210."
			valuesDict["MSG"]   		= ""

		return valuesDict




########### --- delete dev/states from tracking 
####-----------------   ---------
	def pickExistingDeviceCALLBACK(self,valuesDict="",typeId=""):               # Select only device/properties that are supported
		if self.ML.decideMyLog(u"Setup"): self.ML.myLog( text =unicode(valuesDict))
		if valuesDict["device"].find("-V") >-1:
			self.devOrVarExist="Var"
			self.devIDSelectedExist= int(valuesDict["device"][:-2])# drop -V
		else:        
			self.devIDSelectedExist= int(valuesDict["device"])
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
		devId= str(self.devIDSelectedExist)
		retList=[]
		if devId in self.devList:
			if self.devOrVarExist =="Var":
				retList.append(("value", "value"))
				return retList
			for test in self.devList[devId]["states"]:
				retList.append((test,test))             
		return retList
####-----------------   ---------
	def buttonRemoveCALLBACK(self,valuesDict="",typeId=""):               # Select only device/properties that are supported
		devId= str(self.devIDSelectedExist)
		state= valuesDict["state"]
		if devId in self.devList:
			if  state in self.devList[devId]["states"]:
				del self.devList[devId]["states"][state]
			if len(self.devList[devId]["states"]) ==0:
				del self.devList[devId]
		self.devIDSelectedExist 	= 0
		valuesDict["state"] = ""
		self.preSelectDevices()
		return valuesDict




########### --- add dev/states to tracking 
####-----------------   ---------
	def pickDeviceCALLBACK(self,valuesDict="",typeId=""):               # Select only device/properties that are supported
		if self.ML.decideMyLog(u"Setup"): self.ML.myLog( text =unicode(valuesDict))
		if valuesDict["device"].find("-V") >-1:
			self.devOrVar="Var"
			self.devIDSelected= int(valuesDict["device"][:-2])# drop -V
		else:        
			self.devIDSelected= int(valuesDict["device"])
			self.devOrVar="Dev"


####-----------------   ---------
	def filterDevicesThatQualify(self,filter="",valuesDict="",typeId=""):               
		retList= copy.copy(self.listOfPreselectedDevices )
		for devId in self.devList:
			if self.devList[devId]["devOrVar"] == "Var":
				try: retList.append([devId,"=v="+indigo.variables[int(devId)].name])
				except: pass
			else:
				try: retList.append([devId,"=D="+indigo.devices[int(devId)].name])
				except: pass
		return retList


####-----------------   ---------
	def filterStatesThatQualify(self,filter="",valuesDict="",typeId=""):                
	
		if self.devIDSelected ==0: return [(0,0)]

		retList=[]
		if self.devOrVar =="Var":
			retList.append(("value", "value"))
			return retList
		
		dev=indigo.devices[self.devIDSelected]
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
		devId= str(self.devIDSelected)
		if self.devOrVar=="Var":
			dev=indigo.variables[int(self.devIDSelected)]
		else:
			dev=indigo.devices[int(self.devIDSelected)]
		
		state= valuesDict["state"]
		if devId not in  self.devList:
			self.devList[devId]={}
			self.devList[devId]["states"]={}

		self.devList[devId]["devOrVar"]=self.devOrVar

		if  "states" not in self.devList[devId]:
			self.devList[devId]["states"]={}

			
		if  state not in self.devList[devId]["states"]:
			self.devList[devId]["states"][state]={}

		if  "measures" not in self.devList[devId]["states"][state]:
			self.devList[devId]["states"][state]["measures"]		= {}
			self.devList[devId]["states"][state]["ignoreLess"]		= -9876543210.
			self.devList[devId]["states"][state]["ignoreGreater"]	= +9876543210.
			self.devList[devId]["states"][state]["formatNumbers"]	= "%.1f"
			
		for tt in _tagsTimes:
			if tt not in self.devList[devId]["states"][state]["measures"]:
				self.devList[devId]["states"][state]["measures"][tt] = {}
				
			for ss in _tagsMMA:
				if ss not in self.devList[devId]["states"][state]["measures"][tt]:
					self.devList[devId]["states"][state]["measures"][tt][ss] = False

		for tt in self.devList[devId]["states"][state]["measures"]:
			TTS= self.devList[devId]["states"][state]["measures"][tt]
			for ss in TTS:
				if self.devList[devId]["states"][state]["measures"][tt][ss]:
					valuesDict[tt+ss]= True
				else:   
					valuesDict[tt+ss]= False
					


		valuesDict["ignoreLess"]    = str(self.devList[devId]["states"][state]["ignoreLess"])
		valuesDict["ignoreGreater"] = str(self.devList[devId]["states"][state]["ignoreGreater"])
		valuesDict["formatNumbers"] =    (self.devList[devId]["states"][state]["formatNumbers"])
		valuesDict["shortName"] 	=    (self.devList[devId]["states"][state]["shortName"])
		valuesDict["showM"]=True          
		return valuesDict                        


####-----------------   ---------
	def buttonConfirmCALLBACK(self,valuesDict="",typeId=""):                # Select only device/properties that are supported
		try:
			valuesDict["MSG"] = "ok"
			devId= str(self.devIDSelected)
			if self.devOrVar=="Var":
				dev=indigo.variables[int(self.devIDSelected)]
			else:
				dev=indigo.devices[int(self.devIDSelected)]

			if devId not in self.devList:
				self.devList[devId] = {}
				
			self.devList[devId]["devOrVar"]= self.devOrVar
		
			state = valuesDict["state"]
			if "states" not in self.devList[devId]:
				self.devList[devId]["states"] ={}
				
			if state not in self.devList[devId]["states"]:
				self.devList[devId]["states"][state] ={}

			if "measures" not in self.devList[devId]["states"][state]:
				self.devList[devId]["states"][state]["measures"]		= {}
				self.devList[devId]["states"][state]["ignoreLess"]		= -9876543210.
				self.devList[devId]["states"][state]["ignoreGreater"]	= +9876543210.
				self.devList[devId]["states"][state]["formatNumbers"]	= "%.1f"
				self.devList[devId]["states"][state]["shortName"]		= ""
				
			anyOne = False
			for tt in  _tagsTimes:
				use=False
				for ss in _tagsMMA: 
					if valuesDict[tt+ss]:
						#self.ML.myLog( text= unicode(self.devList[devId]) )
						self.devList[devId]["states"][state]["measures"][tt][ss]=True
						anyOne = True
					else:    
						self.devList[devId]["states"][state]["measures"][tt][ss]=False

			try: 	self.devList[devId]["states"][state]["ignoreLess"]		= float(valuesDict["ignoreLess"])
			except:	pass
			try:	self.devList[devId]["states"][state]["ignoreGreater"]	= float(valuesDict["ignoreGreater"])
			except:	pass
			self.devList[devId]["states"][state]["formatNumbers"]			= valuesDict["formatNumbers"]

			self.devList[devId]["states"][state]["shortName"]				= valuesDict["shortName"].replace(" ","_")

			self.saveNow=True
			self.preSelectDevices()

			self.printConfigCALLBACK(printDevId=devId)
		except  Exception, e:
			if len(unicode(e)) > 5:
				self.ML.myLog( errorType = u"bigErr", text ="error in  Line '%s' ;  error='%s'" % (sys.exc_traceback.tb_lineno, e), destination="standard" )
		valuesDict["showM"]=False          
		if not anyOne: valuesDict["MSG"] ="no measure selected-- no variable will be cretaed"

		return valuesDict



	###########################	   cProfile stuff   ############################ START
	####-----------------  ---------
	def getcProfileVariable(self):

		try:
			if self.timeTrVarName in indigo.variables:
				xx = (indigo.variables[self.timeTrVarName].value).strip().lower().split("-")
				if len(xx) ==1: 
					cmd = xx[0]
					pri = ""
				elif len(xx) == 2:
					cmd = xx[0]
					pri = xx[1]
				else:
					cmd = "off"
					pri  = ""
				self.timeTrackWaitTime = 20
				return cmd, pri
		except	Exception, e:
			pass

		self.timeTrackWaitTime = 60
		return "off",""

	####-----------------            ---------
	def printcProfileStats(self,pri=""):
		try:
			if pri !="": pick = pri
			else:		 pick = 'cumtime'
			outFile		= self.userIndigoPluginDir+"timeStats"
			indigo.server.log(" print time track stats to: "+outFile+".dump / txt  with option: "+pick)
			self.pr.dump_stats(outFile+".dump")
			sys.stdout 	= open(outFile+".txt", "w")
			stats 		= pstats.Stats(outFile+".dump")
			stats.strip_dirs()
			stats.sort_stats(pick)
			stats.print_stats()
			sys.stdout = sys.__stdout__
		except: pass
		"""
		'calls'			call count
		'cumtime'		cumulative time
		'file'			file name
		'filename'		file name
		'module'		file name
		'pcalls'		primitive call count
		'line'			line number
		'name'			function name
		'nfl'			name/file/line
		'stdname'		standard name
		'time'			internal time
		"""

	####-----------------            ---------
	def checkcProfile(self):
		try: 
			if time.time() - self.lastTimegetcProfileVariable < self.timeTrackWaitTime: 
				return 
		except: 
			self.cProfileVariableLoaded = 0
			self.do_cProfile  			= "x"
			self.timeTrVarName 			= "enableTimeTracking_"+self.pluginShortName
			indigo.server.log("testing if variable "+self.timeTrVarName+" is == on/off/print-option to enable/end/print time tracking of all functions and methods (option:'',calls,cumtime,pcalls,time)")

		self.lastTimegetcProfileVariable = time.time()

		cmd, pri = self.getcProfileVariable()
		if self.do_cProfile != cmd:
			if cmd == "on": 
				if  self.cProfileVariableLoaded ==0:
					indigo.server.log("======>>>>   loading cProfile & pstats libs for time tracking;  starting w cProfile ")
					self.pr = cProfile.Profile()
					self.pr.enable()
					self.cProfileVariableLoaded = 2
				elif  self.cProfileVariableLoaded >1:
					self.quitNow = " restart due to change  ON  requested for print cProfile timers"
			elif cmd == "off" and self.cProfileVariableLoaded >0:
					self.pr.disable()
					self.quitNow = " restart due to  OFF  request for print cProfile timers "
		if cmd == "print"  and self.cProfileVariableLoaded >0:
				self.pr.disable()
				self.printcProfileStats(pri=pri)
				self.pr.enable()
				indigo.variable.updateValue(self.timeTrVarName,"done")

		self.do_cProfile = cmd
		return 

	####-----------------            ---------
	def checkcProfileEND(self):
		if self.do_cProfile in["on","print"] and self.cProfileVariableLoaded >0:
			self.printcProfileStats(pri="")
		return
	###########################	   cProfile stuff   ############################ END



####-----------------   main loop          ---------
	def runConcurrentThread(self):

		self.dorunConcurrentThread()
		self.checkcProfileEND()

		self.stopConcurrentCounter = 1
		serverPlugin = indigo.server.getPlugin(self.pluginId)
		serverPlugin.restart(waitUntilDone=False)

		self.sleep(1)
		if self.quitNow !="":
			indigo.server.log( u"runConcurrentThread stopping plugin due to:  ::::: " + self.quitNow + " :::::")
			serverPlugin = indigo.server.getPlugin(self.pluginId)
			serverPlugin.restart(waitUntilDone=False)

		return

####-----------------   main loop            ---------
	def dorunConcurrentThread(self): 

		
		nextQuerry				= time.time()   -1
		lastSave				= time.time()
		self.preSelectDevices()
		try:
			while self.quitNow =="":
				for ii in range(20):
					self.sleep(1)
					
				now=time.time()

				if now < nextQuerry: 		continue

				dd= datetime.datetime.now()
				day =dd.day         # day in month
				wDay=dd.weekday()   # day of week
				hour=dd.hour        # hour in day

				if hour != self.hourLast: # recalculate the limits
					self.doDateLimits() 
					self.hourLast= hour 
					self.preSelectDevices()  

				if self.saveNow or lastSave +600 < now:
					self.pluginPrefs["devList"] =json.dumps(self.devList)
					self.saveNow=False


				self.fillVariables()

				nextQuerry= now+self.refreshRate        
	

				
		except : pass
		self.pluginPrefs["devList"] =json.dumps(self.devList)
		return



####-----------------  do the calculations and sql statements  ---------
	def fillVariables(self):

		delList =[]
		try:
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
						   
				#_tagsTimes   =["thisHour","lastHour","thisDay","lastDay","thisWeek","lastWeek","thisMonth","lastMonth","last7Days"]
				#_tagsMMA     =["Min","Max","DateMin","DateMax","Ave","Count","Count1"]
				ddd =self.devList[devID]["states"]
				for state in ddd:

					if self.devList[devID]["states"][state]["shortName"] !="":
						varName	= self.devList[devID]["states"][state]["shortName"]
					else:
						varName	= devName.replace(" ","_")+"_"+state.replace(" ","_")
						
					params		= ddd[state]
					dataSQL		= self.doSQL(devID,state,self.devList[devID]["devOrVar"])
					dataClean	= self.removeDoublesInSQL(dataSQL,ddd[state]["ignoreLess"],ddd[state]["ignoreGreater"])
					values		= self.calculate(dataClean)

					if self.ML.decideMyLog(u"Loop"): self.ML.myLog( text ="variName "+vn0)
					#if self.ML.decideMyLog(u"Loop"): self.ML.myLog( text ="dataSQL   " +unicode(dataSQL)[0:500])
					#if self.ML.decideMyLog(u"Loop"): self.ML.myLog( text ="dataClean " +unicode(dataClean)[0:500])
					if self.ML.decideMyLog(u"Loop"): self.ML.myLog( text ="values    " +unicode(values)[0:500])
					if self.ML.decideMyLog(u"Loop"): self.ML.myLog( text =";   state: "+ state+" params: "+unicode(params)+" "+unicode(values)[0:30])

					for tag in values:
						if tag not in params["measures"]: continue
						
						value=values[tag]
						if self.ML.decideMyLog(u"Loop"): self.ML.myLog( text ="tag    " + tag+" "+unicode(value))
						
						for mma in _tagsMMA:
							if mma not in params["measures"][tag]: continue
							if not params["measures"][tag][mma]: continue

							try: 	vari = indigo.variables[varName+"_"+tag+"_"+mma]
							except:
								try:	indigo.variable.create(varName+"_"+tag+"_"+mma,      "", self.variFolderName)
								except:	pass

							if  mma.find("Count")>-1:
								indigo.variable.updateValue(varName+"_"+tag+"_"+mma,          ("%d"%(value[mma])).strip())
							elif mma.find("Date")>-1:
								indigo.variable.updateValue(varName+"_"+tag+"_"+mma,          value[mma].strip())
							else:
								indigo.variable.updateValue(varName+"_"+tag+"_"+mma,          (params["formatNumbers"]%(value[mma])).strip())
								
			for devID in delList:
				del self.devList[devID]
		except  Exception, e:
			if len(unicode(e)) > 5:
				self.ML.myLog( errorType = u"bigErr", text ="fillVariables: error in  Line '%s' ;  error='%s'" % (sys.exc_traceback.tb_lineno, e), destination="standard" )


####-----------------  do the calculations and sql statements  ---------
	def doDateLimits(self):
#       self.dateLimits=[["2015-11-00 00:00:00","2015-12-00 00:00:00"],["2015-12-00 00:00:00","2015-12-12 00:00:00"]]

		try:
			now				= time.time()
			dd				= datetime.datetime.now()
			day				= dd.day         # day in month
			wDay			= dd.weekday()   # day of week
			hour			= dd.hour        # hour in day
			nDay			= dd.timetuple().tm_yday
			nDay7			= nDay-7
			self.dateLimits	= {}
			self.firstDate 	= (dd-datetime.timedelta(dd.day+31,hours=dd.hour)).strftime(self.timeFormatInternal)      # last day of 2 months ago so that we always get 2 months

			hour0= dd-datetime.timedelta(minutes=dd.minute,seconds=dd.second)
			dh0=hour0.strftime(self.timeFormatInternal)
			dh1=(hour0+datetime.timedelta(hours=1)).strftime(self.timeFormatInternal)
			self.dateLimits["thisHour"] = [dh0,dh1,0,0,0]

			dh1=dh0
			dh0=(hour0-datetime.timedelta(hours=1)).strftime(self.timeFormatInternal)
			self.dateLimits["lastHour"] = [dh0,dh1,0,0,0]

			day0= dd-datetime.timedelta(hours=dd.hour,minutes=dd.minute,seconds=dd.second)
			dh0=day0.strftime(self.timeFormatInternal)
			dh1=(day0+datetime.timedelta(hours=24)).strftime(self.timeFormatInternal)
			self.dateLimits["thisDay"] = [dh0,dh1,0,0,0]

			dh1=day0.strftime(self.timeFormatInternal)
			dh0=(day0-datetime.timedelta(days=1)).strftime(self.timeFormatInternal)
			self.dateLimits["lastDay"] = [dh0,dh1,0,0,0]

			week0= dd-datetime.timedelta(days=dd.weekday(),hours=dd.hour,minutes=dd.minute,seconds=dd.second)
			dh0=week0.strftime(self.timeFormatInternal)
			dh1=(dd+datetime.timedelta(hours=24)).strftime(self.timeFormatInternal)
			self.dateLimits["thisWeek"] = [dh0,dh1,0,0,0]

			dh1=week0.strftime(self.timeFormatInternal)
			dh0=(week0-datetime.timedelta(days=7)).strftime(self.timeFormatInternal)
			self.dateLimits["lastWeek"] = [dh0,dh1,0,0,0]

			month0= dd-datetime.timedelta(days=dd.day,hours=dd.hour,minutes=dd.minute,seconds=dd.second)
			dh0=month0.strftime(self.timeFormatInternal)
			dh1=(dd+datetime.timedelta(hours=24)).strftime(self.timeFormatInternal)
			self.dateLimits["thisMonth"] = [dh0,dh1,0,0,0]

			dh1=month0.strftime(self.timeFormatInternal)
			dh0=(month0-datetime.timedelta(days=1))
			dh0=(month0-datetime.timedelta(days=dh0.day)).strftime(self.timeFormatInternal)    
			self.dateLimits["lastMonth"] = [dh0,dh1,0,0,0]

			day0= dd
			day7= day0 - datetime.timedelta(days=7,hours=dd.hour,minutes=dd.minute,seconds=dd.second) 
			dh1=dd.strftime(self.timeFormatInternal)
			dh0=day7.strftime(self.timeFormatInternal)
			self.dateLimits["last7Days"] = [dh0,dh1,0,0,0]


			for tag in self.dateLimits:
				self.dateLimits[tag][2] = (datetime.datetime.strptime(self.dateLimits[tag][0], self.timeFormatInternal)-self.epoch).total_seconds()
				self.dateLimits[tag][3] = (datetime.datetime.strptime(self.dateLimits[tag][1], self.timeFormatInternal)-self.epoch).total_seconds()
				self.dateLimits[tag][4] = max(1.,self.dateLimits[tag][3] - self.dateLimits[tag][2])

			if self.ML.decideMyLog(u"Loop"): 
				self.ML.myLog( text ="first-Date:  "+unicode(self.firstDate))
				self.ML.myLog( text ="date-limits: "+unicode(self.dateLimits))
		except  Exception, e:
			if len(unicode(e)) > 5:
				self.ML.myLog( errorType = u"bigErr", text ="error in  Line '%s' ;  error='%s'" % (sys.exc_traceback.tb_lineno, e), destination="standard" )
		return 
					



####----------------- do the sql statement  ---------
	def doSQL(self,devId,state,devOrVar): 
		dataOut = []
		ii 		= 0
		try:
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
					sql= self.liteOrPsqlString+ " -t -A -F ';' -c \"SELECT to_char(ts,'YYYY-mm-dd-HH24:MI:ss'), "
					sql4="  where to_char(ts,'YYYY-mm-dd-HH24:MI:ss') > '"+ self.firstDate+"'  ORDER by id  ;\""
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
			dataOut = out[0]
			if self.ML.decideMyLog(u"Sql"): self.ML.myLog( text ="data-out: "+out[0][:300])
			if self.ML.decideMyLog(u"Sql"): self.ML.myLog( text ="err-out:  "+out[1][:300])
		except  Exception, e:
			if len(unicode(e)) > 5:
				self.ML.myLog( errorType = u"bigErr", text ="error in  Line '%s' ;  error='%s'" % (sys.exc_traceback.tb_lineno, e), destination="standard" )
		
		return dataOut
		
####----------------- calculate ave min max for all  ---------
	def calculate(self,dataIn):             
		line				= ""
		value				= ""
		addedSecsForLastBin	= 90.
		dataOut 			= {}
		dateErrorShown 		= False
		for tag in self.dateLimits:
			dataOut[tag] = {"Min": -987654321000.,"Max":987654321000.,"DateMin":"","DateMax":"","Count": 0.,"Count1":0,"Ave":0,"AveSimple":0}
		try:

			nData = len(dataIn)
			if nData > 0:

				if dataIn[nData-1][1] !="":
					lastSecInData = (   datetime.datetime.strptime(dataIn[nData-1][1], self.timeFormatInternal) - self.epoch   ).total_seconds() 
				else:
					lastSecInData = int(time.time())

				for nn in range(nData):
					line = dataIn[nn]
					date	= line[1]
					if date == "": continue
					value	= self.getNumber(line[0])
					##self.ML.myLog(text =date+"  "+ unicode(value))
					if value =="x": continue

					secondsStartD	= (datetime.datetime.strptime(date, self.timeFormatInternal)-self.epoch).total_seconds()
					if nn < nData-1:
						lastData = False
						secondsEndD	= (datetime.datetime.strptime(dataIn[nn+1][1], self.timeFormatInternal)-self.epoch).total_seconds()
						dateNext   = dataIn[nn+1][1]
					else: 				
						lastData = True
						secondsEndD	= lastSecInData +addedSecsForLastBin # last measurement point + 90 secs 
						dateNext 	= "9999-12-01-12:33:12"

					for tag in self.dateLimits:
						try:
							if dateNext < self.dateLimits[tag][0]: continue

#							_tagsMMA       =["Min","Max","DateMin","DateMax","Ave","Count","Count1"]
						#                         # of seconds in bin                                     +90secs    last sec in bin           fist sec in bin  == dont take whole bin otherwise last value is overweighted
							detalSecTotal	= max( 1., min(self.dateLimits[tag][4],   min(lastSecInData+addedSecsForLastBin, self.dateLimits[tag][3]) - self.dateLimits[tag][2]  ) )
							secondsEnd   	= min(secondsEndD,  self.dateLimits[tag][3]) 
							# first data point?
							norm = 1.0
							if  date  < self.dateLimits[tag][0] and dataOut[tag]["Count"] <= 1:  ## use last below date range?
								dataOut[tag]["Min"] 				= value 				# min
								dataOut[tag]["DateMin"] 			= date  				# datestamp

								dataOut[tag]["Max"] 				= value 				# max 
								dataOut[tag]["DateMax"] 			= date  				# datestamp

								if not lastData: norm 				= (secondsEnd - self.dateLimits[tag][2])/detalSecTotal 
								dataOut[tag]["Ave"]					= value * norm			# time weighted average
								dataOut[tag]["Count"]				= 1    					# count
								dataOut[tag]["AveSimple"]			= value					# sum for simple average
								if value >0: dataOut[tag]["Count1"]	+= 1					# count if > 0
	
							# regular datapoint in bin
							if date  > self.dateLimits[tag][0] and  date <=  self.dateLimits[tag][1]:  ## in date range?
								if dataOut[tag]["Min"] > value:
									dataOut[tag]["Min"] 			= value				# min 
									dataOut[tag]["DateMin"] 		= date				# datestamp

								if dataOut[tag]["Max"] < value:
									dataOut[tag]["Max"] 			= value				# max  
									dataOut[tag]["DateMax"]			= date				# datestamp
	
								norm 								= (secondsEnd - secondsStartD)/detalSecTotal
								dataOut[tag]["Ave"]					+= value * norm		# time weighted average
								dataOut[tag]["Count"]				+= 1				# count
								dataOut[tag]["AveSimple"]			+= value 			# sum for simple average
								if value >0: dataOut[tag]["Count1"] += 1				# count if > 0
						except Exception, e:
							self.ML.myLog( text="error in  Line '%s' ;  error='%s'" % (sys.exc_traceback.tb_lineno, e))
							self.ML.myLog( text=unicode(line))
							self.ML.myLog( text=unicode(value))
							continue            
				for tag in self.dateLimits:
					if  dataOut[tag]["DateMin"] !="" and dataOut[tag]["DateMin"] <   self.dateLimits[tag][0]: dataOut[tag]["DateMin"] = self.dateLimits[tag][0]      
					if  dataOut[tag]["DateMax"] !="" and dataOut[tag]["DateMax"] <   self.dateLimits[tag][0]: dataOut[tag]["DateMax"] = self.dateLimits[tag][0]
					if self.timeFormatInternal != self.timeFormatDisplay:
						try:
							dataOut[tag]["DateMin"] = (datetime.datetime.strptime(dataOut[tag]["DateMin"],self.timeFormatInternal)).strftime(self.timeFormatDisplay)
							dataOut[tag]["DateMax"] = (datetime.datetime.strptime(dataOut[tag]["DateMax"],self.timeFormatInternal)).strftime(self.timeFormatDisplay)
						except Exception, e:
							if not dateErrorShown:
								self.ML.myLog(" date conversion error , bad format: "+self.timeFormatDisplay+"  %s"%e )
								dateErrorShown = True
							
					dataOut[tag]["AveSimple"] = dataOut[tag]["AveSimple"]/max(1.,dataOut[tag]["Count"])    #  simple average
		except  Exception, e:
			if len(unicode(e)) > 5:
				self.ML.myLog( errorType = u"bigErr", text ="error in  Line '%s' ;  error='%s'" % (sys.exc_traceback.tb_lineno, e), destination="standard" )
				self.ML.myLog(                        text ="dataIn: "+ unicode(dataIn) )
				
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
			if value =="x": 
				value=0.
			else:
				dataOut.append((value,date))

			for line in dataIn:
				if len(line) < 20: continue
				line=line.split(";")
 
				v = self.getNumber(line[1])
				if line[0] == date: 
					if v =="x": 			continue
					if v == value: 			continue
					if v > ignoreGreater:	continue
					if v < ignoreLess:		continue
					value=v
					dataOut.append((value,date))
					continue
					
				v = self.getNumber(line[1])
				if v =="x": continue
				if v > ignoreGreater:   continue
				if v < ignoreLess:      continue
				value=v
				date=line[0]
				dataOut.append((value,date))

			if len(dataOut) ==0:
				dataOut=[[0.,""]]
         
		except  Exception, e:
			if len(unicode(e)) > 5:
				self.ML.myLog( errorType = u"bigErr", text ="error in  Line '%s' ;  error='%s'" % (sys.exc_traceback.tb_lineno, e), destination="standard" )
		##indigo.server.log("dataOut"+unicode(dataOut))

		return dataOut


####-----------------   ---------
	def preSelectDevices(self):             # Select only device/properties that are supported:  numbers, bool, but not props that have "words"
		self.listOfPreselectedDevices=[]
		self.devIDSelectedToTypeandName={}


		for theVar in indigo.variables:
			val = theVar.value
			x = self.getNumber(val)
			if x !="x":
				try:
					if str(theVar.id) in self.devList:
						self.listOfPreselectedDevices.append((str(theVar.id)+"-V", "=TRACKED--Var-"+unicode(theVar.name)))
					else:
						self.listOfPreselectedDevices.append((str(theVar.id)+"-V", "Var-"+unicode(theVar.name)))
				except  Exception, e:
					self.ML.myLog( errorType = u"bigErr", text ="Line '%s' has error='%s'" % (sys.exc_traceback.tb_lineno, e))

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
					if str(dev.id) in self.devList:
						self.listOfPreselectedDevices.append((dev.id,"=TRACKED--"+ dev.name))
					else:
						self.listOfPreselectedDevices.append((dev.id, dev.name))
				except  Exception, e:
					self.ML.myLog( errorType = u"bigErr", text ="Line '%s' has error='%s'" % (sys.exc_traceback.tb_lineno, e))
		return





	def getNumber(self, val):
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
				return															 float(val)
			except:
				if type(val) is bool										   : return 1.0 if val else 0.0
			if val ==""														   : return "x"
			try:
				xx = ''.join([c for c in val if c in '-1234567890.'])								# remove non numbers 
				lenXX= len(xx)
				if lenXX > 0:																		# found numbers..
					if len( ''.join([c for c in xx if c in '.']) )           >1: return "x"			# remove strings that have 2 or more dots " 5.5 6.6"
					if len( ''.join([c for c in xx if c in '-']) )           >1: return "x"			# remove strings that have 2 or more -    " 5-5 6-6"
					if len( ''.join([c for c in xx if c in '1234567890']) ) ==0: return "x"			# remove strings that just no numbers, just . amd - eg "abc.xyz- hij"
					if lenXX ==1											   : return float(xx)	# just one number
					if xx.find("-") > 0										   : return "x"			# reject if "-" is not in first position
					valList = list(val)																# make it a list
					count = 0																		# count number of numbers
					for i in range(len(val)-1):														# reject -0 1 2.3 4  not consecutive numbers:..
						if (len(''.join([c for c in valList[i] if c in '-1234567890.'])) ==1 ):		# check if this character is a number, if yes:
							count +=1																# 
							if count >= lenXX									: break				# end of # of numbers, end of test: break, its a number
							if (len(''.join([c for c in valList[i+1] if c in '-1234567890.'])) )== 0: return "x" #  next is not a number and not all numbers accounted for, so it is numberXnumber
					return 														float(xx)			# must be a real number, everything else is excluded
				else:																				# only text left,  no number in this string
					ONE  = [ u"TRUE" , u"T", u"ON",  u"HOME", u"YES", u"JA" , u"SI",  u"IGEN", u"OUI", u"UP",  u"OPEN", u"CLEAR"   ]
					ZERO = [ u"FALSE", u"F", u"OFF", u"AWAY", u"NO",  u"NON", u"NEIN", u"NEM",        u"DOWN", u"CLOSED", u"FAULTED", u"FAULT", u"EXPIRED"]
					val = unicode(val).upper()
					if val in ONE : return 1.0		# true/on   --> 1
					if val in ZERO: return 0.0		# false/off --> 0

	# SPECIAL CASES 
					if (val.find(u"LEAV")    == 0 or  # leave 
						  val.find(u"UNK")   == 0 or  
						  val.find(u"LEFT")  == 0  
											   ): return -1. 

					if( val.find(u"ENABL")   == 0 or   # ENABLE ENABLED 
						  val.find(u"ARRIV") == 0 
											   ): return 1.0		# 

					if( val.find(u"STOP")    == 0  # stop stopped
												): return 0.0		# 

					return "x"																		# all tests failed ... nothing there, return "
			except:
				return "x"																			# something failed eg unicode only ==> return ""
			return "x"																				# should not happen just for safety
