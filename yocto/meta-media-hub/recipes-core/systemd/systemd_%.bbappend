# This enables the timesyncd feature to be built into the systemd package
PACKAGECONFIG:append = " timesyncd"

# This tells the build system to enable the service when the systemd package is installed
SYSTEMD_SERVICE:${PN} = "systemd-timesyncd.service"