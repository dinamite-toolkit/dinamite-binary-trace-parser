#ifndef AllocCounterPlugin_H
#define AllocCounterPlugin_H

#include "traceplugin.h"
#include <map>

class AllocCounterPlugin : TracePlugin {
    map<string, unsigned long long> alloc_counts; // In bytes

    public:
    AllocCounterPlugin() : TracePlugin("alloccount") {
    }

    void processLog(logentry *log) {

	    if (log->entry_type == LOG_ALLOC) {
            alloclog *all = &(log->entry.alloc);
            string tname = (*nmaps->getType(all->type));
            if (alloc_counts.count(tname) == 0) {
                alloc_counts[tname] = all->size * all->num;
            } else {
                alloc_counts[tname] += all->size * all->num;
            }
	    }
    }

    void passArgs(char *args) {

    }
    void finalize() {
        for (auto it = alloc_counts.begin(); it != alloc_counts.end(); it++) {
            cout << it->second << "\t\t\t" << it->first << endl;
        }
    }
};

static AllocCounterPlugin registeracp;


#endif

