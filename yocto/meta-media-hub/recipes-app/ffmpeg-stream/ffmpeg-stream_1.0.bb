SUMMARY = "FFmpeg RTSP to TCP Streaming Service for Wyze Cams"
DESCRIPTION = "A systemd service to permanently stream from a Wyze camera using ffmpeg."
LICENSE = "CLOSED"

# Add both service files to the source URI
SRC_URI = " \
    file://ffmpeg-stream.service \
    file://ffmpeg-stream2.service \
"

inherit systemd

# Tell systemd to manage both services
SYSTEMD_SERVICE:${PN} = "ffmpeg-stream.service ffmpeg-stream2.service"

S = "${WORKDIR}"

# Install both service files
do_install() {
    install -d ${D}${systemd_unitdir}/system
    install -m 0644 ${S}/ffmpeg-stream.service ${D}${systemd_unitdir}/system/
    install -m 0644 ${S}/ffmpeg-stream2.service ${D}${systemd_unitdir}/system/
}