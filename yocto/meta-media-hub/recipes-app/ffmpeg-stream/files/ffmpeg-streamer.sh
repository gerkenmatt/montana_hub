#!/bin/bash

INSTANCE_NAME=$1
CONFIG_FILE="/etc/montana-hub/camera_config.env"

# 1. Load the specific line for this instance
LINE=$(grep "^${INSTANCE_NAME}=" "$CONFIG_FILE" | cut -d'=' -f2-)

if [ -z "$LINE" ]; then
    echo "Error: Configuration for '$INSTANCE_NAME' not found in $CONFIG_FILE"
    exit 1
fi

# 2. Parse the variables using the pipe delimiter
IFS='|' read -r CAM_IP RES_PATH OUTPUT_URL <<< "$LINE"

INPUT_URL="rtsp://${CAM_IP}:8554${RES_PATH}"

echo "Starting Stream: $INSTANCE_NAME"
echo "Input: $INPUT_URL"
echo "Output: $OUTPUT_URL"

# 3. Exec FFmpeg 
exec /usr/bin/ffmpeg -hide_banner -loglevel info -nostdin \
  -rtsp_transport tcp -rtsp_flags prefer_tcp \
  -allowed_media_types video -analyzeduration 5M -probesize 50M \
  -fflags +genpts+igndts+discardcorrupt -reorder_queue_size 0 \
  -i "$INPUT_URL" \
  -map 0:v:0 -c:v copy -an -bsf:v h264_mp4toannexb \
  -f mpegts -mpegts_flags +resend_headers -flush_packets 1 -muxpreload 0 -muxdelay 0 \
  "$OUTPUT_URL"