SHELL=/bin/sh
P=cp -frp
MV=mv
RM=rm -rf


ENSTORE_TOP_DIR=$$ENSTORE_INSTALL_DIR
TARGET_DIR=$(ENSTORE_TOP_DIR)/external_distr
FILE_LIST:=$(shell ls -1 pyinstaller | sed -e "s^.spec^^g")


all:
	@echo nothing to build

clean:
	- $(RM) *.pyc
	- $(RM) *.pyo
	- $(RM) dist
	- $(RM) build
	- $(RM) $(TARGET_DIR)
pre_compile:
	{ \
	if [ ! -d $(TARGET_DIR) ]; then \
		mkdir -p $(TARGET_DIR); \
	fi; \
	for f in $$(ls -1 | grep -v ".py"); do \
        if [ ! -d $$f ] && [ ! -L $$f ] ; then \
        $(CP) $$f $(TARGET_DIR); \
        fi; \
        done \
	}

post_compile:
	$(RM) dist
	$(RM) build

.SECONDEXPANSION:
$(FILE_LIST): $$@
	if [ -f $@ ]; then \
		$(RM) $@; \
	fi
	pyinstaller pyinstaller/$@.spec
	$(CP) dist/$@ $(TARGET_DIR)
	$(RM) dist/$@



