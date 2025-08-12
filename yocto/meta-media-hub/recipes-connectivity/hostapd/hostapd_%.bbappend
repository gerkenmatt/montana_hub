# meta-camera-hub/recipes-connectivity/hostapd/hostapd_%.bbappend
FILESEXTRAPATHS:prepend := "${THISDIR}/files:"

SRC_URI += " file://hostapd.conf "

SYSTEMD_AUTO_ENABLE:${PN} = "enable"

do_install:append() {
    install -d ${D}${sysconfdir}/hostapd
    install -m 0600 ${WORKDIR}/hostapd.conf ${D}${sysconfdir}/hostapd/hostapd.conf
}