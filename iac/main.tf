data "aws_caller_identity" "current" {}

data "aws_region" "current" {}



// Create Bucket
resource "aws_s3_bucket" "cam_birds_bucket" {
  bucket = "${var.bucket_name}-${data.aws_caller_identity.current.account_id}"
}

// Create User
resource "aws_iam_user" "restricted_user" {
  name = "bird-user"
}

// Generate keys for user
resource "aws_iam_access_key" "user_key" {
  user = aws_iam_user.restricted_user.name
}

// Policy allowing user to access bucket
data "aws_iam_policy_document" "allow_bucket_access" {
  statement {
    effect = "Allow"

    actions = [
      "s3:ListBucket",
      "s3:GetObject",
      "s3:PutObject",
      "s3:DeleteObject"
    ]

    resources = [
      "${aws_s3_bucket.cam_birds_bucket.arn}",
      "${aws_s3_bucket.cam_birds_bucket.arn}/*"
    ]
  }
}
// Attach Policy
resource "aws_iam_user_policy" "user_policy" {
  name   = "restricted-bucket-policy"
  user   = aws_iam_user.restricted_user.name
  policy = data.aws_iam_policy_document.allow_bucket_access.json
}

// Create Bucket Policy
data "aws_iam_policy_document" "bucket_policy" {

  statement {
    sid    = "DenyAllExceptAllowedPrincipals"
    effect = "Deny"

    principals {
      type        = "*"
      identifiers = ["*"]
    }

    actions = ["s3:*"]

    resources = [
      aws_s3_bucket.cam_birds_bucket.arn,
      "${aws_s3_bucket.cam_birds_bucket.arn}/*"
    ]

    condition {
      test     = "ArnNotEquals"
      variable = "aws:PrincipalArn"
      values = [
        aws_iam_user.restricted_user.arn,
        data.aws_caller_identity.current.arn,
        aws_iam_role.lambda_role.arn
      ]
    }
  }
}

// Attach Bucket Policy
resource "aws_s3_bucket_policy" "restricted_policy" {
  bucket = aws_s3_bucket.cam_birds_bucket.id
  policy = data.aws_iam_policy_document.bucket_policy.json
}


# ===========================
# SES EMAIL VERIFICATION
# ===========================
resource "aws_ses_email_identity" "sender" {
  email = var.from_email
}

resource "aws_ses_email_identity" "recipients" {
  for_each = toset(var.to_emails)
  email    = each.value
}

# ===========================
# LAMBDA IAM ROLE
# ===========================
resource "aws_iam_role" "lambda_role" {
  name = "bird-email-lambda-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
      }
    ]
  })
}

resource "aws_iam_role_policy" "lambda_policy" {
  name = "bird-email-lambda-policy"
  role = aws_iam_role.lambda_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "arn:aws:logs:*:*:*"
      },
      {
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:ListBucket"
        ]
        Resource = [
          aws_s3_bucket.cam_birds_bucket.arn,
          "${aws_s3_bucket.cam_birds_bucket.arn}/*"
        ]
      },
      {
        Effect = "Allow"
        Action = [
          "ses:SendEmail",
          "ses:SendRawEmail"
        ]
        Resource = "*"
      }
    ]
  })
}

# ===========================
# LAMBDA FUNCTION
# ===========================
data "archive_file" "lambda_zip" {
  type        = "zip"
  output_path = "${path.module}/lambda_function.zip"

  source {
    content  = file("${path.module}/lambda_function.py")
    filename = "lambda_function.py"
  }
}

resource "aws_lambda_function" "bird_email" {
  filename         = data.archive_file.lambda_zip.output_path
  function_name    = "bird-email-sender"
  role            = aws_iam_role.lambda_role.arn
  handler         = "lambda_function.lambda_handler"
  source_code_hash = data.archive_file.lambda_zip.output_base64sha256
  runtime         = "python3.12"
  timeout         = 60
  memory_size     = 256

  environment {
    variables = {
      FROM_EMAIL  = var.from_email
      TO_EMAILS   = jsonencode(var.to_emails)
      BUCKET_NAME = aws_s3_bucket.cam_birds_bucket.bucket
    #   AWS_REGION  = data.aws_region.current.name
    }
  }
}

# ===========================
# CLOUDWATCH LOGS
# ===========================
resource "aws_cloudwatch_log_group" "lambda_logs" {
  name              = "/aws/lambda/${aws_lambda_function.bird_email.function_name}"
  retention_in_days = 7
}

# EventBridge Rule to trigger Lambda daily at 7 AM UK time
resource "aws_cloudwatch_event_rule" "daily_bird_email" {
  name                = "daily-bird-email"
  description         = "Trigger bird email Lambda daily at 7 AM UK time"
  schedule_expression = "cron(0 7 * * ? *)" # UTC
}

# Give the rule permission to invoke Lambda
resource "aws_lambda_permission" "allow_eventbridge" {
  statement_id  = "AllowExecutionFromEventBridge"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.bird_email.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.daily_bird_email.arn
}

# EventBridge target (connect rule to Lambda)
resource "aws_cloudwatch_event_target" "daily_bird_email_target" {
  rule      = aws_cloudwatch_event_rule.daily_bird_email.name
  target_id = "LambdaTarget"
  arn       = aws_lambda_function.bird_email.arn
}












