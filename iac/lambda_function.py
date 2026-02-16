import boto3
import json
import os
import random
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from datetime import datetime, timedelta
import zoneinfo

s3 = boto3.client('s3')
ses = boto3.client('ses')

FROM_EMAIL = os.environ['FROM_EMAIL']
TO_EMAILS = json.loads(os.environ['TO_EMAILS'])
BUCKET_NAME = os.environ['BUCKET_NAME']

def lambda_handler(event, context):
    """
    Get a random bird image from today's folder and send via email
    
    S3 structure:
    bucket/
      02-12-2025/
        img1_birds_2_conf_0.87.jpg
        img2_birds_1_conf_0.92.jpg
      02-13-2025/
        img3_birds_3_conf_0.75.jpg
    """
    
    # Get today's date folder (MM-DD-YYYY)
    uk_tz = zoneinfo.ZoneInfo("Europe/London")
    uk_now = datetime.now(uk_tz)
    yesterday_uk = (uk_now - timedelta(days=1)).strftime("%m-%d-%Y")
    prefix = f"{yesterday_uk}/"

    print(f"Looking for images in S3 folder: {prefix}")
    
    try:
        # List all objects in today's folder
        response = s3.list_objects_v2(
            Bucket=BUCKET_NAME,
            Prefix=prefix
        )
        
        if 'Contents' not in response or len(response['Contents']) == 0:
            print(f"No images found in {prefix}")
            return {
                'statusCode': 200,
                'body': json.dumps(f'No bird images found for {yesterday_uk}')
            }
        
        # Filter for bird images only (in case there are other files)
        bird_images = [
            obj for obj in response['Contents']
            if obj['Size'] > 0 and obj['Key'].endswith('.jpg') 
            # if obj['Key'].endswith('.jpg') and 'birds' in obj['Key']
        ]
        
        if len(bird_images) == 0:
            print(f"No bird images found in {prefix}")
            return {
                'statusCode': 200,
                'body': json.dumps(f'No bird images detected for {yesterday_uk}')
            }
        
        print(f"Found {len(bird_images)} bird images in {prefix}")
        
        # Pick a random bird image
        selected_image = random.choice(bird_images)
        key = selected_image['Key']
        timestamp_obj = selected_image['LastModified'] 
        timestamp_image = timestamp_obj.astimezone(uk_tz).strftime("%Y-%m-%d %H:%M:%S")

        print(f"Selected random bird image: {key}")
        
        # Download the image
        image_obj = s3.get_object(Bucket=BUCKET_NAME, Key=key)
        image_data = image_obj['Body'].read()
        
        filename = key.split('/')[-1]
        
        
        # Create email
        subject = f"🐦 Daily Bird Photo from River Cam - {yesterday_uk}"
        
        msg = MIMEMultipart()
        msg['From'] = FROM_EMAIL
        msg['To'] = ', '.join(TO_EMAILS)
        msg['Subject'] = subject


        
        body = f"""
Hello bird watchers!

Here's yesterday's random bird sighting from the River Cam!

📅 Date: {yesterday_uk}
📸 Image: {filename}
📊 Total bird photos yesterday: {len(bird_images)}
⏰ Captured at: {timestamp_image}
🎯 Detection confidence: 15%


See the attached photo with detection boxes around the bird(s).

Happy bird watching! 🦆

---
Ethan's Automated Bird Camera 🎥
Cambridge, UK
        """
        
        msg.attach(MIMEText(body, 'plain'))
        
        # Attach image
        img = MIMEImage(image_data, name=filename)
        msg.attach(img)
        
        # Send email
        response = ses.send_raw_email(
            Source=FROM_EMAIL,
            Destinations=TO_EMAILS,
            RawMessage={'Data': msg.as_string()}
        )
        
        print(f"✅ Email sent successfully!")
        print(f"   Message ID: {response['MessageId']}")
        print(f"   Recipients: {TO_EMAILS}")
        
        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': 'Email sent successfully',
                'image': filename,
                # 'birds_detected': num_birds,
                'total_images_today': len(bird_images),
                'recipients': TO_EMAILS
            })
        }
    
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        import traceback
        traceback.print_exc()
        
        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': str(e),
                'message': 'Failed to send bird email'
            })
        }
