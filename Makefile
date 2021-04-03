
# Redirect to GNU make

.SUFFIXES:

default: config/finished
	config/bin/make

.DEFAULT:
	$(MAKE) config/finished
	config/bin/make $(.TARGETS)

# Dependency changes here should be mirrored in GNUmakefile
config/finished: configure config/configure config/configure.inc config/*.in
	MAKE= ./configure
