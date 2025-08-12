# Load the DNN model
net = cv2.dnn.readNet("path/to/yolov4-tiny.weights", "path/to/yolov4-tiny.cfg")
layer_names = net.getLayerNames()
output_layers = [layer_names[i - 1] for i in net.getUnconnectedOutLayers()]
# Load class names
with open("path/to/coco.names", "r") as f:
    classes = [line.strip() for line in f.readlines()]

def detect_humans(frame):
    height, width, _ = frame.shape
    blob = cv2.dnn.blobFromImage(frame, 0.00392, (416, 416), (0, 0, 0), True, crop=False)
    net.setInput(blob)
    outs = net.forward(output_layers)

    # Process results
    for out in outs:
        for detection in out:
            scores = detection[5:]
            class_id = np.argmax(scores)
            confidence = scores[class_id]
            if classes[class_id] == "person" and confidence > 0.5:
                # A person has been detected with sufficient confidence
                return True
    return False