Summary: Enstore: Mass Storage System Binary Distribution
Name: enstore_bin_distr
Version: __VERSION__
Release: __RELEASE__.el7
License: GPL
Group: Applications/System
Source0: %{name}-%{version}.tgz
#Source: %{name}.tgz
BuildRoot: %(mktemp -ud %{_tmppath}/%{name}-%{version}-XXXXXX)
AutoReqProv: no
AutoProv: no
AutoReq: no
Prefix: opt/enstore_bin_distr

%description
Enstore Distributed Mass Storage System.
The main storage media it uses is magnetic tape, although the new media can be added.
Beginning with version 3.X File Aggregation Feature is added.
This is binary ditribution version
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
if [ ! -f $RPM_BUILD_ROOT/usr/local/etc/setups.sh ];then
	cp -r $RPM_BUILD_ROOT/%{prefix}/external_distr/setups.sh $RPM_BUILD_ROOT/usr/local/etc/setups.sh
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
   echo "moving $RPM_BUILD_ROOT/%{prefix} to /tmp/enstore_backup.$d"
   mv $RPM_BUILD_ROOT/%{prefix} /tmp/enstore_backup.$d
fi

%post
echo "POSTINSTALL"
export ENSTORE_DIR=$RPM_BUILD_ROOT/%{prefix}

echo "Creating sudoers file"
sed -e "s^/enstore/^/enstore_bin_distr/^g" $ENSTORE_DIR/etc/enstore.sudoers > /etc/sudoers.d/enstore 
#cp -f $ENSTORE_DIR/etc/enstore.sudoers /etc/sudoers.d/enstore
chmod 440 /etc/sudoers.d/enstore

echo "Copying $ENSTORE_DIR/etc/enstore-boot.service to /usr/lib/systemd/system/enstore.service"
cp -f $ENSTORE_DIR/etc/enstore.service /usr/lib/systemd/system/enstore.service
echo "Configuring the system to start enstore on boot"
systemctl is-enabled enstore.service
if [ $? -ne 0 ]; then
    systemctl enable enstore.service
fi
echo "Copying $ENSTORE_DIR/bin/monitor-boot.service.SLF7 to /usr/lib/systemd/system/enstore-monitor.service"
cp -f $ENSTORE_DIR/etc/enstore-monitor.service /usr/lib/systemd/system/enstore-monitor.service
echo "Configuring the system to start monitor server on boot"
systemctl is-enabled enstore-monitor.service
if [ $? -ne 0 ]; then
    systemctl enable enstore-monitor.service
fi
#cp -f $ENSTORE_DIR/sbin/rc.local /etc/rc.d
sed -e '/setup ftt/d' -e 's/$FTT_DIR/$ENSTORE_DIR/' $ENSTORE_DIR/sbin/rc.local > /etc/rc.d/rc.local
chmod +x /etc/rc.d/rc.local

if [ ! -d ~enstore/config ]; then
   echo "Creating default output directory: /var/log/enstore"
   mkdir -p /var/log/enstore
   chown enstore.enstore /var/log/enstore
fi
ln -s $ENSTORE_DIR/sbin/_internal $ENSTORE_DIR/bin/_internal
ln -s $ENSTORE_DIR/sbin/_internal $ENSTORE_DIR/tools/_internal
ln -s $ENSTORE_DIR/sbin/_internal $ENSTORE_DIR/external_distr/_internal
ln -s $ENSTORE_DIR/sbin/_internal $ENSTORE_DIR/www/cgi-bin/_internal

rm -f $ENSTORE_DIR/debugfiles.list
rm -f $ENSTORE_DIR/debugsources.list
echo "Enstore installed. Please read README file"

%preun
echo "PRE UNINSTALL"
#$RPM_BUILD_ROOT/%{prefix}/external_distr/rpm_uninstall.sh $1
%clean
rm -rf $RPM_BUILD_ROOT/*

%files
%defattr(-,enstore,enstore,-)
%doc
/%{prefix}
#%config /%{prefix}/etc/enstore_configuration
#%config /%{prefix}/etc/sam.conf
#%config /%{prefix}/etc/stk.conf
%config /usr/local/etc/setups.sh

%changelog
