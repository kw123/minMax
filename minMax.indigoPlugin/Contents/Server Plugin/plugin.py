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
import logging
import math
import Queue
import cProfile
import pstats




'''
how it works:
user selects dates from to and the devces/ states or variables to track 
the main loop check the sqllogger db every x minutes and build the min/max/averages ...  for each device/state/variable and fills 
device_state_Min  .. Max   Ave DateMin DateMax Count Count1 with the values. 
'''

_timeWindows	=[u"thisHour",u"lastHour",u"thisDay",u"lastDay",u"thisWeek",u"lastWeek",u"thisMonth",u"lastMonth",u"last7Days"] #   ,u"weekdays"]
_MeasBins		=[u"Min",u"Max",u"DateMin",u"DateMax",u"Ave",u"Count",u"Count1",u"StdDev",u"Start",u"End",u"FirstEntryDate",u"FirstEntryValue",u"LastEntryDate",u"LastEntryValue"]

################################################################################
class Plugin(indigo.PluginBase):
####----------------- logfile  ---------
	def __init__(self, pluginId, pluginDisplayName, pluginVersion, pluginPrefs):
		indigo.PluginBase.__init__(self, pluginId, pluginDisplayName, pluginVersion, pluginPrefs)

		self.pluginShortName 			= u"minMax"


		self.getInstallFolderPath		= indigo.server.getInstallFolderPath()+"/"
		self.indigoPath					= indigo.server.getInstallFolderPath()+"/"
		self.indigoRootPath 			= indigo.server.getInstallFolderPath().split("Indigo")[0]
		self.pathToPlugin 				= self.completePath(os.getcwd())

		major, minor, release 			= map(int, indigo.server.version.split("."))
		self.indigoVersion				= major
		self.pluginVersion				= pluginVersion
		self.pluginId					= pluginId
		self.pluginName					= pluginId.split(".")[-1]
		self.myPID						= os.getpid()
		self.pluginState				= u"init"

		self.myPID 						= os.getpid()
		self.MACuserName				= pwd.getpwuid(os.getuid())[0]

		self.MAChome					= os.path.expanduser(u"~")
		self.userIndigoDir				= self.MAChome + "/indigo/"
		self.indigoPreferencesPluginDir = self.getInstallFolderPath+"Preferences/Plugins/"+self.pluginId+"/"
		self.indigoPluginDirOld			= self.userIndigoDir + self.pluginShortName+"/"
		self.PluginLogFile				= indigo.server.getLogsFolderPath(pluginId=self.pluginId) +"/plugin.log"


		formats=	{   logging.THREADDEBUG: "%(asctime)s %(msg)s",
						logging.DEBUG:       "%(asctime)s %(msg)s",
						logging.INFO:        "%(asctime)s %(msg)s",
						logging.WARNING:     "%(asctime)s %(msg)s",
						logging.ERROR:       "%(asctime)s.%(msecs)03d\t%(levelname)-12s\t%(name)s.%(funcName)-25s %(msg)s",
						logging.CRITICAL:    "%(asctime)s.%(msecs)03d\t%(levelname)-12s\t%(name)s.%(funcName)-25s %(msg)s" }

		date_Format = { logging.THREADDEBUG: "%d %H:%M:%S",
						logging.DEBUG:       "%d %H:%M:%S",
						logging.INFO:        "%H:%M:%S",
						logging.WARNING:     "%H:%M:%S",
						logging.ERROR:       "%Y-%m-%d %H:%M:%S",
						logging.CRITICAL:    "%Y-%m-%d %H:%M:%S" }
		formatter = LevelFormatter(fmt="%(msg)s", datefmt="%Y-%m-%d %H:%M:%S", level_fmts=formats, level_date=date_Format)

		self.plugin_file_handler.setFormatter(formatter)
		self.indiLOG = logging.getLogger("Plugin")  
		self.indiLOG.setLevel(logging.THREADDEBUG)

		self.indigo_log_handler.setLevel(logging.INFO)
		indigo.server.log(u"initializing ... ")

		indigo.server.log(u"path To files:      =================")
		indigo.server.log(u"indigo              "+self.indigoRootPath)
		indigo.server.log(u"installFolder       "+self.indigoPath)
		indigo.server.log(u"plugin.py           "+self.pathToPlugin)
		indigo.server.log(u"Plugin params       "+self.indigoPreferencesPluginDir)

		self.indiLOG.log( 0, u"logger  enabled for   0")
		self.indiLOG.log( 5, u"logger  enabled for   THREADDEBUG")
		self.indiLOG.log(10, u"logger  enabled for   DEBUG")
		self.indiLOG.log(20, u"logger  enabled for   INFO")
		self.indiLOG.log(30, u"logger  enabled for   WARNING")
		self.indiLOG.log(40, u"logger  enabled for   ERROR")
		self.indiLOG.log(50, u"logger  enabled for   CRITICAL")
		indigo.server.log(u"check               "+self.PluginLogFile +u"  <<<<    for detailed logging")
		indigo.server.log(u"Plugin short Name   "+self.pluginShortName)
		indigo.server.log(u"my PID              "+str(self.myPID))	 
	
		self.quitNow = u""

####-----------------   ---------
	def __del__(self):
		indigo.PluginBase.__del__(self)
	
####-----------------   ---------
	def startup(self):

		self.epoch = datetime.datetime(1970, 1, 1)

		self.myPID = os.getpid()
		self.MACuserName   = pwd.getpwuid(os.getuid())[0]


		if True:

			if not os.path.exists(self.indigoPreferencesPluginDir):
				os.mkdir(self.indigoPreferencesPluginDir)
	
				if not os.path.exists(self.indigoPreferencesPluginDir):
					self.indiLOG.log(50,u"error creating the plugin data dir did not work, can not create: "+ self.indigoPreferencesPluginDir)
					self.sleep(1000)
					exit()
				
		self.debugLevel = []
		for d in [u"Loop",u"Sql",u"Setup",u"all"]:
			if self.pluginPrefs.get(u"debug"+d, False): self.debugLevel.append(d)
		self.timeFormatInternal			= "%Y-%m-%d-%H:%M:%S"
		self.refreshRate        		= float(self.pluginPrefs.get(u"refreshRate",5))
		self.liteOrPsql         		= self.pluginPrefs.get(     u"liteOrPsql",       u"sqlite")
		self.liteOrPsqlString   		= self.pluginPrefs.get(     u"liteOrPsqlString", u"/Library/PostgreSQL/bin/psql indigo_history postgres ")
		self.postgresUserId				= self.pluginPrefs.get(		u"postgresUserId",	u"postgres")
		self.postgresPassword			= self.pluginPrefs.get(		u"postgresPassword",	u"")
		if self.postgresPassword != u"" and self.liteOrPsql.find("psql") >-1: 
			self.postgresPasscode 		= u"PGPASSWORD="+self.postgresPassword +u" "
		else: self.postgresPasscode 	= u""
		self.timeFormatDisplay  		= self.pluginPrefs.get(     u"timeFormatDisplay", self.timeFormatInternal)
		self.devList            		= json.loads(self.pluginPrefs.get(u"devList",u"{}"))

		self.checkcProfile()

		self.setLogfile(unicode(self.pluginPrefs.get(u"logFileActive2", u"indigo")))

		self.cleandevList()
		self.resetOldValues()

		self.variFolderName				= self.pluginPrefs.get(u"variFolderName",u"minMax")
		self.saveNow					= False
		self.devIDSelected				= 0
		self.devIDSelectedExist			= 0
		self.devOrVarExist				= u"Var"
		self.devOrVar					= u"Var"
		self.pluginPrefs[u"devList"]		= json.dumps(self.devList)
		self.dateLimits					= [[u"2015-11-00-00:00:00",u"2015-12-00-00:00:00",0,0],[u"2015-12-00-00:00:00",u"2015-12-12-00:00:00",0,0]]
		self.firstDate					= "2015-11-00-00:00:00"
		self.hourLast					= -99 # last hour
		self.subscribeVariable			= False
		self.subscribeDevice			= False

		self.pluginPrefs["postgreHelp2"] = "/Library/PostgreSQL/bin/psql indigo_history postgres "
		self.pluginPrefs["postgreHelp1"] = "/Applications/Postgres.app/Contents/Versions/latest/bin/psql indigo_history postgres "

		self.printConfigCALLBACK()

		return


	####-----------------    ---------
	def cleandevList(self):
		try:
			delID=[]
			for devId in self.devList:
				if u"devOrVar" not in self.devList[devId]:
					delID.append(devId)
				if u"states" not in self.devList[devId]:
					delID.append(devId)
			for devId in delID:
				try:
					del self.devList[devId]
				except:
					pass

			for devId in self.devList:
				#self.indiLOG.log(10,u"devId devList "+ str(devId)+ " " +unicosde(self.devList[devId]) )
				if u"states" not in self.devList[devId]: continue
				remState =[]
				for state in self.devList[devId][u"states"]:
					if len(state)< 2:
						remState.append(state)
					if u"ignoreLess"    not in self.devList[devId][u"states"][state]:
							self.devList[devId][u"states"][state][u"ignoreLess"]			= -9876543210.
					if u"ignoreGreater" not in self.devList[devId][u"states"][state]:
							self.devList[devId][u"states"][state][u"ignoreGreater"]			= +9876543210.
					if u"measures" not in self.devList[devId][u"states"][state]:
							self.devList[devId][u"states"][state][u"measures"] 				= {}
					if u"formatNumbers" not in self.devList[devId][u"states"][state]:
							self.devList[devId][u"states"][state][u"formatNumbers"] 		= u"%.1f"
					if u"timeFormatDisplay" not in self.devList[devId][u"states"][state]:
							self.devList[devId][u"states"][state][u"timeFormatDisplay"] 	= self.timeFormatInternal
					if u"shortName" not in self.devList[devId][u"states"][state]:
							self.devList[devId][u"states"][state][u"shortName"] 			= u""
					delTW =[]
					for TW in self.devList[devId][u"states"][state][u"measures"]:
						if TW not in _timeWindows:
							delTW.append(TW)
						else:
							delMes =[]
							for MB in self.devList[devId][u"states"][state][u"measures"][TW]:
								if MB not in _MeasBins:
									delMes.append(MB)
							for MB in delMes:
								del self.devList[devId][u"states"][state][u"measures"][TW][MB]
					for TW in delTW:
						del self.devList[devId][u"states"][state][u"measures"][TW]

				for state in remState:
					del self.devList[devId][u"states"][state]
		except  Exception, e:
			if len(unicode(e)) > 5:
				self.indiLOG.log(40, u"cleandevList error in  Line '%s' ;  error='%s'" % (sys.exc_traceback.tb_lineno, e))



####-----------------   ---------

####-----------------   ---------
	def deviceStartComm(self, dev):
		dev.stateListOrDisplayStateIdChanged()
		return
	
####-----------------   ---------
	def deviceStopComm(self, dev):
		return


 
####-----------------  set the geneeral config parameters---------
	def validatePrefsConfigUi(self, valuesDict):

		self.debugLevel = []
		for d in [u"Loop",u"Sql",u"Setup",u"all"]:
			if valuesDict[u"debug"+d]: self.debugLevel.append(d)

		self.setLogfile(valuesDict[u"logFileActive2"])

		self.variFolderName     = valuesDict[u"variFolderName"]
		self.refreshRate        = float(valuesDict[u"refreshRate"])
		self.liteOrPsql         = valuesDict[u"liteOrPsql"]
		self.liteOrPsqlString   = valuesDict[u"liteOrPsqlString"]
		self.postgresPassword	= valuesDict[u"postgresPassword"]
		if self.postgresPassword != "" and self.liteOrPsql.find("psql") >-1: 
			self.postgresPasscode 		= "PGPASSWORD="+self.postgresPassword +" "
		else: self.postgresPasscode 	= ""
		self.timeFormatDisplay  = valuesDict[u"timeFormatDisplay"]

		try:
			indigo.variables.folder.create(self.variFolderName)
		except:
			pass

		self.hourLast	= -99
		
		self.printConfigCALLBACK()
		return True, valuesDict


####-----------------   ---------
	def dummyCALLBACK(self):
		
		return
####-----------------   ---------
	def printConfigCALLBACK(self, printDevId=""):
		try:
			self.indiLOG.log(20,u"Configuration: " )
			header = u"Dev/Var-Name-----                 ID               State   ignoreLess ignoreGreater  format  "
			self.indiLOG.log(20,header+u"tracking measures: -------")
			for devId in self.devList:
				if devId == printDevId or printDevId== u"":
					for state in self.devList[devId][u"states"]:
						out = u"%13.0f"%self.devList[devId][u"states"][state][u"ignoreLess"]+u"%14.0f"%(self.devList[devId][u"states"][state][u"ignoreGreater"])+(u"'"+self.devList[devId][u"states"][state][u"formatNumbers"]+"'").rjust(8)+u"  "
						measures = u""
						for TW in self.devList[devId][u"states"][state][u"measures"]:
							ssLine = u""
							for MB in self.devList[devId][u"states"][state][u"measures"][TW]:
								if  self.devList[devId][u"states"][state][u"measures"][TW][MB]:
									if ssLine == u"":
										if measures !=u"":
											ssLine +=u"\n ".ljust(len(header)+1 )
										ssLine += (TW+"-").ljust(11)
									ssLine	+= MB+" "
							measures += ssLine
						if measures == u"":
							measures = "--- no measure selected, no variable will be created---"
						if self.devList[devId][u"devOrVar"] == u"Var":           
							self.indiLOG.log(20,indigo.variables[int(devId)].name.ljust(28) +  devId.rjust(11)+ state.rjust(17) + out+measures )
						else:           
							self.indiLOG.log(20,indigo.devices[int(devId)].name.ljust(28)   +  devId.rjust(11)+ state.rjust(17) + out+measures  )
			self.indiLOG.log(20,u"config parameters  foldername         >{}<".format(self.variFolderName) )
			self.indiLOG.log(20,u"config parameters  refreshRate        >{}<".format(self.refreshRate) )
			self.indiLOG.log(20,u"config parameters  liteOrPsql         >{}<".format(self.liteOrPsql ) )
			self.indiLOG.log(20,u"config parameters  refreshRate        >{}<[secs]".format( self.refreshRate) )
			self.indiLOG.log(20,u"config parameters  liteOrPsql         >{}<".format(self.liteOrPsql) )
			self.indiLOG.log(20,u"config parameters  liteOrPsqlString   >{}<".format(self.liteOrPsqlString) )
			self.indiLOG.log(20,u"config parameters  postgresPassword   >{}<".format(self.postgresPassword ) )
			self.indiLOG.log(20,u"config parameters  timeFormatDisplay  >{}<".format(self.timeFormatDisplay ) )

		except  Exception, e:
			if len(unicode(e)) > 5:
				self.indiLOG.log(40,u"printConfigCALLBACK error in  Line '%s' ;  error='%s'" % (sys.exc_traceback.tb_lineno, e) )
			self.indiLOG.log(40, unicode(self.devList))
		return



####-----------------  ---------
	def getMenuActionConfigUiValues(self, menuId):
		
		valuesDict=indigo.Dict()
		if menuId == u"defineDeviceStates":
			for TW in _timeWindows:
				for mb in _MeasBins:
					valuesDict[TW+mb]		= False
			valuesDict[u"showM"]			= False          
			valuesDict[u"ignoreGreater"]	= u"+9876543210."
			valuesDict[u"ignoreLess"]		= u"-9876543210."
			valuesDict[u"MSG"]   			= u""
			self.devIDSelectedExist 		= 0
			self.devIDSelected				= 0
		return valuesDict




########### --- delete dev/states from tracking 
####-----------------   ---------
	def pickExistingDeviceCALLBACK(self,valuesDict="",typeId=""):               # Select only device/properties that are supported
		if self.decideMyLog(u"Setup"): self.indiLOG.log(10, unicode(valuesDict))
		if valuesDict[u"device"].find(u"-V") >-1:
			self.devOrVarExist = u"Var"
			self.devIDSelectedExist = int(valuesDict[u"device"][:-2])# drop -V
		else:        
			self.devIDSelectedExist = int(valuesDict[u"device"])
			self.devOrVarExist = u"Dev"

####-----------------   ---------
	def filterExistingDevices(self,filter="",valuesDict="",typeId=""):  
		retList = []
		for devId in self.devList:
			try: retList.append([devId,indigo.devices[int(devId)].name])
			except: 
				try:retList.append([devId,indigo.variables[int(devId)].name])
				except: pass
		return retList
####-----------------   ---------
	def filterExistingStates(self,filter="",valuesDict="",typeId=""):                
		if self.devOrVarExist == 0: return [(0,0)]
		devId = str(self.devIDSelectedExist)
		retList =[]
		if devId in self.devList:
			if self.devOrVarExist == u"Var":
				retList.append((u"value", u"value"))
				return retList
			for test in self.devList[devId][u"states"]:
				retList.append((test,test))             
		return retList
####-----------------   ---------
	def buttonRemoveCALLBACK(self,valuesDict="",typeId=""):  
		devId = str(self.devIDSelectedExist)
		state = valuesDict[u"state"]
		deldev={}
		theName = u""
		if devId in self.devList:
			if  state in self.devList[devId][u"states"]:
				del self.devList[devId][u"states"][state]
			if len(self.devList[devId][u"states"]) ==0:
				deldev[devId] = True
		for dd in deldev:
			try: 	theName = indigo.devices[int(devId)].name
			except: 
				try: theName = indigo.variables[int(devId)].name
				except: pass
			del self.devList[dd]
		self.devIDSelectedExist 	= 0
		valuesDict[u"state"] = ""
		self.preSelectDevices()
		self.resetOldValues()
		self.indiLOG.log(20,u" dev/state / var: {} - {} - {} / removed from tracking".format(theName, devId, state))
		return valuesDict


####-----------------   ---------
	def buttonSelectAllCALLBACK(self,valuesDict="",typeId=""):   
		for val in valuesDict:
			for TW in _timeWindows:
				if TW in val:
					valuesDict[val]= True
					break
		return valuesDict

####-----------------   ---------
	def buttonDeSelectAllCALLBACK(self,valuesDict="",typeId=""):   
		for val in valuesDict:
			for TW in _timeWindows:
				if TW in val:
					valuesDict[val]= False
					break
		return valuesDict




########### --- add dev/states to tracking 
####-----------------   ---------
	def pickDeviceCALLBACK(self,valuesDict="",typeId=""):               # Select only device/properties that are supported
		if self.decideMyLog(u"Setup"): self.indiLOG.log(10,unicode(valuesDict))
		if valuesDict[u"device"].find("-V") >-1:
			self.devOrVar = u"Var"
			self.devIDSelected= int(valuesDict[u"device"][:-2])# drop -V
		else:        
			self.devIDSelected= int(valuesDict[u"device"])
			self.devOrVar = u"Dev"


####-----------------   ---------
	def filterDevicesThatQualify(self,filter="",valuesDict="",typeId=""):               
		retList= copy.copy(self.listOfPreselectedDevices )
		for devId in self.devList:
			if self.devList[devId][u"devOrVar"] == u"Var":
				try: retList.append([devId,u"=TRACKED--"+indigo.variables[int(devId)].name])
				except: pass
			else:
				try: retList.append([devId,u"=TRACKED--"+indigo.devices[int(devId)].name])
				except: pass
		return retList


####-----------------   ---------
	def filterStatesThatQualify(self,filter="",valuesDict="",typeId=""):                
	
		if self.devIDSelected ==0: return [(0,0)]

		retList=[]
		if self.devOrVar == u"Var":
			retList.append((u"value", u"value"))
			return retList
		
		dev=indigo.devices[self.devIDSelected]
		retList=[]
		theStates = dev.states.keys()
		for test in theStates:
				count=0
				try:
					if u"Mode" in test or u"All" in test or u".ui" in test:
						skip= True
					else:
						skip= False
				except:
						skip=False
				if not skip:    
					val= dev.states[test]
					x = self.getNumber(val)
					if x != u"x" :
						count +=1
				if count>0:                                                 
					retList.append((test,test))             
		return retList
####-----------------   ---------
	def buttonConfirmStateCALLBACK(self,valuesDict="",typeId=""):               # Select only device/properties that are supported
		devId= str(self.devIDSelected)

		if len(str(self.devIDSelected)) < 2:
			valuesDict[u"showM"] = False          
			valuesDict[u"MSG"] = u"please select Device" 
			return valuesDict
		
		if self.devOrVar == u"Var":
			dev=indigo.variables[int(self.devIDSelected)]
		else:
			dev=indigo.devices[int(self.devIDSelected)]
		
		state= valuesDict[u"state"]
		if len(state) < 2:
			valuesDict[u"showM"] = False          
			valuesDict[u"MSG"] = u"please select State" 
			return valuesDict
			
		if devId not in self.devList:
			self.devList[devId]={}
			self.devList[devId][u"states"]={}

			
		self.devList[devId][u"devOrVar"]=self.devOrVar

		if  u"states" not in self.devList[devId]:
			self.devList[devId][u"states"]={}

			
		if  state not in self.devList[devId][u"states"]:
			self.devList[devId][u"states"][state] = {}

		if  u"measures" not in self.devList[devId][u"states"][state]:
			self.devList[devId][u"states"][state][u"measures"]		= {}
			self.devList[devId][u"states"][state][u"ignoreLess"]	= -9876543210.
			self.devList[devId][u"states"][state][u"ignoreGreater"]	= +9876543210.
			self.devList[devId][u"states"][state][u"formatNumbers"]	= u"%.1f"
			self.devList[devId][u"states"][state][u"shortName"]		= u""
			
		for TW in _timeWindows:
			if TW not in self.devList[devId][u"states"][state][u"measures"]:
				self.devList[devId][u"states"][state][u"measures"][TW] = {}
				
			for MB in _MeasBins:
				if MB not in self.devList[devId][u"states"][state][u"measures"][TW]:
					self.devList[devId][u"states"][state][u"measures"][TW][MB] = False

		for TW in self.devList[devId][u"states"][state][u"measures"]:
			for MB in self.devList[devId][u"states"][state][u"measures"][TW]:
				if self.devList[devId][u"states"][state][u"measures"][TW][MB]:
					valuesDict[TW+MB]= True
				else:   
					valuesDict[TW+MB]= False
				


		valuesDict[u"ignoreLess"]		= str(self.devList[devId][u"states"][state][u"ignoreLess"])
		valuesDict[u"ignoreGreater"]	= str(self.devList[devId][u"states"][state][u"ignoreGreater"])
		valuesDict[u"formatNumbers"] 	=    (self.devList[devId][u"states"][state][u"formatNumbers"])
		valuesDict[u"shortName"] 		=    (self.devList[devId][u"states"][state][u"shortName"])
		valuesDict[u"showM"]			= True 
		self.resetOldValues()  
       
		return valuesDict                        


####-----------------   ---------
	def buttonConfirmCALLBACK(self,valuesDict="",typeId=""):                # Select only device/properties that are supported

		anyOne = False
		try:
			valuesDict[u"MSG"] = u"ok"
			devId= str(self.devIDSelected)
			if len(devId) < 3:
				valuesDict[u"MSG"] = u"please select device"
				return valuesDict
			
			if self.devOrVar == u"Var":
				dev=indigo.variables[int(self.devIDSelected)]
			else:
				dev=indigo.devices[int(self.devIDSelected)]

			if devId not in self.devList:
				self.devList[devId] = {}
				
			self.devList[devId][u"devOrVar"]= self.devOrVar
		
			state = valuesDict[u"state"]
			if len(state) < 2:
				valuesDict[u"showM"] = False          
				valuesDict[u"MSG"] = u"please select State" 
				return valuesDict

			
			if "states" not in self.devList[devId]:
				self.devList[devId][u"states"] ={}
				
			if state not in self.devList[devId][u"states"]:
				self.devList[devId][u"states"][state] ={}

			if u"measures" not in self.devList[devId][u"states"][state]:
				self.devList[devId][u"states"][state][u"measures"]		= {}
				self.devList[devId][u"states"][state][u"ignoreLess"]		= -9876543210.
				self.devList[devId][u"states"][state][u"ignoreGreater"]	= +9876543210.
				self.devList[devId][u"states"][state][u"formatNumbers"]	= "%.1f"
				self.devList[devId][u"states"][state][u"shortName"]		= ""
				
			for TW in  _timeWindows:
				use=False
				for MB in _MeasBins: 
					if valuesDict[TW+MB]:
						#self.indiLOG.log(10, unicode(self.devList[devId]) )
						self.devList[devId][u"states"][state][u"measures"][TW][MB]=True
						anyOne = True
					else:    
						self.devList[devId][u"states"][state][u"measures"][TW][MB]=False

			try: 	self.devList[devId][u"states"][state][u"ignoreLess"]		= float(valuesDict[u"ignoreLess"])
			except:	pass
			try:	self.devList[devId][u"states"][state][u"ignoreGreater"]	= float(valuesDict[u"ignoreGreater"])
			except:	pass
			self.devList[devId][u"states"][state][u"formatNumbers"]			= valuesDict[u"formatNumbers"]

			self.devList[devId][u"states"][state][u"shortName"]				= valuesDict[u"shortName"].replace(u" ",u"_")

			self.saveNow 		= True
			self.devIDSelected	= 0
			self.preSelectDevices()

			self.printConfigCALLBACK(printDevId=devId)
		except  Exception, e:
			if len(unicode(e)) > 5:
				self.indiLOG.log(40,u"error in  Line '%s' ;  error='%s'" % (sys.exc_traceback.tb_lineno, e) )

		valuesDict[u"showM"] = False          
		if not anyOne: valuesDict[u"MSG"] = u"no measure selected-- no variable will be cretaed"

		return valuesDict


	####-----------------  ---------
	def buttonrefreshDataNowCALLBACKaction(self,action):
		return self.buttonrefreshDataNowCALLBACK(valuesDict=action.props)

	####-----------------  ---------
	def buttonrefreshDataNowCALLBACK(self,valuesDict=""):
		self.hourLast	= -99
		self.indiLOG.log(20,u"data refresh requested")
		return

	###########################	   cProfile stuff   ############################ START
	####-----------------  ---------
	def getcProfileVariable(self):

		try:
			if self.timeTrVarName in indigo.variables:
				xx = (indigo.variables[self.timeTrVarName].value).strip().lower().split("-")
				if len(xx) ==1: 
					cmd = xx[0]
					pri = u""
				elif len(xx) == 2:
					cmd = xx[0]
					pri = xx[1]
				else:
					cmd = u"off"
					pri  = u""
				self.timeTrackWaitTime = 20
				return cmd, pri
		except	Exception, e:
			pass

		self.timeTrackWaitTime = 60
		return "off",u""

	####-----------------            ---------
	def printcProfileStats(self,pri=""):
		try:
			if pri !="": pick = pri
			else:		 pick =  u'cumtime'
			outFile		= self.indigoPreferencesPluginDir+u"timeStats"
			indigo.server.log( u" print time track stats to: "+outFile+".dump / txt  with option: "+pick)
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
			self.do_cProfile  			= u"x"
			self.timeTrVarName 			= u"enableTimeTracking_"+self.pluginShortName
			indigo.server.log(u"testing if variable "+self.timeTrVarName+u" is == on/off/print-option to enable/end/print time tracking of all functions and methods (option:'',calls,cumtime,pcalls,time)")

		self.lastTimegetcProfileVariable = time.time()

		cmd, pri = self.getcProfileVariable()
		if self.do_cProfile != cmd:
			if cmd == u"on": 
				if  self.cProfileVariableLoaded ==0:
					indigo.server.log(u"======>>>>   loading cProfile & pstats libs for time tracking;  starting w cProfile ")
					self.pr = cProfile.Profile()
					self.pr.enable()
					self.cProfileVariableLoaded = 2
				elif  self.cProfileVariableLoaded >1:
					self.quitNow = u" restart due to change  ON  requested for print cProfile timers"
			elif cmd == u"off" and self.cProfileVariableLoaded >0:
					self.pr.disable()
					self.quitNow = u" restart due to  OFF  request for print cProfile timers "
		if cmd == u"print"  and self.cProfileVariableLoaded >0:
				self.pr.disable()
				self.printcProfileStats(pri=pri)
				self.pr.enable()
				indigo.variable.updateValue(self.timeTrVarName,u"done")

		self.do_cProfile = cmd
		return 

	####-----------------            ---------
	def checkcProfileEND(self):
		if self.do_cProfile in[u"on",u"print"] and self.cProfileVariableLoaded >0:
			self.printcProfileStats(pri="")
		return
	###########################	   cProfile stuff   ############################ END

####-----------------   var update ==> trigger sql run          ---------
	def variableUpdated(self, orig, new):
		#self.indiLOG.log(10,u"variable data refresh "+ new.name)
		if str(new.id) not in self.devList: return 
		self.QList.put(str(new.id))
		#self.indiLOG.log(10,u"variable data refresh requested due to new data in "+ new.name)
	
####-----------------   dev update ==> trigger sql run          ---------
	def deviceUpdated(self, orig, new):
		if str(new.id) not in self.devList: return 
		#self.indiLOG.log(10,u"device data refresh requested due to new data in "+ new.name)
		for state in self.devList[str(new.id)][u"states"]:
			if state in new.states and new.states[state] != orig.states[state]:
				#self.indiLOG.log(10,u"device data refresh requested due to new data in "+ new.name+"  "+unicode(new.states[state] ))
				self.QList.put(str(new.id))
				break


####-----------------   main loop          ---------
	def runConcurrentThread(self):

		self.QList = Queue.Queue()
		self.dorunConcurrentThread()
		self.checkcProfileEND()


		self.sleep(1)
		if self.quitNow !="":
			indigo.server.log( u"runConcurrentThread stopping plugin due to:  ::::: " + self.quitNow + u" :::::")

		self.quitNow =""

		exit()

####-----------------   main loop            ---------
	def dorunConcurrentThread(self): 

		
		self.timerCheckConfig 		= 0
		self.nextQuerry				= 0
		lastSave					= 0
		nextMinTime 				= 20
		lastSqlTime					= 0
		self.hourLast				= -99
		allUpdates					= False
		self.preSelectDevices()

		try:
			while self.quitNow =="":

				nowTT	= time.time()
				cond1	= ((nowTT- self.nextQuerry > self.refreshRate)  or self.hourLast == -99)
				cond2	= not self.QList.empty()
				cond3	= nowTT - lastSqlTime > nextMinTime
				#self.indiLOG.log(10,u"timers: " +str(cond1) +"  "+str(cond2) +"  "+str(cond3) +"  "+str(allUpdates))
				if  (cond1 or cond2) and cond3:
					if nowTT - lastSqlTime > nextMinTime: 
						dd= datetime.datetime.now()
						day 		=dd.day         # day in month
						wDay		=dd.weekday()   # day of week
						hourNow		=dd.hour        # hour in day

						if hourNow != self.hourLast: # recalculate the limits
							self.doDateLimits() 
							self.preSelectDevices()
							self.resetOldValues()
							self.hourLast = -99

						if self.saveNow or lastSave +600 < nowTT:
							self.pluginPrefs[u"devList"] = json.dumps(self.devList)
							self.saveNow=False

						allUpdates = self.fillVariables(allUpdates, cond1)
							
						self.hourLast	= hourNow 
						self.nextQuerry	= nowTT 
						lastSqlTime 	= nowTT

				for ii in range(20):
					self.sleep(1)
					if self.hourLast ==-99: break
				self.checkConfig()
				self.checkcProfile()
					

				
		except Exception, e:
			if len(unicode(e)) > 5:
				self.indiLOG.log(40,u" in  Line '%s' ;  error='%s'" % (sys.exc_traceback.tb_lineno, e) )

		self.pluginPrefs[u"devList"] =json.dumps(self.devList)
		return


####-----------------   ---------
	def checkConfig(self):
		if time.time() - self.timerCheckConfig < 100: return
		self.timerCheckConfig = time.time()
		try:
			nVars = 0
			nDevs = 0
			for devId in self.devList:
				if self.devList[devId][u"devOrVar"] == u"Var":
					if not self.subscribeVariable: indigo.variables.subscribeToChanges()
					nVars +=1
					if nVars == 1 and not self.subscribeVariable: self.indiLOG.log(20,u"subscribing to variable changes")
					self.subscribeVariable = True
				else:
					if not self.subscribeDevice: indigo.devices.subscribeToChanges()
					nDevs +=1
					if nDevs ==1 and not self.subscribeDevice: self.indiLOG.log(20,u"subscribing to device changes")
					self.subscribeDevice = True
					
			if nVars ==0 and self.subscribeVariable: self.quitNow =" restart due to no variables subcriptions needed"
			if nDevs ==0 and self.subscribeDevice:  self.quitNow =" restart due to no variables subcriptions needed"
		except  Exception, e:
			if len(unicode(e)) > 5:
				self.indiLOG.log(40,u"checkoldValues: error in  Line '%s' ;  error='%s'" % (sys.exc_traceback.tb_lineno, e) )




####-----------------   ---------
	def resetOldValues(self):
		try:
				
			self.oldValues = {}
			for devId in self.devList:
				self.oldValues[devId] = {}
				for state in self.devList[devId][u"states"]:
					self.oldValues[devId][state] = {u"sum":-1,u"nv":-1}

		except  Exception, e:
			if len(unicode(e)) > 5:
				self.indiLOG.log(40,u"Line '%s' ;  error='%s'" % (sys.exc_traceback.tb_lineno, e) )


####-----------------  do the calculations and sql statements  ---------
	def fillVariables(self, allUpdatesLast, cond1):

		delList =[]
		qDevIds =[]
		allUpdates = False
		try:
			if allUpdatesLast and not cond1: 
				while not self.QList.empty():
					qDevIds.append(self.QList.get())
				try:	self.QList.task_done()
				except:	pass

			if len(qDevIds) ==0: allUpdates = True
			else:				 allUpdates = False

			for devId in self.devList:
				if not( len(qDevIds) == 0 or devId in qDevIds ): continue
				
				if int(devId) >0:
					try:
						if self.devList[devId][u"devOrVar"] == u"Var":
							devName= indigo.variables[int(devId)].name
						else:                            
							devName= indigo.devices[int(devId)].name
					except  Exception, e:
						if unicode(e).find(u"timeout waiting") > -1:
							self.indiLOG.log(40, u"in Line '%s' has error='%s'" % (sys.exc_traceback.tb_lineno, e))
							self.indiLOG.log(40,u"communication to indigo is interrupted")
							return
						self.indiLOG.log(40,u" error; device with indigoID = "+ str(devId) +" does not exist, removing from tracking") 
						delList.append(devId)
						continue
						   
				#_timeWindows   =[u"thisHour",u"lastHour",u"thisDay",u"lastDay",u"thisWeek",u"lastWeek",u"thisMonth",u"lastMonth",u"last7Days"]
				#_MeasBins     =[u"Min",u"Max",u"DateMin",u"DateMax",u"Ave",u"Count",u"Count1",u"StdDev""]

				states =self.devList[devId][u"states"]
				for state in states:
					params				= states[state]
					if params[u"shortName"] != u"":
						varName	= params[u"shortName"]
					else:
						varName	= devName.replace(u" ",u"_")+"_"+state.replace(u" ",u"_")
						
					dataSQL				= self.doSQL(devId,state,self.devList[devId][u"devOrVar"])
					dataClean,sum,nv	= self.removeDoublesInSQL(dataSQL, params[u"ignoreLess"], params[u"ignoreGreater"])
					if sum == self.oldValues[devId][state][u"sum"] and nv == self.oldValues[devId][state][u"nv"] and self.hourLast != -99: 
						continue
						
					self.oldValues[devId][state][u"sum"] = sum
					self.oldValues[devId][state][u"nv"]  = nv
					values								 = self.calculate(dataClean)

					if self.decideMyLog(u"Loop"): self.indiLOG.log(10,u"variName "+varName)
					if self.decideMyLog(u"Loop"): self.indiLOG.log(10,u"values    " +unicode(values)[0:500])
					if self.decideMyLog(u"Loop"): self.indiLOG.log(10,u";   state: "+ state+u" params: "+unicode(params)+" "+unicode(values)[0:30])

					for TW in values:
						if TW not in params[u"measures"]: continue
						
						value=values[TW]
						if self.decideMyLog(u"Loop"): self.indiLOG.log(10,u"TW    " + TW+u" "+unicode(value))
						
						for MB in _MeasBins:
							if MB not in params[u"measures"][TW]:	continue
							if not params[u"measures"][TW][MB]:	continue

							try:	vari = indigo.variables[varName+"_"+TW+"_"+MB]
							except:
								try:	indigo.variable.create(varName+"_"+TW+"_"+MB,      "", self.variFolderName)
								except:	pass

							if  MB.find("Count")>-1:
										indigo.variable.updateValue(varName+u"_"+TW+u"_"+MB,          (u"%d"%(value[MB])).strip())
							elif MB.find("Date")>-1:
										indigo.variable.updateValue(varName+u"_"+TW+u"_"+MB,          value[MB].strip())
							else:
								try:	indigo.variable.updateValue(varName+u"_"+TW+u"_"+MB,          (params[u"formatNumbers"]%(value[MB])).strip())
								except:	indigo.variable.updateValue(varName+u"_"+TW+u"_"+MB,          u"")
								
			for devId in delList:
				del self.devList[devId]
		except  Exception, e:
			if len(unicode(e)) > 5:
				self.indiLOG.log(40,u"Line '%s' ;  error='%s'" % (sys.exc_traceback.tb_lineno, e),)
		return allUpdates

####-----------------  do the calculations and sql statements  ---------
	def doDateLimits(self):
#       self.dateLimits=[[u"2015-11-00 00:00:00",u"2015-12-00 00:00:00"],[u"2015-12-00 00:00:00",u"2015-12-12 00:00:00"]]

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

			hour0	= dd-datetime.timedelta(minutes=dd.minute,seconds=dd.second)
			day0	= dd-datetime.timedelta(hours=dd.hour,minutes=dd.minute,seconds=dd.second)
			day0End	= day0+datetime.timedelta(hours=24)
			day0EndF= (day0End).strftime(self.timeFormatInternal)

			dh0		= hour0.strftime(self.timeFormatInternal)
			dh1		= (hour0+datetime.timedelta(hours=1)).strftime(self.timeFormatInternal)
			self.dateLimits[u"thisHour"] = [dh0,dh1,0,0,0]

			dh1		= dh0
			dh0		= (hour0-datetime.timedelta(hours=1)).strftime(self.timeFormatInternal)
			self.dateLimits[u"lastHour"] = [dh0,dh1,0,0,0]

			dh0		= day0.strftime(self.timeFormatInternal)
			dh1		= day0EndF
			self.dateLimits[u"thisDay"] = [dh0,dh1,0,0,0]

			dh1		= day0.strftime(self.timeFormatInternal)
			dh0		= (day0-datetime.timedelta(days=1)).strftime(self.timeFormatInternal)
			self.dateLimits[u"lastDay"] = [dh0,dh1,0,0,0]

			week0	= dd-datetime.timedelta(days=dd.weekday(),hours=dd.hour,minutes=dd.minute,seconds=dd.second)
			dh0		= week0.strftime(self.timeFormatInternal)
			weekend  =week0+datetime.timedelta(days=7)
			dh1		= weekend.strftime(self.timeFormatInternal)
			self.dateLimits[u"thisWeek"] = [dh0,dh1,0,0,0]

			dh1		= week0.strftime(self.timeFormatInternal)
			dh0		= (week0-datetime.timedelta(days=7)).strftime(self.timeFormatInternal)
			self.dateLimits[u"lastWeek"] = [dh0,dh1,0,0,0]

			month0	= dd-datetime.timedelta(days=dd.day-1,hours=dd.hour,minutes=dd.minute,seconds=dd.second)
			dh0		= month0.strftime(self.timeFormatInternal)
			monthEnd= month0+datetime.timedelta(days=31)
			if monthEnd.day < 5:
				monthEnd = monthEnd-datetime.timedelta(days=monthEnd.day-1)
			dh1		= monthEnd.strftime(self.timeFormatInternal)
			self.dateLimits[u"thisMonth"] = [dh0,dh1,0,0,0]

			dh1		= month0.strftime(self.timeFormatInternal)
			d0		= (month0-datetime.timedelta(days=1))
			dh0 	= (month0-datetime.timedelta(days=d0.day)).strftime(self.timeFormatInternal)    
			self.dateLimits[u"lastMonth"] = [dh0,dh1,0,0,0]

			dh0		= (dd - datetime.timedelta(days=7,hours=dd.hour,minutes=dd.minute,seconds=dd.second) ).strftime(self.timeFormatInternal)
			dh1		= day0EndF
			self.dateLimits[u"last7Days"] = [dh0,dh1,0,0,0]

			for TW in self.dateLimits:
				self.dateLimits[TW][2] = (datetime.datetime.strptime(self.dateLimits[TW][0], self.timeFormatInternal)-self.epoch).total_seconds()
				self.dateLimits[TW][3] = (datetime.datetime.strptime(self.dateLimits[TW][1], self.timeFormatInternal)-self.epoch).total_seconds()
				self.dateLimits[TW][4] = max(1.,self.dateLimits[TW][3] - self.dateLimits[TW][2])

			if self.decideMyLog(u"Loop"): 
				self.indiLOG.log(10,u"first-Date:  "+unicode(self.firstDate))
				self.indiLOG.log(10,u"date-limits: "+unicode(self.dateLimits))
		except  Exception, e:
			if len(unicode(e)) > 5:
				self.indiLOG.log(40,u" Line '%s' ;  error='%s'" % (sys.exc_traceback.tb_lineno, e) )
		return 
					



####----------------- do the sql statement  ---------
	def doSQL(self,devId,state,devOrVar): 
		dataOut = []
		ii 		= 0
		try:
			while ii<3:

				if devOrVar== u"Dev":
					sql2 = state+" from device_history_"+str(devId)
				else:    
					sql2 = u" value from variable_history_"+str(devId)

				if self.liteOrPsql =="sqlite": 
					sql = "/usr/bin/sqlite3  -separator \";\" '"+self.indigoPath+ "logs/indigo_history.sqlite' \"select strftime('%Y-%m-%d-%H:%M:%S',ts,'localtime'), "
					sql4 ="  where ts > '"+ self.firstDate+"';\""
					cmd =sql+sql2+sql4

				else:    
					sql = self.liteOrPsqlString+ " -t -A -F ';' -c \"SELECT to_char(ts,'YYYY-mm-dd-HH24:MI:ss'), "
					sql4 ="  where to_char(ts,'YYYY-mm-dd-HH24:MI:ss') > '"+ self.firstDate+"'  ORDER by id  ;\""
					cmd = sql+sql2+sql4
					cmd = self.postgresPasscode + cmd
					if self.postgresUserId != "" and self.postgresUserId !="postgres": cmd = cmd.replace(" postgres ",u" "+self.postgresUserId+" ")

					
				if self.decideMyLog(u"Sql"): self.indiLOG.log(10,cmd)
				p=subprocess.Popen(cmd,shell=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
				out=p.communicate()
				p.stdout.close()        
				p.stderr.close()        
				p.wait
				if unicode(out).find(u"ERROR")>-1:
					ii+=1
					self.sleep(1)
					continue
				break    
			dataOut = out[0]
			if self.decideMyLog(u"Sql"): self.indiLOG.log(10,u"data-out: "+out[0][:300])
			if self.decideMyLog(u"Sql"): self.indiLOG.log(10,u"err-out:  "+out[1][:300])
		except  Exception, e:
			if len(unicode(e)) > 5:
				sself.indiLOG.log(40,u"error in  Line '%s' ;  error='%s'" % (sys.exc_traceback.tb_lineno, e) )
		
		return dataOut
		
####----------------- calculate ave min max for all  ---------
	def calculate(self,dataIn):             
		line				= ""
		value				= ""
		addedSecsForLastBin	= 90.
		dataOut 			= {}
		dateErrorShown 		= False
		for TW in self.dateLimits:
			dataOut[TW] = {u"Min": -987654321000.,u"Max":987654321000.,u"DateMin":u"",u"DateMax":u"",u"Count":0.,u"Count1":0,u"StdDev":0,u"Ave":0,u"AveSimple":0,u"FirstEntryDate":u"",u"FirstEntryValue":u"",u"LastEntryDate":u"",u"LastEntryValue":u""}
		try:

			nData = len(dataIn)
			if nData > 0:

				if dataIn[nData-1][1] != u"":
					lastSecInData = (   datetime.datetime.strptime(dataIn[nData-1][1], self.timeFormatInternal) - self.epoch   ).total_seconds() 
				else:
					lastSecInData = int(time.time())

				for nn in range(nData):
					line = dataIn[nn]
					date	= line[1]
					if date == "": continue
					value	= self.getNumber(line[0])
					##self.indiLOG.log(10,date+"  "+ unicode(value))
					if value == u"x": continue

					secondsStartD	= (datetime.datetime.strptime(date, self.timeFormatInternal)-self.epoch).total_seconds()
					if nn < nData-1:
						lastData = False
						secondsEndD	= (datetime.datetime.strptime(dataIn[nn+1][1], self.timeFormatInternal)-self.epoch).total_seconds()
						dateNext   = dataIn[nn+1][1]
					else: 				
						lastData = True
						secondsEndD	= lastSecInData +addedSecsForLastBin # last measurement point + 90 secs 
						dateNext 	= u"9999-12-01-12:33:12"

					for TW in self.dateLimits:
						try:
							if dateNext < self.dateLimits[TW][0]: 					continue
							if dateNext > self.dateLimits[TW][1] and not lastData: continue

#							_MeasBins       =[u"Min",u"Max",u"DateMin",u"DateMax",u"Ave",u"Count",u"Count1"]
						#                         # of seconds in bin                                     +90secs    last sec in bin           fist sec in bin  == dont take whole bin otherwise last value is overweighted
							detalSecTotal	= max( 1., min(self.dateLimits[TW][4],   min(lastSecInData+addedSecsForLastBin, self.dateLimits[TW][3]) - self.dateLimits[TW][2]  ) )
							secondsEnd   	= min(secondsEndD,  self.dateLimits[TW][3]) 
							# first data point?
							norm = 1.0
							if  date  >= self.dateLimits[TW][0] and dataOut[TW][u"FirstEntryDate"] =="" and value != 0:  ## use last below date range?
								dataOut[TW][u"FirstEntryDate"] 		= date 				# 
								dataOut[TW][u"FirstEntryValue"]		= value 			# 

							if  (date  < self.dateLimits[TW][0] and dataOut[TW][u"Count"] <= 1) or dataOut[TW][u"Count"] == 0:  ## use last below date range?
								dataOut[TW][u"Start"] 				= value 				# Start value
								dataOut[TW][u"End"] 				= value 				# 
								dataOut[TW][u"Min"] 				= value 				# min
								dataOut[TW][u"DateMin"] 			= date  				# datestamp

								dataOut[TW][u"Max"] 				= value 				# max 
								dataOut[TW][u"DateMax"] 			= date  				# datestamp

								if not lastData: norm 				= (secondsEnd - self.dateLimits[TW][2])/detalSecTotal 
								dataOut[TW][u"Ave"]					= value*norm			# time weighted average
								dataOut[TW][u"Count"]				= 1    					# count
								dataOut[TW][u"AveSimple"]			= value					# sum for simple average
								dataOut[TW][u"StdDev"]				= value*value*norm		# std dev
								if value >0: dataOut[TW][u"Count1"]	+= 1					# count if > 0
	
							# regular datapoint in bin
							if date  > self.dateLimits[TW][0] and  date <=  self.dateLimits[TW][1]:  ## in date range?
								if dataOut[TW][u"Min"] > value:
									dataOut[TW][u"Min"] 			= value				# min 
									dataOut[TW][u"DateMin"] 		= date				# datestamp

								if dataOut[TW][u"Max"] < value:
									dataOut[TW][u"Max"] 			= value				# max  
									dataOut[TW][u"DateMax"]			= date				# datestamp

								if value != 0:
									dataOut[TW][u"LastEntryDate"] 	= date 				#
									dataOut[TW][u"LastEntryValue"]	= value 			# 

	
								dataOut[TW][u"End"] 				= value 				# min
								norm 								= (secondsEnd - secondsStartD)/detalSecTotal
								dataOut[TW][u"Ave"]					+= value * norm		# time weighted average
								dataOut[TW][u"Count"]				+= 1				# count
								dataOut[TW][u"AveSimple"]			+= value 			# sum for simple average
								dataOut[TW][u"StdDev"]				+= value*value * norm# sum for simple average
								if value >0: dataOut[TW][u"Count1"] += 1				# count if > 0
								
						except Exception, e:
							self.indiLOG.log(40,u"error in  Line '%s' ;  error='%s'" % (sys.exc_traceback.tb_lineno, e))
							self.indiLOG.log(40,unicode(line))
							self.indiLOG.log(40,unicode(value))
							continue            
				for TW in self.dateLimits:
					if  dataOut[TW][u"DateMin"] !="" and dataOut[TW][u"DateMin"] <   self.dateLimits[TW][0]: dataOut[TW][u"DateMin"] = self.dateLimits[TW][0]      
					if  dataOut[TW][u"DateMax"] !="" and dataOut[TW][u"DateMax"] <   self.dateLimits[TW][0]: dataOut[TW][u"DateMax"] = self.dateLimits[TW][0]
					if self.timeFormatInternal != self.timeFormatDisplay:
						try:
							for xxx in [u"DateMin",u"DateMax",u"FirstEntryDate",u"LastEntryDate"]:
								if dataOut[TW][xxx]	!= "": 
									dataOut[TW][xxx] = (datetime.datetime.strptime(dataOut[TW][xxx], self.timeFormatInternal)).strftime(self.timeFormatDisplay)
						except Exception, e:
							if not dateErrorShown:
								self.indiLOG.log(40,u" date conversion error , bad format: "+self.timeFormatDisplay+"  %s"%e )
								self.indiLOG.log(20,u"TW: "+TW+u";  dataOut "+ unicode(dataOut[TW]))
								dateErrorShown = True
					dataOut[TW][u"StdDev"] 		= math.sqrt(abs(dataOut[TW][u"StdDev"]  - dataOut[TW][u"Ave"]**2)) #  std dev
					dataOut[TW][u"AveSimple"]	= dataOut[TW][u"AveSimple"]/max(1.,dataOut[TW][u"Count"])     #  simple average
		except  Exception, e:
			if len(unicode(e)) > 5:
				self.indiLOG.log(40,u"error in  Line '%s' ;  error='%s'" % (sys.exc_traceback.tb_lineno, e))
				self.indiLOG.log(40,u"dataIn: "+ unicode(dataIn) )
				
		return dataOut

####----------------- prep sql return data  ---------
	def removeDoublesInSQL(self,dataLines,ignoreLess,ignoreGreater):    # remove doubles same date/timestamp            
		dataOut=[]
		sum 	= 0
		nValues	= 0
		try:
			dataIn=dataLines.split(u"\n")
			t= dataIn[0].split(u";")
			if len(t)!=2: return dataOut, sum, nValues
			if self.decideMyLog(u"Loop"): self.indiLOG.log(10,unicode(t))
			date=t[0]
			try:
				value=self.getNumber(t[1])
			except:
				value=0.
			if value =="x": 
				value=0.
			else:
				dataOut.append((value,date))
				nValues += 1
				sum     += value 

			for line in dataIn:
				if len(line) < 20: continue
				line=line.split(u";")
 
				v = self.getNumber(line[1])
				if line[0] == date: 
					if v == u"x": 			continue
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
				sum 	+= value
				nValues +=1

			if len(dataOut) ==0:
				dataOut=[[0.,u""]]

		except  Exception, e:
			if len(unicode(e)) > 5:
				self.indiLOG.log(40,u"error in  Line '%s' ;  error='%s'" % (sys.exc_traceback.tb_lineno, e) )
		##indigo.server.log("dataOut"+unicode(dataOut))

		return dataOut, sum, nValues


####-----------------   ---------
	def preSelectDevices(self):             # Select only device/properties that are supported:  numbers, bool, but not props that have "words"
		self.listOfPreselectedDevices=[]
		self.devIDSelectedToTypeandName={}


		for theVar in indigo.variables:
			val = theVar.value
			x = self.getNumber(val)
			if x != u"x":
				try:
					if str(theVar.id) in self.devList:
						self.listOfPreselectedDevices.append((str(theVar.id)+u"-V", u"=TRACKED--Var-"+unicode(theVar.name)))
					else:
						self.listOfPreselectedDevices.append((str(theVar.id)+u"-V", u"Var-"+unicode(theVar.name)))
				except  Exception, e:
					self.indiLOG.log(40,u"Line '%s' has error='%s'" % (sys.exc_traceback.tb_lineno, e))

		for dev in indigo.devices.iter():
			theStates = dev.states.keys()
			count =0
			for test in theStates:
				try:
					if u"Mode" in test or u"All" in test or u".ui" in test:
						skip= True
					else:
						skip= False
				except:
					skip=False
				if not skip:    
					val= dev.states[test]
					x = self.getNumber(val)
					if x != u"x" :
						count +=1
			if count>0:                                                 # add to the selection list
				try:
					if str(dev.id) in self.devList:
						self.listOfPreselectedDevices.append((dev.id, u"=TRACKED--"+ dev.name))
					else:
						self.listOfPreselectedDevices.append((dev.id, dev.name))
				except  Exception, e:
					self.indiLOG.log(40,u"Line '%s' has error='%s'" % (sys.exc_traceback.tb_lineno, e))
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
			if val ==""														   : return u"x"
			try:
				xx = ''.join([c for c in val if c in u'-1234567890.'])								# remove non numbers 
				lenXX= len(xx)
				if lenXX > 0:																		# found numbers..
					if len( ''.join([c for c in xx if c in '.']) )           >1: return u"x"			# remove strings that have 2 or more dots " 5.5 6.6"
					if len( ''.join([c for c in xx if c in '-']) )           >1: return u"x"			# remove strings that have 2 or more -    " 5-5 6-6"
					if len( ''.join([c for c in xx if c in '1234567890']) ) ==0: return u"x"			# remove strings that just no numbers, just . amd - eg "abc.xyz- hij"
					if lenXX ==1											   : return float(xx)	# just one number
					if xx.find(u"-") > 0										   : return u"x"			# reject if "-" is not in first position
					valList = list(val)																# make it a list
					count = 0																		# count number of numbers
					for i in range(len(val)-1):														# reject -0 1 2.3 4  not consecutive numbers:..
						if (len(''.join([c for c in valList[i] if c in u'-1234567890.'])) ==1 ):		# check if this character is a number, if yes:
							count +=1																# 
							if count >= lenXX									: break				# end of # of numbers, end of test: break, its a number
							if (len(''.join([c for c in valList[i+1] if c in u'-1234567890.'])) )== 0: return u"x" #  next is not a number and not all numbers accounted for, so it is numberXnumber
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

					return u"x"																		# all tests failed ... nothing there, return "
			except:
				return u"x"																			# something failed eg unicode only ==> return ""
			return u"x"																				# should not happen just for safety




	####-----------------	 ---------
	def completePath(self,inPath):
		if len(inPath) == 0: return u""
		if inPath == u" ":	 return u""
		if inPath[-1] != u"/": inPath += u"/"
		return inPath


########################################
########################################
####-----------------  logging ---------
########################################
########################################
	####-----------------    ---------
	def setLogfile(self,lgFile):
		self.logFileActive =lgFile
		if   self.logFileActive =="standard":	self.logFile = ""
		elif self.logFileActive =="indigo":		self.logFile = self.indigoPath+"Logs/"+self.pluginId+"/plugin.log"
		else:									self.logFile = self.indigoPreferencesPluginDir +"plugin.log"
		self.myLogSet(debugLevel = self.debugLevel ,logFileActive=self.logFileActive, logFile = self.logFile, pluginSelf=self)

	####----------------- ---------
	def setLogfile(self, lgFile):
		self.logFileActive =lgFile
		if   self.logFileActive =="standard":	self.logFile = ""
		elif self.logFileActive =="indigo":		self.logFile = self.indigoPath.split("Plugins/")[0]+"Logs/"+self.pluginId+"/plugin.log"
		else:									self.logFile = self.indigoPreferencesPluginDir +"plugin.log"
		self.myLog( text="myLogSet setting parameters -- logFileActive= "+ unicode(self.logFileActive) + "; logFile= "+ unicode(self.logFile)+ ";  debugLevel= "+ unicode(self.debugLevel) , destination="standard")



			
			
	####-----------------	 ---------
	def decideMyLog(self, msgLevel):
		try:
			if msgLevel	 == u"all" or u"all" in self.debugLevel:	 return True
			if msgLevel	 == ""	 and u"all" not in self.debugLevel:	 return False
			if msgLevel in self.debugLevel:							 return True
			return False
		except	Exception, e:
			if len(unicode(e)) > 5:
				indigo.server.log( u"decideMyLog in Line '%s' has error='%s'" % (sys.exc_traceback.tb_lineno, e))
		return False

	####-----------------  print to logfile or indigo log  ---------
	def myLog(self,	 text="", mType="", errorType="", showDate=True, destination=""):
		   

		try:
			if	self.logFileActive =="standard" or destination.find("standard") >-1:
				if errorType == u"smallErr":
					self.indiLOG.error(u"------------------------------------------------------------------------------")
					self.indiLOG.error(text)
					self.indiLOG.error(u"------------------------------------------------------------------------------")

				elif errorType == u"bigErr":
					self.indiLOG.error(u"==================================================================================")
					self.indiLOG.error(text)
					self.indiLOG.error(u"==================================================================================")

				elif mType == "":
					indigo.server.log(text)
				else:
					indigo.server.log(text, type=mType)


			if	self.logFileActive !="standard":

				ts =""
				try:
					if len(self.logFile) < 3: return # not properly defined
					f =	 open(self.logFile,u"a")
				except	Exception, e:
					indigo.server.log(u"in Line '%s' has error='%s'" % (sys.exc_traceback.tb_lineno, e))
					try:
						f.close()
					except:
						pass
					return

				if errorType == u"smallErr":
					if showDate: ts = datetime.datetime.now().strftime(u"%H:%M:%S")
					f.write(u"----------------------------------------------------------------------------------\n")
					f.write((ts+u" ".ljust(12)+u"-"+text+u"\n").encode(u"utf8"))
					f.write(u"----------------------------------------------------------------------------------\n")
					f.close()
					return

				if errorType == u"bigErr":
					if showDate: ts = datetime.datetime.now().strftime(u"%H:%M:%S")
					ts = datetime.datetime.now().strftime(u"%H:%M:%S")
					f.write(u"==================================================================================\n")
					f.write((ts+u" "+u" ".ljust(12)+u"-"+text+u"\n").encode(u"utf8"))
					f.write(u"==================================================================================\n")
					f.close()
					return
				if showDate: ts = datetime.datetime.now().strftime(u"%H:%M:%S")
				if mType == u"":
					f.write((ts+u" " +u" ".ljust(25)  +u"-" + text + u"\n").encode("utf8"))
				else:
					f.write((ts+u" " +mType.ljust(25) +u"-" + text + u"\n").encode("utf8"))
				### print calling function 
				#f.write(u"_getframe:   1:" +sys._getframe(1).f_code.co_name+"   called from:"+sys._getframe(2).f_code.co_name+" @ line# %d"%(sys._getframe(1).f_lineno) ) # +"    trace# "+unicode(sys._getframe(1).f_trace)+"\n" )
				f.close()
				return


		except	Exception, e:
			if len(unicode(e)) > 5:
				self.indiLOG.critical(u"myLog in Line '%s' has error='%s'" % (sys.exc_traceback.tb_lineno, e))
				indigo.server.log(text)
				try: f.close()
				except: pass




##################################################################################################################
####-----------------  valiable formatter for differnt log levels ---------
# call with: 
# formatter = LevelFormatter(fmt='<default log format>', level_fmts={logging.INFO: '<format string for info>'})
# handler.setFormatter(formatter)
class LevelFormatter(logging.Formatter):
	def __init__(self, fmt=None, datefmt=None, level_fmts={}, level_date={}):
		self._level_formatters = {}
		self._level_date_format = {}
		for level, format in level_fmts.items():
			# Could optionally support level names too
			self._level_formatters[level] = logging.Formatter(fmt=format, datefmt=level_date[level])
		# self._fmt will be the default format
		super(LevelFormatter, self).__init__(fmt=fmt, datefmt=datefmt)

	def format(self, record):
		if record.levelno in self._level_formatters:
			return self._level_formatters[record.levelno].format(record)

		return super(LevelFormatter, self).format(record)


