#ifndef NAMEMAPS_H
#define NAMEMAPS_H

#include <map>
#include "json11.hpp"
#include <sstream>
#include <iostream>

using namespace std;

class NameMaps {
    private:
        class NameMap {
            map<int, string> nmap;

            public:
            NameMap() {
            }

            void loadMap(string filename) {
                ifstream mapin;
                mapin.open(filename);
                if (!mapin.is_open()) {
                    return;
                }
                string fname;
                stringstream ss;
                string err;
                ss << mapin.rdbuf();
                json11::Json jsmap;
                jsmap = json11::Json::parse(ss.str(), err);
                for (auto entry : jsmap.object_items()) {
                    //cout << "namemap: " << entry.first << " " << entry.second.int_value() << endl;
                    nmap[entry.second.int_value()] = entry.first;
                    //cout << entry.second.int_value() << " " <<  entry.first << endl;
                }
            }

            string *get(int idx) {
                if (nmap.count(idx) == 0) {
                    nmap[idx] = to_string(idx);
                }
                return &(nmap[idx]);
            }
        };

        NameMap var;
        NameMap file;
        NameMap type;
        NameMap func;

        string empty;

        bool loaded;

    public:
        NameMaps(const char *dir) : empty("") {
            if (dir == NULL) {
                loaded = false;
            } else {
                loaded = true;
                string base(dir);
                var.loadMap(base + "/map_variables.json");
                file.loadMap(base + "/map_sources.json");
                type.loadMap(base + "/map_types.json");
                func.loadMap(base + "/map_functions.json");
            }
        }

        string *getVariable(int idx) {
            if (loaded)
                return var.get(idx);
            else
                return &empty;
        }
        string *getType(int idx) {
            if (loaded)
                return type.get(idx);
            else
                return &empty;
        }
        string *getFile(int idx) {
            if (loaded)
                return file.get(idx);
            else
                return &empty;
        }
        string *getFunction(int idx) {
            if (loaded)
                return func.get(idx);
            else
                return &empty;
        }


};

#endif
