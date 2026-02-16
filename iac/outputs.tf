# ===========================
# OUTPUTS
# ===========================
output "ses_verification_instructions" {
  value = <<-EOT
  
  ⚠️  IMPORTANT: Verify your email addresses!
  
  1. Check inbox for: ${var.from_email}
  2. Click the verification link from AWS
  3. Repeat for recipient emails: ${join(", ", var.to_emails)}
  
  Once verified, invoke the Lambda manually to send bird emails.
  EOT
}

output "lambda_function_name" {
  value = aws_lambda_function.bird_email.function_name
}

output "lambda_invoke_command" {
  value = "aws lambda invoke --function-name ${aws_lambda_function.bird_email.function_name} response.json"
}


output "access_key_id" {
  value     = aws_iam_access_key.user_key.id
  sensitive = true
}

output "secret_access_key" {
  value     = aws_iam_access_key.user_key.secret
  sensitive = true
}

output "bucket_name" {
    value = aws_s3_bucket.cam_birds_bucket.bucket
}
