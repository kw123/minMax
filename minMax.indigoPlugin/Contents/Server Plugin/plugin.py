#! /usr/bin/env python
# -*- coding: utf-8 -*-
####################
# Plugin miMax
# Developed by Karl Wachs
# karlwachs@me.com
# last change dec 14, 2015
#
#
#


import os, sys, subprocess, pwd
import datetime
import time
import json
#from time import strftime
import urllib
import fcntl
import signal
import copy
import logging
import math
import queue

try:
	unicode("x")
except:
	unicode = str

import traceback


'''
how it works:
user selects dates from to and the devces/ states or variables to track 
the main loop check the sqllogger db every x minutes and build the min/max/averages ...  for each device/state/variable and fills 
device_state_Min  .. Max   Ave DateMin DateMax Count Count1 with the values. 

abreviations used:
TW = time window
MB = mesaurement Bin

'''

_timeWindows			= ["thisHour","lastHour","this12Hours","last12Hours","thisDay","lastDay","thisDay6-18","lastDay6-18","thisDay18-6","lastDay18-6","last7Days","thisWeek","lastWeek","thisMonth","lastMonth"] #   ,"weekdays"]
_MeasBins				= ["Min","DateMin","Max","DateMax","Ave","StdDev","AveSimple","StdDevSimple","Count","Count1","UpTime","Start","End","Consumption","FirstEntryValue","FirstEntryDate","LastEntryValue","LastEntryDate"]
_MeasBinsExplanation	= {"Min":				"min value in time window / bin ",
						   "Max":				"max value in time window / bin ",
						   "DateMin":			"date-time when min value was in time window / bin ",
						   "DateMax":			"date-time when max value was in time window / bin ",
						   "Ave":				"average of values in time window / bin  weighted with time",
						   "StdDev":			"std deviation around average in time window / bin ",
						   "AveSimple":			"average of values in time window / bin , simple sum/count",
						   "StdDevSimple":		"std deviation around average in time window / bin , simple sum/count",
						   "Count":				"number of values in time window / bin ",
						   "Count1":			"number of values >0 in time window / bin  ",
						   "UpTime":			"% time when value was not 0",
						   "Start":				"value at start of time window / bin , might be measured in previous bin",
						   "End":				"value at end of time window / bin ",
						   "FirstEntryDate":	"date-time of first measured value in time window / bin ",
						   "FirstEntryValue":	"first measured value in time window / bin ",
						   "LastEntryDate":		"date-time of last measured value in time window / bin ",
						   "LastEntryValue":	"last measured value in time window / bin ",
						   "Consumption":		"end value - start value in time window / bin "
						  }


_debugAreas				= ["Loop","Sql","Setup","AddData","Fill","Special","all"]

################################################################################
class Plugin(indigo.PluginBase):
####----------------- logfile  ---------
	def __init__(self:"",
						   pluginId, pluginDisplayName, pluginVersion, pluginPrefs):
		indigo.PluginBase.__init__(self, pluginId, pluginDisplayName, pluginVersion, pluginPrefs)

		self.pluginShortName 			= "minMax"


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
		self.pluginState				= "init"

		self.myPID 						= os.getpid()
		self.MACuserName				= pwd.getpwuid(os.getuid())[0]

		self.MAChome					= os.path.expanduser("~")
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
		indigo.server.log("initializing ... ")

		indigo.server.log("path To files:      =================")
		indigo.server.log("indigo              "+self.indigoRootPath)
		indigo.server.log("installFolder       "+self.indigoPath)
		indigo.server.log("plugin.py           "+self.pathToPlugin)
		indigo.server.log("Plugin params       "+self.indigoPreferencesPluginDir)

		if pluginPrefs.get('showLoginTest',False):
			self.indiLOG.log( 0, "logger  enabled for   0")
			self.indiLOG.log( 5, "logger  enabled for   THREADDEBUG")
			self.indiLOG.log(10, "logger  enabled for   DEBUG")
			self.indiLOG.log(20, "logger  enabled for   INFO")
			self.indiLOG.log(30, "logger  enabled for   WARNING")
			self.indiLOG.log(40, "logger  enabled for   ERROR")
			self.indiLOG.log(50, "logger  enabled for   CRITICAL")
		indigo.server.log("check               "+self.PluginLogFile +"  <<<<    for detailed logging")
		indigo.server.log("Plugin short Name   "+self.pluginShortName)
		indigo.server.log("my PID              "+"{}".format(self.myPID))	 
	
		self.quitNow = ""

####-----------------   ---------
	def __del__(self):
		indigo.PluginBase.__del__(self)
	
####-----------------   ---------
	def startup(self):

		self.epoch = datetime.datetime(1970, 1, 1)

		self.myPID = os.getpid()
		self.MACuserName   = pwd.getpwuid(os.getuid())[0]



		if not os.path.exists(self.indigoPreferencesPluginDir):
			os.mkdir(self.indigoPreferencesPluginDir)

			if not os.path.exists(self.indigoPreferencesPluginDir):
				self.indiLOG.log(50,"error creating the plugin data dir did not work, can not create: "+ self.indigoPreferencesPluginDir)
				self.sleep(1000)
				exit()
				
		self.debugLevel = []
		for d in _debugAreas:
			if self.pluginPrefs.get("debug"+d, False): self.debugLevel.append(d)
		self.timeFormatInternal			= "%Y-%m-%d-%H:%M:%S"
		self.refreshRate        		= float(self.pluginPrefs.get("refreshRate",5))
		self.liteOrPsql         		= self.pluginPrefs.get(     "liteOrPsql",       "sqlite")
		self.liteOrPsqlString   		= self.pluginPrefs.get(     "liteOrPsqlString", "/Library/PostgreSQL/bin/psql indigo_history postgres ")
		self.postgresUserId				= self.pluginPrefs.get(		"postgresUserId",	"postgres")
		self.postgresPassword			= self.pluginPrefs.get(		"postgresPassword",	"")
		if self.postgresPassword != "" and self.liteOrPsql.find("psql") >-1: 
			self.postgresPasscode 		= "PGPASSWORD="+self.postgresPassword +" "
		else: self.postgresPasscode 	= ""
		self.timeFormatDisplay  		= self.pluginPrefs.get(     "timeFormatDisplay", self.timeFormatInternal)
		self.newdata = {0:False}
		self.devList            		= json.loads(self.pluginPrefs.get("devList","{}"))
		self.lastDevSave				= 0
		self.lastpreSelectDevices		= 0.
		self.doSQLNow					= True
		self.actionList					= ""

		self.cleandevList()

		self.variFolderName				= self.pluginPrefs.get("variFolderName","minMax")
		self.saveNow					= True
		self.devIDSelected				= 0
		self.devIDSelectedExist			= 0
		self.devOrVarExist				= "Var"
		self.devOrVar					= "Var"
		self.saveDevList()
		self.subscribeVariable			= False
		self.subscribeDevice			= False

		self.pluginPrefs["postgreHelp2"] = "/Library/PostgreSQL/bin/psql indigo_history postgres "
		self.pluginPrefs["postgreHelp1"] = "/Applications/Postgres.app/Contents/Versions/latest/bin/psql indigo_history postgres "


		self.doDateLimits()

		return


	####-----------------    ---------
	def cleandevList(self):
		try:
			delID=[]
			for devId in self.devList:
				if "devOrVar" not in self.devList[devId]:
					self.indiLOG.log(30,"deleting var-id:{}  from tracking, devOrVar not in list  ".format(devId) )
					delID.append(devId)
				if "states" not in self.devList[devId]:
					self.indiLOG.log(30,"deleting dev-id:{}  from tracking >>states<< not in list".format(devId) )
					delID.append(devId)
			for devId in delID:
				try:
					self.indiLOG.log(30,"deleting dev-id:{}  from tracking:".format(devId) )
					del self.devList[devId]
				except:
					pass

			for devId in self.devList:
				if "states" not in self.devList[devId]: continue
				self.newdata[devId] = True
				remState = []
				for state in self.devList[devId]["states"]:
					if len(state)< 2:
						self.indiLOG.log(30,"deleting dev-id:{}/state:{}<   from tracking state mot properly defined".format(devId, state) )
						remState.append(state)
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
					if "data" not in self.devList[devId]["states"][state]:
							self.devList[devId]["states"][state]["data"] 			= []
					delTW =[]
					for TW in self.devList[devId]["states"][state]["measures"]:
						if TW not in _timeWindows:
							self.indiLOG.log(30,"deleting dev-id:{}/state:{}   from tracking >>TW<< not in list".format(devId, state) )
							delTW.append(TW)
						else:
							delMes =[]
							for MB in self.devList[devId]["states"][state]["measures"][TW]:
								if MB not in _MeasBins:
									self.indiLOG.log(30,"deleting dev-id:{}/state:{}  from tracking >>MB<< not in list".format(devId, state) )
									delMes.append(MB)
							for MB in delMes:
								del self.devList[devId]["states"][state]["measures"][TW][MB]
					for TW in delTW:
						del self.devList[devId]["states"][state]["measures"][TW]

				for state in remState:
					del self.devList[devId]["states"][state]
		except	Exception:
			self.logger.error("", exc_info=True)



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
		for d in _debugAreas:
			if valuesDict["debug"+d]: self.debugLevel.append(d)

		self.variFolderName     = valuesDict["variFolderName"]
		self.refreshRate        = float(valuesDict["refreshRate"])
		self.liteOrPsql         = valuesDict["liteOrPsql"]
		self.liteOrPsqlString   = valuesDict["liteOrPsqlString"]
		self.postgresPassword	= valuesDict["postgresPassword"]
		if self.postgresPassword != "" and self.liteOrPsql.find("psql") >-1: 
			self.postgresPasscode 		= "PGPASSWORD="+self.postgresPassword +" "
		else: self.postgresPasscode 	= ""
		self.timeFormatDisplay  = valuesDict["timeFormatDisplay"]

		try:
			indigo.variables.folder.create(self.variFolderName)
		except:
			pass

		self.doSQLNow	= True
		
		self.printConfigCALLBACK()
		return True, valuesDict




####-----------------   ---------
	def dummyCALLBACK(self):
		
		return
####-----------------   ---------
	def printConfigCALLBACK(self, printDevId=""):
		try:
			self.saveDevList()
			outTotal = "Configuration: "
			#         12345678901234567890123456789012345 12345678901212345678901234567 123456789012312345678901234
			header = "Short_Name      Dev/Var-Name-----------------------------   ID         State                  ignoreLess ignoreGreater    format  "
			outTotal += "\n"+header+" tracking     measures: -------"
			for devId in copy.deepcopy(self.devList):
				if devId == printDevId or printDevId == "":
					
					for state in self.devList[devId]["states"]:
						shortName = self.devList[devId]["states"][state]["shortName"]
						measures = ""
						for TW in _timeWindows:
							if TW in self.devList[devId]["states"][state]["measures"]: # TW = time Window
								ssLine = ""
								for MB in _MeasBins:
									if MB in self.devList[devId]["states"][state]["measures"][TW]:  # MB = measurement bin 
										if  self.devList[devId]["states"][state]["measures"][TW][MB]:
											if ssLine == "":
												if measures != "":
													ssLine += "\n ".ljust(len(header)+2 )
												ssLine += (TW+"-").ljust(14)
											ssLine += MB+" "
								measures += ssLine
						if measures == "":
							measures = "--- no measure selected, no variable will be created---"

						out = "{:13.0f}{:14.0f} '{:>8}'  ".format(self.devList[devId]["states"][state]["ignoreLess"], self.devList[devId]["states"][state]["ignoreGreater"], self.devList[devId]["states"][state]["formatNumbers"])

						if self.devList[devId]["devOrVar"] ==  "Var":  
							try:         
								outTotal += "\n{:16}{:42}{:>12} {:>19} {}{}".format(shortName, indigo.variables[int(devId)].name, devId, state, out, measures) 
							except	Exception:
								outTotal += "\n===> var: id:{} does not exist, removing".format(devId) 
								del self.devList[devId]
						else:           
							try:         
								outTotal += "\n{:16}{:42}{:>12} {:>19} {}{}".format(shortName, indigo.devices[int(devId)].name,   devId, state, out, measures) 
							except	Exception:
								outTotal += "\n===> dev: id:{} does not exist, removing".format(devId) 
								del self.devList[devId]

			self.indiLOG.log(20, outTotal )
			self.indiLOG.log(20,"config parameters foldername         >{}<".format(self.variFolderName) )
			self.indiLOG.log(20,"config parameters timeFormatDisplay  >{}<".format(self.timeFormatDisplay ) )
			self.indiLOG.log(20,"config parameters refreshRate        >{}<[secs]".format( self.refreshRate) )
			self.indiLOG.log(20,"config parameters scan data starting >{}<".format(self.firstDate) )
			self.indiLOG.log(20,"config parameters debug areas        >{}<".format(self.debugLevel) )

			self.indiLOG.log(20,"config parameters sqlite Or Psql     >{}<".format(self.liteOrPsql ) )
			if self.liteOrPsql == "psql":
				self.indiLOG.log(20,"config parameters psqlString         >{}<".format(self.liteOrPsqlString) )
				self.indiLOG.log(20,"config parameters postgresPassword   >{}<".format(self.postgresPassword ) )

			self.indiLOG.log(20,"" )
			self.indiLOG.log(20,"Time windows(bins)  fromm               to:" )
			#self.indiLOG.log(20, "{}".format( self.dateLimits) )
			for TW in _timeWindows:
				self.indiLOG.log(20, "{:15}     {} {}".format( TW, self.dateLimits[TW][0] , self.dateLimits[TW][1] ) )
			self.indiLOG.log(20,"" )
			self.indiLOG.log(20,"Explanation of measurements" )
			for binName in _MeasBins:
				self.indiLOG.log(20, "{:20}  {}".format( binName, _MeasBinsExplanation[binName] ) )
				
		except	Exception:
			self.logger.error("", exc_info=True)
		return



####-----------------  ---------
	def getMenuActionConfigUiValues(self, menuId):
		
		valuesDict=indigo.Dict()
		if menuId == "defineDeviceStates":
			for TW in _timeWindows:
				for mb in _MeasBins:
					valuesDict[TW+mb]		= False
			valuesDict["showM"]				= False          
			valuesDict["ignoreGreater"]		= "+9876543210."
			valuesDict["ignoreLess"]		= "-9876543210."
			valuesDict["MSG"]   			= ""
			self.devIDSelectedExist 		= 0
			self.devIDSelected				= 0
		return valuesDict




########### --- delete dev/states from tracking 
####-----------------   ---------
	def pickExistingDeviceCALLBACK(self,valuesDict="",typeId=""):               # Select only device/properties that are supported
		if self.decideMyLog("Setup"): self.indiLOG.log(10, "{}".format(valuesDict))
		if valuesDict["device"].find("-V") >-1:
			self.devOrVarExist = "Var"
			self.devIDSelectedExist = int(valuesDict["device"][:-2])# drop -V
		else:        
			self.devIDSelectedExist = int(valuesDict["device"])
			self.devOrVarExist = "Dev"

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
		devId = "{}".format(self.devIDSelectedExist)
		retList =[]
		if devId in self.devList:
			if self.devOrVarExist == "Var":
				retList.append(("value", "value"))
				return retList
			for test in self.devList[devId]["states"]:
				retList.append((test,test))             
		return retList
####-----------------   ---------
	def buttonRemoveCALLBACK(self,valuesDict="",typeId=""):  
		devId = "{}".format(self.devIDSelectedExist)
		state = valuesDict["state"]
		deldev={}
		theName = ""
		if devId in self.devList:
			if  state in self.devList[devId]["states"]:
				del self.devList[devId]["states"][state]
			if len(self.devList[devId]["states"]) ==0:
				deldev[devId] = True
		for dd in deldev:
			try: 	theName = indigo.devices[int(devId)].name
			except: 
				try: theName = indigo.variables[int(devId)].name
				except: pass
			del self.devList[dd]
		self.devIDSelectedExist 	= 0
		valuesDict["state"] = ""
		self.actionList += "preSelectDevices"
		self.indiLOG.log(20," dev/state / var: {} - {} - {} / removed from tracking".format(theName, devId, state))
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
		if self.decideMyLog("Setup"): self.indiLOG.log(10,str(valuesDict))
		if valuesDict["device"].find("-V") >-1:
			self.devOrVar = "Var"
			self.devIDSelected= int(valuesDict["device"][:-2])# drop -V
		else:        
			self.devIDSelected= int(valuesDict["device"])
			self.devOrVar = "Dev"


####-----------------   ---------
	def filterDevicesThatQualify(self,filter="",valuesDict="",typeId=""):               
		self.actionList += "preSelectDevices"
		retList= copy.copy(self.listOfPreselectedDevices )
		for devId in self.devList:
			if self.devList[devId]["devOrVar"] == "Var":
				try: retList.append([devId, "=TRACKED--"+indigo.variables[int(devId)].name])
				except: pass
			else:
				try: retList.append([devId, "=TRACKED--"+indigo.devices[int(devId)].name])
				except: pass
		return retList


####-----------------   ---------
	def filterStatesThatQualify(self,filter="",valuesDict="",typeId=""):                
	
		if self.devIDSelected == 0: return [(0,0)]

		retList=[]
		if self.devOrVar == "Var":
			retList.append(( "value", "value"))
			return retList
		
		dev=indigo.devices[self.devIDSelected]
		retList = []
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
					if x != "x" :
						count +=1
				if count>0:                                                 
					retList.append((test,test))             
		return retList
####-----------------   ---------
	def buttonConfirmStateCALLBACK(self,valuesDict="",typeId=""):               # Select only device/properties that are supported

		devId= "{}".format(self.devIDSelected)

		if len("{}".format(self.devIDSelected)) < 2:
			valuesDict["showM"] = False          
			valuesDict["MSG"] = "please select Device" 
			return valuesDict
		
		if self.devOrVar == "Var":
			dev=indigo.variables[int(self.devIDSelected)]
		else:
			dev=indigo.devices[int(self.devIDSelected)]
		
		state= valuesDict["state"]
		if len(state) < 2:
			valuesDict["showM"] = False          
			valuesDict["MSG"] = "please select State" 
			return valuesDict
			
		if devId not in self.devList:
			self.devList[devId]={}
			self.devList[devId]["states"]={}

			
		self.devList[devId]["devOrVar"]=self.devOrVar

		if  "states" not in self.devList[devId]:
			self.devList[devId]["states"]={}

			
		if  state not in self.devList[devId]["states"]:
			self.devList[devId]["states"][state] = {}

		if  "measures" not in self.devList[devId]["states"][state]:
			self.devList[devId]["states"][state]["measures"]		= {}
			self.devList[devId]["states"][state]["ignoreLess"]		= -9876543210.
			self.devList[devId]["states"][state]["ignoreGreater"]	= +9876543210.
			self.devList[devId]["states"][state]["formatNumbers"]	= "%.1f"
			self.devList[devId]["states"][state]["shortName"]		= ""
			self.devList[devId]["states"][state]["data"]			= []
			
		for TW in _timeWindows:
			if TW not in self.devList[devId]["states"][state]["measures"]:
				self.devList[devId]["states"][state]["measures"][TW] = {}
				
			for MB in _MeasBins:
				if MB not in self.devList[devId]["states"][state]["measures"][TW]:
					self.devList[devId]["states"][state]["measures"][TW][MB] = False

		for TW in self.devList[devId]["states"][state]["measures"]:
			for MB in self.devList[devId]["states"][state]["measures"][TW]:
				if self.devList[devId]["states"][state]["measures"][TW][MB]:
					valuesDict[TW+MB]= True
				else:   
					valuesDict[TW+MB]= False
				


		valuesDict["ignoreLess"]		= "{}".format(self.devList[devId]["states"][state]["ignoreLess"])
		valuesDict["ignoreGreater"]		= "{}".format(self.devList[devId]["states"][state]["ignoreGreater"])
		valuesDict["formatNumbers"] 	=  self.devList[devId]["states"][state]["formatNumbers"]
		valuesDict["shortName"] 		=  self.devList[devId]["states"][state]["shortName"]
		valuesDict["showM"]				= True 
       
		return valuesDict                        


####-----------------   ---------
	def buttonConfirmAddCALLBACK(self,valuesDict="",typeId=""):                # Select only device/properties that are supported

		anyOne = False
		try:
			valuesDict["MSG"] = "ok"
			devId = "{}".format(self.devIDSelected)
			if len(devId) < 3:
				valuesDict["MSG"] = "please select device"
				return valuesDict

			
			if self.devOrVar == "Var":
				dev=indigo.variables[int(self.devIDSelected)]
			else:
				dev=indigo.devices[int(self.devIDSelected)]


			if devId not in self.devList:
				self.devList[devId] = {}
				
			self.devList[devId]["devOrVar"]= self.devOrVar
		
			state = valuesDict["state"]
			if len(state) < 2:
				valuesDict["showM"] = False          
				valuesDict["MSG"] = "please select State" 
				return valuesDict

			
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
				self.devList[devId]["states"][state]["data"]			= []

				
			for TW in  _timeWindows:
				use=False
				for MB in _MeasBins: 
					if valuesDict[TW+MB]:
						self.devList[devId]["states"][state]["measures"][TW][MB]=True
						anyOne = True
					else:    
						self.devList[devId]["states"][state]["measures"][TW][MB]=False


			try: 	self.devList[devId]["states"][state]["ignoreLess"]		= float(valuesDict["ignoreLess"])
			except:	pass
			try:	self.devList[devId]["states"][state]["ignoreGreater"]	= float(valuesDict["ignoreGreater"])
			except:	pass
			self.devList[devId]["states"][state]["formatNumbers"]			= valuesDict["formatNumbers"]

			self.devList[devId]["states"][state]["shortName"]				= valuesDict["shortName"].replace(" ","_")
			# this makes it more readable
			if self.devList[devId]["states"][state]["shortName"] != "" and self.devList[devId]["states"][state]["shortName"][-1] not in ["_","-",":","@","#","~","*"]:
				self.devList[devId]["states"][state]["shortName"] += "_"

			self.saveNow 		= True
			self.doSQLNow		= True
			self.devIDSelected	= 0
			self.actionList 	+= "preSelectDevices"

			self.printConfigCALLBACK(printDevId=devId)
		except	Exception:
			self.logger.error("", exc_info=True)

		valuesDict["showM"] = False          
		if not anyOne: valuesDict["MSG"] = "no measure selected-- no variable will be created"

		return valuesDict


	####-----------------  ---------
	def buttonrefreshDataNowCALLBACKaction(self,action):
		return self.buttonrefreshDataNowCALLBACK(valuesDict=action.props)

	####-----------------  ---------
	def buttonrefreshDataNowCALLBACK(self,valuesDict=""):
		self.doSQLNow	= True
		self.indiLOG.log(20,"data refresh requested")
		return


####-----------------   main loop          ---------
	def runConcurrentThread(self):

		self.indiLOG.log(20,"runConcurrentThread")
		self.dorunConcurrentThread()
		self.saveDevList()


		if self.quitNow !="":
			indigo.server.log( "runConcurrentThread stopping plugin due to:  ::::: {} :::::".format(self.quitNow))

		self.quitNow =""

		exit()

####-----------------   main loop            ---------
	def dorunConcurrentThread(self): 

		refreshRate					= 30
		lastUpdate					= 0
		nextMinTimeSQL 				= 3600
		lastSqlTime					= 0
		hourLast					= datetime.datetime.now().hour
		self.doSQLNow				= True
		self.preSelectDevices()
		self.printConfigCALLBACK()
		try:
			while self.quitNow =="":

				nowTT	= time.time()
				condTime	= nowTT- lastUpdate > refreshRate
				condNewData	= self.newdata[0]
				condSQL		= self.doSQLNow or (nowTT - lastSqlTime > nextMinTimeSQL)
				if self.decideMyLog("Loop"): self.indiLOG.log(10,"timers: t:{}  d:{}  q:{}".format(condTime, condNewData, condSQL) )
				if self.actionList != "":
					if "doDateLimits" in self.actionList:
						self.doDateLimits()
					if "preSelectDevices" in self.actionList:
						self.preSelectDevices()
					self.saveNow = True
					self.actionList = ""	
					condTime = True
					condSQL = True

				if  condTime: 
					hourNow	= datetime.datetime.now().hour
						
					if hourNow != hourLast: # recalculate the limits etc
						self.doDateLimits() 
						condSQL 	= True
						hourLast	= hourNow 


					retCode = self.fillVariables(condSQL)
					if condSQL: 
						lastSqlTime = time.time()
						self.doSQLNow = False
					lastUpdate = time.time()

				if self.saveNow:
					self.saveDevList()
					self.saveNow = False

				if not self.subscribeDevice:
					indigo.variables.subscribeToChanges()
					indigo.devices.subscribeToChanges()
					self.indiLOG.log(20,"subscribing to device changes")
					self.subscribeDevice = True

				for ii in range(10):
					self.sleep(1)
					if self.actionList != "": 	break
					if self.doSQLNow: 			break
					if self.newdata[0]: 		break

				
		except Exception:
			pass

		return


####-----------------   ---------
	def variableUpdated(self, old, new):
		devId = "{}".format(old.id)
		if devId not in self.devList: return 
		if old.value == new.value: return

		nowDD 				= datetime.datetime.now()
		ddNow 				= nowDD.strftime(self.timeFormatInternal)
		ttNow 				= round((nowDD-self.epoch).total_seconds(),1)

		state = "value"
		nrec = len(self.devList[devId]["states"][state]["data"])
		if  nrec > 0 and ttNow < self.devList[devId]["states"][state]["data"][-1][2]:
			self.indiLOG.log(20,"bad old devList for {}-{}, old:{}, new:{}, dt:{}, data stored, last recs:{}".format(old.name,state, old.value, new.value, ttNow - self.devList[devId]["states"][state]["data"][-1][2], self.devList[devId]["states"][state]["data"][-2:] )) 
			return 

		self.devList[devId]["states"][state]["data"].append((self.getNumber(new.value), ddNow, ttNow))
		self.newdata[devId] = True
		self.newdata[0] = True
		if self.decideMyLog("AddData"): self.indiLOG.log(10,"new data for {}-{}, old:{}, new:{}, data added, last 2 recs:{}".format(old.name,state, old.value, new.value, self.devList[devId]["states"][state]["data"][-min(2,nrec):] )) 

		return 
			

####-----------------   ---------
	def deviceUpdated(self,  old, new):
		devId = "{}".format(old.id)
		if devId not in self.devList: return 
		nowDD 				= datetime.datetime.now()
		ddNow 				= nowDD.strftime(self.timeFormatInternal)
		ttNow 				= round((nowDD-self.epoch).total_seconds(),1)

		for state in self.devList[devId]["states"]:
			if state not in new.states: continue
			if old.states[state] == new.states[state]: continue

			nrec = len(self.devList[devId]["states"][state]["data"])
			if  nrec > 0 and ttNow < self.devList[devId]["states"][state]["data"][-1][2]:
				self.indiLOG.log(20,"bad old devList for {}-{}, old:{}, new:{}, dt:{}, data stored, last recs:{}".format(old.name,state, old.states[state], new.states[state], ttNow - self.devList[devId]["states"][state]["data"][-1][2], self.devList[devId]["states"][state]["data"][-2:] )) 
				continue

			self.devList[devId]["states"][state]["data"].append((self.getNumber(new.states[state]), ddNow, ttNow))
			self.newdata[devId] = True
			self.newdata[0] = True
			if self.decideMyLog("AddData"): self.indiLOG.log(10,"new data for {}-{}, old:{}, new:{}, data added, last 2 recs:{}".format(old.name,state, old.states[state], new.states[state], self.devList[devId]["states"][state]["data"][-min(2,nrec):] )) 

		return 

####-----------------  do the calculations and sql statements  ---------
	def fillVariables(self, condSQL):

		self.newdata[0] = False
		delList =[]
		t0 = time.time()
		nchanges = 0
		try:


			for devId in self.devList:
				if not condSQL and not self.newdata.get(devId,False): continue
				self.newdata[devId] = False
				
				if int(devId) > 0:
					try:
						if self.devList[devId]["devOrVar"] == "Var":
							devName= indigo.variables[int(devId)].name
						else:                            
							devName= indigo.devices[int(devId)].name
					except  Exception as e:
						if str(e).find("timeout waiting") > -1:
							self.logger.error("communication to indigo is interrupted", exc_info=True)
							return
						self.indiLOG.log(40," error; device with indigoID = {} does not exist, removing from tracking".format(devId)) 
						delList.append(devId)
						continue
						   
				#_timeWindows   =["thisHour","lastHour","thisDay","lastDay","thisWeek","lastWeek","thisMonth","lastMonth","lastWeek"]
				#_MeasBins     =["Min","Max","DateMin","DateMax","Ave","Count","Count1","StdDev""]
			
				states = self.devList[devId]["states"]
				for state in states:
					params				= states[state]
					if params["shortName"] != "":
						varName	= params["shortName"]
					else:
						varName	= devName.replace(" ","_")+"__"+state.replace(" ","_")+"__"
						
					if self.devList[devId]["states"][state]["data"] == [] or condSQL:
						dataSQL				= self.doSQL(devId,state,self.devList[devId]["devOrVar"])
						if self.decideMyLog("Fill"): self.indiLOG.log(20,"time used for                 sql:{:.2f}".format(time.time()- t0) )
						self.devList[devId]["states"][state]["data"]	= self.removeDoublesInSQL(dataSQL, params["ignoreLess"], params["ignoreGreater"])
						if self.decideMyLog("Fill"): self.indiLOG.log(20,"time used for  removeDoublesInSQL:{:.2f}".format(time.time()- t0) )

					values								= self.calculate(self.devList[devId]["states"][state]["data"], devName, params["measures"])
					if self.decideMyLog("Fill"): self.indiLOG.log(20,"time used for           calculate:{:.2f}".format(time.time()- t0) )

					if self.decideMyLog("Loop"): self.indiLOG.log(10,"variName:{}".format(varName))
					if self.decideMyLog("Loop"): self.indiLOG.log(10,";   state: {} params: {}".format(state, params) )
					if self.decideMyLog("Loop"): self.indiLOG.log(10,"values    {}".format(values)[0:500])

					for TW in values:
						if TW not in params["measures"]: continue
						
						value = values[TW]
						if self.decideMyLog("Loop"): self.indiLOG.log(10,"TW    {}; v: {}".format(TW, value))
						
						for MB in _MeasBins:
							if MB not in params["measures"][TW]:	continue
							if not params["measures"][TW][MB]:		continue
							try:	vari = indigo.variables[varName+TW+"_"+MB]
							except:
								try:	indigo.variable.create(varName+TW+"_"+MB,      "", self.variFolderName)
								except:	pass

							if  MB.find("Count")>-1:
								if indigo.variables[varName+TW+"_"+MB].value != "%d"%(value[MB]):
									nchanges += 1
									indigo.variable.updateValue(varName+TW+"_"+MB,          "%d"%(value[MB]) )
							elif MB.find("Date")>-1:
								if indigo.variables[varName+TW+"_"+MB].value != value[MB]:
									nchanges += 1
									indigo.variable.updateValue(varName+TW+"_"+MB,          value[MB])
							else:
								try:	
									if indigo.variables[varName+TW+"_"+MB].value != params["formatNumbers"]%(value[MB]):
										nchanges += 1
										indigo.variable.updateValue(varName+TW+"_"+MB,          params["formatNumbers"]%(value[MB]))
								except:	
										indigo.variable.updateValue(varName+TW+"_"+MB,          str(alue[MB]))
										nchanges += 1
								
			for devId in delList: 
				del self.devList[devId]
			if len(delList) > 0:
				self.saveDevList()
			if self.decideMyLog("Fill"): self.indiLOG.log(10,"filling Variables  #of changes:{}  total:{:.2f}[secs], doSQL:{}".format(nchanges,  time.time()- t0,  condSQL) )
			return True
		except	Exception:
			self.logger.error("", exc_info=True)
		return False

####-----------------  do the calculations and sql statements  ---------
	def doDateLimits(self):
		
		try:
			now				= time.time()
			dd				= datetime.datetime.now()
			day				= dd.day         # day in month
			wDay			= dd.weekday()   # day of week
			hour			= dd.hour        # hour in day
			nDay			= dd.timetuple().tm_yday
			nDay7			= nDay-7
			self.dateLimits	= {}
			self.firstDate 	= "99999999999999"      # last day of 2 months ago so that we always get 2 months
			day0	= dd-datetime.timedelta(hours=dd.hour,minutes=dd.minute,seconds=dd.second)
			day0End	= day0+datetime.timedelta(hours=24)
			day0EndF= (day0End).strftime(self.timeFormatInternal)


			hour0	= day0+datetime.timedelta(hours=hour)
			hour6	= day0+datetime.timedelta(hours=6)
			hour18	= day0+datetime.timedelta(hours=18)
			hour6Last	= hour6-datetime.timedelta(hours=24)
			hour18Last	= hour18-datetime.timedelta(hours=24)
			hour6Last2	= hour6Last-datetime.timedelta(hours=24)
			hour18Last2	= hour18Last-datetime.timedelta(hours=24)


			dh0		= hour0.strftime(self.timeFormatInternal)
			dh1		= (hour0+datetime.timedelta(hours=1)).strftime(self.timeFormatInternal)
			self.dateLimits["thisHour"] = [dh0,dh1,0,0,0]

			dh0	= (hour0-datetime.timedelta(hours=11)).strftime(self.timeFormatInternal)
			dh1 = (hour0+datetime.timedelta(hours=1)).strftime(self.timeFormatInternal)
			self.dateLimits["this12Hours"] = [dh0,dh1,0,0,0]

			dh0 = (hour0-datetime.timedelta(hours=23)).strftime(self.timeFormatInternal)
			dh1	= (hour0-datetime.timedelta(hours=11)).strftime(self.timeFormatInternal)
			self.dateLimits["last12Hours"] = [dh0,dh1,0,0,0]


			dh1	= hour0.strftime(self.timeFormatInternal)
			dh0	= (hour0-datetime.timedelta(hours=1)).strftime(self.timeFormatInternal)
			self.dateLimits["lastHour"] = [dh0,dh1,0,0,0]

			dh0	= (hour6).strftime(self.timeFormatInternal)
			dh1	= (hour18).strftime(self.timeFormatInternal)
			self.dateLimits["thisDay6-18"] = [dh0,dh1,0,0,0]

			dh0	= (hour18Last).strftime(self.timeFormatInternal)
			dh1	= (hour6).strftime(self.timeFormatInternal)
			self.dateLimits["thisDay18-6"] = [dh0,dh1,0,0,0]

			dh0	= (hour6Last).strftime(self.timeFormatInternal)
			dh1	= (hour18Last).strftime(self.timeFormatInternal)
			self.dateLimits["lastDay6-18"] = [dh0,dh1,0,0,0]

			dh0	= (hour18Last2).strftime(self.timeFormatInternal)
			dh1	= (hour6Last).strftime(self.timeFormatInternal)
			self.dateLimits["lastDay18-6"] = [dh0,dh1,0,0,0]

			dh0		= day0.strftime(self.timeFormatInternal)
			dh1		= day0EndF
			self.dateLimits["thisDay"] = [dh0,dh1,0,0,0]

			dh1		= day0.strftime(self.timeFormatInternal)
			dh0		= (day0-datetime.timedelta(days=1)).strftime(self.timeFormatInternal)
			self.dateLimits["lastDay"] = [dh0,dh1,0,0,0]

			dh1		= day0.strftime(self.timeFormatInternal)
			dh0		= (day0-datetime.timedelta(days=7)).strftime(self.timeFormatInternal)
			self.dateLimits["last7Days"] = [dh0,dh1,0,0,0]

			week0	= dd-datetime.timedelta(days=dd.weekday(),hours=dd.hour,minutes=dd.minute,seconds=dd.second)
			dh0		= week0.strftime(self.timeFormatInternal)
			weekend  =week0+datetime.timedelta(days=7)
			dh1		= weekend.strftime(self.timeFormatInternal)
			self.dateLimits["thisWeek"] = [dh0,dh1,0,0,0]

			dh1		= week0.strftime(self.timeFormatInternal)
			dh0		= (week0-datetime.timedelta(days=7)).strftime(self.timeFormatInternal)
			self.dateLimits["lastWeek"] = [dh0,dh1,0,0,0]

			month0	= dd-datetime.timedelta(days=dd.day-1,hours=dd.hour,minutes=dd.minute,seconds=dd.second) #move tobeginning of this month
			dh0		= month0.strftime(self.timeFormatInternal)
			monthEnd= month0+datetime.timedelta(days=31) # monve to end of month or previous month
			if monthEnd.day < 5: # if day is single digit, move back to last day of previous month
				monthEnd = monthEnd-datetime.timedelta(days=monthEnd.day-1)
			dh1		= monthEnd.strftime(self.timeFormatInternal)
			self.dateLimits["thisMonth"] = [dh0,dh1,0,0,0]

			dh1		= month0.strftime(self.timeFormatInternal)
			d0		= (month0-datetime.timedelta(days=28)) # move to previous month
			d0	 	= (d0-datetime.timedelta(days=d0.day)) #move to beginning of previous month
			dh0 	= d0.strftime(self.timeFormatInternal)    
			self.dateLimits["lastMonth"] = [dh0,dh1,0,0,0]

			# set first data 3 days before last month begins
			self.firstDate = (d0-datetime.timedelta(days=3)).strftime(self.timeFormatInternal)  

			for TW in self.dateLimits:
				self.dateLimits[TW][2] = (datetime.datetime.strptime(self.dateLimits[TW][0], self.timeFormatInternal)-self.epoch).total_seconds()
				self.dateLimits[TW][3] = (datetime.datetime.strptime(self.dateLimits[TW][1], self.timeFormatInternal)-self.epoch).total_seconds()
				self.dateLimits[TW][4] = max(1.,self.dateLimits[TW][3] - self.dateLimits[TW][2])


			if self.decideMyLog("Loop"): 
				self.indiLOG.log(10,"first-Date:  {}".format(self.firstDate))
				self.indiLOG.log(10,"date-limits: {}".format(self.dateLimits))
		except	Exception:
			self.logger.error("", exc_info=True)
		return 
					



####----------------- do the sql statement  ---------
	def doSQL(self, devId ,state, devOrVar): 
		dataOut = []
		ii 		= 0
		t0 = time.time()
		try:
			while ii < 3:

				if devOrVar== "Dev":
					sql2 = state+" from device_history_"+"{}".format(devId)
				else:    
					sql2 = " value from variable_history_"+"{}".format(devId)

				if self.liteOrPsql =="sqlite": 
					sql = "/usr/bin/sqlite3  -separator \";\" '"+self.indigoPath+ "logs/indigo_history.sqlite' \"select strftime('%Y-%m-%d-%H:%M:%S',ts,'localtime'), "
					sql4 ="  where ts > '"+ self.firstDate+"';\""
					cmd =sql+sql2+sql4

				else:    
					sql = self.liteOrPsqlString+ " -t -A -F ';' -c \"SELECT to_char(ts,'YYYY-mm-dd-HH24:MI:ss'), "
					sql4 ="  where to_char(ts,'YYYY-mm-dd-HH24:MI:ss') > '"+ self.firstDate+"'  ORDER by id  ;\""
					cmd = sql+sql2+sql4
					cmd = self.postgresPasscode + cmd
					if self.postgresUserId != "" and self.postgresUserId !="postgres": cmd = cmd.replace(" postgres "," "+self.postgresUserId+" ")

					
				ret, err = self.readPopen(cmd)
				if self.decideMyLog("Sql"): self.indiLOG.log(10,"time used:{:.2f}, {}".format(time.time()-t0, cmd))

				if ret.find("ERROR") > -1:
					ii += 1
					self.sleep(1)
					continue
				break    
			dataOut = ret
			if self.decideMyLog("Sql"): self.indiLOG.log(10,"data-out: "+ret[:300])
			if self.decideMyLog("Sql"): self.indiLOG.log(10,"err-out:  "+err[:300])
		except	Exception:
			self.logger.error("devId:{} ,state:{}, devOrVar:{}".format(evId ,state, devOrVar), exc_info=True)
		
		return dataOut
		
####----------------- calculate ave min max for all  ---------
	def calculate(self, dataIn, name, measures):     
		# TW = time window = bin
		# dataIn[n][Datestamp, value, time stamp]
		# dateLimits[TW][Startof bin date, endof bin date, start of bin timestamp, end of bin timestamp, secs in bin]
		# th method does:
		# go through data and calculate various measurs for each time window / bin 


		# init variables
		line				= ""
		value				= ""
		addedSecsForLastBin	= 20.
		dataOut 			= {}
		dateErrorShown 		= False
		valuesX 			= {}
		secondsWeight 		= {}
		secTotalInBin		= {}
		ttNow 				= (datetime.datetime.now()-self.epoch).total_seconds()

		# init dicts ..
		for TW in measures:
			dataOut[TW] = {"Min": +987654321000.,"Max":-987654321000.,"DateMin":"","DateMax":"","Start":-1234567890, "End":-1234567890,"Consumption":0,"Count":0.,"Count1":0,"StdDev":0,"StdDevSimple":0,"Ave":0,"AveSimple":0,"UpTime":0,"FirstEntryDate":"","FirstEntryValue":0,"LastEntryDate":"","LastEntryValue":0}

		for TW in measures:
			valuesX[TW] = []
			secondsWeight[TW] = []
			secTotalInBin[TW] = []

		try:

			#self.indiLOG.log(10,"dataIn :{}, =====: {} ".format( len(dataIn), str(dataIn)[0:1000]))
			nData = len(dataIn)
			if nData > 0:

				if dataIn[nData-1][1] != "":  # date time in data  of very last bin 
					lastSecInData = dataIn[nData-1][2] 
				else:
					lastSecInData = ttNow

				for nn in range(nData):

					dateDataPoint	= dataIn[nn][1]
					if dateDataPoint == "": continue

					secondsDataPoint  = dataIn[nn][2]
					# ceck make sure we have time stamp
					if type(secondsDataPoint) != type(1.0): 
						self.indiLOG.log(10,"dataIn bad data nn:{}, =====: {} ".format( dataIn[nn]))
						continue

					value	= dataIn[nn][0]
					if value == "x": continue


					# we need to know when the next data point is to calc averages properly
					if nn < nData - 1:
						lastData = False
						# next data time in secs
						secondsNextDataPoint	= dataIn[nn+1][2]
					else: 				
						lastData = True
						secondsNextDataPoint	= lastSecInData + addedSecsForLastBin # last measurement point + 90 secs 

					# loop through the timewindows
					for TW in measures:
						try:
							#if TW =="thisHour" and lastData: self.indiLOG.log(10,"{}, 1    secondsNextDataPoint:{:.0f}, secondsDataPoint:{:.0f}, lastSecInData:{:.0f},  ds:{:.0f}- {:.0f}".format(name,  secondsNextDataPoint, secondsDataPoint,lastSecInData,  secondsNextDataPoint - secondsDataPoint, secondsNextDataPoint - self.dateLimits[TW][2]))
							# skip if not at least one before TW or after timewindow

							if secondsDataPoint      < self.dateLimits[TW][2] and	  lastData:	
								secondsNextDataPoint = self.dateLimits[TW][2] + 3 # add virtual point in time window to get existing value into time window
								secondsDataPoint	 = self.dateLimits[TW][2] + 2
								lastSecInData		 = self.dateLimits[TW][2] + 1
								dateDataPoint		 = self.dateLimits[TW][0]

							if secondsNextDataPoint  < self.dateLimits[TW][2]: 					continue
							if secondsNextDataPoint  > self.dateLimits[TW][3] and not lastData:	continue

							#if TW =="thisHour" and lastData: self.indiLOG.log(10,"{},2    secondsNextDataPoint:{:.0f}, secondsDataPoint:{:.0f}, lastSecInData:{},  ds:{:.0f}".format( name,  secondsNextDataPoint, secondsDataPoint,lastSecInData,  secondsNextDataPoint - secondsDataPoint ))

							#_MeasBins       =["Min","Max","DateMin","DateMax","Ave","Count","Count ,..
							# self.dateLimits[TW]	[0] = start datetime string 
							#						[1] = end date time string
							#						[2] = start time sec since epoch
							#						[2] = end time sec since epoch
							#						[4] = total secs in bin

							# calulate validity of this datapoint from to secs, use that as weight fator for average
							#                                 # of seconds in bin              +90secs    last sec in bin           fist sec in bin  == dont take whole bin otherwise last value is overweighted
							secTotalInBin[TW] 	= min( self.dateLimits[TW][4], min( lastSecInData, self.dateLimits[TW][3]) - self.dateLimits[TW][2] ) 
							if secTotalInBin[TW] <= 0:
								self.indiLOG.log(20,"error delta sec <=0 for {}  lastData{} lastSecInData:{} dateLimits:{}".format( TW, lastData, lastSecInData, self.dateLimits[TW]  ))
								secTotalInBin[TW] = 1

							norm = 1.0

							#if TW =="thisHour" and lastData: self.indiLOG.log(10,"{},3    secondsNextDataPoint:{:.0f}, secondsDataPoint:{:.0f}, lastSecInData:{},  ds:{:.0f}, secTotalInBin:{}".format( name,  secondsNextDataPoint, secondsDataPoint,lastSecInData,  secondsNextDataPoint - secondsDataPoint,secTotalInBin[TW] ))


							if 	secondsNextDataPoint > self.dateLimits[TW][3]:  # no entry in this bin (time window)
								secondsEffective		   		=	self.dateLimits[TW][3] - secondsDataPoint
								test = 1
							elif secondsDataPoint < self.dateLimits[TW][2]:								  # at least one entry in bin (time window)
								secondsEffective		   		=	secondsNextDataPoint - self.dateLimits[TW][2]
								test = 2
							else:									# next is right of this time window
								secondsEffective		   		=	secondsNextDataPoint - secondsDataPoint
								test = 3

							try:	testL = dataOut[TW]["FirstEntryDate"] == ""
							except:	continue

							if  testL:  ## use last below date range?
								dataOut[TW]["Start"] 				= value 
								dataOut[TW]["End"] 					= value 

								dataOut[TW]["LastEntryDate"] 		= dateDataPoint 
								dataOut[TW]["LastEntryValue"]		= value 

								dataOut[TW]["FirstEntryDate"] 		= dateDataPoint 				# 
								dataOut[TW]["FirstEntryValue"]		= value 			# 

								valuesX[TW].append(value)				# std dev

								dataOut[TW]["Start"] 				= value 				# Start value
								dataOut[TW]["End"] 					= value 				# 
								dataOut[TW]["Min"] 					= value 				# min
								dataOut[TW]["DateMin"] 				= dateDataPoint  				# datestamp
								dataOut[TW]["Max"] 					= value 				# max 
								dataOut[TW]["DateMax"] 				= dateDataPoint  				# datestamp
								dataOut[TW]["Consumption"]			= dataOut[TW]["End"] - dataOut[TW]["Start"] 	

								secondsWeight[TW].append(secondsEffective)				# std dev
								norm 								= secondsEffective/secTotalInBin[TW]  
								dataOut[TW]["Ave"]					= value*norm			# time weighted average
								dataOut[TW]["Count"]				= 1    					# count
								dataOut[TW]["AveSimple"]			= value					# sum for simple average
								#if TW =="thisDay": self.indiLOG.log(10,"        0           norm:{:.3f}, av:{:.2f}, test:{}, secondsNextDataPoint:{:.0f}, secondsDataPoint:{:.0f}, ds:{:.0f}?{:.0f},  secTotalInBin:{:.0f}".format( norm, dataOut[TW]["Ave"],  test, secondsNextDataPoint, secondsDataPoint, secondsEffective, secondsNextDataPoint - secondsDataPoint, secTotalInBin))
								if value > 0: 
									dataOut[TW]["Count1"]			+= 1					# count if > 0
								if value != 0:
									dataOut[TW]["UpTime"]			= norm			# time weighted average
									#if dataOut[TW]["Ontime"] 	 == 0 				# datestamp
								continue
	
							# regular datapoint in bin
							try: 	testL = secondsDataPoint  > self.dateLimits[TW][2] and  secondsDataPoint <=  self.dateLimits[TW][3]
							except:	continue
							#if TW =="lastMonth": self.indiLOG.log(20,"{}  {:.1f} testL:{} ".format( dateDataPoint, value, testL))

							if testL:  ## in date range?
								valuesX[TW].append(value)				# std dev

								if dataOut[TW]["Min"] > value:
									dataOut[TW]["Min"] 				= value				# min 
									dataOut[TW]["DateMin"] 			= dateDataPoint				# datestamp
								if dataOut[TW]["Max"] < value:
									dataOut[TW]["Max"] 				= value				# max  
									dataOut[TW]["DateMax"]			= dateDataPoint				# datestamp

								dataOut[TW]["LastEntryDate"] 	= dateDataPoint 				#
								dataOut[TW]["LastEntryValue"]	= value 			# 

	
								dataOut[TW]["End"] 					= value 				# min

								secondsWeight[TW].append(secondsEffective)				# std dev
								norm 								= secondsEffective/secTotalInBin[TW] 
								dataOut[TW]["Ave"]					+= value * norm		# time weighted average
									
								dataOut[TW]["AveSimple"]			+= value 			# sum for simple average
								#if TW =="thisDay": self.indiLOG.log(10,"                    norm:{:.3f}, av:{:.2f}, test:{}, secondsNextDataPoint:{:.0f}, secondsDataPoint:{:.0f}, ds:{:.0f}?{:.0f},  secTotalInBin:{:.0f}".format( norm, dataOut[TW]["Ave"],  test, secondsNextDataPoint, secondsDataPoint, secondsEffective, secondsNextDataPoint - secondsDataPoint, secTotalInBin))

								dataOut[TW]["Count"]				+= 1				# count
								if value > 0: 
									dataOut[TW]["Count1"]			+= 1				# count if > 0
								if value != 0:
									dataOut[TW]["UpTime"]			+= norm			# time weighted average



							dataOut[TW]["Consumption"]				= dataOut[TW]["End"] - dataOut[TW]["Start"] 	
							
						except	Exception:
							self.logger.error("in  data line: {}  error ".format(dataIn[nn]), exc_info=True)
							continue       

				#finish averages dates etc       
				for TW in measures:
					if  dataOut[TW]["DateMin"] !="" and dataOut[TW]["DateMin"] <   self.dateLimits[TW][0]: dataOut[TW]["DateMin"] = self.dateLimits[TW][0]      
					if  dataOut[TW]["DateMax"] !="" and dataOut[TW]["DateMax"] <   self.dateLimits[TW][0]: dataOut[TW]["DateMax"] = self.dateLimits[TW][0]
					if self.timeFormatInternal != self.timeFormatDisplay:
						try:
							for xxx in ["DateMin","DateMax","FirstEntryDate","LastEntryDate"]:
								if dataOut[TW][xxx]	!= "": 
									dataOut[TW][xxx] = (datetime.datetime.strptime(dataOut[TW][xxx], self.timeFormatInternal)).strftime(self.timeFormatDisplay)
						except	Exception:
							if not dateErrorShown:
								self.logger.error("date conversion error , bad format: {}\nTW: {}, dataout:{}".format(self.timeFormatDisplay, TW, dataOut[TW]), exc_info=True)
								dateErrorShown = True

					dataOut[TW]["UpTime"]		= min(1.0, dataOut[TW]["UpTime"]) * 100		# uptime in %
					dataOut[TW]["AveSimple"]	= dataOut[TW]["AveSimple"]/max(1.,dataOut[TW]["Count"])     #  simple average

					# std deviations 
					if TW in valuesX and len(valuesX[TW]) > 0:
						stdSimple 	= 0
						stdTWA 		= 0

						for n in range(len(valuesX[TW])):
							x 			= valuesX[TW][n]
							stdSimple  += 						 (x - dataOut[TW]["AveSimple"])**2
							stdTWA	   += secondsWeight[TW][n] * (x - dataOut[TW]["Ave"])**2
							
						try:
							dataOut[TW]["StdDevSimple"] = math.sqrt(stdSimple / len(valuesX[TW]))
							dataOut[TW]["StdDev"] 		= math.sqrt(stdTWA    / max(1., secTotalInBin[TW]))
							#if  TW =="lastDay": self.indiLOG.log(10,"TW:{}  StdDevSimple:{:.5f}, AveSimple:{:.3f}, StdDev:{:.5f}, Ave:{:.3f}, len:{}; Count:{}".format(TW, dataOut[TW]["StdDevSimple"], dataOut[TW]["AveSimple"], dataOut[TW]["StdDev"], dataOut[TW]["Ave"], len(valuesX[TW]), dataOut[TW]["Count"]))# , valuesX[TW] ))
						except	Exception:
							self.indiLOG.log(10,"error in data: TW:{}, stdSimple: {}, len:{}  stdTWA:{}, secTotalInBin:{}, secondsWeight:{}, skipping ".format(TW, stdSimple, len(valuesX[TW]), stdTWA,  secTotalInBin[TW], str(secondsWeight[TW])[-100:] ))

		except	Exception:
			self.logger.error("dataIn: {}".format(dataIn), exc_info=True)
				
		return dataOut

####----------------- prep sql return data  ---------
	def removeDoublesInSQL(self,dataLines,ignoreLess,ignoreGreater):    # remove doubles same date/timestamp            
		dataOut 		= []
		try:
			date = ""
			value = -1234567890
			for line in dataLines.split("\n"):
				if len(line) < 20: continue
				line = line.split(";")
 
				v = self.getNumber(line[1])
				if v == "x": 			continue
				if v > ignoreGreater:   continue
				if v < ignoreLess:      continue
				# remove doubles
				if line[0] == date and v == value: 
										continue
				value = v
				date = line[0]
				dataOut.append((value, date, (datetime.datetime.strptime(date, self.timeFormatInternal)-self.epoch).total_seconds() ))

			if len(dataOut) == 0:
				dataOut=[[0., "", 0]]

		except	Exception:
			self.logger.error("", exc_info=True)
		#indigo.server.log("dataOut{}".format(str(dataOut))[0:1000])

		return dataOut

####-----------------   ---------
	def preSelectDevices(self):             # Select only device/properties that are supported:  numbers, bool, but not props that have "words"

		if time.time() - self.lastpreSelectDevices < 20: return # only every 10 secs max
		
		timeSpend = time.time()
		temp_listOfPreselectedDevices = []
		temp_devIDSelectedToTypeandName = {}

		devMax = ''
		stTimeMax = 0
		countMax = 0
		avTime  = 0
		countStates = 0
		countAllStates = 0

		for theVar in indigo.variables:
			val = theVar.value
			x = self.getNumber(val)
			if x != "x":
				try:
					if "{}".format(theVar.id) in self.devList:
						temp_listOfPreselectedDevices.append(("{}".format(theVar.id)+ "-V", "=TRACKED--Var-{}".format(theVar.name)))
					else:
						temp_listOfPreselectedDevices.append(("{}".format(theVar.id)+ "-V", "Var-{}".format(theVar.name)))
				except	Exception:
					self.logger.error("", exc_info=True)

		timeSpendDevs = time.time()
		for dev in indigo.devices.iter():
			theStates = dev.states.keys()
			count = 0
			stTime = time.time()
			for test in theStates:
				if "Mode" in test or "All" in test or ".ui" in test:
					skip = True
				else:
					skip = False

				if not skip:    
					val = dev.states[test]
					x = self.getNumber(val)
					if x != "x" :
						count += 1
						break
				countAllStates += 1	
				countStates += 1	
			if count > 0:                                                 # add to the selection list
				try:
					if "{}".format(dev.id) in self.devList:
						temp_listOfPreselectedDevices.append((dev.id, "=TRACKED--{}".format(dev.name)))
					else:
						temp_listOfPreselectedDevices.append((dev.id, dev.name))
				except	Exception:
					self.logger.error("", exc_info=True)
			stTime = time.time() - stTime
			if stTime > stTimeMax: 
				devMax = dev.name
				stTimeMax = stTime
				countMax = count
			avTime += stTime

		self.indiLOG.log(10,"preSelectDevices finished, total secs used:{:.2f} ".format(time.time() - timeSpend))
		self.listOfPreselectedDevices  = temp_listOfPreselectedDevices 
		self.devIDSelectedToTypeandName = temp_devIDSelectedToTypeandName


		self.lastpreSelectDevices = time.time()
		return




	def getNumber(self, val):
		# test if a val contains a valid number, if not return ""
		# return the number if any meaningful number (with letters before and after return that number)
		# "a-123.5e" returns -123.5
		# -1.3e5 returns -130000.0
		# -1.3e-5 returns -0.000013
		# "1.3e-5" returns -0.000013
		# "1.3e-5x" returns "" ( - sign not first position  ..need to include)
		# True, "truE" "on" "ON".. returns 1.0;  False "faLse" "off" returns 0.0
		# "1 2 3" returns ""
		# "1.2.3" returns ""
		# "12-5" returns ""
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
					ONE  = [ "TRUE" , "T", "ON",  "HOME", "YES", "JA" , "SI",  "IGEN", "OUI", "UP",  "OPEN", "CLEAR"   ]
					ZERO = [ "FALSE", "F", "OFF", "AWAY", "NO",  "NON", "NEIN", "NEM",        "DOWN", "CLOSED", "FAULTED", "FAULT", "EXPIRED"]
					val = "{}".format(val).upper()
					if val in ONE : return 1.0		# true/on   --> 1
					if val in ZERO: return 0.0		# false/off --> 0

	# SPECIAL CASES 
					if (val.find("LEAV")    == 0 or  # leave 
						  val.find("UNK")   == 0 or  
						  val.find("LEFT")  == 0  
											   ): return -1. 

					if( val.find("ENABL")   == 0 or   # ENABLE ENABLED 
						  val.find("ARRIV") == 0 
											   ): return 1.0		# 

					if( val.find("STOP")    == 0  # stop stopped
												): return 0.0		# 

					return "x"																		# all tests failed ... nothing there, return "
			except:
				return "x"		
			return "x"		



	####-----------------	 ---------
	def saveDevList(self):
		if time.time() - self.lastDevSave  < 20: return 
		xx = copy.deepcopy(self.devList)
		for devId in self.devList:
			if  "states" not in self.devList[devId]: continue
			for state in self.devList[devId]["states"]:
				if  "data" in self.devList[devId]["states"][state]:
					xx[devId]["states"][state]["data"] = []
		self.pluginPrefs["devList"] = json.dumps(xx)
		indigo.server.savePluginPrefs()
		self.lastDevSave = time.time()
		return 

	####-----------------	 ---------
	def completePath(self,inPath):
		if len(inPath) == 0: return ""
		if inPath == " ":	 return ""
		if inPath[-1] != "/": inPath += "/"
		return inPath

	####-----------------	 ---------
	def decideMyLog(self, msgLevel):
		try:
			if msgLevel	 == "all" or "all" in self.debugLevel:	 	return True
			if msgLevel	 == ""	 and "all" not in self.debugLevel:	return False
			if msgLevel in self.debugLevel:							return True
			return False
		except	Exception:
			self.logger.error("", exc_info=True)
		return False


####-------------------------------------------------------------------------####
	def readPopen(self, cmd):
		try:
			ret, err = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE).communicate()
			return ret.decode('utf_8'), err.decode('utf_8')
		except	Exception:
			self.logger.error("", exc_info=True)



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


