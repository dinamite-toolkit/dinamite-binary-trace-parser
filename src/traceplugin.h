#ifndef TRACEPLUGIN_H
#define TRACEPLUGIN_H

#include <map>
#include <string>
#include <iostream>

#include <stdint.h>
#include "binaryinstrumentation.h"

#define MISS_MASK 0x8000
//#define MISS_MASK 0x1
#define WASTE_MASK 0x3f

using namespace std;

class TracePlugin {
    public:
        static map<string, TracePlugin*> registry;

    static TracePlugin *getPlugin(const char *name) {
        string sName(name);
        if (TracePlugin::registry.count(sName) > 0) {
            return TracePlugin::registry[sName];
        }
        return NULL;

    }

    void setNameMaps(NameMaps *nnmaps) {
        nmaps = nnmaps;
    }


    protected:
    NameMaps *nmaps;
    TracePlugin(const char *name) {
#ifdef V_REGISTRATIONS
        cout << "Registering " << name << endl;
#endif
        string sName(name);
        TracePlugin::registry[sName] = this;
    }

    public:
    virtual void processLog(logentry *log) = 0;
    virtual void finalize() = 0;
    virtual void passArgs(char *args) = 0;

};

map<string, TracePlugin*> TracePlugin::registry;


#endif

