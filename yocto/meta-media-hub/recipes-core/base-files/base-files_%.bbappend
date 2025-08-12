# Inherit the class that lets us add users/groups
inherit extrausers

# Define the group to be added during image creation
EXTRA_USERS_PARAMS = "addgroup netdev;"

# Add our custom network config file to the build
FILESEXTRAPATHS:prepend := "${THISDIR}/files:"
SRC_URI += "file://wlan0.network"

do_install:append() {
    # Install the network config into the correct location
    install -d ${D}${sysconfdir}/systemd/network
    install -m 0644 ${WORKDIR}/wlan0.network ${D}${sysconfdir}/systemd/network/
}

# Tell Yocto to package the new file
FILES:${PN} += "${sysconfdir}/systemd/network/wlan0.network"