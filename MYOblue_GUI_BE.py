# Graphical interface for signal visualization and interaction with ELEMYO MYOblue sensors
# 2025-07-15 by ELEMYO (https://github.com/ELEMYO)
# 
# Changelog:
#     2025-07-15 - added functions for bruxism analysis
#     2022-04-22 - improved user interface
#     2021-10-04 - serial port connection stability improved
#     2021-09-01 - initial release

# Code is placed under the MIT license
# Copyright (c) 2021 ELEMYO
# 
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
# 
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
# 
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.
# ===============================================

import sys
import os
from importlib import metadata

missing = {'pyserial', 'pyqtgraph', 'PyQt5', 'numpy', 'scipy'} 
for dist in metadata.distributions():
    if dist.name in missing:
        missing.remove(dist.name)

if missing:
    for module in missing:
        os.system("python -m pip install " + module)

from PyQt5 import QtCore, QtWidgets, QtGui
from PyQt5.QtCore import Qt
import serial
import pyqtgraph as pg
import numpy as np
import time
from scipy.signal import butter, lfilter
import serial.tools.list_ports
from scipy.fftpack import fft
from serial import SerialException
from datetime import datetime
from scipy import integrate

# Main window
class GUI(QtWidgets.QMainWindow):
    # Initialize constructor
    def __init__(self):
          super(GUI, self).__init__()
          self.initUI()
    # Custom constructor 
    def initUI(self): 
        # Values        
        self.delay = 0.21 # Graphics update delay
        self.setWindowTitle("ELEMYO MYOblue GUI v1.1.0")
        self.setWindowIcon(QtGui.QIcon('img/icon.png'))
        
        self.fs = 500 # Sampling frequency in Hz
        self.dt = [1/self.fs]*4  # Time between two signal measurements in s
        
        self.passLowFrec = 1 # Low frequency for band-pass filter
        self.passHighFrec = 250 # High frequency for band-pass filter
        
        self.timeWidth = 10 # Plot window length in seconds
        self.dataWidth = int((self.timeWidth + 10)*self.fs) # Maximum count of plotting data points (40 seconds window)
        self.Data = np.zeros((4, self.dataWidth)) # Raw data matrix, first index - sensor number, second index - sensor data 
        self.DataEnvelope = np.zeros((4, self.dataWidth)) # Envelope of row data, first index - sensor number, second index - sensor data
        self.DataIntegral = np.zeros((4, self.dataWidth))
        self.l = [0]*4 # Current sensor data point
        self.Time = np.zeros((4, self.dataWidth)) # Time array (in seconds), first index - sensor number, second index - time of measurement
        self.xRangeStart = 0
        
        self.MovingAverage = MovingAverage(self.fs) # Variable for data envelope (for moving average method)
        self.MovingAverage_Integral = MovingAverage_Integral(self.fs) # Variable for data envelope (for moving average method)
        
        self.recordingFileName_BIN = '' # Recording file name
        self.recordingFileName_TXT = '' # Recording file name
        self.recordingFile_BIN = 0 # Recording file 
        self.recordingFile_TXT = 0 # Recording file
        self.loadFileName = '' # Data load file name
        self.loadFile = 0 # Data load variable
        self.sliderpos = 0 # Position of data slider 
        self.loadDataLen = 0 # Number of signal samples in data file
        self.loadData = 0 # Data from load file
        self.startNum = 0 # Sensors message number associated with 0% data slider position
        self.stopNum = 0 # Sensors message number associated with 100% data slider position
        
        self.FFT = np.zeros((4, 500)) # Fast Fourier transform data
        
        # Accessory variables for data read from serial
            
        self.TIMER = 0;
        self.ms_len = [0]*4;
        self.msg_end = bytearray([0])
        
        self.VDD = [0]*4 # Battery charge array (in voltes) 
        self.MSG_NUM = [0]*4
        self.MSG_NUM_0 = [0]*4
        
        # Accessory variables for BE mask
        self.TimeStartBE = [0]*4
        self.FlagBE = [0]*4

        # Menu panel
        self.liveFromSerialAction = QtWidgets.QAction(QtGui.QIcon('img/play.png'), 'Start/Stop live from serial ', self)
        self.liveFromSerialAction.setCheckable(True)
        self.liveFromSerialAction.setChecked(False)
        self.liveFromSerialAction.triggered.connect(self.liveFromSerial)
        
        self.COMports=QtWidgets.QComboBox()
        self.COMports.setDisabled(False)
        
        self.refreshAction = QtWidgets.QAction(QtGui.QIcon('img/refresh.png'), 'Refresh screen (R)', self)
        self.refreshAction.setShortcut('r')
        self.refreshAction.triggered.connect(self.refreshForAction)
        
        self.dataRecordingAction = QtWidgets.QAction(QtGui.QIcon('img/rec.png'), 'Start/Stop recording', self)
        self.dataRecordingAction.triggered.connect(self.dataRecording)
        self.dataRecordingAction.setCheckable(True)
        self.dataRecordingAction.setDisabled(True)
        
        self.pauseAction = QtWidgets.QAction(QtGui.QIcon('img/pause.png'), 'Pause (Space)', self)
        self.pauseAction.setCheckable(True)
        self.pauseAction.setChecked(False)
        self.pauseAction.triggered.connect(self.pause)
        self.pauseAction.setShortcut('Space')
               
        self.PlaybackAction = QtWidgets.QAction(QtGui.QIcon('img/playback.png'), 'Start/Stop playback from file: \nFILE NOT SELECTED', self)
        self.PlaybackAction.triggered.connect(self.Playback)
        self.PlaybackAction.setCheckable(True)
        self.PlaybackAction.setDisabled(True)
        
        dataLoadAction = QtWidgets.QAction(QtGui.QIcon('img/load.png'), 'Select playback file', self)
        dataLoadAction.triggered.connect(self.dataLoad)
        
        self.bandstopAction = QtWidgets.QCheckBox('BANDSTOP FILTER:', self)
        self.bandstopAction.setCheckable(True)
        
        self.notchActiontypeBox=QtWidgets.QComboBox()
        self.notchActiontypeBox.addItem("50 Hz")
        self.notchActiontypeBox.addItem("60 Hz")
        self.notchActiontypeBox.setDisabled(True)
                        
        self.bandpassAction = QtWidgets.QCheckBox('BANDPASS FILTER:', self)
        self.bandpassAction.setCheckable(True)
        self.bandpassAction.setChecked(True)
        self.bandpassAction1 = QtWidgets.QLabel('  -  ', self)
        self.bandpassAction2 = QtWidgets.QLabel('       ', self)
        
        self.passLowFreq = QtWidgets.QSpinBox()
        self.passLowFreq.setRange(1, 249)
        self.passLowFreq.setValue(1)
        self.passLowFreq.setDisabled(True)
                      
        self.passHighFreq = QtWidgets.QSpinBox()
        self.passHighFreq.setRange(1, 249)
        self.passHighFreq.setValue(250)
        self.passHighFreq.setDisabled(True)     
        
        self.slider = QtWidgets.QScrollBar(QtCore.Qt.Horizontal)
        self.slider.setValue(0)
        self.slider.setFixedWidth(40)
        self.slider.setDisabled(True)

        self.sensorsNumberAction = QtWidgets.QLabel(' SENSORS NUMBER: ', self)
        self.sensorsNumberAction1 = QtWidgets.QLabel('     ', self)
        self.sensorsNumber = QtWidgets.QDoubleSpinBox()
        self.sensorsNumber.setRange(1, 4)
        self.sensorsNumber.setDecimals(0)
        self.sensorsNumber.setDisabled(True)
        self.sensorsNumber.setValue(2) 
        
        self.rawSignalAction = QtWidgets.QCheckBox('MAIN SIGNAL', self)
        self.rawSignalAction.setChecked(True)
        self.rawSignalAction1 = QtWidgets.QLabel('       ', self)        
        
        self.EnvelopeSignalAction = QtWidgets.QCheckBox('ENVELOPE:', self)
        self.EnvelopeSignalAction.setChecked(True)
        self.EnvelopeSignalAction1 = QtWidgets.QLabel('    ', self)
        self.EnvelopeSignalAction2 = QtWidgets.QLabel('      ', self)
        self.envelopeSmoothingСoefficient = QtWidgets.QDoubleSpinBox()
        self.envelopeSmoothingСoefficient.setSingleStep(0.01)
        self.envelopeSmoothingСoefficient.setRange(0, 1)
        self.envelopeSmoothingСoefficient.setValue(0.95)
        
        self.IntegralSignalAction = QtWidgets.QCheckBox('INTEGRAL:', self)
        self.IntegralSignalAction.setChecked(True)
        self.IntegralSignalAction1 = QtWidgets.QLabel('    ', self)
        self.IntegralSignalAction2 = QtWidgets.QLabel('      ', self)
        self.integrationInterval = QtWidgets.QDoubleSpinBox()
        self.integrationInterval.setSingleStep(0.01)
        self.integrationInterval.setRange(0, 2)
        self.integrationInterval.setValue(0.5)

        self.sensorSelectedAction = QtWidgets.QLabel('Sensor: ', self)
        self.sensorSelectedAction.setStyleSheet("background-color: transparent; font-weight: bold;")

        self.sensorSelectedActionBox=QtWidgets.QComboBox()
        self.sensorSelectedActionBox.addItem("1")
        self.sensorSelectedActionBox.setStyleSheet("background-color: gray; font-weight: bold;")

#--------------------------        
        # Toolbar
        toolbar = []
        toolbar.append(self.addToolBar('Tool1'))
        toolbar.append(self.addToolBar('Tool2'))
        toolbar.append(self.addToolBar('Tool3'))
        toolbar[0].addWidget(self.COMports)
        toolbar[0].addAction(self.liveFromSerialAction)
        toolbar[0].addAction(self.dataRecordingAction)
        toolbar[0].addAction(self.refreshAction)
        toolbar[0].addAction(self.pauseAction)
        toolbar[1].addAction(dataLoadAction)
        toolbar[1].addAction(self.PlaybackAction)
        toolbar[1].addWidget(self.slider)
        toolbar[2].addWidget(self.sensorsNumberAction)
        toolbar[2].addWidget(self.sensorsNumber)
        toolbar[2].addWidget(self.rawSignalAction1)
        toolbar[2].addWidget(self.rawSignalAction)
        
        toolbar[2].addWidget(self.EnvelopeSignalAction1)
        toolbar[2].addWidget(self.EnvelopeSignalAction)
        toolbar[2].addWidget(self.envelopeSmoothingСoefficient)
        toolbar[2].addWidget(self.EnvelopeSignalAction2)
        
        toolbar[2].addWidget(self.IntegralSignalAction1)
        toolbar[2].addWidget(self.IntegralSignalAction)
        toolbar[2].addWidget(self.integrationInterval)
        toolbar[2].addWidget(self.IntegralSignalAction2)
        
        toolbar[2].addWidget(self.bandstopAction)
        toolbar[2].addWidget(self.notchActiontypeBox)
        toolbar[2].addWidget(self.bandpassAction2)
        toolbar[2].addWidget(self.bandpassAction)
        toolbar[2].addWidget(self.passLowFreq)
        toolbar[2].addWidget(self.bandpassAction1)
        toolbar[2].addWidget(self.passHighFreq)
        
        # Plot widgets for 1-4 sensor
        self.pw = [] # Plot widget array, index - sensor number
        self.p = [] # Raw data plot, index - sensor number
        self.pe = [] # Envelope data plot, index - sensor number
        self.pi = [] 
        for i in range(4):
            self.pw.append(pg.PlotWidget(background=(21 , 21, 21, 255)))
            self.pw[i].showGrid(x=True, y=True, alpha=0.7) 
            self.p.append(self.pw[i].plot())
            self.pe.append(self.pw[i].plot())
            self.pi.append(self.pw[i].plot())
            self.p[i].setPen(color=(100, 255, 255), width=0.8)
            self.pe[i].setPen(color=(255, 0, 0), width=1)
            self.pi[i].setPen(color=(0, 255, 0), width=2)
            # self.pw[i].getAxis('bottom').setStyle(showValues=False)
        # self.pw[3].getAxis('bottom').setStyle(showValues=True)
        
        
        # Plot widget for spectral Plot
        self.pwFFT = pg.PlotWidget(background=(13, 13, 13, 255))
        self.pwFFT.showGrid(x=True, y=True, alpha=0.7) 
        self.pFFT = self.pwFFT.plot()
        self.pFFT.setPen(color=(100, 255, 255), width=1)
        self.pwFFT.setLabel('bottom', 'Frequency', 'Hz')
        
        # Histogram widget
        self.pb = [] # Histogram item array, index - sensor number
        self.pbar = pg.PlotWidget(background=(13 , 13, 13, 255))
        self.pbar.showGrid(x=True, y=True, alpha=0.7)            
        self.pb.append(pg.BarGraphItem(x=np.linspace(1, 2, num=1), height=np.linspace(1, 2, num=1), width=0.3, pen=QtGui.QColor(153, 0, 0), brush=QtGui.QColor(153, 0, 0)))
        self.pb.append(pg.BarGraphItem(x=np.linspace(2, 3, num=1), height=np.linspace(2, 3, num=1), width=0.3, pen=QtGui.QColor(229, 104, 19), brush=QtGui.QColor(229, 104, 19)))
        self.pb.append(pg.BarGraphItem(x=np.linspace(3, 4, num=1), height=np.linspace(3, 4, num=1), width=0.3, pen=QtGui.QColor(221, 180, 10), brush=QtGui.QColor(221, 180, 10)))
        self.pb.append(pg.BarGraphItem(x=np.linspace(4, 5, num=1), height=np.linspace(4, 5, num=1), width=0.3, pen=QtGui.QColor(30, 180, 30), brush=QtGui.QColor(30, 180, 30)))
        for i in range(4):
            self.pbar.addItem(self.pb[i])  
        self.pbar.setLabel('bottom', 'Sensor number')
        
        # Style
        centralStyle = "color: rgb(255, 255, 255); background-color: rgb(13, 13, 13);"
        
        # Numbering of graphs
        backLabel = []
        for i in range(2):
            backLabel.append(QtWidgets.QLabel(""))
            backLabel[i].setStyleSheet("font-size: 25px; background-color: rgb(21, 21, 21);")
        
        numberLabel = []
        for i in range(4):
            numberLabel.append(QtWidgets.QLabel(" " + str(i+1) + " "))
        numberLabel[0].setStyleSheet("font-size: 25px; background-color: rgb(153, 0, 0); border-radius: 14px;")
        numberLabel[1].setStyleSheet("font-size: 25px; background-color: rgb(229, 104, 19); border-radius: 14px;") 
        numberLabel[2].setStyleSheet("font-size: 25px; background-color: rgb(221, 180, 10); border-radius: 14px;")
        numberLabel[3].setStyleSheet("font-size: 25px; background-color: rgb(30, 180, 30); border-radius: 14px;")
        
        self.ChargeLabel  = []
        for i in range(4):
            self.ChargeLabel.append(QtWidgets.QLabel("BATTERY: 0.00 V"))
            self.ChargeLabel[i].setStyleSheet("background-color: transparent; font-weight: bold;")
        
        self.TriggerLabel  = []
        self.TriggerValue  = []
        self.StartTimeLabel = []
        self.NumberBE_Lable = []
        self.NumberBE_PerTime_Lable = []
        
        self.StartTimeValue  = []
        self.EndTimeLabel = []
        self.EndTimeValue  = []
        self.NumberBE = []
        self.NumberBE_PerTime = []
        
        for i in range(4):
            self.TriggerLabel.append(QtWidgets.QLabel("Trigger value:"))
            self.StartTimeLabel.append(QtWidgets.QLabel("Start timer (s):"))
            self.EndTimeLabel.append(QtWidgets.QLabel("Stop timer (s):"))
            self.NumberBE_Lable.append(QtWidgets.QLabel("Number of BE:"))
            self.NumberBE_PerTime_Lable.append(QtWidgets.QLabel("BE per hour:"))
            
            self.TriggerLabel[i].setStyleSheet("background-color: transparent; font-weight: bold;")
            self.StartTimeLabel[i].setStyleSheet("background-color: transparent; font-weight: bold;")
            self.EndTimeLabel[i].setStyleSheet("background-color: transparent; font-weight: bold;")
            self.NumberBE_Lable[i].setStyleSheet("background-color: transparent; font-weight: bold;")
            self.NumberBE_PerTime_Lable[i].setStyleSheet("background-color: transparent; font-weight: bold;")
            
            self.TriggerValue.append(QtWidgets.QSpinBox())
            self.TriggerValue[i].setSingleStep(1)
            self.TriggerValue[i].setRange(0, 2500)
            self.TriggerValue[i].setValue(100)
            
            self.StartTimeValue.append(QtWidgets.QDoubleSpinBox())
            self.StartTimeValue[i].setSingleStep(0.1)
            self.StartTimeValue[i].setRange(0, 60)
            self.StartTimeValue[i].setValue(0.5)
            
            self.EndTimeValue.append(QtWidgets.QDoubleSpinBox())
            self.EndTimeValue[i].setSingleStep(0.1)
            self.EndTimeValue[i].setRange(0, 60)
            self.EndTimeValue[i].setValue(30)
            
            self.NumberBE.append(QtWidgets.QSpinBox())
            self.NumberBE[i].setSingleStep(1)
            self.NumberBE[i].setRange(0, 10000)
            self.NumberBE[i].setValue(0)
            
            self.NumberBE_PerTime.append(QtWidgets.QDoubleSpinBox())
            self.NumberBE_PerTime[i].setSingleStep(1)
            self.NumberBE_PerTime[i].setRange(0, 10000)
            self.NumberBE_PerTime[i].setValue(0)
        
        # Main widget
        centralWidget = QtWidgets.QWidget()
        centralWidget.setStyleSheet(centralStyle)
        
        self.textWindow = QtWidgets.QPlainTextEdit()
        self.textWindow.setReadOnly(True)
        
        self.textWindow.insertPlainText(datetime.now().strftime("[%H:%M:%S] ") + "program launched\n")
        
        # Layout
        vbox = QtWidgets.QVBoxLayout()
        
        topleft = QtWidgets.QFrame()
        topleft.setFrameShape(QtWidgets.QFrame.StyledPanel)
        
        plotLayout = []
        self.row = []
        for i in range(4):
            plotLayout.append(QtWidgets.QGridLayout())
            plotLayout[i] = QtWidgets.QGridLayout()
            if i == 0: plotLayout[0].addWidget(backLabel[0], 0, 0, 10, 1)
            if i == 2: plotLayout[2].addWidget(backLabel[1], 0, 0, 10, 1)
            plotLayout[i].addWidget(numberLabel[i], 0, 0, 10, 1, Qt.AlignVCenter)
            plotLayout[i].addWidget(self.pw[i], 0, 1, 10, 50)
            plotLayout[i].addWidget(self.ChargeLabel[i], 0, 49) 
            plotLayout[i].addWidget(self.TriggerLabel[i], 1, 49) 
            plotLayout[i].addWidget(self.TriggerValue[i], 1, 50) 
            plotLayout[i].addWidget(self.StartTimeLabel[i], 2, 49) 
            plotLayout[i].addWidget(self.StartTimeValue[i], 2, 50) 
            plotLayout[i].addWidget(self.EndTimeLabel[i], 3, 49) 
            plotLayout[i].addWidget(self.EndTimeValue[i], 3, 50)  
            plotLayout[i].addWidget(self.NumberBE_Lable[i], 4, 49) 
            plotLayout[i].addWidget(self.NumberBE[i], 4, 50) 
            plotLayout[i].addWidget(self.NumberBE_PerTime_Lable[i], 5, 49) 
            plotLayout[i].addWidget(self.NumberBE_PerTime[i], 5, 50) 
            plotLayout[i].setContentsMargins(0, 0, 0, 0)    
            
            self.row.append(QtWidgets.QWidget())
            self.row[i].setLayout(plotLayout[i])
            
        splitter = QtWidgets.QSplitter(Qt.Vertical)
        splitter.handle(100)
        for i in range(4): splitter.addWidget(self.row[i])
        
        layout = QtWidgets.QGridLayout()       
        layout.addWidget(splitter, 0, 0, 40, 4)
        layout.addWidget(self.pbar, 0, 4, 20, 11)
        layout.addWidget(self.pwFFT, 20, 4, 16, 11)
        layout.setColumnStretch(2, 2)

        layout.addWidget(self.sensorSelectedAction , 20, 13, 1, 1)
        layout.addWidget(self.sensorSelectedActionBox , 20, 14, 1, 1)  
        
        layout.addWidget(self.textWindow, 37, 4, 3, 12)  
        
        layout.addWidget(self.textWindow, 36, 4, 3, 12)   
        
        vbox.addLayout(layout)
        centralWidget.setLayout(vbox)
        self.setCentralWidget(centralWidget)  
        self.showMaximized()
        self.show()    
        
        # Serial monitor
        self.serialMonitor = SerialMonitor(self.delay)
        ports = [self.COMports.itemText(i) for i in range(self.COMports.count())]
        
        for i in range(len(self.serialMonitor.ports)):
                if self.serialMonitor.ports[i] not in ports:
                    self.COMports.addItem(self.serialMonitor.ports[i])
                    
        if self.serialMonitor.COM != '':
            self.serialMonitor.serialConnect()
            self.liveFromSerialAction.setChecked(True)
            self.dataRecordingAction.setDisabled(False)
            self.sensorsNumber.setDisabled(False)
            self.textWindow.insertPlainText(datetime.now().strftime("[%H:%M:%S] ") + "live from " + self.serialMonitor.COM +" \n")
            self.textWindow.verticalScrollBar().setValue(self.textWindow.verticalScrollBar().maximum()-2)
            self.COMports.setDisabled(True)

        self.sensorsNumber.valueChanged.connect(self.setSensorsNumber)
        self.setSensorsNumber(2)
        self.mainrun = MainRun(self.delay)
        self.mainrun.bufferUpdated.connect(self.updateListening, QtCore.Qt.QueuedConnection)  
        
    def liveFromSerial(self):
        if self.liveFromSerialAction.isChecked():
            self.refresh()
            self.serialMonitor.serialConnect()
            self.textWindow.insertPlainText(datetime.now().strftime("[%H:%M:%S] ") + "live from " + self.serialMonitor.COM +" \n")
            self.textWindow.verticalScrollBar().setValue(self.textWindow.verticalScrollBar().maximum()-2)
            self.PlaybackAction.setChecked(False)
            self.refreshAction.setDisabled(False)   
            self.pauseAction.setDisabled(False)
            self.dataRecordingAction.setDisabled(False)
            self.COMports.setDisabled(True)
            self.slider.setDisabled(True)
            self.slider.setFixedWidth(40)
            self.sensorsNumber.setDisabled(False)

        else:
            self.refresh()
            self.serialMonitor.serialDisconnection()
            self.textWindow.insertPlainText(datetime.now().strftime("[%H:%M:%S] ") + "live stopped\n")
            self.textWindow.verticalScrollBar().setValue(self.textWindow.verticalScrollBar().maximum()-2)
            self.refreshAction.setDisabled(True)   
            self.pauseAction.setDisabled(True)
            self.dataRecordingAction.setDisabled(True)
            self.COMports.setDisabled(False)
            self.sensorsNumber.setDisabled(True)
           
    # Start working
    def start(self):
        self.mainrun.running = True
        self.mainrun.start()
    
    # Pause data plotting
    def pause(self):
        if self.pauseAction.isChecked():
            self.mainrun.running = False
            self.textWindow.insertPlainText(datetime.now().strftime("[%H:%M:%S] ") + "pause ON" + "\n")
            self.textWindow.verticalScrollBar().setValue(self.textWindow.verticalScrollBar().maximum()-2)
        else:
            self.mainrun.running = True
            self.mainrun.start()
            self.textWindow.insertPlainText(datetime.now().strftime("[%H:%M:%S] ") + "pause OFF" + "\n")
            self.textWindow.verticalScrollBar().setValue(self.textWindow.verticalScrollBar().maximum()-2)

    # Refresh data
    def refresh(self):
        self.l = [0] * 4
        self.Time = np.zeros((4, self.dataWidth))
        self.Data = np.zeros((4, self.dataWidth))
        self.DataEnvelope = np.zeros((4, self.dataWidth))
        self.DataIntegral = np.zeros((4, self.dataWidth))
        self.msg_end = bytearray([0])      
        self.MSG_NUM = [0]*4
        self.ms_len =  [0]*4
        self.MSG_NUM_0 = [0]*4
        self.slider.setValue(0)
        self.xRangeStart = 0
        self.TIMER = 0
        for i in range(4):
            self.NumberBE[i].setValue(0)
            self.NumberBE_PerTime[i].setValue(0)
            self.FlagBE[i] = 0

    # Refresh screen
    def refreshForAction(self):
        self.refresh()
        self.textWindow.insertPlainText(datetime.now().strftime("[%H:%M:%S] ") + "refresh" + "\n")
        self.textWindow.verticalScrollBar().setValue(self.textWindow.verticalScrollBar().maximum()-2)      
         
    # Initialize recording data to a file
    def dataRecording(self):
        if (self.dataRecordingAction.isChecked()):
            self.sensorsNumber.setDisabled(True)
            self.recordingFileName_TXT = datetime.now().strftime("%Y_%m_%d_%H_%M_%S") + ".txt"
            self.recordingFileName_BIN = datetime.now().strftime("%Y_%m_%d_%H_%M_%S") + ".bin"
            self.textWindow.insertPlainText(datetime.now().strftime("[%H:%M:%S] ") + "recording to \"" + os.getcwd() +"\\" + self.recordingFileName_BIN + "\"\n")
            self.textWindow.verticalScrollBar().setValue(self.textWindow.verticalScrollBar().maximum()-2)

            self.recordingFile_TXT = open(self.recordingFileName_TXT, "a") # Data file creation
            self.recordingFile_TXT.write(datetime.now().strftime("Date: %Y.%m.%d\rTime: %H:%M:%S") + "\r\n") # Data file name
            self.recordingFile_TXT.write("File format: \r\nsensor number | message number | battery charge | 119 data points \r\n") # Data file format

            
            self.recordingFile_BIN = open(self.recordingFileName_BIN, 'ab')
        else:
            self.recordingFile_TXT.close()
            self.recordingFile_BIN.close()
            self.sensorsNumber.setDisabled(False)
            self.textWindow.insertPlainText(datetime.now().strftime("[%H:%M:%S] ") + "recording stopped. Result file: \"" + os.getcwd() + self.recordingFileName_TXT + "\"\n")
            self.textWindow.verticalScrollBar().setValue(self.textWindow.verticalScrollBar().maximum()-2)
                
    # Selecting playback file
    def dataLoad(self):
        if self.liveFromSerialAction.isChecked():
            self.dataRecordingAction.setChecked(False)
            self.refreshAction.setDisabled(False)    
            self.pauseAction.setDisabled(False)
        self.recordingFileName_TXT = ''
        path = QtWidgets.QFileDialog.getOpenFileName(self, 'Open a file', '',
                                        'All Files (*.bin*)')
        if path != ('', ''):
            self.loadFileName = str(path[0])
            self.textWindow.insertPlainText(datetime.now().strftime("[%H:%M:%S] ") + "playback file selected: " + self.loadFileName + "\n")
            self.textWindow.verticalScrollBar().setValue(self.textWindow.verticalScrollBar().maximum()-2)
            self.PlaybackAction.setText("Start/Stop playback from file: \n" + self.loadFileName)
            self.PlaybackAction.setDisabled(False)
    
    # Playback initialization 
    def Playback(self):
        if self.PlaybackAction.isChecked():
            self.slider.setDisabled(False)
            self.slider.setFixedWidth(300)
            if self.liveFromSerialAction.isChecked():
                self.liveFromSerialAction.setChecked(False)
            self.refresh()
            self.liveFromSerialAction.setChecked(False)
            self.serialMonitor.serialDisconnection()
            self.dataRecordingAction.setDisabled(False)  
            self.refreshAction.setDisabled(True) 
            self.pauseAction.setDisabled(False)  
            self.COMports.setDisabled(False)
            self.sensorsNumber.setDisabled(False)
            
            self.loadFile = open(self.loadFileName, 'rb')
            
            self.textWindow.insertPlainText(datetime.now().strftime("[%H:%M:%S] ") + "playback from: " + self.loadFileName + "\n")
            self.textWindow.verticalScrollBar().setValue(self.textWindow.verticalScrollBar().maximum()-2)
            
            self.loadData = self.loadFile.read()
            self.loadDataLen = int(len(self.loadData)/244)
            self.loadFile.close()
            
        else:
            self.slider.setDisabled(True)
            self.slider.setFixedWidth(40)
            self.refresh()
            self.dataRecordingAction.setDisabled(True)
            self.textWindow.insertPlainText(datetime.now().strftime("[%H:%M:%S] ") + "playback stopped \n")
            self.textWindow.verticalScrollBar().setValue(self.textWindow.verticalScrollBar().maximum()-2)
            self.pauseAction.setDisabled(True)  

    # Update
    def updateListening(self): 
        if (not self.liveFromSerialAction.isChecked()):
            self.serialMonitor.updatePorts()
                   
            ports = [self.COMports.itemText(i) for i in range(self.COMports.count())]
            
            for i in range(self.COMports.count()):
                if self.COMports.itemText(i) not in self.serialMonitor.ports:
                    self.COMports.removeItem(i)
                    
            for i in range(len(self.serialMonitor.ports)):
                if self.serialMonitor.ports[i] not in ports:
                    self.COMports.addItem(self.serialMonitor.ports[i])
            
            if self.serialMonitor.COM != self.COMports.currentText():
                self.serialMonitor.COM = self.COMports.currentText()
                self.serialMonitor.connect = False
        
        if self.passLowFreq.value() > self.passHighFreq.value(): self.passLowFreq.setValue(self.passHighFreq.value())
        self.passLowFrec = self.passLowFreq.value()
        self.passHighFrec = self.passHighFreq.value()
        
        if self.bandpassAction.isChecked():
            self.passLowFreq.setDisabled(False)
            self.passHighFreq.setDisabled(False)
        else:
            self.passLowFreq.setDisabled(True)
            self.passHighFreq.setDisabled(True)
        
        if self.bandstopAction.isChecked(): 
            self.notchActiontypeBox.setDisabled(False)
        else:
            self.notchActiontypeBox.setDisabled(True)
            
        if self.EnvelopeSignalAction.isChecked():
            self.envelopeSmoothingСoefficient.setDisabled(False)
            self.MovingAverage.MA_alpha = self.envelopeSmoothingСoefficient.value()
        else:
            self.envelopeSmoothingСoefficient.setDisabled(True)
            
        if self.IntegralSignalAction.isChecked():
            self.integrationInterval.setDisabled(False)
        else:
            self.integrationInterval.setDisabled(True)
        
        # Read data from File               
        if (self.PlaybackAction.isChecked() and self.loadFileName != ''):
            self.readFromFile()
        
        # Read data from serial          
        if (self.liveFromSerialAction.isChecked()):
            self.readFromSerial()

        while self.sensorSelectedActionBox.count() < int(self.sensorsNumber.value()): 
            self.sensorSelectedActionBox.addItem(str(self.sensorSelectedActionBox.count() + 1))
            
        while self.sensorSelectedActionBox.count() > int(self.sensorsNumber.value()): 
            self.sensorSelectedActionBox.removeItem(self.sensorSelectedActionBox.count()-1)
        
        # Filtering
        if (self.PlaybackAction.isChecked() and self.loadFileName != '') or (self.liveFromSerialAction.isChecked()):
            Data = np.zeros((4, self.dataWidth))
            Time = np.zeros((4, self.dataWidth))
            for i in range(4):
                Data[i] = np.concatenate((self.Data[i][self.l[i]: self.dataWidth], self.Data[i][0: self.l[i]]))
                Time[i] = np.concatenate((self.Time[i][self.l[i]: self.dataWidth], self.Time[i][0: self.l[i]]))
            
                if self.bandstopAction.isChecked():
                    if (self.notchActiontypeBox.currentText() == "50 Hz"): 
                        for j in range(4): Data[i] = self.butter_bandstop_filter(Data[i], 48 + j*50, 52 + j*50, self.fs)
                    if (self.notchActiontypeBox.currentText() == "60 Hz"):
                        for j in range(3): Data[i] = self.butter_bandstop_filter(Data[i], 58 + j*60, 62 + j*60, self.fs)
                    for j in range(int(1.5*self.fs)): Data[i][j] = 0
                                
                if (self.bandpassAction.isChecked()) :
                    Data[i] = self.butter_bandpass_filter(Data[i], self.passLowFrec, self.passHighFrec, self.fs)
                    for j in range(int(1.5*self.fs)): Data[i][j] = 0
            
                # Shift the boundaries of the graph                
                self.pw[i].setXRange(self.xRangeStart + self.timeWidth*((self.Time[i][self.l[i] - 1] - self.xRangeStart)// self.timeWidth), 
                                     self.xRangeStart + self.timeWidth*((self.Time[i][self.l[i] - 1] - self.xRangeStart) // self.timeWidth + 1))
                
                # Plot raw and envelope data
                if  self.rawSignalAction.isChecked(): self.p[i].setData(y=Data[i], x=Time[i])
                else: self.p[i].clear()
                    
                # Plot envelope data
                self.DataEnvelope[i][0: self.dataWidth - self.ms_len[i]] = self.DataEnvelope[i][self.ms_len[i]:self.dataWidth]
                for j in range (self.dataWidth - self.ms_len[i], self.dataWidth):
                    self.DataEnvelope[i][j] = self.MovingAverage.movingAverage(i, Data[i][j])
                
                if  self.EnvelopeSignalAction.isChecked(): self.pe[i].setData(y=self.DataEnvelope[i], x=Time[i])
                else: self.pe[i].clear()
                
                # Plot integral data
                self.DataIntegral[i][0: self.dataWidth - self.ms_len[i]] = self.DataIntegral[i][self.ms_len[i]:self.dataWidth]
                for j in range (self.dataWidth - self.ms_len[i], self.dataWidth):
                    self.DataIntegral[i][j] = ((integrate.simpson(abs(Data[i][j-int(self.integrationInterval.value()*1000/2):j]), x=None, dx=self.dt[i])))
                    self.DataIntegral[i][j] = self.MovingAverage_Integral.movingAverage(i, self.DataIntegral[i][j])
                    
                    if (self.FlagBE[i] == 0) & (self.DataIntegral[i][j] >= self.TriggerValue[i].value()):
                        self.FlagBE[i] = 1
                        self.TimeStartBE[i] = Time[i][j]
                    
                    if (self.FlagBE[i] == 1) & ((Time[i][j] - self.TimeStartBE[i]) > self.StartTimeValue[i].value()):
                        self.FlagBE[i] = 2
                        self.NumberBE[i].setValue(self.NumberBE[i].value() + 1)
                        self.NumberBE_PerTime[i].setValue(self.NumberBE[i].value()/Time[i][j]*60*60)
                   
                    if (self.DataIntegral[i][j] < self.TriggerValue[i].value()):
                        if (self.FlagBE[i] == 1):
                            self.FlagBE[i] = 0  
                        if (self.FlagBE[i] == 2):
                            self.FlagBE[i] = 3
                            self.TimeStartBE[i] = Time[i][j]  
                    
                    if (self.FlagBE[i] == 3) & (self.DataIntegral[i][j] >= self.TriggerValue[i].value()): 
                        self.TimeStartBE[i] = Time[i][j]       
                    
                    if (self.FlagBE[i] == 3) & ((Time[i][j] - self.TimeStartBE[i]) > self.EndTimeValue[i].value()):
                        self.FlagBE[i] = 0  
                        
                
                if  self.IntegralSignalAction.isChecked(): self.pi[i].setData(y=self.DataIntegral[i], x=Time[i])
                else: self.pi[i].clear()
                    
                # Plot histogram
                self.pb[i].setOpts(height=2*self.DataEnvelope[i][-1])

            for i in range( int(self.sensorsNumber.value()), 4):
                self.p[i].clear()
                self.pe[i].clear()
                self.pi[i].clear()
                self.pb[i].setOpts(height=0)
            
            self.ms_len = [0]*4        
            
            # Plot FFT data
            Y = np.zeros((4, 500))
            i = int(self.sensorSelectedActionBox.currentIndex())
            Y[i] = abs(fft(Data[i][-501: -1]))/500
            self.FFT[i] = (1-0.5)*Y[i] + 0.5*self.FFT[i]
            X = self.fs*np.linspace(0, 1, 500)
            sensor = self.sensorSelectedActionBox.currentIndex()
            self.pFFT.setData(y=self.FFT[sensor][2: int(len(self.FFT[sensor])/2)], x=X[2: int(len(X)/2)])
        else:
            for i in range(int(self.sensorsNumber.value())):
                self.p[i].clear()
                self.pe[i].clear()
                self.pi[i].clear()
                self.pb[i].setOpts(height=0)
            self.pFFT.clear()

    # Read data from File   
    def readFromFile(self): 
        j = 0
        while j < 5:
            j += 1

            if ( self.sliderpos > self.loadDataLen - 2):
                self.refresh()
                self.sliderpos = 0
                self.slider.setValue(0) 
                self.xRangeStart = 0
                    
            msg = self.loadData[self.sliderpos*244:(self.sliderpos+1)*244]
            sensorNum = int(msg[0])-1
            
            MSG_NUM = int(msg[1] | msg[2] << 8 | msg[3] << 16)
            
            if self.MSG_NUM_0[sensorNum] == 0: 
                self.MSG_NUM_0[sensorNum] = MSG_NUM
                if self.TIMER == 0:
                    self.TIMER = time.perf_counter()
                    
            if MSG_NUM - self.MSG_NUM_0[sensorNum] >= 0:
                self.MSG_NUM[sensorNum] += MSG_NUM - self.MSG_NUM_0[sensorNum]
                self.Time[sensorNum][self.l[sensorNum]] += self.dt[sensorNum]*119*(MSG_NUM - self.MSG_NUM_0[sensorNum] - 1)
                self.MSG_NUM_0[sensorNum] = MSG_NUM
                MSG_NUM = self.MSG_NUM[sensorNum]
            else:
                self.MSG_NUM_0[sensorNum] = MSG_NUM
                MSG_NUM = max(self.MSG_NUM)
                self.MSG_NUM[sensorNum] = MSG_NUM 
                self.Time[sensorNum][self.l[sensorNum]-1] = np.amax(self.Time)                
                        
            for i in range(6, 244, 2):
                if (self.l[sensorNum] == self.dataWidth):
                    self.l[sensorNum] = 0
                self.Data[sensorNum][self.l[sensorNum]]  = ((int(msg[i] | msg[i+1] << 8) - 8192)/16384.0*2.49)*2000
                self.Time[sensorNum][self.l[sensorNum]] = self.Time[sensorNum][self.l[sensorNum] - 1] + self.dt[sensorNum]
                self.l[sensorNum] = self.l[sensorNum] + 1
                self.ms_len[sensorNum] += 1 
            
            if ((self.slider.value() != int(self.sliderpos/self.loadDataLen*100))):
                self.sliderpos += int(self.slider.value()*self.loadDataLen/100 - self.sliderpos)
                self.xRangeStart = self.sliderpos/self.fs*119
                temp = self.l
                self.refresh()
                self.l  = temp
                for i in range(0, 4, 1):
                    self.Time[i][self.l[i]-1] = self.sliderpos/self.fs*119
            
            self.sliderpos += 1
            self.slider.setValue(int(self.sliderpos/self.loadDataLen*100))
        

    # Read data from serial                  
    def readFromSerial(self): 
        
        msg = self.serialMonitor.serialRead() 
        TIME = time.perf_counter()
        
        # Parsing data from serial buffer
        if (len(msg) > 7):
            if (len(self.msg_end) > 1):
                msg =  self.msg_end + msg
                self.msg_end = bytearray([0])
            
            if (len(msg) % (246) != 0):
                if(len(msg)>250):
                    for i in range(len(msg) - 250, len(msg)-1, 1):
                       if (msg[i] == 0xFF) and (msg[i+1] == 0xFF):
                           self.msg_end = msg[i:]
                           msg = msg[0:i]
                           break
            
            if (len(msg) % 246 == 0):
                for msg_i in range(0, len(msg), 246):
                    sensorNum = int(msg[msg_i+2])-1
                    if (sensorNum > 3): break
                    MSG_NUM = int(msg[msg_i+3] | msg[msg_i+4] << 8 | msg[msg_i+5] << 16)
                    
                    if self.MSG_NUM_0[sensorNum] == 0: 
                        self.MSG_NUM_0[sensorNum] = MSG_NUM
                        if self.TIMER == 0:
                            self.TIMER = time.perf_counter()
                        self.Time[sensorNum][self.l[sensorNum]-1] = TIME - self.TIMER
                            
                    if MSG_NUM - self.MSG_NUM_0[sensorNum] > 0:
                        self.MSG_NUM[sensorNum] += MSG_NUM - self.MSG_NUM_0[sensorNum]
                        self.Time[sensorNum][self.l[sensorNum]] += self.dt[sensorNum]*119*(MSG_NUM - self.MSG_NUM_0[sensorNum] - 1)
                        self.MSG_NUM_0[sensorNum] = MSG_NUM
                        MSG_NUM = self.MSG_NUM[sensorNum]
                    else:
                        self.MSG_NUM_0[sensorNum] = MSG_NUM
                        MSG_NUM = max(self.MSG_NUM)
                        self.MSG_NUM[sensorNum] = MSG_NUM
                        self.Time[sensorNum][self.l[sensorNum]-1] = TIME - self.TIMER

                    self.VDD[sensorNum] = round(int(msg[msg_i+6] | msg[msg_i+7] << 8)/16384*0.6*6*2, 2)
                    string = "BATTERY: " + str(self.VDD[int(msg[msg_i+2])-1]) + " V"
                    while len(string) < 13:
                        string += "0"
                    self.ChargeLabel[int(msg[msg_i+2])-1].setText(string)
                   
                    if (self.VDD[int(msg[msg_i+2])-1]) > 2.5:
                        self.ChargeLabel[int(msg[msg_i+2])-1].setStyleSheet("color: green; background-color: transparent; font-weight: bold;")
                    else:
                        self.ChargeLabel[int(msg[msg_i+2])-1].setStyleSheet("color: red; background-color: transparent; font-weight: bold;")
                    
                    if TIME > self.TIMER:
                        for i in range(msg_i+8, msg_i + 246, 2):
                            if ( self.l[sensorNum] == self.dataWidth):
                                self.l[sensorNum] = 0 
                                
                            self.Data[sensorNum][self.l[sensorNum]]  = ((int(msg[i] | msg[i+1] << 8) - 8192)/16384.0*2.49)*2000
                            if ( self.l[sensorNum] > 0):
                                self.Time[sensorNum][self.l[sensorNum]] = self.Time[sensorNum][self.l[sensorNum] - 1] + self.dt[sensorNum] 
                            else:
                                self.Time[sensorNum][self.l[sensorNum]] = self.Time[sensorNum][self.dataWidth - 1] + self.dt[sensorNum]

                            self.l[sensorNum] += 1
                            self.ms_len[sensorNum] += 1 
                            
                        timeDifference = (TIME - self.TIMER) - self.Time[sensorNum][self.l[sensorNum]-1]
                        if timeDifference > 0.2:
                            self.Time[sensorNum][:] += 0.005
                            self.dt[sensorNum]*=1.001
                            if timeDifference > 0.3:
                                self.Time[sensorNum][:] += 0.2
                        if timeDifference < -0.2:
                            self.dt[sensorNum]*=0.999
                            self.Time[sensorNum][:] -= 0.005
                            if timeDifference < -0.3:
                                self.Time[sensorNum][:] -= 0.2
                
                        
                    if (self.dataRecordingAction.isChecked()):
                        self.recordingFile_BIN.write(msg[msg_i+2:msg_i+246])
                        
                        sensors_data = str(sensorNum)+' '+str(MSG_NUM)+" " + str(self.VDD[int(msg[msg_i+2])-1])+' '
                        for i in range(msg_i+8, msg_i+246, 2):
                            sensors_data = sensors_data + str(int(msg[i] | msg[i+1] << 8))+' '
                        sensors_data = sensors_data + '\n'
                        self.recordingFile_TXT.write(sensors_data)
    
    # Butterworth bandpass filter
    def butter_bandpass_filter(self, data, lowcut, highcut, fs, order=4):
        nyq = 0.5*fs
        low = lowcut/nyq
        high = highcut/nyq
        b, a = butter(order, [low, high], btype='bandpass')
        y = lfilter(b, a, data)
        return y
    
    # Butterworth bandstop filter
    def butter_bandstop_filter(self, data, lowcut, highcut, fs, order=4):
        nyq = 0.5*fs
        low = lowcut/nyq
        high = highcut/nyq
        b, a = butter(order, [low, high], btype='bandstop')
        y = lfilter(b, a, data)
        return y

    def setSensorsNumber(self, num):
        if self.liveFromSerialAction.isChecked():
            self.refresh()
        
        for i in range(4):
            self.row[i].hide()
            self.pw[i].getAxis('bottom').setStyle(showValues=False)
            self.pw[i].showLabel('bottom', 0)
            self.pw[i].getAxis('bottom').setStyle(showValues=True)
        
        self.pbar.clear()
        for i in range(int(num)):  
            self.pbar.addItem(self.pb[i])  
            self.row[i].show()
   
    # Exit event
    def closeEvent(self, event):
        self.mainrun.running = False
        self.serialMonitor.serialDisconnection()
        event.accept()

# Serial monitor class
class SerialMonitor:
    # Custom constructor
    def __init__(self, delay):
        self.running = False
        self.connect = False
        self.baudRate = 1000000
        self.playFile = 0
        self.delay = delay      
        self.ports = [p[0] for p in serial.tools.list_ports.comports(include_links=False) ]
        self.COM = ''
        self.ser = serial.Serial()
        if len(self.ports) > 0:
            self.COM = self.ports[0]
        
    def updatePorts(self):
        self.ports = [p[0] for p in serial.tools.list_ports.comports(include_links=False) ]
    
    def serialConnect(self):
        self.updatePorts()
        if not self.connect:
            if self.COM != '':
                try:
                    self.ser = serial.Serial(self.COM, self.baudRate)
                    self.connect = True  
                except SerialException :
                    self.connect = False
                    
    def serialDisconnection(self):
        self.ser.close()
        self.connect = False
        
    def serialRead(self):  
        msg = bytes(0)
        try:
            msg = self.ser.read( self.ser.inWaiting() )
        except SerialException :
            try:
               self.ser.close()
               self.ser.open()
               msg = bytes(0)
            except SerialException :
                pass
            pass
        return msg

# Moving average class
class MovingAverage:
    # Custom constructor
    def __init__(self, fs):
        self.MA = np.zeros((4, 3)) 
        self.MA_alpha = 0.95
        self.Y0 = np.zeros(4)
        self.X0 = np.zeros(4)
        self.fs = fs
    
    def movingAverage(self, i, data):
        wa = 2.0*self.fs*np.tan(3.1416*1/self.fs)
        HPF = (2*self.fs*(data-self.X0[i]) - (wa-2*self.fs)*self.Y0[i])/(2*self.fs+wa)
        self.Y0[i] = HPF
        self.X0[i] = data
        data = HPF
        if data < 0:
            data = -data
        self.MA[i][0] = (1 - self.MA_alpha)*data + self.MA_alpha*self.MA[i][0];
        self.MA[i][1] = (1 - self.MA_alpha)*(self.MA[i][0]) + self.MA_alpha*self.MA[i][1];
        self.MA[i][2] = (1 - self.MA_alpha)*(self.MA[i][1]) + self.MA_alpha*self.MA[i][2];
        return self.MA[i][2]*2

# Moving average class for Integral
class MovingAverage_Integral:
    # Custom constructor
    def __init__(self, fs):
        self.MA = np.zeros((4, 3)) 
        self.MA_alpha = 0.98
        self.Y0 = np.zeros(4)
        self.X0 = np.zeros(4)
        self.fs = fs
    
    def movingAverage(self, i, data):
        if data < 0:
            data = -data
        self.MA[i][0] = (1 - self.MA_alpha)*data + self.MA_alpha*self.MA[i][0];
        self.MA[i][1] = (1 - self.MA_alpha)*(self.MA[i][0]) + self.MA_alpha*self.MA[i][1];
        self.MA[i][2] = (1 - self.MA_alpha)*(self.MA[i][1]) + self.MA_alpha*self.MA[i][2];
        return self.MA[i][2]*2

# Serial monitor class
class MainRun(QtCore.QThread):
    bufferUpdated = QtCore.pyqtSignal()
    # Custom constructor
    def __init__(self, delay):
        QtCore.QThread.__init__(self)
        self.running = False
        self.playFile = 0
        self.delay = delay      

    # Listening port
    def run(self):
        while self.running is True:
            self.bufferUpdated.emit()
            time.sleep(self.delay) 
         
# Starting program       
if __name__ == '__main__':
    app = QtCore.QCoreApplication.instance()
    if app is None:
        app = QtWidgets.QApplication(sys.argv)
    window = GUI()
    window.show()
    window.start()
    sys.exit(app.exec_())
