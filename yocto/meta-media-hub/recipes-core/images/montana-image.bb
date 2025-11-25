SUMMARY = "A custom image for the Montana IoT Hub"
LICENSE = "MIT"

# Start with the minimal image capabilities
require recipes-core/images/core-image-minimal.bb

IMAGE_INSTALL:append = " \
    kernel-modules \
    linux-firmware-rpidistro-bcm43455 \
    wpa-supplicant \
    python3 \
    python3-opencv \
    python3-pip \
    python3-dev \
    python3-core \
    python3-paho-mqtt \
    python3-requests \
    mosquitto \
    mosquitto-clients \
    gstreamer1.0 \
    gstreamer1.0-plugins-base \
    gstreamer1.0-plugins-good \
    gstreamer1.0-plugins-bad \
    gstreamer1.0-libav \
    gstreamer1.0-python \
    ffmpeg \
    msmtp \
    human-detector \
    hostapd \ 
    dnsmasq \
    iptables \
    rtl8812au \
    usbutils \
    iproute2 \
    rfkill \ 
    iw \
    curl \
    tcpdump \
    ca-certificates \
    ffmpeg-stream \
    wireguard-tools \
"
# Enable SSH and 1GB of free space for logs/updates
EXTRA_IMAGE_FEATURES += "ssh-server-dropbear"
IMAGE_ROOTFS_EXTRA_SPACE = "1048576"