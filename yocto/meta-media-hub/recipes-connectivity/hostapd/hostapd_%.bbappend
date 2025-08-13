# meta-media-hub/recipes-connectivity/hostapd/hostapd_%.bbappend
FILESEXTRAPATHS:prepend := "${THISDIR}/files:"

SRC_URI += "file://hostapd.conf"

SYSTEMD_AUTO_ENABLE:${PN} = "enable"

do_install:append() {
    # Install directly into /etc, where the service expects it
    install -m 0600 ${WORKDIR}/hostapd.conf ${D}${sysconfdir}/hostapd.conf
}

# Add the file to the package (this was the missing piece)
FILES:${PN} += "${sysconfdir}/hostapd.conf"