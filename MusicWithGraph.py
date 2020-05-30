from maya import cmds, mel
import wave, struct
import os.path, math, array, time
from cmath import exp,pi

class WavReader:
    """
    This class is the responsible of managing the way the wav files open and their information
    """
    def __init__(self, filePath):
        
        # Save the path to the file
        self.fileName = filePath
        
        # Open the wav file in read mode
        self.waveFile = wave.open(filePath, "r")
        
        # Get the file's information
        self.frameRate = self.waveFile.getframerate()               # The samples per second
        self.nFrames = self.waveFile.getnframes()                   # The total amount of samples
        self.volume = 2**(8*self.waveFile.getsampwidth()-1) - 1     # The max volume is equal to the max value that the sample can have
        self.volume /= 1.0                                          # Conver to float

        self.sizes = {1: 'B', 2: 'h', 3: 'i', 4: 'i'}               # Different formatting depending on the amount of bytes
        
        self.channels = self.waveFile.getnchannels()                # The number of channels (mono / stereo)
        
        self.fmt_size = self.sizes[self.waveFile.getsampwidth()]    # The actual format size of the file using the bytes
        self.fmt = "<" + self.fmt_size * self.channels              # Build the format to use with struct unpack
        
    def sampleFrequency(self, rate, actualTime, bands=7):
        """
        This function samples the frequency of the file at a specific time
        """
        # Calculate the positions where we want to sample
        samples = 1.0 * self.frameRate / rate                       # The amount of samples per frame
        startSample = samples * actualTime                          
        endSample = startSample + samples

        # Exit the function the endsample is greater than the last sample of the file
        if endSample > self.nFrames:
            return []
        
        # Get the range of samples
        soundWave = self.sampleRange(int(startSample), int(endSample))

        # Get only the first channel
        soundWave = [v[0] for v in soundWave]
        
        #  The amount of samples that we got
        values_count = len(soundWave)
        # Calculate the power of two that fits the amount of samples
        log = math.log(values_count, 2)
        # Get that power of two
        finalSamples = 2 ** int(math.floor(log))
        
        # Calculate the fourier transform of only the first -power of two- samples
        spectrum = self.fft(soundWave[:finalSamples])
        # Get only the real part of complex numbers
        realSpectrum = [abs(v.real) for v in spectrum]
        # Calculate linear spacing between the frequencies gotten
        bandSample = 1.0 * finalSamples / (bands + 1)

        # Get the values separated by the band spacing
        sampledSpectrum = [realSpectrum[frame] for frame in xrange(0, len(realSpectrum), int(bandSample))]

        # If the final result has less values than the bands desired, we return the last item on the spectrum
        if len(sampledSpectrum) - 2 < bands:
            sampledSpectrum.append(realSpectrum[-1])

        # Return the middle values as first and last are (by experimenting) really high
        return sampledSpectrum[1:-1]

    def sampleRange(self, startFrame, endFrame):
        """
        Returns the samples in the file between a certain range
        """
        # Set the position of the "marker" in the file
        self.waveFile.setpos(startFrame)

        # Calculate the amount of samples that we want
        samples = endFrame - startFrame

        soundArray = []
        
        # If the file's ampWidth is 3, means it is 24 bits
        if  self.waveFile.getsampwidth() == 3:
            s = ''
            for k in xrange(samples):
                # Read a frame
                fr = self.waveFile.readframes(1)
                for c in xrange(0,3*self.channels,3):                
                    s += '\0'+fr[c:(c+3)] # put TRAILING 0 to make 32-bit (file is little-endian)
            
            # Unpack the resulting string
            unpstr = '<{0}{1}'.format(samples*self.channels, 'i')
            x = struct.unpack(unpstr, s)
            
            # Move the value to get positives and negatives
            x = [k >> 8 for k in x]
            
            # Convert the result to a tuple to fit the formating of the other lists
            result = tuple([value/self.volume for value in x])
            
            # Make an array to finish the formatting
            soundArray = [result[i:i + self.channels] for i in xrange(0, len(result), self.channels)]
            
            return soundArray
        
        # If the file is not 24 bits
        for f in xrange(samples):
            # Read a frame and unpack
            frameValue = struct.unpack(self.fmt, self.waveFile.readframes(1))
            
            # Convert to tuple
            result = tuple([value/self.volume for value in frameValue])
            
            # Append to the result array
            soundArray.append(result)
          
        return soundArray

    def sampleStepped(self, rate):
        """
        This function looks for samples in the sound that fit the spacing between frames
        """
        # Move the file's "marker" to the beginning
        self.waveFile.rewind()
        soundArray = []

        stepPerFrame = self.frameRate/rate
        totalFrames = int(self.nFrames/stepPerFrame) + 1

        if  self.waveFile.getsampwidth() == 3:
            s = ''
            for sample in xrange(0, self.nFrames, stepPerFrame):
                self.waveFile.setpos(sample)
                
                fr = self.waveFile.readframes(1)
                for c in xrange(0,3*self.channels,3):                
                    s += '\0'+fr[c:(c+3)] # put TRAILING 0 to make 32-bit (file is little-endian)
            
            unpstr = '<{0}{1}'.format(totalFrames*self.channels, 'i')
            x = struct.unpack(unpstr, s)
            
            x = [sample >> 8 for sample in x]
            
            result = tuple([value/self.volume for value in x])
            
            newArray = [result[i:i + self.channels] for i in xrange(0, len(result), self.channels)]

            soundArray = newArray
            
            return soundArray

        for sample in xrange(0, self.nFrames, stepPerFrame):

            self.waveFile.setpos(sample)

            frameValue = struct.unpack(self.fmt, self.waveFile.readframes(1))
            
            result = tuple([value/self.volume for value in frameValue])
            
            soundArray.append(result)
          
        return soundArray

    def fft(self, values):
        """
        Fast Fourier Transform algorithm
        """
        values_count = len(values)          # The amount of data that we will process
    
        # We can only use a power of two amount so we can divide the list
        if math.log(values_count, 2) % 1 > 0:
            raise ValueError('values count must be a power of 2, "{}" given.'.format(values_count))
    
        # E^x (this is the fourier's formula)
        t = exp(-2 * pi * 1j / values_count)
    
        # If there is more than one value on the list given
        if values_count > 1:

            # Recursively calculate the fourier transform
            # First calculate FFT of even numbers, then go to odd numbers
            # Append them together
            values = self.fft(values[::2]) + self.fft(values[1::2])
    
            # For every value in half of the values amount
            for k in range(values_count // 2):
                # Get the value
                k_value = values[k]

                # Apply the formula for Discrete Fourier Transform
                # Calculate the value for k
                values[k] = k_value + t ** k * values[k + values_count // 2]
                # Calculate the value for the index in the other half
                values[k + values_count // 2] = k_value - t ** k * values[k + values_count // 2]
        
        return values

class MainUI():
    """
    This class manages the UI creation and its functionality
    """
    
    def __init__(self):
        self.readersList = []                                           # List of the wav reader objects created     
        self.reader = None                                              # The current wav reader being used
        self.audioNode = ""                                             # The audio node in the Maya scene
        self.playBackSlider = mel.eval('$tmpVar=$gPlayBackSlider')      # Maya's playback slider (to add sound on it)
        self.valueMultiplier = 1                                        # The multiplier being applied to the wave values
        self.analyzerMethod = "WaveForm"                                # The method to analyze the wav file
        self.bandAmount = 4                                             # The amount of bands to divide the frequencies on spectrum mode
        self.selectedBand = 1                                           # The selected band to animate the object
        
        self.graph = ""                                                 # The UI component representing the graphs
        self.mainLayout = ""                                            # The layout that will keep the graphs
        self.spectrumLayout = ""                                        # UI elements to modify how to analyze with spectrum methos

        # Create the window
        self.MakeWin()

    def MakeWin(self):
        """
        Builds and shows the window
        """
        windowName = "mainUI"
        
        if cmds.window(windowName, query=True, exists=True):
            cmds.deleteUI(windowName)
        
        # Creating window
        self.window = cmds.window(windowName, title="Music Animator", width=510)
        
        
        # Creatin main layout that will contain everything
        cmds.columnLayout(columnOffset=("both", 5))
        
        allowedAreas = ['right', 'left']
        if cmds.dockControl("MusicAnimator", query=True, exists=True):
            cmds.deleteUI("MusicAnimator")
            
        cmds.dockControl("MusicAnimator", area='right', content=windowName, allowedArea=allowedAreas )

        # Space for the user to select the wav file
        cmds.separator(height=10, style="none")
        fileNameField = cmds.textFieldButtonGrp(label="Select wav file", buttonLabel="...", buttonCommand=lambda: self.OpenFile(fileNameField))
        
        # Button for Applying the audio (this creates an audio node)
        # and adds it to the timeline
        cmds.separator(height=5, style="none")
        cmds.rowLayout(numberOfColumns=2, adjustableColumn=1)
        cmds.separator(width=410, style="none")
        cmds.button(label="Apply audio", width = 80, command=lambda x: self.ApplyAudio(fileNameField, tracksMenu))
        cmds.setParent("..")
        
        # Track chooser (in case more than one audio is created)
        cmds.separator(height=10, style="none")
        tracksMenu = cmds.optionMenu(label="Select audio track: ", width=500, changeCommand=lambda x: self.ChangeTrack(tracksMenu, x))
        
        # Creating spaces for adding objects and attributes
        cmds.separator(height=10, style="none")
        cmds.rowColumnLayout(numberOfColumns=5, columnWidth=[(1,100),(2,150),(3,10),(4,100),(5,150)])
        cmds.button(label="Add Object(s)", command=lambda x: self.AddObj(OBJSelect))
        OBJSelect=cmds.textScrollList(allowMultiSelection=True, selectCommand= lambda: self.selectObjectsOnScene(OBJSelect))
        cmds.separator(width=10, style="none")
        cmds.button(label="Add Attributes", command=lambda x: self.AddAttr(OBJSelect, AttrSelect))
        AttrSelect=cmds.textScrollList(allowMultiSelection=True)
        cmds.setParent("..")

        # Button for resetting the scrollList
        cmds.separator(height=5, style="none")
        cmds.button(label="Reset Lists", width=100, command= lambda x: self.ResetScrollLists(OBJSelect, AttrSelect))
        cmds.separator(height=10, style="none")

        # Create option for audio methods
        cmds.separator(height=5, style="none")
        cmds.optionMenu(label="Select analyzing method: ", width=500, changeCommand=lambda x: self.ChangeAnalizer(x))
        cmds.menuItem(label="WaveForm", annotation="Use the entire shape of the wave for animation")
        cmds.menuItem(label="Spectrum", annotation="Use the state of the frequencies on each frame")

        # Create Spectrum options
        self.spectrumLayout = cmds.columnLayout()
        cmds.separator(height=5, style="none")
        cmds.intSliderGrp(label="Band Amount", value=3, minValue=4, maxValue=20, field=True,
                        annotation = "The amount of divisions in the frequencies",
                        statusBarMessage = "The amount of divisions in the frequencies", 
                        changeCommand=  lambda x: self.ChangeBandAmount(x, BandSelector))
        cmds.separator(height=5, style="none")
        BandSelector = cmds.intSliderGrp(label="Selected Band", value=3, minValue=1, maxValue=4, field=True, 
                        annotation="The specific division to use",
                        statusBarMessage="The specific division to use",
                        changeCommand=  lambda x: self.ChangeSelectedBand(x))
        cmds.layout(self.spectrumLayout, edit=True, enable=False)
        cmds.setParent("..")
        
        # Creating multiplier for values
        cmds.separator(height=5, style="none")
        cmds.intSliderGrp(label="Value Multiplier", min=1, max=100, value=1,field=True, changeCommand= self.setMultiplier)

        # Creating buttons for preview or animation
        cmds.separator(height=5, style="none")
        cmds.rowLayout(numberOfColumns=3, columnWidth=[(1,250),(2,10),(3,250)])
        cmds.button(label="Preview", width=250, command=lambda x: self.PreviewAnim(OBJSelect, AttrSelect))
        cmds.separator(width=10, style="none")
        cmds.button(label="Animate", width=250, command=lambda x: self.SetKeys(OBJSelect, AttrSelect))
        cmds.setParent("..")
        
        # Separation for experiments
        cmds.separator(height=5, style="none")
        self.mainLayout = cmds.frameLayout(label="Analizing functions", labelIndent=1, width=510, collapsable=True, collapse=True,marginHeight=5)
        cmds.text(label="Draw the shape of the wave:")
        cmds.button(label="Draw Waveform", command= self.drawGraph)

        cmds.separator(height=5, style="none")
        cmds.text(label="Draw the spectrum of the frequencies on the current frame.")
        cmds.text(label="Change the analyzing method above to modify the number of divisions.")
        cmds.button(label="Draw Spectrum", command= self.drawSpectrum)
        
        #cmds.showWindow(windowName)
        

    def selectObjectsOnScene(self, ObjScroll, *args):
        """
        This function selects the objects in the scene that the user pick on the scrollList
        """
        currentItems = cmds.textScrollList(ObjScroll, query=True, selectUniqueTagItem=True)

        cmds.select(currentItems, replace=True)

    def ResetScrollLists(self, ObjScroll, AttrScroll, *args):
        """
        Resets the lists of objects and attributes
        """
        cmds.textScrollList(ObjScroll, edit=True, removeAll=True)
        cmds.textScrollList(AttrScroll, edit=True, removeAll=True)

    def ChangeAnalizer(self, method):
        """
        Change how to analyze the wav file
        """

        self.analyzerMethod = method

        if method == "Spectrum":
            # Enable the spectrum layout
            cmds.layout(self.spectrumLayout, edit=True, enable=True)

        else:
            # Disable the spectrum layout
            cmds.layout(self.spectrumLayout, edit=True, enable=False)

    def ChangeBandAmount(self, amount, BandSelector, *args):
        """
        Updates the amount of bands to analyze with spectrum mode
        """

        self.bandAmount = amount

        # Get the current value of selected band
        currentValue = cmds.intSliderGrp(BandSelector, query=True, value=True)

        # If the selected band is greater than the total amount of bands, 
        # change that value to the new maximum
        if currentValue > amount:
            cmds.intSliderGrp(BandSelector, edit=True, value=amount)

        # Modify band selector to reflect the new MaxValue
        cmds.intSliderGrp(BandSelector, edit=True, maxValue=amount)

    def ChangeSelectedBand(self, band, *args):
        """
        Updates the selected band used to animate objects
        """
        self.selectedBand = band
        
    def OpenFile(self, theTextField, *args):
        """
        Opens a dialog to let the user select a wav file on their computer
        """
        
        waveFile = cmds.fileDialog2(caption="Select wav file", fileFilter="*.wav", fileMode=1)
        
        cmds.textFieldButtonGrp(theTextField, edit=True, text=waveFile[0])
        
    def ApplyAudio(self, fileNameField, tracksMenu, *args):
        """
        Applies the selected audio to the timeline and creates a wav reader
        """
        # Get path from text field
        audioPath = cmds.textFieldButtonGrp(fileNameField, query=True, text=True)
        
        # Create new reader
        newReader = WavReader(audioPath)
        
        # Get base name from the path and remove the 
        songName = os.path.basename(audioPath).split('.')[0]
        
        # Create audio node with the song name
        audioNode = cmds.createNode("audio", name=songName)

        # Add the song to the optionMenu
        cmds.setParent(tracksMenu, menu=True)
        cmds.menuItem(label=audioNode)
        numberOfItems = cmds.optionMenu(tracksMenu, query=True, numberOfItems=True)
        cmds.optionMenu(tracksMenu, edit=True, select=numberOfItems)
        
        # Append reader to the reader list and make it the selected reader
        self.readersList.append(newReader)
        self.reader = self.readersList[-1]
        
        # Put file name on audio node
        cmds.setAttr("{}.filename".format(audioNode), audioPath, type="string")
        
        # Put music on playBackSlider
        cmds.timeControl(self.playBackSlider, edit=True, sound=audioNode, displaySound=True)
        
    def ChangeTrack(self, tracksMenu, selectedTrack):
        """
        Changes from one audio node to another
        """
        # Set selected track as the audio in the playBackSlider
        cmds.timeControl(self.playBackSlider, edit=True, sound=selectedTrack, displaySound=True)
        
        # Get the index of this track
        numberOfItems = cmds.optionMenu(tracksMenu, query=True, select=True)

        # Set the wav reader
        self.reader = self.readersList[numberOfItems-1]
        
    def AddObj(self, scrollList, *args):
        """
        Adds an object to the textScrollList
        """
        # Get list of selected onbjects
        selectedObjects = cmds.ls(selection=True, objectsOnly=True)

        if not selectedObjects:
            cmds.warning("Please select an object in the scene")
            return
        
        # Get current items  on the scroll list
        currentItems = cmds.textScrollList(scrollList, query=True, allItems=True)
        
        itemsToAdd = selectedObjects
        
        # If there are items selected on the scroll, only add those that were not previously added
        if currentItems:
            itemsToAdd = [item for item in selectedObjects if not item in currentItems]
        
        cmds.textScrollList(scrollList, edit=True, append=itemsToAdd, uniqueTag=itemsToAdd)
        
    def AddAttr(self, ObjScroll, scrollList, *args):
        """
        Add attributes from the objects
        """
        selectedObjects = cmds.textScrollList(ObjScroll, query=True, selectUniqueTagItem=True)

        if not selectedObjects:
            cmds.warning("Please add select an object from the Object Scroll List")
            return
        
        # Restart the attr scrollList
        cmds.textScrollList(scrollList, edit=True, removeAll=True)
        
        # Get the attrs in the first object
        attrList = cmds.listAttr(selectedObjects[0], keyable=True, scalar=True)
        resultList = []

        # Avoid inserting the visibility attribute
        if "visibility" in attrList:
            attrList.remove("visibility")
        
        # Loop trrough the rest of objects
        for obj in selectedObjects:
            
            objectAttrs = cmds.listAttr(obj, keyable=True, scalar=True)

            # Add only those attributes that are in both list, this makes that only shared attributes are shown
            attrList = [attr for attr in objectAttrs if attr in attrList]
        
        # Append to scroll list
        cmds.textScrollList(scrollList, edit=True, append=attrList, uniqueTag=attrList)
        
    def PreviewAnim(self, ObjScroll, AttrScroll, *args):
        """
        This function shows the user how the animation will look
        """
        if not self.reader:
            cmds.warning("Please apply an audio first")
            return

        # Get lists of objects and attrs
        objList = cmds.textScrollList(ObjScroll, query=True, selectUniqueTagItem=True)
        attrList = cmds.textScrollList(AttrScroll, query=True, selectUniqueTagItem=True)

        if not objList:
            cmds.warning("Please select at least one object in the Object scroll list")
            return

        if not attrList:
            cmds.warning("Please select at least one attribute in the Attribute scroll list")
            return

        endFrame = int(cmds.playbackOptions(query=True, maxTime=True))      # The final frame on the timeslider
        frameRate = mel.eval('currentTimeUnitToFPS()')                      # The fps of the scene
        soundValues = []

        # Dictionary containing the original attribute names
        originalAttributes = {(objList*len(attrList))[x] + "." + attrList[x/len(objList)]:0 for x in xrange(len(objList)*len(attrList))}

        # Get their values
        for key in originalAttributes.keys():
            originalAttributes[key] = cmds.getAttr(key)

        # If user selects the waveform
        if self.analyzerMethod == "WaveForm":

            # Analyzes only by frames
            soundValues = self.reader.sampleStepped(int(frameRate))
        
            for frame in xrange(endFrame):
                
                # Break the loop if the music is finished
                if frame >= len(soundValues):
                    break

                for obj in objList:
                    for attr in attrList:
                        # Move the time one frame
                        cmds.currentTime(frame+1)
                        # Get orinal attr's value
                        originalValue = originalAttributes[obj+"."+attr]
                        # Set the new value
                        cmds.setAttr(obj+"."+attr,soundValues[frame][0] * self.valueMultiplier + originalValue)

                # Waits a little so the user can visualize the animation
                time.sleep(.5/frameRate)        

        # Using spectrum mode
        else:
            for frame in xrange(endFrame):
                
                # Sample the frequencies on this frame
                soundValues = self.reader.sampleFrequency(frameRate, frame, self.bandAmount)

                # Break the loop if the music is finished
                if not soundValues:
                    break

                for obj in objList:
                    for attr in attrList:
                        # Move the time one frame
                        cmds.currentTime(frame+1)
                        # Get orinal attr's value
                        originalValue = originalAttributes[obj+"."+attr]
                        # Set the new value
                        cmds.setAttr(obj+"."+attr, soundValues[self.selectedBand-1] * self.valueMultiplier + originalValue)
                
                # Waits a little so the user can visualize the animation
                time.sleep(.5/frameRate)

        # Return to start of the time
        cmds.currentTime(1)

        # Return values to their original
        for key in originalAttributes.keys():
            cmds.setAttr(key, originalAttributes[key])
                    
    def SetKeys(self, ObjScroll, AttrScroll, *args):
        """
        This function applies the animation from the music
        """
        if not self.reader:
            cmds.warning("Please apply an audio first")
            return

        objList = cmds.textScrollList(ObjScroll, query=True, selectUniqueTagItem=True)
        attrList = cmds.textScrollList(AttrScroll, query=True, selectUniqueTagItem=True)

        if not objList:
            cmds.warning("Please select at least one object in the Object scroll list")
            return

        if not attrList:
            cmds.warning("Please select at least one attribute in the Attribute scroll list")
            return

        endFrame = int(cmds.playbackOptions(query=True, maxTime=True))
        frameRate = mel.eval('currentTimeUnitToFPS()')
        
        secondsAmount = int(math.ceil(1.0*endFrame/frameRate))
        
        soundValues = []

        # Dictionary containing the original attribute names
        originalAttributes = {(objList*len(attrList))[x] + "." + attrList[x/len(objList)]:0 for x in xrange(len(objList)*len(attrList))}

        # Get their values
        for key in originalAttributes.keys():
            originalAttributes[key] = cmds.getAttr(key)

        if self.analyzerMethod == "WaveForm":
            soundValues = self.reader.sampleStepped(int(frameRate))
            
            for frame in xrange(endFrame):

                if frame >= len(soundValues):
                    break

                for obj in objList:
                    for attr in attrList:
                        cmds.currentTime(frame+1)
                        originalValue = originalAttributes[obj+"."+attr]
                        cmds.setAttr(obj+"."+attr, soundValues[frame][0] * self.valueMultiplier + originalValue)
                        cmds.setKeyframe(obj+"."+attr)
        else:
            for frame in xrange(endFrame):

                soundValues = self.reader.sampleFrequency(frameRate, frame, self.bandAmount)

                if not soundValues:
                    break

                for obj in objList:
                    for attr in attrList:
                        cmds.currentTime(frame+1)
                        originalValue = originalAttributes[obj+"."+attr]
                        cmds.setAttr(obj+"."+attr, soundValues[self.selectedBand-1] * self.valueMultiplier + originalValue)
                        cmds.setKeyframe(obj+"."+attr)
                    
    def setMultiplier(self, multiplier):
        """
        Sets the valueMultiplier
        """
        
        self.valueMultiplier = multiplier
            
    def drawSpectrum(self, *args):
        """
        This function draws the audio spectrum on the UI
        """
        if not self.reader:
            cmds.warning("Please apply an audio first")
            return

        frameRate = mel.eval('currentTimeUnitToFPS()')
        values = self.reader.sampleFrequency(frameRate, cmds.currentTime(query=True), self.bandAmount)

        if not values:
            cmds.warning("End of file reached")
            return

        # Normalize value from 0 to 1 using the max value
        norm = [float(i*self.valueMultiplier)/(max(values)*self.valueMultiplier) for i in values]

        #norm = [float(i)/sum(values) for i in values]  
        
        curvePoints = ["{},{},".format(1.0*x/self.bandAmount, norm[x-1]) for x in xrange(self.bandAmount+1)]
        
        curveString = ""
        curveString = curveString.join(curvePoints)
        curveString = curveString[:-1]

        cmds.setParent(self.mainLayout)
        cmds.deleteUI(self.graph)
        self.graph = cmds.frameLayout(height=200, width=500, labelVisible=False)

        cmds.falloffCurve(asString=curveString)

        
    def drawGraph(self, *args):
        """
        This function draws the soundWave on the UI
        """
        if not self.reader:
            cmds.warning("Please apply an audio first")
            return

        if cmds.objExists("AudioVisHelper"):
            cmds.delete("AudioVisHelper")

        visualizer = cmds.polySphere(name="AudioVisHelper")[0]

        cmds.setAttr(visualizer + ".visibility", 0)

        frameRate = mel.eval('currentTimeUnitToFPS()')
        values = self.reader.sampleStepped(int(frameRate))
        
        for f in xrange(len(values)):
            cmds.currentTime(f)
            cmds.setAttr("{}.translateY".format(visualizer), values[int(f)][0])
            cmds.setKeyframe("{}.translateY".format(visualizer))
        
        cmds.setParent(self.mainLayout)
        cmds.deleteUI(self.graph)
        self.graph = cmds.frameLayout(height=200, width=500, labelVisible=False)
        cmds.animCurveEditor(autoFit=True, displayKeys=False, displayNormalized=True)
        cmds.setParent("..")
        
    
theUI = MainUI()