#!/bin/bash 
#############################################################
#
#  $Id$
#
#############################################################

pnfs_path=''
data=''
ff_width=3
batch=10
if [ "${1:-}" = "-x" ] ; then set -xv; shift; fi
if [ "${1:-}" = "-p" ] ; then shift; pnfs_path=$1; shift; fi
if [ "${1:-}" = "-d" ] ; then shift; data=$1; shift; fi
if [ "${1:-}" = "-f" ] ; then shift; ff_width=$1; shift; fi
if [ "${1:-}" = "-b" ] ; then shift; batch=$1; shift; fi

if [ -z $pnfs_path ]; then pnfs_path="/pnfs/cdfen/test/sl8500/test"; fi
if [ ! -z $data ]; then data=${data}/; fi
#sizes="1 10 50 100 200 500 800 1000 2000 3000 4000 5000"
sizes="3 4 5 6 7 8 9 10 11 12"

if [ ! -d $data ]; then mkdir -p $data;fi
#echo  $data*$$.data
files=`ls $data*.data`
host=`hostname | cut -f 1 -d \.`
fsz=${#files}
date=`date +%F`
#echo fsz $fsz
for s in $sizes
  do
  if [ ! -e $pnfs_path/$date/${host}/$s ] 
      then 
      mkdir -p $pnfs_path/$date/${host}/${s}
      cd $pnfs_path/$date/${host}/$s 
      enstore pnfs --file_family=test
      enstore pnfs --file_family_width=$ff_width
      cd - > /dev/null 2>&1
  fi
done

if [ $fsz -eq 0 ]; then
      for s in $sizes
      do
	i=1
	while [ $i -lt $batch ] 
	do
	  #name=test_${s}_`date +"%s"`.data
	  name=${host}_test_${s}_`date +"%s"`_$$.data
	  sz=`~/enstore/test/torture/gauss ${s}|awk '{ print $1}'`
	  #echo "$$ $s $sz "
	  ~/enstore/test/torture/createfile $sz $data$name 
	  let i=i+1
	  sleep 1
	done 
      done
fi
files=`ls $data*.data`

for s in $sizes
  do
  files=`ls $data/${host}_test_${s}*.data`
  for f in $files
    do
      encp --threaded  $f $pnfs_path/$date/${host}/$s/`basename $f`.$$ &
    done
done
wait
#  rm $files
