SUMMARY = "FFmpeg RTSP to TCP Streaming Service for Wyze Cams"
DESCRIPTION = "A systemd service to permanently stream from a Wyze camera using ffmpeg."
LICENSE = "CLOSED"

# 1. List all 8 new service files here
SRC_URI = " \
    file://ffmpeg-cam1-sd-local.service \
    file://ffmpeg-cam1-sd-remote.service \
    file://ffmpeg-cam1-hd-local.service \
    file://ffmpeg-cam1-hd-remote.service \
    file://ffmpeg-cam2-sd-local.service \
    file://ffmpeg-cam2-sd-remote.service \
    file://ffmpeg-cam2-hd-local.service \
    file://ffmpeg-cam2-hd-remote.service \
"

inherit systemd

# 2. List all 8 services here to enable them on boot
SYSTEMD_SERVICE:${PN} = " \
    ffmpeg-cam1-sd-local.service \
    ffmpeg-cam1-sd-remote.service \
    ffmpeg-cam1-hd-local.service \
    ffmpeg-cam1-hd-remote.service \
    ffmpeg-cam2-sd-local.service \
    ffmpeg-cam2-sd-remote.service \
    ffmpeg-cam2-hd-local.service \
    ffmpeg-cam2-hd-remote.service \
"

S = "${WORKDIR}"

do_install() {
    install -d ${D}${systemd_unitdir}/system

    install -m 0644 ${S}/ffmpeg-cam1-sd-local.service ${D}${systemd_unitdir}/system/
    install -m 0644 ${S}/ffmpeg-cam1-sd-remote.service ${D}${systemd_unitdir}/system/
    install -m 0644 ${S}/ffmpeg-cam1-hd-local.service ${D}${systemd_unitdir}/system/
    install -m 0644 ${S}/ffmpeg-cam1-hd-remote.service ${D}${systemd_unitdir}/system/

    install -m 0644 ${S}/ffmpeg-cam2-sd-local.service ${D}${systemd_unitdir}/system/
    install -m 0644 ${S}/ffmpeg-cam2-sd-remote.service ${D}${systemd_unitdir}/system/
    install -m 0644 ${S}/ffmpeg-cam2-hd-local.service ${D}${systemd_unitdir}/system/
    install -m 0644 ${S}/ffmpeg-cam2-hd-remote.service ${D}${systemd_unitdir}/system/
}