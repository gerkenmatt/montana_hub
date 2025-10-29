SUMMARY = "FFmpeg RTSP to TCP Streaming Service for Wyze Cams"
DESCRIPTION = "A systemd service to permanently stream from a Wyze camera using ffmpeg."
LICENSE = "CLOSED"

# Add the new script to the source URI
SRC_URI = " \
    file://ffmpeg-stream.service \
    file://ffmpeg-stream2.service \
    file://ffmpeg-stream-1080p.service \
    file://ffmpeg-stream2-1080p.service \
"

inherit systemd

SYSTEMD_SERVICE:${PN} = "ffmpeg-stream.service ffmpeg-stream2.service ffmpeg-stream-1080p.service ffmpeg-stream2-1080p.service"

S = "${WORKDIR}"

do_install() {
    install -d ${D}${systemd_unitdir}/system
    install -m 0644 ${S}/ffmpeg-stream.service ${D}${systemd_unitdir}/system/
    install -m 0644 ${S}/ffmpeg-stream2.service ${D}${systemd_unitdir}/system/
    install -m 0644 ${S}/ffmpeg-stream-1080p.service ${D}${systemd_unitdir}/system/
    install -m 0644 ${S}/ffmpeg-stream2-1080p.service ${D}${systemd_unitdir}/system/

    # Install the script to /usr/bin and make it executable
    install -d ${D}${bindir}
    install -m 0755 ${S}/start-stream.sh ${D}${bindir}/
}