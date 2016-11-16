#include <stdio.h>
#include <unistd.h>
#include <stdlib.h>
#include <fstream>
#include <errno.h>
#include <sys/types.h>
#include <sys/stat.h>
#include <fcntl.h>

#include "binaryinstrumentation.h"
#include "namemaps.h"
#include "printplugin.h"
#include "alloc_counter.h"
#include "access_counter.h"

using namespace std;

void printUsage(char *prog) {

	cout << prog << " -p <plugin name> -m <map directory> <file>" << endl;
	cout << "Available plugins:" << endl;

	for (auto it = TracePlugin::registry.begin();
	     it != TracePlugin::registry.end(); it++) {
		cout << "\t" << it->first << endl;
	}
}

#define BUFFER_SIZE 4 * 1024

int main(int argc, char **argv) {

    char c;
    char *pluginName = NULL;
    char *pluginArgs = NULL;
    char *mapDir = NULL;
    char *fileName = NULL;

    while ((c = getopt(argc, argv, "p:m:a:")) != -1) {
        switch (c) {
            case 'p':
                pluginName = optarg;
                break;
            case 'a':
                pluginArgs = optarg;
                break;
            case 'm':
                mapDir = optarg;
                break;
        }
    }

    if (pluginName == NULL || mapDir == NULL) {
        printUsage(argv[0]);
        return -1;
    }

    NameMaps nmaps(mapDir);

    fileName = argv[optind];
    if(fileName == NULL)
    {
	    printUsage(argv[0]);
	    return -1;
    }

    logentry log[BUFFER_SIZE];
    TracePlugin *plugin = TracePlugin::getPlugin(pluginName);
    plugin->setNameMaps(&nmaps);
    if (plugin == NULL) {
        cerr << "Plugin " << pluginName << " not found!" << endl;
        printUsage(argv[0]);
        exit(-1);
    }
    cerr << "Plugin: " << pluginName << "\tFile: " << fileName << endl;
    plugin->passArgs(pluginArgs);

    FILE *f = fopen(fileName, "rb");
    if (f == NULL) {
        perror("Error opening file");
    }

    int sizeRead;
    while (1) {
        sizeRead = fread(&log, sizeof(logentry), BUFFER_SIZE, f);
        if (sizeRead == 0) {
            break;
        }

        for (int i = 0; i < sizeRead; i++) {
            plugin->processLog(&(log[i]));
        }
    }
    plugin->finalize();

}
