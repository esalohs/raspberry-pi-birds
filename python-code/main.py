from picamera2 import Picamera2
from ultralytics import YOLO
import cv2
import numpy as np
import time
from datetime import datetime
from pathlib import Path
import boto3
from io import BytesIO

# ==========================
# CONFIG
# ==========================
# S3 settings
S3_BUCKET_NAME = "your-bucket-name"  # CHANGE THIS
AWS_REGION = "us-east-1"  # Change if needed
AWS_PROFILE = None  # Set to your profile name, e.g., "my-profile" or leave None for default

# Optional: Local backup directory
LOCAL_BACKUP_DIR = Path("bird_detections_backup")
LOCAL_BACKUP_DIR.mkdir(exist_ok=True)
SAVE_LOCAL_BACKUP = True  # Set to False if you only want S3

# Motion capture directory (saves all motion, even non-birds)
MOTION_DIR = Path("motion_captures")
MOTION_DIR.mkdir(exist_ok=True)
SAVE_ALL_MOTION = True  # Set to False to only save confirmed birds

# YOLO settings
MODEL_PATH = "yolov8n.pt"
BIRD_CONFIDENCE = 0.15

# Motion detection settings
MIN_CONTOUR_AREA = 500      # Minimum size (filters out tiny noise)
MAX_CONTOUR_AREA = 15000    # Maximum size (filters out people/boats)
MOTION_THRESHOLD = 25        # Sensitivity (lower = more sensitive)

# Camera settings
FRAME_WIDTH = 1920
FRAME_HEIGHT = 1080
CHECK_INTERVAL = 0.3  # Seconds between motion checks

# ==========================
# BIRD DETECTION CAMERA
# ==========================
class BirdDetectionCamera:
    def __init__(self):
        print("🚀 Initializing bird detection camera...")
        
        # Setup S3 client
        print("☁️  Connecting to S3...")
        if AWS_PROFILE:
            session = boto3.Session(profile_name=AWS_PROFILE)
            self.s3_client = session.client('s3', region_name=AWS_REGION)
            print(f"   Using AWS profile: {AWS_PROFILE}")
        else:
            self.s3_client = boto3.client('s3', region_name=AWS_REGION)
            print(f"   Using default AWS credentials")
        
        # Verify bucket exists
        try:
            self.s3_client.head_bucket(Bucket=S3_BUCKET_NAME)
            print(f"✅ Connected to S3 bucket: {S3_BUCKET_NAME}")
        except Exception as e:
            print(f"⚠️  Warning: Could not verify S3 bucket: {e}")
            print("   Make sure AWS credentials are configured and bucket exists")
        
        # Load YOLO model
        print("📦 Loading YOLO model...")
        self.model = YOLO(MODEL_PATH)
        
        # Setup camera
        print("📷 Setting up camera...")
        self.camera = Picamera2()
        config = self.camera.create_preview_configuration(
            main={"size": (FRAME_WIDTH, FRAME_HEIGHT)}
        )
        self.camera.configure(config)
        self.camera.start()
        
        # Warm up camera
        time.sleep(2)
        
        print(f"✅ Camera ready ({FRAME_WIDTH}x{FRAME_HEIGHT})")
        print(f"🎯 Bird confidence threshold: {BIRD_CONFIDENCE}")
        print(f"📏 Detecting motion: {MIN_CONTOUR_AREA}-{MAX_CONTOUR_AREA} pixels")
        print(f"☁️  Uploading to: s3://{S3_BUCKET_NAME}/MM-DD-YYYY/")
        if SAVE_LOCAL_BACKUP:
            print(f"💾 Local backup: {LOCAL_BACKUP_DIR}")
        if SAVE_ALL_MOTION:
            print(f"📁 All motion saved to: {MOTION_DIR}")
        print()
    
    def detect_motion(self, frame1, frame2):
        """
        Detect motion between two frames
        Returns: (has_motion, motion_areas, bounding_boxes)
        """
        # Convert to grayscale
        gray1 = cv2.cvtColor(frame1, cv2.COLOR_BGR2GRAY)
        gray2 = cv2.cvtColor(frame2, cv2.COLOR_BGR2GRAY)
        
        # Blur to reduce noise
        gray1 = cv2.GaussianBlur(gray1, (21, 21), 0)
        gray2 = cv2.GaussianBlur(gray2, (21, 21), 0)
        
        # Calculate difference
        diff = cv2.absdiff(gray1, gray2)
        
        # Threshold
        _, thresh = cv2.threshold(diff, MOTION_THRESHOLD, 255, cv2.THRESH_BINARY)
        
        # Dilate to fill gaps
        thresh = cv2.dilate(thresh, None, iterations=2)
        
        # Find contours
        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        # Check for significant motion
        has_motion = False
        motion_areas = []
        bounding_boxes = []
        
        for contour in contours:
            area = cv2.contourArea(contour)
            
            # Only count appropriately-sized objects (bird-sized, not people)
            if MIN_CONTOUR_AREA < area < MAX_CONTOUR_AREA:
                has_motion = True
                motion_areas.append(area)
                
                # Get bounding box and add padding
                x, y, w, h = cv2.boundingRect(contour)
                # Add 50% padding around the motion area
                padding = max(w, h) // 2
                x1 = max(0, x - padding)
                y1 = max(0, y - padding)
                x2 = min(frame1.shape[1], x + w + padding)
                y2 = min(frame1.shape[0], y + h + padding)
                bounding_boxes.append((x1, y1, x2, y2))
        
        return has_motion, motion_areas, bounding_boxes
    
    def detect_bird(self, frame, bounding_boxes=None):
        """
        Run YOLO bird detection on frame
        If bounding_boxes provided, check those regions with extra crops for better detection
        Returns: result object from YOLO
        """
        # First try full frame
        results = self.model(frame, classes=[14], conf=BIRD_CONFIDENCE, verbose=False)
        
        # If no birds found and we have motion regions, try cropped regions with lower confidence
        if len(results[0].boxes) == 0 and bounding_boxes:
            for bbox in bounding_boxes:
                x1, y1, x2, y2 = bbox
                cropped = frame[y1:y2, x1:x2]
                
                # Skip if crop is too small
                if cropped.shape[0] < 50 or cropped.shape[1] < 50:
                    continue
                
                # Try detection on cropped region with lower confidence
                crop_results = self.model(cropped, classes=[14], conf=BIRD_CONFIDENCE * 0.7, verbose=False)
                
                if len(crop_results[0].boxes) > 0:
                    # Found a bird in the cropped region! Use full frame result
                    return results[0]
        
        return results[0]
    
    def save_motion_image(self, frame, motion_areas):
        """
        Save motion detection image locally for review
        Returns: filepath
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"motion_{timestamp}_areas_{len(motion_areas)}.jpg"
        filepath = MOTION_DIR / filename
        cv2.imwrite(str(filepath), frame)
        return filepath
    
    def upload_to_s3(self, frame, result):
        """
        Upload image with bird bounding boxes to S3
        Returns: (s3_key, num_birds, avg_conf, local_path)
        """
        now = datetime.now()
        timestamp = now.strftime("%Y%m%d_%H%M%S")
        date_folder = now.strftime("%m-%d-%Y")  # MM-DD-YYYY format
        
        # Count birds and get confidence
        num_birds = len(result.boxes)
        confidences = [float(box.conf[0]) for box in result.boxes]
        avg_conf = sum(confidences) / len(confidences) if confidences else 0
        
        # Draw boxes on image
        annotated_frame = result.plot()
        
        # Create filename
        filename = f"bird_{timestamp}_count_{num_birds}_conf_{avg_conf:.2f}.jpg"
        
        # S3 key with date folder
        s3_key = f"{date_folder}/{filename}"
        
        # Encode image to bytes
        _, buffer = cv2.imencode('.jpg', annotated_frame)
        image_bytes = BytesIO(buffer)
        
        # Upload to S3
        try:
            self.s3_client.upload_fileobj(
                image_bytes,
                S3_BUCKET_NAME,
                s3_key,
                ExtraArgs={'ContentType': 'image/jpeg'}
            )
            print(f"   ☁️  Uploaded to S3: {s3_key}")
        except Exception as e:
            print(f"   ❌ S3 upload failed: {e}")
        
        # Optional: Save local backup
        local_path = None
        if SAVE_LOCAL_BACKUP:
            local_path = LOCAL_BACKUP_DIR / filename
            cv2.imwrite(str(local_path), annotated_frame)
            print(f"   💾 Local backup: {local_path.name}")
        
        return s3_key, num_birds, avg_conf, local_path
    
    def run(self, duration_hours=None):
        """
        Main detection loop
        duration_hours: None = run forever, or specify hours to run
        """
        print("="*60)
        print("🔍 BIRD DETECTION ACTIVE")
        print("="*60)
        print("Monitoring for motion and birds...")
        if duration_hours:
            print(f"Will run for {duration_hours} hours")
        print("Press Ctrl+C to stop\n")
        
        start_time = datetime.now()
        prev_frame = None
        
        motion_detections = 0
        bird_detections = 0
        checks = 0
        
        try:
            while True:
                # Check if duration exceeded
                if duration_hours:
                    elapsed_hours = (datetime.now() - start_time).total_seconds() / 3600
                    if elapsed_hours >= duration_hours:
                        print(f"\n⏰ {duration_hours} hour duration complete")
                        break
                
                # Capture current frame
                frame = self.camera.capture_array()
                frame_bgr = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
                
                # Motion detection
                if prev_frame is not None:
                    checks += 1
                    
                    has_motion, areas, bboxes = self.detect_motion(prev_frame, frame_bgr)
                    
                    if has_motion:
                        motion_detections += 1
                        print(f"\n🚨 Motion #{motion_detections} detected! Areas: {areas}")
                        
                        # Save motion image locally for review (before bird detection)
                        if SAVE_ALL_MOTION:
                            motion_file = self.save_motion_image(frame_bgr, areas)
                            print(f"   📁 Motion saved: {motion_file.name}")
                        
                        print(f"   Running bird detection...")
                        
                        # Run bird detection with motion regions for better small bird detection
                        result = self.detect_bird(frame_bgr, bboxes)
                        
                        # Check if birds detected
                        if len(result.boxes) > 0:
                            bird_detections += 1
                            s3_key, num_birds, avg_conf, local_path = self.upload_to_s3(frame_bgr, result)
                            
                            print(f"   ✅ BIRD DETECTED!")
                            print(f"   🐦 Birds: {num_birds} | Confidence: {avg_conf:.2f}")
                        else:
                            print(f"   ❌ Motion but no birds detected")
                    
                    # Status update every 100 checks
                    if checks % 100 == 0:
                        elapsed = (datetime.now() - start_time).total_seconds() / 60
                        print(f"📊 Status: {checks} checks | {motion_detections} motions | "
                              f"{bird_detections} birds | {elapsed:.1f} min elapsed")
                
                # Update previous frame
                prev_frame = frame_bgr.copy()
                
                # Wait before next check
                time.sleep(CHECK_INTERVAL)
        
        except KeyboardInterrupt:
            print(f"\n\n⚠️  Stopped by user")
        
        finally:
            self.camera.stop()
            
            elapsed_time = (datetime.now() - start_time).total_seconds() / 60
            
            print(f"\n{'='*60}")
            print("✅ BIRD DETECTION STOPPED")
            print(f"{'='*60}")
            print(f"⏱️  Runtime: {elapsed_time:.1f} minutes")
            print(f"📊 Motion checks: {checks}")
            print(f"🚨 Motion detections: {motion_detections}")
            print(f"🐦 Bird detections: {bird_detections}")
            if motion_detections > 0:
                print(f"📈 Bird hit rate: {bird_detections/motion_detections*100:.1f}% of motions")
            print(f"☁️  Images uploaded to: s3://{S3_BUCKET_NAME}/MM-DD-YYYY/")
            if SAVE_LOCAL_BACKUP:
                print(f"💾 Local backups in: {LOCAL_BACKUP_DIR}")
            if SAVE_ALL_MOTION:
                print(f"📁 All motion in: {MOTION_DIR}")

# ==========================
# MAIN
# ==========================
if __name__ == "__main__":
    camera = BirdDetectionCamera()
    
    # Run forever (or specify hours)
    # camera.run()  # Run forever
    camera.run(duration_hours=6)  # Run for 4 hours
