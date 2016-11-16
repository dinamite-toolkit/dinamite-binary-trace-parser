#ifndef PRINTPLUGIN_H
#define PRINTPLUGIN_H

#include "traceplugin.h"
#include <string.h>

enum formatType {
	DEFAULT,
	ACCESS_VAL_ONLY,
	ACCESS_VAR
};

class PrintPlugin : TracePlugin {
private:
	formatType fmt;

public:
PrintPlugin() : TracePlugin("print") {
		fmt = DEFAULT;
	}

	void printValue(logentry *log) {
		switch (log->entry.access.value_type) {
		case I8:
			cout << log->entry.access.value.i8;
			break;
		case I16:
			cout << log->entry.access.value.i16;
			break;
		case I32:
			cout << log->entry.access.value.i32;
			break;
		case I64:
			cout << log->entry.access.value.i64;
			break;
		case F32:
			cout << log->entry.access.value.f32;
			break;
		case F64:
			cout << log->entry.access.value.f64;
			break;
		case PTR:
			cout << hex << log->entry.access.value.ptr << dec;
			break;
		}
	}

	void processLog(logentry *log) {
		if (log->entry_type == LOG_ACCESS) {
			if (fmt == ACCESS_VAL_ONLY) {
				cout << " ";
				printValue(log);
				cout << " ";
			}
			else if (fmt == ACCESS_VAR) {
				cout << endl;
				cout << "@ "
				     << log->entry.access.type
				     << " "
				     << log->entry.access.ptr << " "
				     << (*nmaps->getType(
						 log->entry.access.typeId))
				     << " "
				     << (*nmaps->getVariable(
						 log->entry.access.varId))
				     << " ";
				printValue(log);
				cout << " " << log->entry.access.ac_timestamp;
			}
			else {
				cout << endl;
				cout << (int) log->entry.access.thread_id << " "
				     << (*nmaps->getFile(log->entry.access.file)) << ":"
				     << log->entry.access.line << " "
				     << log->entry.access.ptr << " "
				     << (*nmaps->getType(log->entry.access.typeId)) << " "
				     << (*nmaps->getVariable(log->entry.access.varId))
				     << " "
				     << (log->entry.access.col == 1 ? 'm' : 'h') << endl;
			}
		}
		if(log->entry_type == LOG_FN) {
			cout << endl;
			cout << (log->entry.fn.fn_event_type == 0? "--> " : "<-- ")
			     << (*nmaps->getFunction(log->entry.fn.function_id))
			     << " "
			     << (unsigned) log->entry.fn.thread_id << " "
			     << log->entry.fn.fn_timestamp;
		}
	}

	void passArgs(char *args) {
		if(args != NULL && strcmp(args, "ac_short") == 0)
			fmt = ACCESS_VAL_ONLY;
		else if(args != NULL && strcmp(args, "ac_var") == 0)
			fmt = ACCESS_VAR;
	}

	void finalize() {
	}
};

static PrintPlugin registerpp;


#endif
