#!/usr/bin/python 

import argparse
import colorsys
import errno
import json
import math
import networkx as nx
import operator
import os
import os.path
import re
import subprocess
import sys

graphFilePostfix = None;
graphType = None;
htmlTemplate = None;
multipleAcquireWithoutRelease = 0;
noMatchingAcquireOnRelease = 0;
outliersFile = None;
separator = " ";
tryLockWarning = 0;
verbose = False;
shortenFuncName = True;


class color:
   PURPLE = '\033[95m'
   CYAN = '\033[96m'
   DARKCYAN = '\033[36m'
   BLUE = '\033[94m'
   GREEN = '\033[92m'
   YELLOW = '\033[93m'
   RED = '\033[91m'
   BOLD = '\033[1m'
   UNDERLINE = '\033[4m'
   END = '\033[0m'

#
# LogRecord contains all the fields we expect in the log record.

class LogRecord:

    def __init__(self, func, op, thread, time, otherInfo):
        self.func = func;
        self.op = op;
        self.thread = thread;
        self.time = long(time);
        self.otherInfo = otherInfo;
        #
        # otherInfo typically includes argument values. We append
        # it to the function name.
        #
        if (otherInfo is not None):
            self.fullName = func + " " + otherInfo;
        else:
            self.fullName = func;

    def printLogRecord(self):
        print(self.op + " " + self.func + " " + str(self.thread) + " "
              + str(self.time));

    def writeToFile(self, file):
        if (self.op == "enter"):
            file.write("-->");
        elif (self.op == "exit"):
            file.write("<--");
        else:
            file.write(self.op);
        file.write(" " + self.func + " " + str(self.thread) +
                       " " + str(self.time));
        if (self.otherInfo is not None):
            file.write(" " + self.otherInfo);

#
# LockRecord contains temporary information for generating lock-held times

class LockRecord:

    def __init__(self, name, fname, thread, timeAcquired):
        self.name = name;
        self.funcName = fname;
        self.thread = thread;
        self.timeAcquired = long(timeAcquired);

    def printLockRecord(self):
        print(self.name + ": [" + str(self.thread) + "] " +
              str(self.timeAcquired) + "\n");


#
# TraceStats class holds attributes pertaining to the performance
# trace.

class TraceStats:

    def __init__(self, name):
        self.name = name;
        self.startTime = 0;
        self.endTime = 0;

    def setStartTime(self, startTime):
        self.startTime = startTime;

    def setEndTime(self, endTime):
        self.endTime = endTime;

    def getTotalTime(self):
        if (self.startTime == 0 or self.endTime == 0):
            print("Warning: start or end time not set for trace " +
                   self.name);
        return self.endTime - self.startTime;
#
# PerfData class contains informtation about the function running
# times.

class PerfData:

    def __init__(self, name, funcName, otherInfo, threadID):
        self.name = name;
        self.originalName = funcName;
        if shortenFuncName and (self.originalName in shortnameMappings):
            self.originalName = shortnameMappings[self.originalName]
        # If this is a lock function, then otherInfo
        # would contain the information for identifying
        # this lock.
        #
        self.lockName = otherInfo;
        self.threadID = threadID;
        self.numCalls = 0;
        self.totalRunningTime = long(0);
        self.runningTimes = [];
        self.maxRunningTime = 0;
        self.maxRunningTimeTimestamp = 0;
        self.filtered = False;
        self.cumSumSquares = 0.0;

    def update(self, runningTime, beginTime):
        global outliersFile;

        self.totalRunningTime = self.totalRunningTime + runningTime;
        self.numCalls = self.numCalls + 1;
        #self.runningTimes.append(runningTime);
        if (runningTime > self.maxRunningTime):
            self.maxRunningTime = runningTime;
            self.maxRunningTimeTimeStamp = beginTime;

        # Update cumulative variance, so we can signal outliers
        # on the fly.
        #
        cumMean = float(self.totalRunningTime) / float(self.numCalls);
        self.cumSumSquares = self.cumSumSquares + \
          math.pow(float(runningTime) - cumMean, 2);
        cumStDev = math.sqrt(self.cumSumSquares / float(self.numCalls));

        if (runningTime > cumMean + 2 * cumStDev):
            if (outliersFile is not None):
                outliersFile.write("T" + str(self.threadID) + ": " + self.name
                                       + " took "
                                       + str(runningTime) +
                                       " ns at time " + str(beginTime) + "\n");


    def getAverage(self):
        return (float(self.totalRunningTime) / float(self.numCalls));

    def printSelf(self, file):
        if(file is None):
            file = sys.stdout;

        file.write("*** " + self.name + "\t" +
                   str(self.numCalls) + "\t" + str(self.totalRunningTime) + "\t"
                   + str(self.getAverage()) + "\n");
        file.write("\t Total running time: " +
                   '{:,}'.format(self.totalRunningTime) +
                   " ns.\n");
        file.write("\t Average running time: "
              + '{:,}'.format(long(self.getAverage())) + " ns.\n");
        file.write("\t Largest running time: " +
                   '{:,}'.format(self.maxRunningTime) +
	           " ns.\n");

    def printSelfCSVLine(self, file):
        if(file is None):
            file = sys.stdout

        file.write("{}, {}, {}, {}, {}\n"
                   .format(self.name, self.numCalls, self.totalRunningTime,
                           self.getAverage(), self.maxRunningTime))

    def printSelfHTML(self, prefix, locksSummaryRecords):
        with open(prefix + "/" + self.name + ".txt", 'w+') as file:
            file.write("*** " + self.name + "\n");
            file.write("\t Origin full name: " + self.originalName + "\n");
            file.write("\t Total running time: " +
                       '{:,}'.format(self.totalRunningTime) +
                       " ns.\n");
            file.write("\t Average running time: "
                       + '{:,}'.format(long(self.getAverage())) + " ns.\n");
            file.write("\t Largest running time: " +
                       '{:,}'.format(self.maxRunningTime) +
	               " ns.\n");
            file.write("------------------\n");
            if (self.lockName is not None):
                if (locksSummaryRecords.has_key(self.lockName)):
                    lockData = locksSummaryRecords[self.lockName];
                    lockData.printSelfHTML(file);


#
# LockData class contains information about lock-related functions

class LockData:

    def __init__(self, name):
        self.name = name;
        self.numAcquire = 0;
        self.numRelease = 0;
        self.numTryLock = 0;
        self.timeAcquire = 0;
        self.timeTryLock = 0;
        self.timeRelease = 0;
        self.timeHeld = 0;
        self.lastAcquireRecord = None;
        self.lockHeldTimes = [];

    def getAverageAcquire(self):
        if(self.numAcquire > 0):
            return (float(self.timeAcquire) / float(self.numAcquire));
        else:
            return 0;

    def getAverageRelease(self):
        if(self.numRelease > 0):
            return (float(self.timeRelease) / float(self.numRelease));
        else:
            return 0;

    def getAverageTryLock(self):
        if(self.numTryLock > 0):
            return (float(self.timeTryLock) / float(self.numTryLock));
        else:
            return 0;

    def getAverageTimeHeld(self):
        if(self.numRelease > 0):
            return (float(self.timeHeld) / float(self.numRelease));
        else:
            return 0;

    def printSelf(self, file):
        if (file is None):
            file = sys.stdout;

        file.write("Lock \"" + self.name + "\":\n");
        file.write("\t Num acquire: " + str(self.numAcquire) + "\n");
        file.write("\t Num trylock: " + str(self.numTryLock) + "\n");
        file.write("\t Num release: " + str(self.numRelease) + "\n");
        file.write("\t Average time in acquire: "
              + str(long(self.getAverageAcquire())) + " ns.\n");
        file.write("\t Average time in trylock: "
              + str(long(self.getAverageTryLock())) + " ns.\n");
        file.write("\t Average time in release: "
              + str(long(self.getAverageRelease())) + " ns.\n");
        file.write("\t Average time the lock was held: "
              + str(long(self.getAverageTimeHeld())) + " ns.\n");

    def printSelfHTML(self, file):

        file.write("Lock \"" + self.name + "\":\n");
        file.write("\t Num acquire: " + str(self.numAcquire) + "\n");
        file.write("\t Num trylock: " + str(self.numTryLock) + "\n");
        file.write("\t Num release: " + str(self.numRelease) + "\n");
        file.write("\t Average time in acquire: "
              + str(long(self.getAverageAcquire())) + " ns.\n");
        file.write("\t Average time in trylock: "
              + str(long(self.getAverageTryLock())) + " ns.\n");
        file.write("\t Average time in release: "
              + str(long(self.getAverageRelease())) + " ns.\n");
        file.write("\t Average time the lock was held: "
              + str(long(self.getAverageTimeHeld())) + " ns.\n");


#
# The following data structures and functions help us decide what
# kind of lock-related action the function is doing:
# acquiring the lock, releasing the lock, of trying to acquire the lock.
#

acquireStrings = ["acquire", "lock"];
trylockStrings = ["trylock"];
releaseStrings = ["release", "unlock"];

def looks_like_acquire(funcname):

    if(looks_like_release(funcname)):
        return False;
    if(looks_like_trylock(funcname)):
        return False;

    for hint in acquireStrings:
        if(funcname.find(hint) != -1):
            return True;
    return False;

def looks_like_trylock(funcname):

    for hint in trylockStrings:
        if(funcname.find(hint) != -1):
            return True;
    return False;


def looks_like_release(funcname):

    for hint in releaseStrings:
        if(funcname.find(hint) != -1):
            return True;
    return False;

def looks_like_lock(funcname):

    if(looks_like_acquire(funcname) or
       looks_like_release(funcname) or
       looks_like_trylock(funcname)):
        return True;
    else:
        return False;

def do_lock_processing(locksDictionary, logRec, runningTime,
                       lockName):
    global multipleAcquireWithoutRelease;
    global noMatchingAcquireOnRelease;
    global tryLockWarning;
    global verbose;

    func = logRec.func

    if(not locksDictionary.has_key(lockName)):
        lockData = LockData(lockName);
        locksDictionary[lockName] = lockData;

    lockData = locksDictionary[lockName];
    lastAcquireRecord = lockData.lastAcquireRecord;

    # If this is an acquire or trylock, simply update the stats in the
    # lockData object and remember the lastAcquire record, so we can
    # later match it with a corresponding lock release.
    #
    # If this is a release, update the stats in the lockData object and
    # get the corresponding acquire or trylock so we can compute the lock
    # held time.
    #
    if(looks_like_acquire(func) or looks_like_trylock(func)):

        lockRec = LockRecord(lockName, func, logRec.thread, logRec.time);

        if(looks_like_acquire(func)):
            if(lastAcquireRecord is not None):
                if(verbose):
                    print("Another acquire record seen on acquire. "
                          " for lock " + lockName);
                    print("Current lock record:");
                    lockRec.printLockRecord();
                    print("Existing acquire record:");
                    lastAcquireRecord.printLockRecord();
                multipleAcquireWithoutRelease = multipleAcquireWithoutRelease \
                                                + 1;
            else:
                lockData.lastAcquireRecord = lockRec;

            lockData.numAcquire = lockData.numAcquire + 1;
            lockData.timeAcquire = lockData.timeAcquire + runningTime;
        elif(looks_like_trylock(func)):
            if(lastAcquireRecord is not None):
                if(lastAcquireRecord.funcName != func):
                    if(verbose):
                        print("Warning: A trylock record seen, but not in the "
                              "same function as ours!");
                        print("Current lock record:");
                        lockRec.printLockRecord();
                        print("Existing acquire record:");
                        lastAcquireRecord.printLockRecord();
                    tryLockWarning = tryLockWarning + 1;
                else:
                    # If there is already an acquire record with the same func
                    # name as ours, this means that the lock was not acquired in
                    # the last try attempt. We update the timestamp, so that
                    # lock held time is subsequently calculated correctly.
                    lastAcquireRecord.timeAcquired = logRec.time;
            else:
                lockData.lastAcquireRecord = lockRec;

            lockData.numTryLock = lockData.numTryLock + 1;
            lockData.timeTryLock = lockData.timeTryLock + runningTime;
        else:
            print("PANIC!")
            sys.exit(-1);

    elif(looks_like_release(func)):

        if(lastAcquireRecord is None):
            if(verbose):
                print("Could not find a matching acquire for: ")
                logRec.printLogRecord();
                print("Lock name: " + lockName);
            noMatchingAcquireOnRelease = noMatchingAcquireOnRelease + 1;
        else:
            lockHeldTime = logRec.time - lastAcquireRecord.timeAcquired;
            lockData.timeHeld = lockData.timeHeld + lockHeldTime;
            lockData.lockHeldTimes.append(long(lockHeldTime));

            # Reset the lockAcquire record to null
            lockData.lastAcquireRecord = None;

        lockData.numRelease = lockData.numRelease + 1;
        lockData.timeRelease = lockData.timeRelease + runningTime;

    else:
        print("PANIC! Unrecognized lock function: " + func);
        sys.exit(-1);


class HSL:
    def __init__(self, h, s, l):
        self.h = h;
        self.s = s;
        self.l = l;

    #
    # Code borrowed from http://www.rapidtables.com/convert/color/hsl-to-rgb.htm
    #
    def toRGB(self):
        h = float(self.h);
        s = self.s;
        l = self.l;

        if(h < 0 or h > 360):
            return -1, -1, -1;
        if(s < 0 or s > 1):
            return -1, -1, -1;
        if(l < 0 or l > 1):
            return -1, -1, -1;

        C = (1 - abs(2*l - 1)) * s;
        X = C * (1 - abs(h / 60 % 2 -1));
        m = l - C/2;

        if(h >= 0 and h < 60):
            r = C;
            g = X;
            b = 0;
        elif(h >= 60 and h < 120):
            r = X;
            g = C;
            b = 0;
        elif(h >= 120 and h < 180):
            r = 0;
            g = C;
            b = 0;
        elif(h >= 180 and h < 240):
            r = 0;
            g = X;
            b = C;
        elif(h >= 240 and h < 300):
            r = X;
            g = 0;
            b = C;
        elif(h >= 300 and h <= 360):
            r = C;
            g = 0;
            b = X;

        r = int(round((r + m) * 255));
        g = int(round((g + m) * 255));
        b = int(round((b + m) * 255));

        return r, g, b;

    def toHex(self):
        r, g, b = self.toRGB();

        hexString = "#" + "%0.2X" % int(r) + "%0.2X" % int(g) + "%0.2X" % int(b)
        return hexString;

def isInt(s):
    try:
        int(s);
        return True;
    except ValueError:
        return False;

def buildColorList():

    # To generate colours from red to pale green, use:
    # baseHue = 360;
    # lightness = 0.56
    # lightInc = 0.02
    #
    # In the loop: baseHue - i * 20.
    #
    colorRange = [];
    baseHue = 200;
    saturation = 0.70;
    lightness = 0.4;
    lightInc = 0.04;

    for i in range(0, 14):
        hslColor = HSL(baseHue, saturation, lightness + lightInc * i,);
        hexColor = hslColor.toHex();
        colorRange.append(hexColor);

    return colorRange;

def extractFuncName(nodeName):

    words = nodeName.split(" ");

    if (words[0] == "enter" or words[0] == "exit"):
        return " ".join(words[1:len(words)]);
    else:
        return nodeName;
#
# Figure out the percent execution time for each function relative to the total.
# Compute the colour based on the percent. Set the node colour accordingly.
# Update the node label with the percent value.
#
def augment_graph(graph, funcSummaryData, traceStats, prefix, htmlDir):

    # This dictionary is the mapping between function names and
    # their percent of execution time.
    #
    percentDict = {};

    # This is the dictionary of function names with colour codes
    # based on their contribution to the total runtime.
    #
    funcWithColorCode = {};

    # Generate a progression of colours from bright red to pale green
    #
    rgbArray = buildColorList();

    # Generate a dictionary keyed by function name, where the value is
    # the percent runtime contributed to total by this function.
    #
    traceRuntime = traceStats.getTotalTime();
    for func, pdr in funcSummaryData.iteritems():
        if(pdr.filtered):
            continue;
        percent = float(pdr.totalRunningTime) / float(traceRuntime) * 100;
        percentDict[func] = percent;

    # Sort the dictionary by percent. We get back a list of tuples.
    #
    sortedByPercentRuntime = sorted(percentDict.items(),
                                    key=operator.itemgetter(1));

    # Look up the colour for each function based on its contribution
    # to the total runtime. Greater contribution --> more intense color.
    #
    for funcPercentTuple in reversed(sortedByPercentRuntime):
        func = funcPercentTuple[0];
        percent = funcPercentTuple[1];
        percentStr = str(round(percent)) + "%";

        # Let's find the color for this percent value.
        #
        idx = int(round((100.0 - percent) / 7.5));
        funcWithColorCode[func] = [rgbArray[idx], percentStr];

    for func, attrs in funcWithColorCode.iteritems():

        if graphType == 'func_only':
            allNames = [func];
        else:
            enterNodeName = "enter " + func;
            exitNodeName  = "exit " + func;
            allNames = [enterNodeName, exitNodeName];

        for nodeName in allNames:
            graph.node[nodeName]['label'] = nodeName + "\n" + \
                                             attrs[1];
            graph.node[nodeName]['style'] = "filled, rounded";
            graph.node[nodeName]['color'] = attrs[0];
            graph.node[nodeName]['URL'] = "_" + prefix.upper() \
              + "/" + extractFuncName(nodeName) + ".txt";

def update_graph(graph, nodeName, prevNodeName):

    if (not graph.has_node(nodeName)):
            graph.add_node(nodeName, fontname="Helvetica");
            graph.node[nodeName]['shape'] = 'box';

    if (not graph.has_edge(prevNodeName, nodeName)):
        graph.add_edge(prevNodeName, nodeName, label = " 1 ",
                       fontname="Helvetica");
    else:
        graph[prevNodeName][nodeName]['label'] = \
            " " + str(int(graph[prevNodeName][nodeName]['label']) + 1) + " ";

    if(prevNodeName == "START"):
        graph[prevNodeName][nodeName]['label'] = "";
        if (graphType == 'func_only'):
            graph[prevNodeName][nodeName]['label'] = " 1 "

def generate_func_only_graph(graph, logRecords, prevNodeName):

    funcStack = [prevNodeName];
    lastFuncName = prevNodeName;

    for logRec in logRecords:
        if logRec.op == 'enter':
            update_graph(graph, logRec.func, lastFuncName)
            funcStack.append(logRec.func)
        elif logRec.op == 'exit':
            if funcStack[-1] == logRec.func:
                lastFuncName = funcStack.pop()

    return lastFuncName;

def generate_graph(logRecords):

    graph = nx.DiGraph();

    graph.add_node("START", fontname="Helvetica");
    graph.node["START"]['shape']='box'
    prevNodeName = "START";

    if graphType == 'func_only':
        prevNodeName = generate_func_only_graph(graph, logRecords, prevNodeName)
    else:
        for logRec in logRecords:
            nodeName = logRec.op + " " + logRec.fullName;
            update_graph(graph, nodeName, prevNodeName);
            prevNodeName = nodeName;

    graph.add_node("END", fontname="Helvetica");
    graph.add_edge(prevNodeName, "END");
    graph.node["END"]['shape']='diamond';

    return graph;

#
# When we compute the execution flow graph, we will not include any functions
# whose percent execution time is below that value.
#
percentThreshold = 0.0;

useMaxRuntimeFilter = False;
maxRuntimeThreshold = 3300000; # in clock cycles

def filterLogRecords(logRecords, funcSummaryRecords, traceStats):

    filteredRecords = [];
    traceRuntime = traceStats.getTotalTime();

    for rec in logRecords:

        # A log may have no corresponding function record if we stopped
        # logging before the function exit record was generated, as can
        # be with functions that start threads.
        #
        if not funcSummaryRecords.has_key(rec.fullName):
            print("Warning: no performance record for function " +
                  rec.func);
            continue;

        pdr = funcSummaryRecords[rec.fullName];
        percent = float(pdr.totalRunningTime) / float(traceRuntime) * 100;

        if (percent <= percentThreshold):
            pdr.filtered = True;
            continue;
        elif (useMaxRuntimeFilter and pdr.maxRunningTime < maxRuntimeThreshold):
            pdr.filtered = True;
            continue;
        else:
            filteredRecords.append(rec);

    return filteredRecords;

def transform_name(name, transformMode, CHAR_OPEN=None, CHAR_CLOSE=None):
    if transformMode == 'multiple lines':
        lineLength = 50
        lines = []
        i = 0
        while len(name) > lineLength:
            if i == 0:
                lines.append(name[0:lineLength])
            else:
                lines.append(name[0:lineLength])
            name = name[lineLength:]
            i += 1
        lines.append(name)
        return '\n'.join(lines)
    elif transformMode == 'replace with *':
        stack = []
        chars = []
        for c in name:
            if c == CHAR_OPEN:
                if len(stack) == 0:
                    chars.append(c)
                stack.append(c)
            elif c == CHAR_CLOSE:
                if len(stack) == 0: # miss the matched '<'
                    chars.append(c)
                else:
                    stack.pop()
                    if len(stack) == 0:
                        chars.append('*')
                        chars.append(CHAR_CLOSE)
            else:
                if len(stack) == 0:
                    chars.append(c)

        return ''.join(chars)
    else:
        return name


shortnameMapped = {}   # originalName     => shortname
shortnameMappings = {} # shortname      => originalName
shortnameVersion = {}  # shortnameBase  => version

# Different functions could have the same short name.
# The following method is to generate unique short names for
# different functions by appending _v* to the generated short name
#
def unique_shortname(originalName):

    if originalName in shortnameMapped:
        return shortnameMapped[originalName];

    shortnameBase = transform_name(originalName, 'replace with *', '<', '>');
    shortnameBase = transform_name(shortnameBase, 'replace with *', '(', ')');
    version = 0;

    if (shortnameBase in shortnameVersion):
        version = shortnameVersion[shortnameBase];
    shortnameVersion[shortnameBase] = version + 1;

    shortname = shortnameBase;
    if (version != 0):
        shortname = shortnameBase + "_v" + str(version)

    shortnameMapped[originalName] = shortname;
    shortnameMappings[shortname] = originalName;
    return shortname;

def dump_shortname_maps(filename):
    with open(filename, 'w') as fp:
        json.dump(shortnameMappings, fp)

def generatePerFuncHTMLFiles(prefix, htmlDir,
                                 funcSummaryRecords, locksSummaryRecords):

    dirname = htmlDir + "/" + "_" + prefix.upper();

    if not os.path.exists(dirname):
        try:
            os.mkdir("./" + dirname);
            print("Directory " + dirname + " created");
        except:
            print "Could not create directory " + dirname;
            return;

    for pdr in funcSummaryRecords.values():
        if (not pdr.filtered):
             pdr.printSelfHTML(dirname, locksSummaryRecords);

# In some cases we need to strip the HTML directory name from the
# beginning of the imageFileName, because the image source
# must be relative to the html file, which itself is in
# the HTML directory.
#
def stripHTMLDirFromFileName(fileName, htmlDir):

    if (fileName.startswith(htmlDir)):
        fileName = fileName[len(htmlDir):];

    while (fileName.startswith("/")):
        fileName = fileName[1:];

    return fileName;

def insertIntoTopHTML(imageFileName, htmlFileName, topHTMLFile):

    global htmlTemplate;

    # Extract thread ID from the file names. We assume that this
    # is the first number encountered in the file name.
    #
    numbers = re.findall(r'\d+', imageFileName);
    if (len(numbers) > 0):
        threadID = str(numbers[0]);
    else:
        threadID = "";

    # Read the file, find the placeholder patterns, replace them
    # with the actual values. Write the text into top HTML file.
    for line in htmlTemplate:
        if ("#Thread" in line):
            line = line.replace("#Thread", "Thread " + threadID);
        if ("#htmlFile" in line):
            line = line.replace("#htmlFile", htmlFileName);
        if ("#imageFile" in line):
            line = line.replace("#imageFile", imageFileName);
        topHTMLFile.write(line);

    # Rewind the template file for the next reader
    htmlTemplate.seek(0);


def generatePerFileHTML(htmlFileName, imageFileName, mapFileName, htmlDir,
                            topHTMLFile):
    i = 0;

    try:
        htmlFile = open(htmlFileName, "w");
    except:
        print("Could not open " + htmlFileName + " for writing");
        return;

    try:
        mapFile = open(mapFileName, "r");
    except:
        print("Could not open " + mapFileName + " for writing");
        return;

    relativeImageFileName = stripHTMLDirFromFileName(imageFileName, htmlDir);

    htmlFile.write("<html><img src=\"" + relativeImageFileName +
                       "\"  usemap=\"#G\">\n");
    htmlFile.write("<map id=\"G\" name=\"G\">\n");

    for line in mapFile:
        i = i + 1;
        if (i == 1):
            assert(line.startswith("<map id="));
            continue;

        htmlFile.write(line);

    htmlFile.write("</html>\n");

    htmlFile.close();
    mapFile.close();

    # Insert the image file linked to the HTML file into the top HTML file.
    insertIntoTopHTML(relativeImageFileName,
                          stripHTMLDirFromFileName(htmlFileName, htmlDir),
                                                       topHTMLFile);

def regenerateHTML(topHTMLFile, filenames):

    # This list will keep track of the trace files, whose images we
    # already added to the top HTML file, so we don't add the same
    # file twice. A user may specify the same file more than once
    # on the command line, because two different file names may
    # contain the same prefix. We are using the prefix to derive
    # image and HTML file names.
    #
    alreadyAdded = [];

    # Iterate over the list of files. Extract the prefix, construct
    # the desired image and HTML file names based on global variables
    # that were set from the command-line arguments, emit HTML into
    # topHTMLFile.
    #
    for fname in filenames:
        prefix = getPrefix(fname);
        if (prefix in alreadyAdded):
            continue;
        else:
            alreadyAdded.append(prefix);
            print("Inserting trace image for " + prefix);

        imageFileName = prefix + "." + graphType + "." + \
          str(percentThreshold) + "." + graphFilePostfix;
        htmlFileName = prefix + "." + graphType + "." + \
          str(percentThreshold) + ".html";

        insertIntoTopHTML(imageFileName, htmlFileName, topHTMLFile);

def parse_file(traceFile, prefix, topHTMLFile, htmlDir, createTextFile):

    startTime = 0;
    endTime = 0;
    stack = [];
    lockStack = [];
    outputFile = None;

    funcSummaryRecords = {}
    locksSummaryRecords = {}
    traceStats = TraceStats(prefix);
    logRecords = [];
    graph = nx.DiGraph();

    graph.add_node("START", fontname="Helvetica");
    graph.node["START"]['shape']='box'
    prevNodeName = "START";

    if (createTextFile):
        try:
            outputFile = open(prefix + ".txt", "w");
        except:
            print("Could not open " + prefix + ".txt for writing.");
            # We will not exit on this error, but will attempt to
            # parse the trace anyway.

    while True:
        line = traceFile.readline();
        if (line is None):
            break;
        if (line == ''):
            break;

        words = line.split(separator);
        thread = 0;
        time = 0;
        func = "";
        otherInfo = None;

        if(len(words) < 4):
           continue;

        try:
            func = words[1];
            if shortenFuncName:
                func = unique_shortname(func)
            thread = int(words[2]);
            time = long(words[3]);
            if (len(words) > 4):
                parts = words[4:len(words)];
                otherInfo = (" ".join(parts)).rstrip();

        except ValueError:
            print "Could not parse: " + line;
            continue;

        if (words[0] == "-->"):
            op = "enter";
        elif (words[0] == "<--"):
            op = "exit";
        else:
            continue;

        rec = LogRecord(func, op, thread, time, otherInfo);

        if(startTime == 0):
            startTime = time;
        else:
            endTime = time;

        if(op == "enter"):
            # Timestamp for function entrance
            # Push each entry record onto the stack.
            stack.append(rec);

            # Add this log record to the array
            logRecords.append(rec);

            # If we are told to write the records to the output
            # file, do so.
            if(outputFile is not None):
                rec.writeToFile(outputFile);
                outputFile.write("\n");

        else:
            if(outputFile is not None):
                # If this is a function exit record, we may need to add
                # the name of the lock to the end of the line, if this
                # happens to be a lock function. So for now we write the
                # line without the newline character at the end. Later we
                # will either add the lock name with the newline character
                # (if this happens to be a lock function, or just the
                # newline character otherwise.
                rec.writeToFile(outputFile);

            found = False;

            # Timestamp for function exit. Find its
            # corresponding entry record by searching
            # the stack.
            while(len(stack) > 0):
                stackRec = stack.pop();
                if(stackRec is None):
                    print("Ran out of opening timestamps when searching "
                          "for a match for: " + line);
                    break;

                # If the name of the entrance record
                # on the stack is not the same as the name
                # in the exit record we have on hand, complain
                # and continue. This means that there are errors
                # in the instrumentation, but we don't want to fail
                # because of them.
                if(not (stackRec.func == rec.func)):
                    continue;
                else:
                    # We have a proper function record. Let's add the data to
                    # the file's dictionary for this function.

                    runningTime = long(rec.time) - long(stackRec.time);

                    if(not funcSummaryRecords.has_key(stackRec.fullName)):
                        newPDR = PerfData(stackRec.fullName, stackRec.func,
                                              otherInfo, thread);
                        funcSummaryRecords[stackRec.fullName] = newPDR;

                    pdr = funcSummaryRecords[stackRec.fullName];
                    pdr.update(runningTime, stackRec.time);
                    found = True

                    # Full name is the name of the function, plus whatever other
                    # info was given to us, usually values of arguments. This
                    # information is only printed for the function entry record,
                    # so if we are at the function exit record, we must copy
                    # that information from the corresponding entry record.
                    #
                    rec.fullName = stackRec.fullName;
                    logRecords.append(rec);

                    # If this is a lock-related function, do lock-related
                    # processing. stackRec.otherInfo variable would contain
                    # the name of the lock, since only the function enter
                    # record has this information, not the exit record.
                    if(stackRec.otherInfo is not None
                       and looks_like_lock(func)):
                        do_lock_processing(locksSummaryRecords, rec,
                                           runningTime,
                                           stackRec.otherInfo);
                        if(outputFile is not None):
                            outputFile.write(" " + stackRec.otherInfo);
                    break;
            if(not found):
                print("Could not find matching function entrance for line: \n"
                      + line);

            if(outputFile is not None):
                outputFile.write("\n");

    traceStats.setStartTime(startTime);
    traceStats.setEndTime(endTime);

    # Filter the log records according to criteria on their attributes
    filteredLogRecords = filterLogRecords(logRecords, funcSummaryRecords,
                                          traceStats);

    if shortenFuncName:
        shortnameMapsFilename = 'shortname_maps.{}.json'.format(prefix)
        dump_shortname_maps(shortnameMapsFilename)
        print("shortname_maps is saved to {}".format(shortnameMapsFilename))

    # Generate HTML files summarizing function stats for all functions that
    # were not filtered.
    print("Generating per-function HTML files...");
    generatePerFuncHTMLFiles(prefix, htmlDir,
                                 funcSummaryRecords, locksSummaryRecords);

    # Augment graph attributes to reflect performance characteristics
    graph = generate_graph(filteredLogRecords);
    augment_graph(graph, funcSummaryRecords, traceStats, prefix, htmlDir);

    # Prepare the graph
    aGraph = nx.drawing.nx_agraph.to_agraph(graph);
    aGraph.add_subgraph("START", rank = "source");
    aGraph.add_subgraph("END", rank = "sink");

    # Generate files
    nameNoPostfix = htmlDir + "/" + \
      prefix + "." + graphType + "."+ str(percentThreshold) + "."


    imageFileName = nameNoPostfix + graphFilePostfix;
    print("Graph image is saved to: " + imageFileName);
    aGraph.draw(imageFileName, prog = 'dot');

    mapFileName = nameNoPostfix + "cmapx";
    aGraph.draw(mapFileName, prog = 'dot');
    print("Image map is saved to: " + mapFileName);

    generatePerFileHTML(nameNoPostfix + "html", imageFileName, mapFileName,
                            htmlDir, topHTMLFile);

    if(outputFile is not None):
        outputFile.close();

    generateSummaryFile('.txt', prefix, traceStats, funcSummaryRecords,
                            locksSummaryRecords)
    generateSummaryFile('.csv', prefix, traceStats, funcSummaryRecords,
                            locksSummaryRecords)


def generateSummaryFile(fileType, prefix, traceStats, funcSummaryRecords,
                            locksSummaryRecords):
    # Write the summary to the output file.
    try:
        summaryFileName = prefix + ".summary" + fileType;
        summaryFile = open(summaryFileName, "w");
        print("Summary file is " + summaryFileName);
    except:
        print("Could not create summary file " + summaryFileName);
        summaryFile = sys.stdout;

    if fileType == '.csv':
        summaryFile.write("Function, Num calls, Total Runtime (ns), "
                              "Averge Runtime (ns), Largest Runtime (ns)\n");
        for fkey, pdr in funcSummaryRecords.iteritems():
            pdr.printSelfCSVLine(summaryFile);
    else:
        summaryFile.write(" SUMMARY FOR FILE " + prefix + ":\n");
        summaryFile.write("------------------------------\n");
        summaryFile.write("Total trace time: "
                      + str(traceStats.getTotalTime()) + "\n");
        summaryFile.write(
            "Function \t Num calls \t Runtime (tot) \t Runtime (avg)\n");

        for fkey, pdr in funcSummaryRecords.iteritems():
            pdr.printSelf(summaryFile);
            summaryFile.write("------------------------------\n");

        lockDataDict = locksSummaryRecords;

        summaryFile.write("\nLOCKS SUMMARY\n");
        for lockKey, lockData in lockDataDict.iteritems():
            lockData.printSelf(summaryFile);

        summaryFile.write("------------------------------\n");

    summaryFile.close();

def getPrefix(fname):

    prefix = re.findall(r'trace.bin.\d+', fname);

    if (len(prefix) > 0):
        return prefix[0];
    else:
        words = fname.split(".txt");
        if (len(words) > 0):
            return words[0];
        else:
            return fname;

def looksLikeTextTrace(fname):

    if (fname.endswith(".txt")):
        return True;
    else:
        return False;

def getTextConverterCommand():

    argsList = [];

    # We need to know where the DINAMITE trace parser lives.
    # Its location should be in the DINAMITE_TRACE_PARSER variable.
    #
    if not os.environ.has_key("DINAMITE_TRACE_PARSER"):
       print("Error: DINAMITE_TRACE_PARSER environment variable MUST be set\n"
             "\t to the location of the trace_parser binary from the\n"
             "\t DINAMITE binary trace toolkit");
       return None;
    parserLocation = os.environ["DINAMITE_TRACE_PARSER"];
    if (parserLocation is None):
        print("Could not determine the location of the DINAMTE " +
                  "binary trace converer trace_parser.");
        print("This script expects to find the location in the " +
                  "DINAMITE_TRACE_PARSER environment variable.");
        return None;

    # Let's make sure that the map files generated by DINAMITE
    # are in the current directory, which is where we expect them
    # to be.
    #
    if not os.path.exists("./map_functions.json"):
        print(color.RED + color.BOLD +
                "Error! Cannot find map_functions.json. Make sure that "
                "this file, generated during DINAMITE compilation, is "
                "in the current working directory." + color.END);
        return None;

    print(color.RED + color.BOLD +
              "IMPORTANT! If you tracked memory accesses, make sure that "
              "map_types.json and map_variables.json generated by "
              "DINAMITE are in the current working directory." + color.END);

    # Things are looking good. We got the location of the parser
    # binary.
    argsList.append(parserLocation);
    argsList.append("-p");
    argsList.append("print");
    argsList.append("-a");
    argsList.append("ac_short");
    argsList.append("-m");
    argsList.append("./");

    return argsList;

def createTopHTML(htmlDir):

    if not os.path.exists(htmlDir):
        try:
            os.mkdir("./" + htmlDir);
            print("Directory " + htmlDir + " created");
        except:
            print "Could not create directory " + htmlDir;
            return None;

    try:
        topHTML = open(htmlDir + "/index.html", "w");
    except:
        print "Could not open " + htmlDir + "/index.html for writing";
        return None;

    topHTML.write("<!DOCTYPE html>\n");
    topHTML.write("<html>\n");
    topHTML.write("<head>\n");
    topHTML.write("<link rel=\"stylesheet\" type=\"text/css\"" +
                      "href=\"style.css\">\n");
    topHTML.write("</head>\n");
    topHTML.write("<body>\n");

    return topHTML;

def completeTopHTML(topHTML):

    topHTML.write("</body>\n");
    topHTML.write("</html>\n");
    topHTML.close();

def findHTMLTemplate(htmlDir):

    scriptLocation = os.path.dirname(os.path.realpath(__file__));
    htmlTemplateLocation = scriptLocation + "/" + \
      "showGraphs/stateTransitionCharts.html";
    cssFileLocation = scriptLocation + "/" + \
      "showGraphs/style.css";
    if (not (os.path.exists(htmlTemplateLocation) and
                 os.path.exists(cssFileLocation))):
        print("Cannot locate either of the required files: ");
        print("\t" + '\033[1m' + htmlTemplateLocation);
        print("\t" + cssFileLocation);
        print("\033[0m" +
                  "Please make sure you run the script from within the same "
                  + " directory structure as in the original repository.");
        return None;
    else:
        os.system('cp '+ cssFileLocation + " " + htmlDir + "/style.css");

    try:
        htmlTemplate = open(htmlTemplateLocation, "r");
        return htmlTemplate;
    except:
        print "Could not open " + htmlTemplateLocation + " for reading";
        return None;

def main():

    global firstNodeName;
    global graphFilePostfix;
    global graphType;
    global htmlTemplate;
    global lastNodeName;
    global multipleAcquireWithoutRelease;
    global noMatchingAcquireOnRelease;
    global outliersFile;
    global percentThreshold;
    global separator;
    global tryLockWarning;
    global verbose;
    global shortenFuncName;

    parser = argparse.ArgumentParser(description=
                                 'Process performance log files');

    parser.add_argument('files', type=str, nargs='*',
                    help='log files to process');

    parser.add_argument('-g', '--graphtype', dest='graphtype',
                        default='enter_exit',
                        help='Default=enter_exit; \
                        Possible values: enter_exit, func_only');

    parser.add_argument('--graph-file-postfix', dest='graphFilePostfix',
                        default='png');

    parser.add_argument('--htmlDir', dest='htmlDir', type=str,
                            default='HTML');

    parser.add_argument('-p', '--percent-threshold', dest='percentThreshold',
                        type=float, default = 2.0,
                        help='Default=2.0; \
                        When we compute the execution flow graph, we will not \
                        include any functions, whose percent execution time   \
                        is smaller that value.');

    parser.add_argument('-r', '--regenHTML', dest='regenHTML',
                            action='store_true');

    parser.add_argument('-s', '--separator', dest='separator', default=' ');
    parser.add_argument('--shorten_func_name', dest='shortenFuncName',
                            type=bool, default=True);

    parser.add_argument('--verbose', dest='verbose', action='store_true');

    args = parser.parse_args();

    graphType = args.graphtype;
    graphFilePostfix = args.graphFilePostfix;
    percentThreshold = args.percentThreshold;
    separator = args.separator;
    shortenFuncName = args.shortenFuncName;
    verbose = args.verbose;

    print("Running with the following parameters:");
    for key, value in vars(args).iteritems():
        print ("\t" + key + ": " + str(value));

    # Let's create the first part of the HTML file, which will contain
    # all graph images linked to per-graph HTML files.
    #
    topHTMLFile = createTopHTML(args.htmlDir);
    if (topHTMLFile is None):
        return;

    # Make sure that we know where to find the HTML file templates
    # before we spend all the time parsing the traces only to fail later.
    #
    htmlTemplate = findHTMLTemplate(args.htmlDir);
    if (htmlTemplate is None):
        return;

    if (args.regenHTML):
        if (len(args.files) > 0):
            print("Regenerating the top HTML file for trace files: "
                      + str(args.files));
            print(color.BOLD + "Contained per-file images, image maps "
                      "and HTML files must be present in the HTML directory!" +
                      color.END);
            regenerateHTML(topHTMLFile, args.files);
            completeTopHTML(topHTMLFile);
            return;
        else:
            print("If asking to only regenerate the top HTML, please supply " +
                      "a list of trace file names you want included.");
            return;

    if (percentThreshold > 0.0):
        print(color.RED + color.BOLD +
                  "IMPORTANT: filtering all functions whose running "
                  "time took less than " + str(percentThreshold) +
                  "% of total.\n To avoid filtering or change the default "
                  "value, use --percent-threshold argument.\n Example: "
                  "--percent-threshold=0.0" + color.END);

    # Create the file for dumping info about outliers
    #
    try:
        outliersFile = open("outliers.txt", "w");
    except:
        print ("Warning: could not open outliers.txt for writing");
        outliersFile = None;

    if(len(args.files) > 0):
        for fname in args.files:
            prefix = getPrefix(fname);
            print(color.BOLD + "Prefix is " + prefix + color.END);

            # If this is a text trace, we simply parse the file.
            # If this is a binary trace we spawn a subprocess to
            # convert the text to binary and read the stdout of
            # the child process.
            #
            if (looksLikeTextTrace(fname)):
                try:
                    traceFile = open(fname, "r");
                except:
                    print("Could not open " + fname + " for reading");
                    continue;

                parse_file(traceFile, prefix, topHTMLFile, args.htmlDir,
                               False);

            else:
                # Figure out the name of the script that will launch
                # the binary-to-text converter.
                #
                argsList = getTextConverterCommand();

                if (argsList is None):
                    sys.exit();
                # Append the file to the argument list and
                # create the subprocess
                #
                argsList.append(fname);
                process = subprocess.Popen(argsList,
                                               stdout=subprocess.PIPE);
                if (process is None):
                    print("Could not create a process from arguments: "
                              + str(argsList));
                    sys.exit();

                # Parse the file, reading from the standard out of the
                # created process. That process will output text trace
                # into its standard out.
                #
                parse_file(process.stdout, prefix, topHTMLFile, args.htmlDir,
                               True);

    completeTopHTML(topHTMLFile);


if __name__ == '__main__':
    main()
