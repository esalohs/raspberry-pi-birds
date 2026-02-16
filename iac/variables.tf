variable "region" {
    type = string
    description = "aws region"
}

variable "aws_profile" {
    type = string
    description = "Named aws profile"
}

variable "bucket_name" {
    type = string
    description = "Name of bucket"
}

variable "from_email" {
  description = "Your verified sender email"
  type        = string
}

variable "to_emails" {
  description = "List of recipient emails"
  type        = list(string)
}
