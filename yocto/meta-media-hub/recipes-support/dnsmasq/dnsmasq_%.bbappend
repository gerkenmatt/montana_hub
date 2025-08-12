# meta-camera-hub/recipes-support/dnsmasq/dnsmasq_%.bbappend
FILESEXTRAPATHS:prepend := "${THISDIR}/files:"

SRC_URI += " file://dnsmasq.conf "

SYSTEMD_AUTO_ENABLE:${PN} = "enable"

do_install:append() {
    install -m 0644 ${WORKDIR}/dnsmasq.conf ${D}${sysconfdir}/dnsmasq.conf
}