# raspberry-pi-birds


### Package Requirements
1. AWS CLI
2. Terraform
3. Python3
4. Raspberry Pi (this is for Trixie on v13)
5. Raspberry Pi Camera

### Execution
1. Run git clone to clone this repo down
2. Create a named AWS Profile in `~/.aws/credentials`
3. Update terraform.tfvars with:
   ```bash
   cd iac
   vi terraform.tfvars
   ```
4. Run the following to create:
   - S3 bucket
   - AWS IAM User and Access Keys --> these will be used by the python script to upload objects to S3
   - Lambda Function
   - AWS SES
   - EventBridge
   ```bash
   terraform plan
   terraform apply
   bash ./postDeployment.sh
   ```
5. CD into `python-code` and update any variables in `main.py`
6. Run
   ```bash
   python3 -m venv --system-site-packages venv
   source venv/bin/activate
   pip install opencv-python ultralytics boto3
   python ./main.py
   ```
7. To schedule the job to run, for example, every day at 8 am, run
   ```
   crontab -e
   # add this line
   0 8 * * * /home/${piUserName}/Documents/${pathToCode}/venv/bin/python /home/${piUserName}/${pathToCode}/python-code/main.py >> /home/${piUserName}/${pathToCode}/bird_detection.log 2>&1
   ```
   

  
