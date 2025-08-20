FILESEXTRAPATHS:prepend := "${THISDIR}/files:"

SRC_URI += " \
    file://wpa_supplicant.conf \
    file://override.conf \
"

SYSTEMD_AUTO_ENABLE = "enable"

do_install:append() {
    install -m 0600 ${WORKDIR}/wpa_supplicant.conf ${D}${sysconfdir}/
    install -d ${D}${sysconfdir}/systemd/system/wpa_supplicant.service.d
    install -m 0644 ${WORKDIR}/override.conf ${D}${sysconfdir}/systemd/system/wpa_supplicant.service.d/
}

FILES:${PN} += " \
    ${sysconfdir}/wpa_supplicant.conf \
    ${sysconfdir}/systemd/system/wpa_supplicant.service.d/override.conf \
"