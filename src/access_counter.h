#ifndef AccessCounterPlugin_H
#define AccessCounterPlugin_H

#include "traceplugin.h"
#include <map>

class AccessCounterPlugin : TracePlugin {
    map<int, unsigned long long> access_counts; // In bytes

    public:
    AccessCounterPlugin() : TracePlugin("access_count") {
    }

    void processLog(logentry *log) {

	    if (log->entry_type == LOG_ACCESS) {
            int varid = log->entry.access.varId;
            if (access_counts.count(varid) == 0) {
                access_counts[varid] = 1;
            } else {
                access_counts[varid] += 1;
            }
	    }
    }

    void passArgs(char *args) {

    }

    void finalize() {
        int first = 1;
        cout << "{" << endl;

        for (auto it = access_counts.begin(); it != access_counts.end(); it++) {
            if (!first) cout << ", " << endl;
            if (first) first = 0;
            string tname = (*nmaps->getVariable(it->first));
            cout << tname << ": " << it->second;
        }
        cout << endl;
        cout << "}" << endl;
    }
};

static AccessCounterPlugin registeraccp;


#endif

