#!/bin/bash
SPEC_PATH=$ENSTORE_DIR/pyinstaller/specs/sbin
#
rm -f spec_list
rm -f sbin_spec_list
for i in `make show_servers`;do echo $i >> spec_list;done
for i in `ls -1 ../sbin/pyinstaller | sed -e "s^.spec^^g"`; do echo $i >> sbin_spec_list;done                                 

for i in $(cat spec_list);do echo $i;pyi-makespec --specpath $SPEC_PATH --hidden-import enroute ../src/$i.py;done
for i in $(cat sbin_spec_list);do echo $i;pyi-makespec --specpath $SPEC_PATH --hidden-import enroute ../sbin/$i.py;done

