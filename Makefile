CC = g++

CXXFLAGS += -I./src/ -I$(INST_LIB) -flto -O2
#CXXFLAGS += -I./src/ -I$(INST_LIB) -g -O0
CXXFLAGS += -MMD -MP -std=c++11
LDFLAGS = -flto

SRC_FILES := $(wildcard src/*.cpp)
OBJ_FILES := $(SRC_FILES:.cpp=.o)
DEP_FILES := $(OBJ_FILES:.o=.d)


.PHONY: all clean

all: trace_parser


-include $(DEP_FILES)

trace_parser: $(OBJ_FILES)
	$(CC) $(LD_FLAGS) -o $@ $^

src/%.o : src/%.cpp
	$(CC) $(CXXFLAGS) -c -o $@ $<
	

clean:
	rm src/*.o src/*.d trace_parser
