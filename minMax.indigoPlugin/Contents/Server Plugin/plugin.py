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
import cProfile
import pstats

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

_timeWindows	=["thisHour","lastHour","thisDay","lastDay","thisWeek","lastWeek","thisMonth","lastMonth","last7Days"] #   ,"weekdays"]
_MeasBins		=["Min","Max","DateMin","DateMax","Ave","Count","Count1","StdDev","Start","End","FirstEntryDate","FirstEntryValue","LastEntryDate","LastEntryValue"]

################################################################################
class Plugin(indigo.PluginBase):
####----------------- logfile  ---------
	def __init__(self, pluginId, pluginDisplayName, pluginVersion, pluginPrefs):
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
		for d in ["Loop","Sql","Setup","all"]:
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
		self.devList            		= json.loads(self.pluginPrefs.get("devList","{}"))

		self.checkcProfile()


		self.cleandevList()
		self.resetOldValues()

		self.variFolderName				= self.pluginPrefs.get("variFolderName","minMax")
		self.saveNow					= False
		self.devIDSelected				= 0
		self.devIDSelectedExist			= 0
		self.devOrVarExist				= "Var"
		self.devOrVar					= "Var"
		self.pluginPrefs["devList"]		= json.dumps(self.devList)
		self.dateLimits					= [["2015-11-00-00:00:00","2015-12-00-00:00:00",0,0],["2015-12-00-00:00:00","2015-12-12-00:00:00",0,0]]
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
				#self.indiLOG.log(10,"devId devList "+ "{}".format(devId)+ " " +unicosde(self.devList[devId]) )
				if "states" not in self.devList[devId]: continue
				remState =[]
				for state in self.devList[devId]["states"]:
					if len(state)< 2:
						remState.append(state)
					if "ignoreLess"    not in self.devList[devId]["states"][state]:
							self.devList[devId]["states"][state]["ignoreLess"]			= -9876543210.
					if "ignoreGreater" not in self.devList[devId]["states"][state]:
							self.devList[devId]["states"][state]["ignoreGreater"]			= +9876543210.
					if "measures" not in self.devList[devId]["states"][state]:
							self.devList[devId]["states"][state]["measures"] 				= {}
					if "formatNumbers" not in self.devList[devId]["states"][state]:
							self.devList[devId]["states"][state]["formatNumbers"] 		= "%.1f"
					if "timeFormatDisplay" not in self.devList[devId]["states"][state]:
							self.devList[devId]["states"][state]["timeFormatDisplay"] 	= self.timeFormatInternal
					if "shortName" not in self.devList[devId]["states"][state]:
							self.devList[devId]["states"][state]["shortName"] 			= ""
					delTW =[]
					for TW in self.devList[devId]["states"][state]["measures"]:
						if TW not in _timeWindows:
							delTW.append(TW)
						else:
							delMes =[]
							for MB in self.devList[devId]["states"][state]["measures"][TW]:
								if MB not in _MeasBins:
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
		for d in ["Loop","Sql","Setup","all"]:
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

		self.hourLast	= -99
		
		self.printConfigCALLBACK()
		return True, valuesDict


####-----------------   ---------
	def dummyCALLBACK(self):
		
		return
####-----------------   ---------
	def printConfigCALLBACK(self, printDevId=""):
		try:
			outTotal = "Configuration: "
			#         12345678901234567890123456789012345 12345678901212345678901234567 123456789012312345678901234
			header = "Dev/Var-Name------------                 ID                  State   ignoreLess  ignoreGreater     format  "
			outTotal += "\n"+header+"tracking measures: -------"
			for devId in self.devList:
				if devId == printDevId or printDevId== "":
					for state in self.devList[devId]["states"]:
						measures = ""
						for TW in self.devList[devId]["states"][state]["measures"]: # TW = time Window
							ssLine = ""
							for MB in self.devList[devId]["states"][state]["measures"][TW]:  # MB = measurement bin 
								if  self.devList[devId]["states"][state]["measures"][TW][MB]:
									if ssLine == "":
										if measures != "":
											ssLine += "\n ".ljust(len(header)+1 )
										ssLine += (TW+"-").ljust(12)
									ssLine += MB+" "
							measures += ssLine
						if measures == "":
							measures = "--- no measure selected, no variable will be created---"

						out = "{:13.0f}{:14.0f} '{:>8}'  ".format(self.devList[devId]["states"][state]["ignoreLess"], self.devList[devId]["states"][state]["ignoreGreater"], self.devList[devId]["states"][state]["formatNumbers"])

						if self.devList[devId]["devOrVar"] ==  "Var":           
							outTotal += "\n{:35} {:>12} {:>17} {}{}".format(indigo.variables[int(devId)].name, devId, state, out, measures) 

						else:           
							outTotal += "\n{:35} {:>12} {:>17} {}{}".format(indigo.devices[int(devId)].name,   devId, state, out, measures) 

			self.indiLOG.log(20,outTotal )
			self.indiLOG.log(20,"config parameters  foldername         >{}<".format(self.variFolderName) )
			self.indiLOG.log(20,"config parameters  refreshRate        >{}<".format(self.refreshRate) )
			self.indiLOG.log(20,"config parameters  liteOrPsql         >{}<".format(self.liteOrPsql ) )
			self.indiLOG.log(20,"config parameters  refreshRate        >{}<[secs]".format( self.refreshRate) )
			self.indiLOG.log(20,"config parameters  liteOrPsql         >{}<".format(self.liteOrPsql) )
			self.indiLOG.log(20,"config parameters  liteOrPsqlString   >{}<".format(self.liteOrPsqlString) )
			self.indiLOG.log(20,"config parameters  postgresPassword   >{}<".format(self.postgresPassword ) )
			self.indiLOG.log(20,"config parameters  timeFormatDisplay  >{}<".format(self.timeFormatDisplay ) )

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
			valuesDict["showM"]			= False          
			valuesDict["ignoreGreater"]	= "+9876543210."
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
		self.preSelectDevices()
		self.resetOldValues()
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
		if self.decideMyLog("Setup"): self.indiLOG.log(10,unicode(valuesDict))
		if valuesDict["device"].find("-V") >-1:
			self.devOrVar = "Var"
			self.devIDSelected= int(valuesDict["device"][:-2])# drop -V
		else:        
			self.devIDSelected= int(valuesDict["device"])
			self.devOrVar = "Dev"


####-----------------   ---------
	def filterDevicesThatQualify(self,filter="",valuesDict="",typeId=""):               
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
	
		if self.devIDSelected ==0: return [(0,0)]

		retList=[]
		if self.devOrVar == "Var":
			retList.append(( "value", "value"))
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
			self.devList[devId]["states"][state]["ignoreLess"]	= -9876543210.
			self.devList[devId]["states"][state]["ignoreGreater"]	= +9876543210.
			self.devList[devId]["states"][state]["formatNumbers"]	= "%.1f"
			self.devList[devId]["states"][state]["shortName"]		= ""
			
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
		valuesDict["formatNumbers"] 	=  (self.devList[devId]["states"][state]["formatNumbers"])
		valuesDict["shortName"] 		=  (self.devList[devId]["states"][state]["shortName"])
		valuesDict["showM"]				= True 
		self.resetOldValues()  
       
		return valuesDict                        


####-----------------   ---------
	def buttonConfirmCALLBACK(self,valuesDict="",typeId=""):                # Select only device/properties that are supported

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

			self.saveNow 		= True
			self.devIDSelected	= 0
			self.preSelectDevices()

			self.printConfigCALLBACK(printDevId=devId)
		except	Exception:
			self.logger.error("dataIn: {}".format(dataIn), exc_info=True)

		valuesDict["showM"] = False          
		if not anyOne: valuesDict["MSG"] = "no measure selected-- no variable will be cretaed"

		return valuesDict


	####-----------------  ---------
	def buttonrefreshDataNowCALLBACKaction(self,action):
		return self.buttonrefreshDataNowCALLBACK(valuesDict=action.props)

	####-----------------  ---------
	def buttonrefreshDataNowCALLBACK(self,valuesDict=""):
		self.hourLast	= -99
		self.indiLOG.log(20,"data refresh requested")
		return

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
		except	Exception as e:
			pass

		self.timeTrackWaitTime = 60
		return "off", ""

	####-----------------            ---------
	def printcProfileStats(self,pri=""):
		try:
			if pri !="": pick = pri
			else:		 pick =  'cumtime'
			outFile		= self.indigoPreferencesPluginDir+"timeStats"
			indigo.server.log( " print time track stats to: {}.dump / txt  with option: {}".format(outFile, pick))
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
			indigo.server.log("testing if variable {} is == on/off/print-option to enable/end/print time tracking of all functions and methods (option:'',calls,cumtime,pcalls,time)".format(self.timeTrVarName))

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

####-----------------   var update ==> trigger sql run          ---------
	def variableUpdated(self, orig, new):
		#self.indiLOG.log(10,"variable data refresh "+ new.name)
		if "{}".format(new.id) not in self.devList: return 
		self.QList.put("{}".format(new.id))
		#self.indiLOG.log(10,"variable data refresh requested due to new data in "+ new.name)
	
####-----------------   dev update ==> trigger sql run          ---------
	def deviceUpdated(self, orig, new):
		if "{}".format(new.id) not in self.devList: return 
		#self.indiLOG.log(10,"device data refresh requested due to new data in "+ new.name)
		for state in self.devList["{}".format(new.id)]["states"]:
			if state in new.states and new.states[state] != orig.states[state]:
				#self.indiLOG.log(10,"device data refresh requested due to new data in "+ new.name+"  {}".format(new.states[state] ))
				self.QList.put("{}".format(new.id))
				break


####-----------------   main loop          ---------
	def runConcurrentThread(self):

		self.QList = queue.Queue()
		self.dorunConcurrentThread()
		self.checkcProfileEND()


		if self.quitNow !="":
			indigo.server.log( "runConcurrentThread stopping plugin due to:  ::::: {} :::::".format(self.quitNow))

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
				#self.indiLOG.log(10,"timers: " +"{}".format(cond1) +"  "+"{}".format(cond2) +"  "+"{}".format(cond3) +"  "+"{}".format(allUpdates))
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
							self.pluginPrefs["devList"] = json.dumps(self.devList)
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
					

				
		except Exception:
			pass

		self.pluginPrefs["devList"] =json.dumps(self.devList)
		return


####-----------------   ---------
	def checkConfig(self):
		if time.time() - self.timerCheckConfig < 100: return
		self.timerCheckConfig = time.time()
		try:
			nVars = 0
			nDevs = 0
			for devId in self.devList:
				if self.devList[devId]["devOrVar"] == "Var":
					if not self.subscribeVariable: indigo.variables.subscribeToChanges()
					nVars +=1
					if nVars == 1 and not self.subscribeVariable: self.indiLOG.log(20,"subscribing to variable changes")
					self.subscribeVariable = True
				else:
					if not self.subscribeDevice: indigo.devices.subscribeToChanges()
					nDevs +=1
					if nDevs ==1 and not self.subscribeDevice: self.indiLOG.log(20,"subscribing to device changes")
					self.subscribeDevice = True
					
			if nVars ==0 and self.subscribeVariable: self.quitNow =" restart due to no variables subcriptions needed"
			if nDevs ==0 and self.subscribeDevice:  self.quitNow =" restart due to no variables subcriptions needed"
		except	Exception:
			self.logger.error("dataIn: {}".format(dataIn), exc_info=True)



####-----------------   ---------
	def resetOldValues(self):
		try:
				
			self.oldValues = {}
			for devId in self.devList:
				self.oldValues[devId] = {}
				for state in self.devList[devId]["states"]:
					self.oldValues[devId][state] = {"sum":-1, "nv":-1}

		except	Exception:
			self.logger.error("dataIn: {}".format(dataIn), exc_info=True)


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
						if self.devList[devId]["devOrVar"] == "Var":
							devName= indigo.variables[int(devId)].name
						else:                            
							devName= indigo.devices[int(devId)].name
					except  Exception as e:
						if unicode(e).find("timeout waiting") > -1:
							self.logger.error("communication to indigo is interrupted", exc_info=True)
							return
						self.indiLOG.log(40," error; device with indigoID = {} does not exist, removing from tracking".format(devId)) 
						delList.append(devId)
						continue
						   
				#_timeWindows   =["thisHour","lastHour","thisDay","lastDay","thisWeek","lastWeek","thisMonth","lastMonth","last7Days"]
				#_MeasBins     =["Min","Max","DateMin","DateMax","Ave","Count","Count1","StdDev""]

				states =self.devList[devId]["states"]
				for state in states:
					params				= states[state]
					if params["shortName"] != "":
						varName	= params["shortName"]
					else:
						varName	= devName.replace(" ","_")+"__"+state.replace(" ","_")+"__"
						
					dataSQL				= self.doSQL(devId,state,self.devList[devId]["devOrVar"])
					dataClean,sum,nv	= self.removeDoublesInSQL(dataSQL, params["ignoreLess"], params["ignoreGreater"])
					if sum == self.oldValues[devId][state]["sum"] and nv == self.oldValues[devId][state]["nv"] and self.hourLast != -99: 
						continue
						
					self.oldValues[devId][state]["sum"] = sum
					self.oldValues[devId][state]["nv"]  = nv
					values								 = self.calculate(dataClean)

					if self.decideMyLog("Loop"): self.indiLOG.log(10,"variName ".format(varName))
					if self.decideMyLog("Loop"): self.indiLOG.log(10,"values    {}".format(values)[0:500])
					if self.decideMyLog("Loop"): self.indiLOG.log(10,";   state: {} params: {}".format(state, params)+" {}".format(values)[0:30])

					for TW in values:
						if TW not in params["measures"]: continue
						
						value=values[TW]
						if self.decideMyLog("Loop"): self.indiLOG.log(10,"TW    " + TW+" {}".format(value))
						
						for MB in _MeasBins:
							if MB not in params["measures"][TW]:	continue
							if not params["measures"][TW][MB]:	continue

							try:	vari = indigo.variables[varName+TW+"_"+MB]
							except:
								try:	indigo.variable.create(varName+TW+"_"+MB,      "", self.variFolderName)
								except:	pass

							if  MB.find("Count")>-1:
										indigo.variable.updateValue(varName+TW+"_"+MB,          ("%d"%(value[MB])).strip())
							elif MB.find("Date")>-1:
										indigo.variable.updateValue(varName+TW+"_"+MB,          value[MB].strip())
							else:
								try:	indigo.variable.updateValue(varName+TW+"_"+MB,          (params["formatNumbers"]%(value[MB])).strip())
								except:	indigo.variable.updateValue(varName+TW+"_"+MB,          "")
								
			for devId in delList:
				del self.devList[devId]
		except	Exception:
			self.logger.error("", exc_info=True)
		return allUpdates

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

			hour0	= dd-datetime.timedelta(minutes=dd.minute,seconds=dd.second)
			day0	= dd-datetime.timedelta(hours=dd.hour,minutes=dd.minute,seconds=dd.second)
			day0End	= day0+datetime.timedelta(hours=24)
			day0EndF= (day0End).strftime(self.timeFormatInternal)

			dh0		= hour0.strftime(self.timeFormatInternal)
			dh1		= (hour0+datetime.timedelta(hours=1)).strftime(self.timeFormatInternal)
			self.dateLimits["thisHour"] = [dh0,dh1,0,0,0]

			dh1		= dh0
			dh0		= (hour0-datetime.timedelta(hours=1)).strftime(self.timeFormatInternal)
			self.dateLimits["lastHour"] = [dh0,dh1,0,0,0]

			dh0		= day0.strftime(self.timeFormatInternal)
			dh1		= day0EndF
			self.dateLimits["thisDay"] = [dh0,dh1,0,0,0]

			dh1		= day0.strftime(self.timeFormatInternal)
			dh0		= (day0-datetime.timedelta(days=1)).strftime(self.timeFormatInternal)
			self.dateLimits["lastDay"] = [dh0,dh1,0,0,0]

			week0	= dd-datetime.timedelta(days=dd.weekday(),hours=dd.hour,minutes=dd.minute,seconds=dd.second)
			dh0		= week0.strftime(self.timeFormatInternal)
			weekend  =week0+datetime.timedelta(days=7)
			dh1		= weekend.strftime(self.timeFormatInternal)
			self.dateLimits["thisWeek"] = [dh0,dh1,0,0,0]

			dh1		= week0.strftime(self.timeFormatInternal)
			dh0		= (week0-datetime.timedelta(days=7)).strftime(self.timeFormatInternal)
			self.dateLimits["lastWeek"] = [dh0,dh1,0,0,0]

			month0	= dd-datetime.timedelta(days=dd.day-1,hours=dd.hour,minutes=dd.minute,seconds=dd.second)
			dh0		= month0.strftime(self.timeFormatInternal)
			monthEnd= month0+datetime.timedelta(days=31)
			if monthEnd.day < 5:
				monthEnd = monthEnd-datetime.timedelta(days=monthEnd.day-1)
			dh1		= monthEnd.strftime(self.timeFormatInternal)
			self.dateLimits["thisMonth"] = [dh0,dh1,0,0,0]

			dh1		= month0.strftime(self.timeFormatInternal)
			d0		= (month0-datetime.timedelta(days=1))
			dh0 	= (month0-datetime.timedelta(days=d0.day)).strftime(self.timeFormatInternal)    
			self.dateLimits["lastMonth"] = [dh0,dh1,0,0,0]

			dh0		= (dd - datetime.timedelta(days=7,hours=dd.hour,minutes=dd.minute,seconds=dd.second) ).strftime(self.timeFormatInternal)
			dh1		= day0EndF
			self.dateLimits["last7Days"] = [dh0,dh1,0,0,0]

			for TW in self.dateLimits:
				self.dateLimits[TW][2] = (datetime.datetime.strptime(self.dateLimits[TW][0], self.timeFormatInternal)-self.epoch).total_seconds()
				self.dateLimits[TW][3] = (datetime.datetime.strptime(self.dateLimits[TW][1], self.timeFormatInternal)-self.epoch).total_seconds()
				self.dateLimits[TW][4] = max(1.,self.dateLimits[TW][3] - self.dateLimits[TW][2])

			if self.decideMyLog("Loop"): 
				self.indiLOG.log(10,"first-Date:  {}".format(self.firstDate))
				self.indiLOG.log(10,"date-limits: {}".format(self.dateLimits))
		except	Exception:
			self.logger.error("dataIn: {}".format(dataIn), exc_info=True)
		return 
					



####----------------- do the sql statement  ---------
	def doSQL(self,devId,state,devOrVar): 
		dataOut = []
		ii 		= 0
		try:
			while ii<3:

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

					
				if self.decideMyLog("Sql"): self.indiLOG.log(10,cmd)
				ret, err = self.readPopen(cmd)
				if ret.find("ERROR")>-1:
					ii+=1
					self.sleep(1)
					continue
				break    
			dataOut = ret
			if self.decideMyLog("Sql"): self.indiLOG.log(10,"data-out: "+ret[:300])
			if self.decideMyLog("Sql"): self.indiLOG.log(10,"err-out:  "+err[:300])
		except	Exception:
			self.logger.error("dataIn: {}".format(dataIn), exc_info=True)
		
		return dataOut
		
####----------------- calculate ave min max for all  ---------
	def calculate(self,dataIn):             
		line				= ""
		value				= ""
		addedSecsForLastBin	= 90.
		dataOut 			= {}
		dateErrorShown 		= False
		for TW in self.dateLimits:
			dataOut[TW] = {"Min": -987654321000.,"Max":987654321000.,"DateMin":"","DateMax":"","Count":0.,"Count1":0,"StdDev":0,"Ave":0,"AveSimple":0,"FirstEntryDate":"","FirstEntryValue":"","LastEntryDate":"","LastEntryValue":""}
		try:

			nData = len(dataIn)
			if nData > 0:

				if dataIn[nData-1][1] != "":
					lastSecInData = (   datetime.datetime.strptime(dataIn[nData-1][1], self.timeFormatInternal) - self.epoch   ).total_seconds() 
				else:
					lastSecInData = int(time.time())

				for nn in range(nData):
					line = dataIn[nn]
					date	= line[1]
					if date == "": continue
					value	= self.getNumber(line[0])
					##self.indiLOG.log(10,date+"  {}".format(value))
					if value == "x": continue

					secondsStartD	= (datetime.datetime.strptime(date, self.timeFormatInternal)-self.epoch).total_seconds()
					if nn < nData-1:
						lastData = False
						secondsEndD	= (datetime.datetime.strptime(dataIn[nn+1][1], self.timeFormatInternal)-self.epoch).total_seconds()
						dateNext   = dataIn[nn+1][1]
					else: 				
						lastData = True
						secondsEndD	= lastSecInData +addedSecsForLastBin # last measurement point + 90 secs 
						dateNext 	= "9999-12-01-12:33:12"

					for TW in self.dateLimits:
						try:
							if dateNext < self.dateLimits[TW][0]: 					continue
							if dateNext > self.dateLimits[TW][1] and not lastData: continue

#							_MeasBins       =["Min","Max","DateMin","DateMax","Ave","Count","Count1"]
						#                         # of seconds in bin                                     +90secs    last sec in bin           fist sec in bin  == dont take whole bin otherwise last value is overweighted
							detalSecTotal	= max( 1., min(self.dateLimits[TW][4],   min(lastSecInData+addedSecsForLastBin, self.dateLimits[TW][3]) - self.dateLimits[TW][2]  ) )
							secondsEnd   	= min(secondsEndD,  self.dateLimits[TW][3]) 
							# first data point?
							norm = 1.0
							if  date  >= self.dateLimits[TW][0] and dataOut[TW]["FirstEntryDate"] =="" and value != 0:  ## use last below date range?
								dataOut[TW]["FirstEntryDate"] 		= date 				# 
								dataOut[TW]["FirstEntryValue"]		= value 			# 

							if  (date  < self.dateLimits[TW][0] and dataOut[TW]["Count"] <= 1) or dataOut[TW]["Count"] == 0:  ## use last below date range?
								dataOut[TW]["Start"] 				= value 				# Start value
								dataOut[TW]["End"] 					= value 				# 
								dataOut[TW]["Min"] 					= value 				# min
								dataOut[TW]["DateMin"] 				= date  				# datestamp

								dataOut[TW]["Max"] 					= value 				# max 
								dataOut[TW]["DateMax"] 				= date  				# datestamp

								if not lastData: norm 				= (secondsEnd - self.dateLimits[TW][2])/detalSecTotal 
								dataOut[TW]["Ave"]					= value*norm			# time weighted average
								dataOut[TW]["Count"]				= 1    					# count
								dataOut[TW]["AveSimple"]			= value					# sum for simple average
								dataOut[TW]["StdDev"]				= value*value*norm		# std dev
								if value >0: dataOut[TW]["Count1"]	+= 1					# count if > 0
	
							# regular datapoint in bin
							if date  > self.dateLimits[TW][0] and  date <=  self.dateLimits[TW][1]:  ## in date range?
								if dataOut[TW]["Min"] > value:
									dataOut[TW]["Min"] 				= value				# min 
									dataOut[TW]["DateMin"] 			= date				# datestamp

								if dataOut[TW]["Max"] < value:
									dataOut[TW]["Max"] 				= value				# max  
									dataOut[TW]["DateMax"]			= date				# datestamp

								if value != 0:
									dataOut[TW]["LastEntryDate"] 	= date 				#
									dataOut[TW]["LastEntryValue"]	= value 			# 

	
								dataOut[TW]["End"] 					= value 				# min
								norm 								= (secondsEnd - secondsStartD)/detalSecTotal
								dataOut[TW]["Ave"]					+= value * norm		# time weighted average
								dataOut[TW]["Count"]				+= 1				# count
								dataOut[TW]["AveSimple"]			+= value 			# sum for simple average
								dataOut[TW]["StdDev"]				+= value*value * norm# sum for simple average
								if value >0: dataOut[TW]["Count1"] += 1				# count if > 0

							
						except	Exception:
							self.logger.error("{}".format(line).format(dataIn), exc_info=True)
							continue            
				for TW in self.dateLimits:
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
					dataOut[TW]["StdDev"] 		= math.sqrt(abs(dataOut[TW]["StdDev"]  - dataOut[TW]["Ave"]**2)) #  std dev
					dataOut[TW]["AveSimple"]	= dataOut[TW]["AveSimple"]/max(1.,dataOut[TW]["Count"])     #  simple average
		except	Exception:
			self.logger.error("dataIn: {}".format(dataIn), exc_info=True)
				
		return dataOut

####----------------- prep sql return data  ---------
	def removeDoublesInSQL(self,dataLines,ignoreLess,ignoreGreater):    # remove doubles same date/timestamp            
		dataOut=[]
		sum 	= 0
		nValues	= 0
		try:
			dataIn=dataLines.split("\n")
			t= dataIn[0].split(";")
			if len(t)!=2: return dataOut, sum, nValues
			if self.decideMyLog("Loop"): self.indiLOG.log(10,"{}".format(t))
			date=t[0]
			try:
				value=self.getNumber(t[1])
			except:
				value=0.
			if value == "x": 
				value=0.
			else:
				dataOut.append((value,date))
				nValues += 1
				sum     += value 

			for line in dataIn:
				if len(line) < 20: continue
				line=line.split(";")
 
				v = self.getNumber(line[1])
				if line[0] == date: 
					if v == "x": 			continue
					if v == value: 			continue
					if v > ignoreGreater:	continue
					if v < ignoreLess:		continue
					value=v
					dataOut.append((value,date))
					continue
					
				v = self.getNumber(line[1])
				if v == "x": continue
				if v > ignoreGreater:   continue
				if v < ignoreLess:      continue
				value=v
				date=line[0]
				dataOut.append((value,date))
				sum 	+= value
				nValues +=1

			if len(dataOut) ==0:
				dataOut=[[0., ""]]

		except	Exception:
			self.logger.error("", exc_info=True)
		##indigo.server.log("dataOut{}".format(dataOut))

		return dataOut, sum, nValues


####-----------------   ---------
	def preSelectDevices(self):             # Select only device/properties that are supported:  numbers, bool, but not props that have "words"
		self.listOfPreselectedDevices=[]
		self.devIDSelectedToTypeandName={}


		for theVar in indigo.variables:
			val = theVar.value
			x = self.getNumber(val)
			if x != "x":
				try:
					if "{}".format(theVar.id) in self.devList:
						self.listOfPreselectedDevices.append(("{}".format(theVar.id)+ "-V", "=TRACKED--Var-{}".format(theVar.name)))
					else:
						self.listOfPreselectedDevices.append(("{}".format(theVar.id)+ "-V", "Var-{}".format(theVar.name)))
				except	Exception:
					self.logger.error("", exc_info=True)

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
					if x != "x" :
						count +=1
			if count>0:                                                 # add to the selection list
				try:
					if "{}".format(dev.id) in self.devList:
						self.listOfPreselectedDevices.append((dev.id, "=TRACKED--"+ dev.name))
					else:
						self.listOfPreselectedDevices.append((dev.id, dev.name))
				except	Exception:
					self.logger.error("", exc_info=True)
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
				return "x"																			# something failed eg unicode only ==> return ""
			return "x"																				# should not happen just for safety




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


