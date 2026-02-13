Summary: Enstore: Mass Storage System Binary Distribution
Name: encp_dcache_bin
Version: __VERSION__
Release: __RELEASE__%{?dist}
License: GPL
Group: Applications/System
Source0: %{name}-%{version}.tgz
#Source: %{name}.tgz
BuildRoot: %(mktemp -ud %{_tmppath}/%{name}-%{version}-XXXXXX)
AutoReqProv: no
AutoProv: no
AutoReq: no
Prefix: opt/encp_dcache_bin
%global _missing_build_ids_terminate_build 0
%undefine __brp_mangle_shebangs
%define _build_id_links none
%define debug_package %{nil}
%global __arch_install_post %{nil}
# disable python_byte_compile
%global __os_install_post %(echo '%{__os_install_post}' | sed -e 's!/usr/lib[^[:space:]]*/brp-python-bytecompile[[:space:]].*$!!g')

%description
Enstore Distributed Mass Storage System client.
The main storage media it uses is magnetic tape, although the new media can be added.
Beginning with version 3.X File Aggregation Feature is added.
This is encp for dcache client
For the postinstallation and configuration instructions please see README

%prep
echo "DOING SETUP"
%setup -q
echo "RPM SETUP DONE"

%build
echo "RPM BUILD"

%install
echo "RPM INSTALL"
mkdir -p $RPM_BUILD_ROOT/%{prefix}
cp -rp ./ $RPM_BUILD_ROOT/%{prefix}
if [ ! -d $RPM_BUILD_ROOT/usr/local/etc ]; then
	mkdir -p $RPM_BUILD_ROOT/usr/local/etc
fi
echo INSTALL DONE
%pre
PATH=/usr/sbin:$PATH
# save existing enstore distribution
d=`date "+%%F-%T"`
if [ -d $RPM_BUILD_ROOT/%{prefix} ]; then
   echo "copying $RPM_BUILD_ROOT/%{prefix} to /tmp/encp_dcache_bin_backup.$d"
   cp -rp $RPM_BUILD_ROOT/%{prefix} /tmp/encp_dcache_bin_backup.$d
fi

%post
echo "POSTINSTALL"
export ENSTORE_DIR=$RPM_BUILD_ROOT/%{prefix}
SETUP_FILE=/opt/ehome/site_specific/config/setup-enstore
if [ ! -f $SETUP_FILE ]; then
   echo "Creating $SETUP_FILE"
   mkdir -p `dirname $SETUP_FILE`
   $ENSTORE_DIR/dcache-deploy/site_specific/config/setup-enstore $SETUP_FILE
fi
echo "Check $SETUP_FILE and modify it as necessary"
ENCP_OPT=/opt/ehome/site_specific/config/encp_options
if [ ! -f $ENCP_OPT ]; then
   echo "Creating $ENCP_OPT"
   mkdir -p `dirname $ENCP_OPT`
   cp $ENSTORE_DIR/dcache-deploy/scripts/encp_options.sample $ENCP_OPT
fi
echo "Check $ENCP_OPT and modify it if needed"

rm -f $ENSTORE_DIR/debugfiles.list
rm -f $ENSTORE_DIR/debugsources.list
echo "encp_dcache installed. Please read README file"

%preun
#echo "PRE UNINSTALL"
%clean
rm -rf $RPM_BUILD_ROOT/*

%files
%doc
/%{prefix}
#%config /usr/local/etc/setups.sh
#%config(noreplace) /%{prefix}/dcache-deploy/scripts/setup-enstore

%changelog
