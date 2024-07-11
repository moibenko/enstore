Summary: Enstore: Mass Storage System Binary Distribution
Name: encp_dcache_bin
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
Prefix: opt/encp_dcache_bin

%description
Enstore Distributed Mass Storage System.
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

rm -f $ENSTORE_DIR/debugfiles.list
rm -f $ENSTORE_DIR/debugsources.list
echo "encp_dcache installed. Please read README file"

%preun
#echo "PRE UNINSTALL"
%clean
rm -rf $RPM_BUILD_ROOT/*

%files
%defattr(-,enstore,enstore,-)
%doc
/%{prefix}
%config /usr/local/etc/setups.sh

%changelog
