############################################################
#
# $Id$
#

SWIG_GENERATED_C_FILES=../derrno_wrap.c \
	../checksum_wrap_thread.c ../socket_ext_wrap.c \
	../strbuffer_wrap_thread.c ../ftt2_wrap_thread.c \
	../runon_wrap.c ../enroute_wrap.c ../mtx_wrap_thread.c

SWIG_GENERATED_PY_FILES=../derrno.py ../checksum.py \
	../ftt2.py ../socket_ext.py ../strbuffer.py ../enroute.py \
	../runon.py ../mtx.py

all: $(SWIG_GENERATED_PY_FILES) $(SWIG_GENERATED_C_FILES)
# SWIG_GENERATED_PY_FILES are automatically created
#at the same time as the C files

clean:
	rm -f *wrap* *doc* *.pyc *~
	rm -f $(SWIG_GENERATED_C_FILES)
	rm -f $(SWIG_GENERATED_PY_FILES)

../derrno_wrap.c: derrno.i
	if [ "$(ACI_DIR)_" != _ ] ; then \
	swig -I$(ACI_DIR)/inc -shadow -python -py3 derrno.i ; \
	mv derrno_wrap.c .. ; \
	mv derrno.py .. ; \
	fi

../derrno.py: ../derrno_wrap.c


../checksum_wrap_thread.c: checksum.i
	swig -shadow -python -py3 -threads -D__STDC__ checksum.i
	mv checksum_wrap.c ../checksum_wrap_thread.c
	mv checksum.py ..

../checksum.py: ../checksum_wrap_thread.c



../ftt2_wrap_thread.c: ftt2.i
	if [ "$(FTT_DIR)_" != _ ] ; then \
		swig -I$(FTT_DIR)/include -shadow -python -py3 -threads ftt2.i ; \
		mv ftt2_wrap.c ../ftt2_wrap_thread.c; \
		mv ftt2.py .. ; \
	fi

../ftt2.py: ../ftt2_wrap_thread.c


../socket_ext_wrap.c: socket_ext.i
	swig -shadow -python -py3 -threads socket_ext.i
	mv socket_ext_wrap.c ..
	mv socket_ext.py ..

../socket_ext.py: ../socket_ext_wrap.c


../strbuffer_wrap_thread.c: strbuffer.i
	swig -shadow -python -py3 -threads strbuffer.i
	mv strbuffer_wrap.c ../strbuffer_wrap_thread.c ; \
	mv strbuffer.py ..

../strbuffer.py: ../strbuffer_wrap_thread.c


../enroute_wrap.c: enroute.i
	swig -shadow -python -py3 enroute.i
	mv enroute_wrap.c ..
	if [ -f enroute.py ]; then \
		mv enroute.py .. ;  \
	fi

../enroute.py: ../enroute_wrap.c


../runon_wrap.c: runon.i
	swig -shadow -python -py3 runon.i
	mv runon_wrap.c ..
	if [ -f runon.py ]; then \
		mv runon.py .. ;  \
	fi

../runon.py: ../runon_wrap.c

../mtx_wrap_thread.c: mtx.i
	swig -I$(ENSTORE_DIR)/mtx/mtx-1.3.12 -shadow -python -py3 -threads mtx.i
	mv mtx_wrap.c ../mtx_wrap_thread.c ; \
	mv mtx.py ..

../mtx.py: ../mtx_wrap_thread.c
