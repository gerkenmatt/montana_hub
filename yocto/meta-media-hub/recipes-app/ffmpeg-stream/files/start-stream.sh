# /usr/bin/start-stream.sh
#!/bin/sh
set -eu
CAMERA_IP="$1"; shift
echo "Waiting for camera RTSP at ${CAMERA_IP}:8554..."
while ! timeout 1 bash -lc "exec 3<>/dev/tcp/${CAMERA_IP}/8554" 2>/dev/null; do
  echo "Not up yet… retrying in 3s"; sleep 3
done
echo "Camera ${CAMERA_IP} is online. Starting ffmpeg."
exec /usr/bin/ffmpeg "$@"
