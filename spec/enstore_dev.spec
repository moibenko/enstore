Summary: Enstore: Mass Storage System Whole Distribution
Name: __NAME__
Version: __VERSION__
Release: __RELEASE__%{?dist}
License: GPL
Group: Applications/System
Source0: %{name}-%{version}.tgz
BuildRoot: %(mktemp -ud %{_tmppath}/%{name}-%{version}-XXXXXX)
AutoReqProv: no
AutoProv: no
AutoReq: no
Prefix: opt/%{name}
Requires: mt-st,sg3_utils,at,mtx
%global _missing_build_ids_terminate_build 0
%undefine __brp_mangle_shebangs
%define _build_id_links none
%define debug_package %{nil}
%define _unpackaged_files_terminate_build 0
%global __arch_install_post %{nil}
# disable python_byte_compile
%global __os_install_post %(echo '%{__os_install_post}' | sed -e 's!/usr/lib[^[:space:]]*/brp-python-bytecompile[[:space:]].*$!!g')

%description
Enstore Distributed Mass Storage System.
The main storage media it uses is magnetic tape, although the new media can be added.
Beginning with version 3.X File Aggregation Feature is added.
This is development ditribution version
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
# check if user "enstore" and group "enstore "exist"

echo 'Checking if group "enstore" exists'
getent group enstore >/dev/null || groupadd -g 6209 enstore
echo 'Checking if user "enstore" exists'
getent passwd enstore >/dev/null || useradd -u 5744 -g enstore enstore;chmod 775 ~enstore

# save existing enstore distribution
d=`date "+%%F-%T"`
if [ -d $RPM_BUILD_ROOT/%{prefix} ]; then
   echo "copying $RPM_BUILD_ROOT/%{prefix} to /tmp/enstore_backup.$d"
   cp -rp $RPM_BUILD_ROOT/%{prefix} /tmp/enstore_backup.$d
fi

%post
echo "POSTINSTALL"
export ENSTORE_DIR=$RPM_BUILD_ROOT/%{prefix}
export ENSTORE_HOME=`getent passwd enstore | cut -d: -f6`
if [ $1 -eq 1 ]; then # first install
   cp -fp /home/enstore/.bashrc /home/enstore/bashrc.orig
   cp -f /opt/enstore/etc/bashrc_template /home/enstore/.bashrc
   chown enstore.enstore /home/enstore/.bashrc
   echo "Creating default output directory: /var/log/enstore"
   mkdir -p /var/log/enstore
   chown enstore.enstore /var/log/enstore
   mkdir -p $ENSTORE_HOME/site_specific/config
   echo "Creating default enstore setup."
   cp -f $ENSTORE_DIR/site_specific/config/setup-enstore $ENSTORE_HOME/site_specific/config/setup-enstore
   cp -f $ENSTORE_DIR/site_specific/config/setup-enstore.local.template $ENSTORE_HOME/site_specific/config/setup-enstore.local
   echo "Modify $ENSTORE_HOME/site_specific/config/setup-enstore.local according to specic needs."
   cp -f $ENSTORE_DIR/etc/minimal_enstore.conf  $ENSTORE_HOME/site_specific/config/enstore-system.conf
   echo "Modify $ENSTORE_DIR/site_specific/config/enstore-system.conf accordidng to required configuration"
   chown -R enstore.enstore $ENSTORE_HOME/site_specific 
   echo "For real-encp.sh do ln -s $ENSTORE_HOME/site_specific/config/setup-enstore-dcache $ENSTORE_HOME/site_specific/config/setup-enstore"
   
fi
echo "Creating sudoers file"
if [ ! -f /etc/sudoers.orig ];then
    cp -f //etc/sudoers /etc/sudoers.orig
    sed -e "s/Defaults    secure_path/#Defaults    secure_path/g" /etc/sudoers.orig > /etc/sudoers
fi

cp $ENSTORE_DIR/etc/enstore.sudoers /etc/sudoers.d/enstore

echo "Copying $ENSTORE_DIR/etc/enstore.service to /usr/lib/systemd/system/enstore.service"
cp -f $ENSTORE_DIR/etc/enstore.service /usr/lib/systemd/system/enstore.service
echo "Configuring the system to start enstore on boot"
systemctl is-enabled enstore.service
if [ $? -ne 0 ]; then
    systemctl enable enstore.service
fi
echo "Copying $ENSTORE_DIR/etc/monitor-boot.service to /usr/lib/systemd/system/enstore-monitor.service"
cp -f $ENSTORE_DIR/etc/enstore-monitor.service /usr/lib/systemd/system/enstore-monitor.service
echo "Configuring the system to start monitor server on boot"
systemctl is-enabled enstore-monitor.service
if [ $? -ne 0 ]; then
    systemctl enable enstore-monitor.service
fi
# copy media changer device rule
if [ ! -d /etc/udev/rules.d ]; then
        mkdir -p /etc/udev/rules.d
fi

cp -f $ENSTORE_DIR/etc/udev/rules.d/75-changer-aliases-generator.rules $RPM_BUILD_ROOT/etc/udev/rules.d/

# copy /rc.local
if [ ! -f /etc/rc.d/rc.local.pre_enstore ]; then
   cp /etc/rc.d/rc.local /etc/rc.d/rc.local.pre_enstore
fi
cp -f $ENSTORE_DIR/sbin/rc.local /etc/rc.d
chmod +x /etc/rc.d/rc.local

# copy setups.sh
if [ ! -f /usr/local/etc/setups.sh ];then
    cp -f $ENSTORE_DIR/external_distr/setups.sh /usr/local/etc/setups.sh
fi

# create ld config file for python library get recognized when doing sudo
if [ ! -f /etc/ld.so.conf.d/enstore.conf ];then
    echo "$ENSTORE_DIR/Python/lib" > /etc/ld.so.conf.d/enstore.conf
    /sbin/ldconfig
fi

echo "Check $ENSTORE_HOME/site_specific/config/setup-enstore and modify it as necessary"
$ENSTORE_DIR/external_distr/update_sym_links.sh
rm -f $ENSTORE_DIR/debugfiles.list
rm -f $ENSTORE_DIR/debugsources.list
echo "Enstore installed. Please read README file"

%preun
echo "PRE UNINSTALL"
%clean
rm -rf $RPM_BUILD_ROOT/*
%postun
if [ $1 -eq 0 ]; then # removing product
    echo "POST UNINSTALL"
    if [ -f /etc/rc.d/rc.local.pre_enstore ]; then
	rm -f /etc/rc.d/rc.local
	mv /etc/rc.d/rc.local.pre_enstore /etc/rc.d
    fi
    systemctl stop enstore-monitor.service
    systemctl disable enstore-monitor.service
    rm -f /usr/lib/systemd/system/enstore-monitor.service
    systemctl stop enstore.service
    systemctl disable enstore.service
    rm -f /usr/lib/systemd/system/enstore.service
    rm -f /etc/udev/rules.d/75-changer-aliases-generator.rules
    rm -f /etc/sudoers.d/enstore
    rm -f /usr/local/etc/setups.sh
    rm -rf /usr/local/etc/farmlets
    rm -rf /opt/enstore
    rm -rf /home/enstore
    userdel enstore
    groupdel enstore
    
fi

%files
%defattr(-,enstore,enstore,-)
%doc
/%{prefix}
#%config /usr/local/etc/setups.sh
#%config(noreplace) /%{prefix}/dcache-deploy/scripts/setup-enstore

%changelog
