SUMMARY = "Dynamic FFmpeg RTSP Streaming Service"
DESCRIPTION = "A systemd template service to stream from Wyze cameras using a central config and MQTT control."
LICENSE = "CLOSED"

SRC_URI = " \
    file://camera_manager.py \
    file://camera_config.env \
    file://ffmpeg-stream@.service \
"

inherit systemd

RDEPENDS:${PN} = " \
    ffmpeg \
    python3-core \
    python3-paho-mqtt \
    python3-threading \
    python3-logging \
"

S = "${WORKDIR}"

do_install() {
    # 1. Install the Python manager script to /usr/bin
    install -d ${D}${bindir}
    install -m 0755 ${S}/camera_manager.py ${D}${bindir}/

    # 2. Install the config file to /etc/montana-hub
    install -d ${D}${sysconfdir}/montana-hub
    install -m 0600 ${S}/camera_config.env ${D}${sysconfdir}/montana-hub/

    # 3. Install the service template to systemd folder
    install -d ${D}${systemd_unitdir}/system
    install -m 0644 ${S}/ffmpeg-stream@.service ${D}${systemd_unitdir}/system/
}

# 4. Enable all 8 instances automatically
SYSTEMD_SERVICE:${PN} = " \
    ffmpeg-stream@cam1-sd-local.service \
    ffmpeg-stream@cam1-sd-remote.service \
    ffmpeg-stream@cam1-hd-local.service \
    ffmpeg-stream@cam1-hd-remote.service \
    ffmpeg-stream@cam2-sd-local.service \
    ffmpeg-stream@cam2-sd-remote.service \
    ffmpeg-stream@cam2-hd-local.service \
    ffmpeg-stream@cam2-hd-remote.service \
"

FILES:${PN} += " \
    ${systemd_unitdir}/system/ffmpeg-stream@.service \
    ${sysconfdir}/montana-hub/camera_config.env \
"