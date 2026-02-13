#!/usr/bin/bash

# This is a good enough working instance
# It is recommended to review this instance and modify it
# specifically
# 1. location of $E_H here it is /opt/ehome
# 2. location of setup-enstore here it is /opt/ehome/site_specific/config

set -u

OVERRIDE_PATH=0  # 1 to enable, 0 to disable the --override-path
version=n

# get example
# ~enstore/dcache-deploy/scripts/real-encp.sh  get 000200000000000000007A80  /tmp/x1 '-si=size=312;new=true;stored=false;sClass=test.dcache;cClass=-;hsm=enstore;alloc-size=309155;onerror=default;timeout=-1;flag-c=1:34677ad2;uid=5744;;path=<Unknown>;group=test;family=dcache;bfid=<Unknown>;volume=<unknown>;location=<unknown>;' -pnfs=/pnfs/fs -command=/home/enstore/dcache-deploy/scripts/real-encp2.sh

# '~enstore/dcache-deploy/scripts/real-encp.sh get 000063ADB93D23C84969B4C51C3DC3BB2CDB /diska/read-pool-1/data/000063ADB93D23C84969B4C51C3DC3BB2CDB -si=size=1073741824;new=false;stored=true;sClass=test.dcache;cClass=-;hsm=enstore;accessLatency=NEARLINE;retentionPolicy=CUSTODIAL;gid=3200;uid=8637;enstore://enstore/?volume=VOO534&location_cookie=0000_000000000_0002267&size=1073741824&file_family=dcache&original_name=/pnfs/fnal.gov/usr/test/litvinse/zero_data_lqcdsrm_dccp_1.data&map_file=&pnfsid_file=000063ADB93D23C84969B4C51C3DC3BB2CDB&pnfsid_map=&bfid=CDMS136605186900000&origdrive=stkenmvr216a:/dev/rmt/tps4d0n:1310065470&crc=0;;path=/pnfs/fnal.gov/usr/test/litvinse/zero_data_lqcdsrm_dccp_1.data;group=test;family=dcache;bfid=CDMS136605186900000;volume=VOO534;location=0000_000000000_0002267; -pnfs=/pnfs/fs -command=/usr/local/bin/real-encp.sh -uri=enstore://enstore/?volume=VOO534&location_cookie=0000_000000000_0002267&size=1073741824&file_family=dcache&original_name=/pnfs/fnal.gov/usr/test/litvinse/zero_data_lqcdsrm_dccp_1.data&map_file=&pnfsid_file=000063ADB93D23C84969B4C51C3DC3BB2CDB&pnfsid_map=&bfid=CDMS136605186900000&origdrive=stkenmvr216a:/dev/rmt/tps4d0n:1310065470&crc=0'

# put example
# /usr/local/bin/real-encp.sh put 001400000000000000B177C0 /data/write-pool-1/data/001400000000000000B177C0 '-si=size=4274832;new=true;stored=false;sClass=cms.cms4;cClass=-;hsm=enstore;path=/pnfs/fnal.gov/usr/cms/WAX/4/pnfs/fnal.gov/cms/PCP04/Digi/eg03_jets_2g_pt50170/jon.test.103;;path=<Unknown>;group=cms;family=cms4;bfid=<Unknown>;volume=<unknown>;location=<unknown>;' -pnfs=/pnfs/fs -command=/usr/local/bin/real-encp.sh

# /usr/local/bin/real-encp.sh put 00005FBD8F37A25941CBA3AB3AE25873B5E0 /diska/write-pool-1/data/00005FBD8F37A25941CBA3AB3AE25873B5E0 -si=size=83886080;new=true;stored=false;sClass=test.dcache;cClass=-;hsm=enstore;accessLatency=NEARLINE;retentionPolicy=CUSTODIAL;uid=-1;path=/pnfs/fnal.gov/usr/test/litvinse/go/fnisd1_c6f54a2e493411e2a3460019b9037377.data;gid=-1;StoreName=sql;;path=<Unknown>;group=test;family=dcache;bfid=<Unknown>;volume=<unknown>;location=<unknown>; -pnfs=/pnfs/fs -command=/usr/local/bin/real-encp.sh'
# remove example
#/usr/local/bin/real-encp.sh  remove -uri=enstore://enstore/?volume=VON589&location_cookie=0000_000000000_0075148&size=1024&file_family=dcache&original_name=/pnfs/fnal.gov/usr/eagle/dcache-tests/yujun/1kfile.1.2013Mar19145325&map_file=&pnfsid_file=0000AB4A74D3B1694EC49AA30D50211140C7&pnfsid_map=&bfid=CDMS136374786500000&origdrive=enmvr035:/dev/rmt/tps4d0n:1310260228&crc=0 -pnfs=/pnfs/fs -command=/usr/local/bin/real-encp.sh
if [[ ! -v E_H ]]; then
    export E_H=/opt/ehome
fi

if [ ! -d $E_H ]; then
    mkdir -p $E_H
fi

f=/tmp/tmpOK$$
touch $f
if [ $? -eq  0 ];then
  out=/tmp/real-encp/`date +'%Y-%m-%d:%H:%M:%S'`.$$.$1.$2
  rm $f
else
  out=$E_H/tmp/real-encp/`date +'%Y-%m-%d:%H:%M:%S'`.$$.$1.$2
  mkdir $E_H/tmp 2>/dev/null
fi

dir=`dirname $out`
if [ ! -d "$dir" ]; then mkdir $dir; fi
export out
exec >>$out 2>&1 <&-

set -xv

if [ -d "${LOG_DIR:-}" ]; then
    LOGFILE=$LOG_DIR/real-encp.log
    ERROR=$LOG_DIR/real-encp-error.log
    SUCCESS=$LOG_DIR/real-encp-success.log
else
    LOGFILE=$E_H/dcache-log/real-encp.log
    ERROR=$E_H/dcache-log/real-encp-error.log
    SUCCESS=$E_H/dcache-log/real-encp-success.log
fi
log_dir=`dirname $LOGFILE`
if [ ! -d $ ]; then
    mkdir -p $log_dir
fi

args="$*"
say() { if [ -n "${LOGFILE-}" ]; then  echo $version `date` ${node:-nonode} ${command:-nocmd} ${pnfsid:-noid} ${filepath:-nofilepath} $* >> $LOGFILE; fi
                                       echo $version `date` ${node:-nonode} ${command:-nocmd} ${pnfsid:-noid} ${filepath:-nofilepath} $*
      }
sayE() { if [ -n "${ERROR}" ];   then  echo $version `date` ${node:-nonode} ${command:-nocmd} ${pnfsid:-noid} ${filepath:-nofilepath} $* >> $ERROR; fi
      }
sayS() { if [ -n "${ERROR}" ];   then  echo $version `date` ${node:-nonode} ${command:-nocmd} ${pnfsid:-noid} ${filepath:-nofilepath} $* >> $SUCCESS; fi
      }

#
# returns file name for pnfs id
#
pathfinder() {
    id=$1
    fname=`head -n 1 "/pnfs/fs/.(pathof)($id)"`
    echo ${fname}
}

#
# TODO : be able to extract constants from somewhere (dcache configuration)
#

atrap1() { say real-encp trapped SIGHUP; }
atrap2() { say real-encp trapped SIGINT; }
atrap3() { say real-encp trapped SIGQUIT; exit 1; }
atrap9() { say real-encp trapped SIGKILL; exit 1; }

trap atrap1 1
trap atrap2 2
trap atrap3 3
trap atrap9 9

sP_bfid=0
sP_ls=0
P_nameof() { (cd $pnfs_root >/dev/null 2>&1;  cat ".(nameof)($1)" 2>/dev/null ); }
P_bfid()   { (cd $pnfs_root >/dev/null 2>&1;  cat ".(access)($1)(1)" ); sP_bfid=$?; }
P_size()   { (cd $pnfs_root >/dev/null 2>&1; stat ".(access)($1)" 2>/dev/null| grep Size: | awk '{print $2}' ); }
P_ls ()    { (cd $pnfs_root >/dev/null 2>&1;   ls ".(access)($1)" 2>/dev/null ); sP_ls=$?; }

read_encp_options() {
    opt_file=$E_H/site_specific/config/encp_options
    if [ -r $opt_file ]; then
	while read l;do
	    if [ ! -z "${l}" ]; then
		addtl_options="${addtl_options} ${l}";
	    fi;
	done < <(grep -v "^#\|^$" $opt_file)
    fi;
}
    
node=`uname -n| sed -e 's/\([^\.]\)\..*/\1/'`

# add path to encp
rpm_dir=`rpm -ql encp_dcache_bin | head -1`
export PATH=$rpm_dir/bin:$PATH
ENCP=`which encp 2>/dev/null`
#
# above should succeed already, but just in case
# try to source encp setup file if it has failed.
#
# execute setup anytime, cuz it might have been changed
# while dcache is running
#
ENCP_SETUP_FILE=$E_H/site_specific/config/setup-enstore
if [ -r ${ENCP_SETUP_FILE} ]; then
	. ${ENCP_SETUP_FILE}
else
    say $0 $* Can not find $ENCP_SETUP_FILE; exit 1;
fi

if [ -z "$ENCP" ]; then say $0 $* Can not find encp in our path; exit 1; fi

addtl_options=''
read_encp_options
options="--verbose=4 --threaded --bypass-filesystem-max-filesize-check $addtl_options"

if [ $# -lt 3 ] ;then
    say Not enough arguments  $0 $args
    exit 4
else
    command=$1
    pnfsid=$2
    filepath=$3
    shift; shift; shift;
    say  $0 $*
fi

# parse the options passed in by the dcache
pnfs_root=""
while [ $# -gt 0 ] ;do
	if expr "$1" : "-pnfs=" >/dev/null 2>&1 ; then
	    pnfs_root=`echo $1 | sed -e "s/^-pnfs=//"`
	elif expr "$1" : "-command=" >/dev/null 2>&1 ; then
	    script_command=`echo $1 | sed -e "s/^-command=//"`
	elif expr "$1" : "-si=" >/dev/null 2>&1 ; then
	    #
	    # parse "-si" option
	    #
	    si=`echo $1 | sed -e 's/^-si=//'`
	    # split into list of key=value pairs
	    parts=`echo $si | tr ";" "\n"`
	    for p in $parts;
	    do
		F1=`echo $p | cut -d= -f1| sed -e 's/-/_/g'`
		F2=`echo $p | cut -d= -f2`
		if expr "${F1}" : "enstore://enstore" > /dev/null 2>&1 ; then
		    continue
		fi
		already="`eval echo \\$si_$F1 2>/dev/null`"
		if [ "$already" == "" -o "$already" == "<Unknown>" -o "$already" == "<unknown>" ]; then
		    eval si_$F1=\"$F2\"
		fi
	    done
	elif expr "$1" : "-uri="  >/dev/null 2>&1 ; then
	    #
	    # parse -uri option
	    #
	    uri=`echo $1 | sed -e 's/^-uri=//'`
	    parts=`echo $uri | tr "&" "\n"`
	    for p in $parts;
	      do
		if expr "${p}" : "enstore://enstore" > /dev/null 2>&1 ; then
		    continue
		fi
		eval uri_$p
	    done
	fi
	shift
done


# echo 'pnfs_root     = ' ${pnfs_root:-unset}
# echo 'script_command= ' ${script_command:-unset}


# si variables:

#echo 'si_size       = ' ${si_size:-unset}
#echo 'si_new        = ' ${si_new:-unset}
#echo 'si_stored     = ' ${si_stored:-unset}
#echo 'si_sClass     = ' ${si_sClass:-unset}
#echo 'si_cClass     = ' ${si_cClass:-unset}
#echo 'si_hsm        = ' ${si_hsm:-unset}
#echo 'si_accessLatency      = ' ${si_accessLatency:-unset}
#echo 'si_retentionPolicy      = ' ${si_retentionPolicy:-unset}
#echo 'si_StoreName  = ' ${si_StoreName:-unset}
#echo 'si_gid        = ' ${si_gid:-unset}
#echo 'si_uid        = ' ${si_uid:-unset}
#echo 'si_path       = ' ${si_path:-unset}
#echo 'si_group      = ' ${si_group:-unset}
#echo 'si_family     = ' ${si_family:-unset}
#echo 'si_bfid       = ' ${si_bfid:-unset}
#echo 'si_volume     = ' ${si_volume:-unset}
#echo 'si_location   = ' ${si_location:-unset}

# uri variables

#echo 'uri_location_cookie = ' ${uri_location_cookie:-unset}
#echo 'uri_size            = ' ${uri_size:-unset}
#echo 'uri_file_family     = ' ${uri_file_family:-unset}
#echo 'uri_original_name   = ' ${uri_original_name:-unset}
#echo 'uri_map_file        = ' ${uri_map_file:-unset}
#echo 'uri_pnfsid_file     = ' ${uri_pnfsid_file:-unset}
#echo 'uri_bfid            = ' ${uri_bfid:-unset}
#echo 'uri_origdrive       = ' ${uri_origdrive:-unset}
#echo 'uri_crc             = ' ${uri_crc:-unset}

fsize=${si_size}

#remove double slashes:

si_path=`echo $si_path | sed -e "s/\/\/*/\//g"`
si_path=`pathfinder ${pnfsid}`


pathtype1=`echo $si_path | grep -c "^/pnfs/fnal.gov/usr"`
pathtype2=`echo $si_path | grep -c "^/pnfs/fs/usr"`
let npathtypesok=${pathtype1}+${pathtype2}
if [ ${npathtypesok} -ne 0 ]; then
  filename="$si_path"
else
  filename=""
fi


if [ -z "$pnfs_root" ] ;then
   say PNFS root not found in $0 $args
   exit 1
fi

# Return codes
# Return Code         Meaning                                Pool Behaviour
#                                                Into HSM                     From HSM
# 30 <= rc < 40       User defined               Deactivates request          Reports Problem to PoolManager
# 41                  No Space Left on device    Pool Retries                 Disables Pool,  Reports Problem to PoolManager
# 42                  Disk Read I/O Error        Pool Retries                 Disables Pool,  Reports Problem to PoolManager
# 43                  Disk Write I/O Error       Pool Retries                 Disables Pool,  Reports Problem to PoolManager
# All other                                      Pool Retries                 Reports Problem to PoolManager

#------------------------------------------------------------------------------------------
if [ "$command" = "get" ] ; then

#
# check if volume system inhibit is none:
#
   vol_info=$(enstore info --gvol ${si_volume} 2>/dev/null)

   if [ $? -eq 0 ]; then
       system_inhibit=$(python -c "
import sys
try:
  code='d='+sys.argv[1]
  exec(code)
  print(d.get('system_inhibit')[0])
except:
  sys.exit(1)
" "${vol_info}")

       if [ $? -eq 0 -a ${system_inhibit} != "none" ]; then
           say"Volume=${si_volume} system inhibit=${system_inhibit}, deactivating request"
           exit 32
       fi
   fi

#
# Check if this is SFA file and we can just copy it
#
   file_info=$(enstore info --file ${si_bfid}  2>/dev/null)
   if [ $? -eq 0 ]; then
       package_id=$(python -c "
import sys
try:
  code='d='+sys.argv[1]
  exec(code)
  print(d.get('package_id'))
except:
  sys.exit(1)
" "${file_info}")

       if [ $? -eq 0 -a "${package_id}" != "" -a "${package_id}" != "None" -a "${package_id}" != "${si_bfid}" ]; then
	   #
	   # get package pnfsid
	   #
	   package_pnfsid=`enstore info --file ${package_id} | grep pnfsid | sed -e "s/[[:punct:]]//g" | awk '{ print $NF}'`
	   package_path=`pathfinder ${package_pnfsid}`
	   #
	   # strip leading slash from location cookie
	   #
	   file_path=`echo ${uri_location_cookie} | sed -e 's/^\///g'`
	   #
	   echo "file path000 =  ${filepath}"
	   # dcap preload library
	   #
	   #export DCACHE_DEBUG=255
	   #export LD_PRELOAD=/usr/lib64/libpdcap.so.1
	   #
	   # extract file from tar
	   echo "file path =  ${filepath}"
	   #
	   file_dir=`dirname ${filepath}`
	   echo "file dir ${file_dir}"
	   #
	   # start timer to measure transfer time
	   #
	   t0=`date +"%s"`
	   
	   #(cd ${file_dir} && tar --seek --record-size=512 --strip-components 5 --force-local -xf ${package_path} ${file_path})  >>$LOGFILE 2>&1
	   cd ${file_dir}
	   echo "FD ${file_dir}"
	   echo "pack path ${package_path}}"
	   echo "FP ${file_path}"
	   if [ ! -f $package_pnfsid ]; then # stage file
	       say g1 $ENCP $options --age-time 60 --delpri 10 --skip-pnfs --get-bfid ${package_id} $package_pnfsid
	       nice -n -3 $ENCP $options --age-time 60 --delpri 10 --skip-pnfs --get-bfid ${package_id} $package_pnfsid >>$LOGFILE 2>&1
	       PACK_ENCP_EXIT=$?
	       say encp --get-bfid ${package_id} $package_pnfsid, rc=$PACK_ENCP_EXIT
	       if [ $PACK_ENCP_EXIT -eq 0 ]; then
		   sayS g2s get, rc=$PACK_ENCP_EXIT
	       else
		   sayE g2e get, rc=$PACK_ENCP_EXIT
		   exit $PACK_ENCP_EXIT
	       fi
	   fi
	   tar --seek --record-size=512 --strip-components 5 --force-local -xf $package_pnfsid ${file_path} >>$LOGFILE 2>&1
	   rc=$?
	   if [ $rc -eq 0 ]; then
	       pnfsid_in_loc=`basename ${file_path}`
	       if [ "${pnfsid_in_loc}" != "${pnfsid}" ]; then
		   #
		   # we have come across packaged files that have different PNFSID in their
		   # name than their PNFSIDs. Handle those:
		   #
		   say pnfsid on location cookie does not match file pnfsid ${pnfsid_in_loc} != ${pnfsid}
		   (cd  ${file_dir} && mv ${pnfsid_in_loc} ${pnfsid})
	       fi
	       chmod 0644 $filepath
	       touch $filepath
	       t1=`date +"%s"`
	       dt=$((t1-t0))
	       say SFA Completed untarring ${uri_size} bytes in ${dt} sec.
	       exit 0
	   else
	       rm -f ${filepath}
	       say Failed to untar file $package_pnfsid
	       exit 1
	   fi
       fi
   fi
   #
   # if crc is known, do not calculate it, check it later
   #
   if [ "${uri_crc}" != "" ]; then
       encp --help | egrep "\-\-cksm\-value"  >/dev/null 2>&1 && options="${options:-} --no-crc"
   fi
   #
   # try to get file by bfid
   #
   say g1 $ENCP $options --age-time 60 --delpri 10 --skip-pnfs --get-bfid ${si_bfid} $filepath
   nice -n -3 $ENCP $options --age-time 60 --delpri 10 --skip-pnfs --get-bfid ${si_bfid} $filepath  >>$LOGFILE 2>&1
   ENCP_EXIT=$?
   say encp --get-bfid ${si_bfid} $filepath, rc=$ENCP_EXIT
   if [ $ENCP_EXIT -eq 0 ]; then
       rm -f $out
       sayS g2s get, rc=$ENCP_EXIT
   else
       #
       # execute normal encp, if getting by bfid failed
       #
       say  g1   $ENCP $options --age-time 60 --delpri 10 --pnfs-mount $pnfs_root --shortcut --get-cache $pnfsid $filepath
       nice -n -3   $ENCP $options --age-time 60 --delpri 10 --pnfs-mount $pnfs_root --shortcut --get-cache $pnfsid $filepath >>$LOGFILE 2>&1
       ENCP_EXIT=$?
       say encp --get-cache $pnfsid $filepath, rc=$ENCP_EXIT
       if [ $ENCP_EXIT -eq 0 ]; then
	   rm -f $out
	   sayS g2s get, rc=$ENCP_EXIT
       else
	   sayE g2e get, rc=$ENCP_EXIT
	   exit $ENCP_EXIT
       fi
   fi
   #
   # check the crc,
   #
   if [ "${uri_crc}" != "" ]; then
       #
       # uri_crc comes from layer 4 and most probably seeded 0
       #
       disk_crc=`ecrc -0 $filepath | awk '{ print $NF }'`
       rc=$?
       if [ ${rc} -ne 0 ]; then
	   sayE Failed to calculate crc, ${rc}
	   exit 1
       fi
       if [ "${disk_crc}" != "${uri_crc}" ]; then
           #
           # try also seeded 1
           #
	   disk_crc=`ecrc -1 $filepath | awk '{ print $NF }'`
	   if [ ${rc} -ne 0 ]; then
	       sayE Failed to calculate crc, ${rc}
	       exit 1
	   fi
	   if [ "${disk_crc}" != "${uri_crc}" ]; then
	       sayE crc mismatch, "${disk_crc}" != "${uri_crc}"
	       exit 1
	   fi
       fi
   fi
   exit  $ENCP_EXIT
#------------------------------------------------------------------------------------------
elif [ "$command" = "put" ] ; then

    filename_length=`basename ${si_path} | wc -c`
    if [ ${filename_length} -gt 200 ]; then
	say "${si_path:-notset} filename length is too long :  ${filename_length}"
	exit 31
    fi

    encp --help | egrep "\-\-enable\-redirection" >/dev/null 2>&1 && options="${options:-} --enable-redirection"
    #
    # if encp supports --cksm-value option, pass checksum value to it
    #
    if [ "${si_flag_c}" != "" ]; then
	#si_flag_c=`echo ${si_flag_c}| cut -d":" -f2` - OLD
	# new below
	# OLD way works in case of single checksum
	# double checksum comes like
	# 2:d27677c3916e215d6722ff2941ee84ca,1:b806421d
	# where adler32 is second.
	# The solution below extracts adler32 no matter how it comes
	si_flag_c=`echo ${si_flag_c} | awk -F, '{for (i=1;i<=NF;i++)print $i}' | grep "^1:" | cut -d":" -f2`
	crc_value=`printf "%d" "0x"${si_flag_c}`
	encp --help | egrep "\-\-cksm\-value"  >/dev/null 2>&1 && options="${options:-} --cksm-value ${crc_value}"
    fi
    # files that bigger than 8 GB need to use the cern wrapper, not the default cpio
    big=`expr 8 \* 1024 \* 1024 \* 1024 - 10000`
    if [ $si_size -gt $big ]; then
      say p1 "si_size=$si_size bigger than $big... user cern wrapper"
      wrapper="--file-family-wrapper cern"
    else
      wrapper=""
    fi

# RDK: test against /pnfs/fnal.gov/usr, /pnfs/fs/usr to avoid local mount paths
    pathtype1=`echo $si_path | grep -c "^/pnfs/fnal.gov/usr"`
    pathtype2=`echo $si_path | grep -c "^/pnfs/fs/usr"`
    let npathtypesok=${pathtype1}+${pathtype2}
    CMD=""
    if [ ${npathtypesok} -ne 0 -a $OVERRIDE_PATH -eq 1 ]; then
        override=1; override_msg=" overriding path "
	destination_path=`cat "/pnfs/fs/.(pathof)(${pnfsid})"`
	CMD="$ENCP $options $wrapper --pnfs-mount $pnfs_root --shortcut --override-path ${destination_path} --put-cache $pnfsid $filepath"
        say p9 $CMD
    else
        override=0; override_msg=" "
        say  p10  can not find acceptable path in SI.  si_path=\"$si_path\"  Using lookup mode
       # sayE p10e can not find acceptable path in SI.  si_path=\"$si_path\"  Using lookup mode
	CMD="$ENCP $options $wrapper --pnfs-mount $pnfs_root --put-cache $pnfsid $filepath"
        say p11 $CMD
    fi


    nice -n -3 $CMD >>$LOGFILE 2>&1

    ENCP_EXIT=$?

    if [ $ENCP_EXIT -eq 0 ]; then
      rm -f $out;
      sayS p29s put rc=$ENCP_EXIT
    fi
    say p30 put rc=$ENCP_EXIT  $pnfsid
    if [ $ENCP_EXIT -ne 0 ];then
      sayE p31e put rc=$ENCP_EXIT
    fi
    exit $ENCP_EXIT
#------------------------------------------------------------------------------------------
else
  say  $0 $args  Command not yet supported: $command
  sayE $0 $args  Command not yet supported: $command
  exit 5
fi
#------------------------------------------------------------------------------------------

say  ERROR $0 $args HOW DID WE GET HERE
exit 99
