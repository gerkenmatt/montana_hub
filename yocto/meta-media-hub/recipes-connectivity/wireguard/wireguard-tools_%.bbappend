FILESEXTRAPATHS:prepend := "${THISDIR}/files:"

SRC_URI += "file://wg0.conf file://90-wireguard.preset"

do_install:append() {
    install -d ${D}${sysconfdir}/wireguard
    install -m 600 ${WORKDIR}/wg0.conf ${D}${sysconfdir}/wireguard/wg0.conf

    install -d ${D}${sysconfdir}/systemd/system-preset
    install -m 0644 ${WORKDIR}/90-wireguard.preset ${D}${sysconfdir}/systemd/system-preset/90-wireguard.preset
}

FILES:${PN} += " \
    ${sysconfdir}/wireguard/wg0.conf \
    ${sysconfdir}/systemd/system-preset/90-wireguard.preset \
"

CONFFILES:${PN} += "${sysconfdir}/wireguard/wg0.conf"
SYSTEMD_AUTO_ENABLE:${PN} = "enable"

inherit systemd
SYSTEMD_SERVICE:${PN} += "wg-quick@wg0.service"
SYSTEMD_AUTO_ENABLE:${PN} = "enable"
